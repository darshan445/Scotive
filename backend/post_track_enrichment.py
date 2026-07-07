"""Conversation enrichment — Phase A (in-thread) + Phase B (out-of-thread).

Runs before curation (staging invoices) so the user sees real state before Track.
On confirm, staging invoices are promoted to the ledger — no second enrichment pass.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from gmail_client import GmailAuthError, get_access_token, get_message, get_thread_messages, list_message_ids
from client_sweep import (
    AI_CONCURRENCY,
    AMOUNT_TOKEN_RE,
    MONEY_SIGNAL_RE,
    _extract_email_addr,
    _sender_domain,
    apply_client_result,
    assign_client_key,
    extract_client_with_ai,
    merge_candidates_by_domain,
    parse_email_date,
    preprocess_body,
    CONSUMER_DOMAINS,
)
from ledger_reconcile import amounts_close, enrich_invoice_doc, normalize_invoice_ref

logger = logging.getLogger("scotive.conversation_enrichment")

STAGING_JOB_FIELD = "staging_job_id"
STAGING_CANDIDATE_FIELD = "staging_candidate_id"

IN_THREAD_PROMPT = """You analyse ONE invoice email thread between USER and CLIENT.
The invoice row already exists — do NOT create new invoice rows.

Return STRICT JSON only:
{
  "events": [{
    "invoice_ref": string,
    "type": "promise"|"partial_payment"|"dispute"|"payment_claimed"|"correction",
    "date": "YYYY-MM-DD"|null,
    "quote": string,
    "message_id": string,
    "confidence": number,
    "amount": number|null,
    "reference": string|null,
    "dispute_kind": string|null
  }],
  "confidence_overall": number
}

Rules:
- TARGET_INVOICE_REF and TARGET_AMOUNT are the tracked invoice. All events must use that invoice_ref.
- Read the FULL thread chronologically — every message is included, no filtering.
- Each thread line is labelled "YOU →" (user sent) or "{client} → YOU" (client sent).
- promise, partial_payment, dispute, payment_claimed: ONLY from client-sent messages ("{client} → YOU"). Never from "YOU →" reminders or chasers.
- "correction" = USER revises amount on the same invoice ("YOU →" only). Set amount to the NEW value.
- For promise dates, resolve relative phrases from each message's date.
- Use verbatim quotes from the message that supports each event.
- Every event must include message_id (use id= from the thread line).
- Never emit duplicate events for the same message_id + type.
- Do not return an invoices[] array.
"""

OUT_OF_THREAD_PROMPT = """You analyse client emails OUTSIDE the invoice thread(s) listed below.
Tracked invoices already exist — never create new invoice rows.

Return STRICT JSON only:
{
  "events": [{
    "invoice_ref": string,
    "type": "promise"|"partial_payment"|"dispute"|"payment_claimed"|"correction"|"approved",
    "date": "YYYY-MM-DD"|null,
    "quote": string,
    "message_id": string,
    "confidence": number,
    "amount": number|null,
    "reference": string|null,
    "dispute_kind": string|null
  }],
  "confidence_overall": number
}

Rules:
- Each event MUST reference one of the TRACKED_INVOICES by invoice_ref.
- Only emit events when the message clearly relates to a tracked invoice (mentions ref, amount, or payment).
- "approved" = client acknowledges/approves payment without claiming paid yet.
- payment_claimed without reference → paid_unconfirmed semantics.
- Ignore unrelated chatter.
- Do not return an invoices[] array.
"""


def _gmail_after_date(dt: datetime) -> str:
    d = dt.astimezone(timezone.utc).date()
    return d.strftime("%Y/%m/%d")


def _invoice_anchor_dt(inv: dict) -> datetime:
    for key in ("source_date", "created_at"):
        dt = parse_email_date(inv.get(key))
        if dt:
            return dt
    return datetime.now(timezone.utc)


def _out_of_thread_relevance(msg: dict, invoices: list[dict]) -> bool:
    hay = " ".join([
        msg.get("subject") or "",
        preprocess_body(msg.get("body") or "", 4000),
        msg.get("snippet") or "",
    ])
    hay_upper = hay.upper()

    for inv in invoices:
        ref = inv.get("invoice_ref_normalized") or inv.get("invoice_ref")
        if ref and ref.upper() in hay_upper:
            return True
        amt = inv.get("amount")
        if amt is not None and AMOUNT_TOKEN_RE.search(hay):
            m = AMOUNT_TOKEN_RE.search(hay)
            if m:
                num = re.sub(r"[^\d.]", "", m.group().replace(",", ""))
                try:
                    if amounts_close(float(num), float(amt)):
                        return True
                except ValueError:
                    pass

    if not MONEY_SIGNAL_RE.search(hay):
        return False
    for inv in invoices:
        ref = inv.get("invoice_ref_normalized")
        if ref and ref.upper() in hay_upper:
            return True
    return False


def _tracked_invoices_context(invoices: list[dict]) -> str:
    lines = ["TRACKED_INVOICES:"]
    for inv in invoices:
        lines.append(
            f"  - ref={inv.get('invoice_ref_normalized') or inv.get('invoice_ref') or 'n/a'} "
            f"amount={inv.get('amount')} {inv.get('currency', 'USD')} "
            f"due={inv.get('due_date') or 'n/a'} thread_id={inv.get('source_thread_id') or 'n/a'}"
        )
    return "\n".join(lines)


async def _phase_a_in_thread(
    db,
    user_id,
    access: str,
    my_email: str,
    invoice: dict,
    now_iso: str,
    email_to_primary: dict[str, str],
) -> dict[str, int]:
    counts = {"threads": 0, "messages": 0, "events_applied": 0}
    thread_id = invoice.get("source_thread_id")
    anchor_id = invoice.get("source_message_id")
    client_email = (invoice.get("counterparty_email") or "").lower()
    inv_ref = invoice.get("invoice_ref_normalized") or invoice.get("invoice_ref") or ""

    messages: list[dict] = []
    if thread_id:
        messages = await get_thread_messages(access, thread_id)
        counts["threads"] = 1
    elif anchor_id:
        msg = await get_message(access, anchor_id)
        if msg:
            messages = [msg]

    if not messages:
        logger.info("enrich.phase_a SKIP inv=%s reason=no_thread", invoice.get("_id"))
        return counts

    counts["messages"] = len(messages)
    anchor_ids = [anchor_id] if anchor_id else [messages[0]["id"]]
    extra = (
        f"TARGET_INVOICE_REF: {inv_ref}\n"
        f"TARGET_AMOUNT: {invoice.get('amount')} {invoice.get('currency', 'USD')}\n"
        f"MODE: in_thread_full_context\n"
    )

    result = await extract_client_with_ai(
        client_email,
        messages,
        anchor_ids,
        my_email,
        truncated=False,
        system_prompt=IN_THREAD_PROMPT,
        extra_context=extra,
    )
    if not result:
        return counts

    _, _ = await apply_client_result(
        db, user_id, client_email, result,
        {m["id"]: m for m in messages},
        my_email, now_iso, email_to_primary,
        pass1_anchor_ids=anchor_ids,
        events_only=True,
        scoped_invoice_id=invoice["_id"],
    )
    if result.get("events"):
        counts["events_applied"] = 1
    return counts


async def _phase_b_out_of_thread(
    db,
    user_id,
    access: str,
    my_email: str,
    client_email: str,
    invoices: list[dict],
    excluded_thread_ids: set[str],
    now_iso: str,
    email_to_primary: dict[str, str],
    domains: set[str],
) -> dict[str, int]:
    counts = {"queried": 0, "kept": 0, "events_applied": 0}
    if not invoices:
        return counts

    anchor_dt = min(_invoice_anchor_dt(inv) for inv in invoices)
    after = _gmail_after_date(anchor_dt)
    primary = email_to_primary.get(client_email.lower(), client_email.lower())

    queries = [f"from:{primary} after:{after}"]
    dom = _sender_domain(primary)
    if dom and dom not in CONSUMER_DOMAINS:
        queries.append(f"from:{dom} after:{after}")

    seen: set[str] = set()
    candidate_ids: list[str] = []
    for q in queries:
        ids = await list_message_ids(access, q, max_pages=10)
        counts["queried"] += len(ids)
        for mid in ids:
            if mid not in seen:
                seen.add(mid)
                candidate_ids.append(mid)

    client_emails = {primary}
    kept_msgs: list[dict] = []
    for mid in candidate_ids:
        msg = await get_message(access, mid)
        if not msg:
            continue
        tid = msg.get("thread_id") or ""
        if tid and tid in excluded_thread_ids:
            continue
        msg_dt = parse_email_date(msg.get("date"))
        if msg_dt and msg_dt < anchor_dt:
            continue
        ck = assign_client_key(msg, client_emails, domains, my_email, email_to_primary)
        if not ck:
            continue
        if not _out_of_thread_relevance(msg, invoices):
            continue
        kept_msgs.append(msg)
        counts["kept"] += 1

    if not kept_msgs:
        return counts

    anchor_ids = [
        inv["source_message_id"]
        for inv in invoices
        if inv.get("source_message_id")
    ]
    extra = _tracked_invoices_context(invoices) + "\nMODE: out_of_thread\n"

    result = await extract_client_with_ai(
        primary,
        kept_msgs,
        anchor_ids,
        my_email,
        truncated=False,
        system_prompt=OUT_OF_THREAD_PROMPT,
        extra_context=extra,
    )
    if not result:
        return counts

    _, _ = await apply_client_result(
        db, user_id, primary, result,
        {m["id"]: m for m in kept_msgs},
        my_email, now_iso, email_to_primary,
        pass1_anchor_ids=anchor_ids,
        events_only=True,
    )
    if result.get("events"):
        counts["events_applied"] = 1
    return counts


async def run_conversation_enrichment(
    db,
    user_id,
    invoices: list[dict],
    *,
    my_email: str | None = None,
    access: str | None = None,
) -> dict[str, Any]:
    """Phase A + B on existing invoice rows (staging or ledger)."""
    counts: dict[str, Any] = {
        "phase_a": {"invoices": 0, "threads": 0, "messages": 0, "events": 0},
        "phase_b": {"clients": 0, "messages": 0, "events": 0},
        "skipped": None,
    }
    if not invoices:
        counts["skipped"] = "no_invoices"
        return counts

    if not access or not my_email:
        conn = await db.gmail_connections.find_one({"user_id": user_id})
        if not conn or conn.get("status") != "connected":
            counts["skipped"] = "no_connection"
            return counts
        try:
            access = await get_access_token(db, user_id)
        except GmailAuthError:
            counts["skipped"] = "auth_error"
            return counts
        my_email = (conn.get("email") or "").lower()

    now_iso = datetime.now(timezone.utc).isoformat()
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    email_to_primary: dict[str, str] = dict(state.get("email_to_primary") or {})
    domains: set[str] = set(state.get("client_domains") or {})

    sem = asyncio.Semaphore(AI_CONCURRENCY)

    for inv in invoices:
        async with sem:
            pa = await _phase_a_in_thread(
                db, user_id, access, my_email, inv, now_iso, email_to_primary,
            )
        counts["phase_a"]["invoices"] += 1
        counts["phase_a"]["threads"] += pa.get("threads", 0)
        counts["phase_a"]["messages"] += pa.get("messages", 0)
        counts["phase_a"]["events"] += pa.get("events_applied", 0)

    by_client: dict[str, list[dict]] = {}
    for inv in invoices:
        em = (inv.get("counterparty_email") or "").lower()
        by_client.setdefault(em, []).append(inv)
        dom = _sender_domain(em)
        if dom and dom not in CONSUMER_DOMAINS:
            domains.add(dom)

    _, merged_etp = merge_candidates_by_domain({
        em: [i.get("source_message_id") for i in invs if i.get("source_message_id")]
        for em, invs in by_client.items()
    })
    email_to_primary = {**email_to_primary, **merged_etp}

    for client_email, client_invs in by_client.items():
        excluded = {
            inv.get("source_thread_id")
            for inv in client_invs
            if inv.get("source_thread_id")
        }
        primary = email_to_primary.get(client_email.lower(), client_email.lower())
        async with sem:
            pb = await _phase_b_out_of_thread(
                db, user_id, access, my_email, primary, client_invs,
                excluded, now_iso, email_to_primary, domains,
            )
        counts["phase_b"]["clients"] += 1
        counts["phase_b"]["messages"] += pb.get("kept", 0)
        counts["phase_b"]["events"] += pb.get("events_applied", 0)

    from invoice_lifecycle import apply_past_due_transitions, apply_promise_broken_transitions
    from invoice_event_idempotency import dedupe_stored_invoice_events

    counts["past_due_flipped"] = await apply_past_due_transitions(db, user_id)
    counts["promise_broken_flipped"] = await apply_promise_broken_transitions(db, user_id)
    counts["events_deduped"] = await dedupe_stored_invoice_events(db, user_id)

    return counts


async def delete_staging_for_job(db, user_id, job_id) -> int:
    """Remove staging invoices + events for a seed job."""
    deleted = 0
    async for inv in db.invoices.find({"user_id": user_id, STAGING_JOB_FIELD: job_id}):
        await db.invoice_events.delete_many({"invoice_id": inv["_id"]})
        await db.invoices.delete_one({"_id": inv["_id"]})
        deleted += 1
    return deleted


async def delete_staging_invoice(db, user_id, staging_invoice_id: str | ObjectId) -> None:
    try:
        oid = staging_invoice_id if isinstance(staging_invoice_id, ObjectId) else ObjectId(str(staging_invoice_id))
    except Exception:
        return
    inv = await db.invoices.find_one({"_id": oid, "user_id": user_id, STAGING_JOB_FIELD: {"$exists": True}})
    if not inv:
        return
    await db.invoice_events.delete_many({"invoice_id": oid})
    await db.invoices.delete_one({"_id": oid})


def _staging_status_from_due(due_date: str | None, today) -> str:
    from invoice_lifecycle import _parse_date
    status = "invoiced"
    due_dt = _parse_date(due_date)
    if due_dt and due_dt < today:
        status = "overdue"
    return status


async def _create_staging_invoice(
    db,
    user_id,
    job_id,
    candidate: dict,
    now_iso: str,
    today,
) -> ObjectId | None:
    due_date = candidate.get("due_date")
    status = _staging_status_from_due(due_date, today)
    inv_doc = enrich_invoice_doc({
        "user_id": user_id,
        STAGING_JOB_FIELD: job_id,
        STAGING_CANDIDATE_FIELD: str(candidate["_id"]),
        "counterparty_email": candidate["counterparty_email"],
        "counterparty_name": candidate.get("counterparty_name"),
        "client_identity_key": candidate.get("client_identity_key"),
        "amount": candidate["amount"],
        "balance_remaining": float(candidate["amount"]),
        "paid_amount": 0.0,
        "currency": candidate.get("currency") or "USD",
        "invoice_ref": candidate.get("invoice_ref"),
        "invoice_ref_normalized": candidate.get("invoice_ref_normalized"),
        "due_date": due_date,
        "due_date_assumed": False,
        "promise_date": None,
        "status": status,
        "kind": "invoice_sent",
        "source_message_id": candidate["message_id"],
        "source_thread_id": candidate.get("source_thread_id"),
        "source_subject": candidate.get("source_subject"),
        "source_from": candidate.get("source_from"),
        "source_date": candidate.get("source_date"),
        "confidence": float(candidate.get("confidence") or 1.0),
        "created_at": now_iso,
    }, candidate["counterparty_email"])
    try:
        res = await db.invoices.insert_one(inv_doc)
        return res.inserted_id
    except Exception as e:
        logger.warning("staging invoice insert failed candidate=%s err=%s", candidate.get("_id"), e)
        return None


async def _sync_candidate_from_staging(db, candidate_id, staging: dict, now_iso: str) -> None:
    await db.seed_candidates.update_one(
        {"_id": candidate_id},
        {"$set": {
            "amount": staging.get("amount"),
            "balance_remaining": staging.get("balance_remaining"),
            "paid_amount": float(staging.get("paid_amount") or 0),
            "enriched_status": staging.get("status"),
            "promise_date": staging.get("promise_date"),
            "staging_invoice_id": str(staging["_id"]),
            "conversation_enriched": True,
            "updated_at": now_iso,
        }},
    )


async def run_pre_curation_enrichment(db, user_id, job_id) -> dict[str, Any]:
    """After sent-invoice scan: expand threads + out-of-thread for every candidate."""
    import os

    counts: dict[str, Any] = {"candidates": 0, "staging_created": 0, "skipped": None}
    if not os.environ.get("OPENROUTER_API_KEY"):
        counts["skipped"] = "no_openrouter_key"
        return counts

    candidates: list[dict] = []
    async for doc in db.seed_candidates.find({
        "user_id": user_id,
        "job_id": job_id,
        "status": "pending",
    }):
        candidates.append(doc)

    if not candidates:
        counts["skipped"] = "no_candidates"
        return counts

    counts["candidates"] = len(candidates)
    await delete_staging_for_job(db, user_id, job_id)

    now_iso = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date()
    staging_invoices: list[dict] = []

    for cand in candidates:
        sid = await _create_staging_invoice(db, user_id, job_id, cand, now_iso, today)
        if not sid:
            continue
        counts["staging_created"] += 1
        inv = await db.invoices.find_one({"_id": sid})
        if inv:
            staging_invoices.append(inv)

    if not staging_invoices:
        counts["skipped"] = "no_staging"
        return counts

    enrich = await run_conversation_enrichment(db, user_id, staging_invoices)
    counts["enrichment"] = enrich

    for inv in staging_invoices:
        fresh = await db.invoices.find_one({"_id": inv["_id"]})
        if not fresh:
            continue
        cid = fresh.get(STAGING_CANDIDATE_FIELD)
        if cid:
            await _sync_candidate_from_staging(db, ObjectId(cid), fresh, now_iso)

    logger.info("pre_curation.DONE user=%s job=%s counts=%s", user_id, job_id, counts)
    return counts


async def promote_staging_invoice(
    db,
    user_id,
    staging_invoice_id: str | ObjectId,
    *,
    due_date: str | None,
    now_iso: str,
    today,
) -> ObjectId | None:
    """Move a staging invoice into the live ledger (same row, flags removed)."""
    try:
        oid = staging_invoice_id if isinstance(staging_invoice_id, ObjectId) else ObjectId(str(staging_invoice_id))
    except Exception:
        return None

    inv = await db.invoices.find_one({"_id": oid, "user_id": user_id})
    if not inv or not inv.get(STAGING_JOB_FIELD):
        return None

    status = inv.get("status") or "invoiced"
    if due_date is not None:
        status = _staging_status_from_due(due_date, today)
        if inv.get("status") in ("disputed", "promised", "partially_paid", "paid_unconfirmed", "promise_broken"):
            status = inv["status"]

    patch: dict[str, Any] = {
        "status": status,
        "status_updated_at": now_iso,
        "updated_at": now_iso,
    }
    if due_date is not None:
        patch["due_date"] = due_date
        patch["due_date_assumed"] = False

    await db.invoices.update_one(
        {"_id": oid},
        {
            "$unset": {STAGING_JOB_FIELD: "", STAGING_CANDIDATE_FIELD: ""},
            "$set": patch,
        },
    )
    return oid


# Backward-compatible alias (incremental / legacy callers)
async def run_post_track_enrichment(
    db,
    user_id,
    tracked_invoice_ids: list[Any],
) -> dict[str, Any]:
    invoices: list[dict] = []
    for iid in tracked_invoice_ids:
        oid = iid if isinstance(iid, ObjectId) else ObjectId(str(iid))
        inv = await db.invoices.find_one({"_id": oid, "user_id": user_id})
        if inv and not inv.get(STAGING_JOB_FIELD):
            invoices.append(inv)
    result = await run_conversation_enrichment(db, user_id, invoices)
    logger.info("post_track.DONE user=%s counts=%s", user_id, result)
    return result
