"""First-pass: attach an inbox thread to an invoicing-tool invoice, then decide status.

Onboarding and newly imported invoices use this path:
  1. Search client mail for this invoice (InvoiceLink → DocNumber → amount → dates)
  2. Attach that thread plus later client threads that still match
  3. OpenAI decides promised / needs-reply / etc. from those messages (full bodies)

Hourly sync must NOT be called from here. Windowed "anything new?" re-eval
lives in incremental_sync._reevaluate_tracked.

Not tied to one books product or one mailbox: open ledger rows from any
connected invoicing tool, mail from any connected inbox.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from apply_conversation_status import (
    apply_rulebook_result,
    invoice_processed_message_ids,
    mark_processed,
)
from gmail_client import list_messages, list_thread_full, mailbox_tokens_for_user
from invoice_mail_match import (
    anchor_after_query_value,
    extra_thread_ids,
    invoice_ref,
    message_hay,
    pay_url_token,
    pick_anchor_message,
    waterfall_threads,
)
from ledger_reconcile import OPEN_INVOICE_STATUSES
from reeval_rulebook import build_reeval_input, build_tracked_state, extract_reeval_with_rulebook
from seed_ai import SEED_AI_CONCURRENCY

logger = logging.getLogger("scotive.conversation_first_pass")

MATCH_LIST_PAGES = 2
MATCH_MAX_MSGS = 80
INVOICING_SOURCES = ("quickbooks", "xero", "freshbooks")
PLACEHOLDER_EMAIL_PREFIXES = ("qbo:", "xero:", "freshbooks:")

# Existing Mongo collection — same job the connect page already polls.
JOBS = "qbo_pipeline_jobs"


def _item_snapshot(inv: dict, *, state: str = "waiting", detail: str = "Waiting…") -> dict[str, Any]:
    return {
        "invoice_id": str(inv.get("_id") or ""),
        "invoice_ref": (inv.get("invoice_ref") or inv.get("invoice_ref_normalized") or "").strip(),
        "client": (inv.get("counterparty_name") or inv.get("counterparty_email") or "Client"),
        "email": (inv.get("counterparty_email") or "").strip().lower(),
        "amount": inv.get("amount"),
        "currency": (inv.get("currency") or "USD"),
        "state": state,
        "detail": detail,
    }


async def _open_invoicing_invoices(db, user_id, invoice_ids: list | None = None) -> list[dict]:
    query: dict[str, Any] = {
        "user_id": user_id,
        "status": {"$in": list(OPEN_INVOICE_STATUSES)},
        "$or": [
            {"qbo_id": {"$type": "string"}},
            {"xero_id": {"$type": "string"}},
            {"freshbooks_id": {"$type": "string"}},
            {"source": {"$in": list(INVOICING_SOURCES)}},
        ],
    }
    if invoice_ids:
        from bson import ObjectId
        oids = []
        for raw in invoice_ids:
            try:
                oids.append(ObjectId(str(raw)) if not hasattr(raw, "binary") else raw)
            except Exception:
                continue
        if not oids:
            return []
        query["_id"] = {"$in": oids}
    invoices = []
    async for inv in db.invoices.find(query):
        invoices.append(inv)
    return invoices


def _has_real_client_email(inv: dict) -> bool:
    email = (inv.get("counterparty_email") or "").strip().lower()
    if not email or "@" not in email:
        return False
    if any(email.startswith(p) for p in PLACEHOLDER_EMAIL_PREFIXES):
        return False
    return True


def _pick_best_thread(
    messages: list[dict],
    invoice: dict,
    *,
    my_email: str,
) -> tuple[Optional[str], Optional[str]]:
    """Primary thread + anchor message from an already-fetched pile."""
    tids = waterfall_threads(messages, invoice)
    if not tids:
        return None, None
    pile = [m for m in messages if m.get("thread_id") in set(tids)]
    anchor = pick_anchor_message(pile, invoice, my_email=my_email)
    tid = (anchor or {}).get("thread_id") or tids[0]
    return tid, (anchor or {}).get("id")


def _account_for_thread(messages: list[dict], thread_id: str, fallback: str) -> str:
    for m in messages:
        if m.get("thread_id") == thread_id and m.get("_account_id"):
            return m["_account_id"]
    return fallback


def _amount_search_token(invoice: dict) -> Optional[str]:
    amt = invoice.get("amount")
    if amt is None:
        return None
    try:
        return f"{float(amt):.2f}"
    except (TypeError, ValueError):
        return None


async def _search_client_mail(
    mailboxes: list[tuple[dict, str]],
    client_email: str,
    *,
    search: str | None = None,
    after: str | None = None,
) -> list[dict]:
    email = client_email.lower().strip()
    bits = [f"(from:{email} OR to:{email})"]
    if after:
        bits.append(f"after:{after}")
    if search:
        bits.append(search)
    q = " ".join(bits)
    out: list[dict] = []
    seen: set[str] = set()
    for conn, access in mailboxes:
        try:
            msgs = await list_messages(
                access, q, max_pages=MATCH_LIST_PAGES, max_msgs=MATCH_MAX_MSGS,
            )
        except Exception as e:
            logger.warning(
                "first-pass LIST FAIL email=%s provider=%s search=%r err=%s",
                email, conn.get("provider"), (search or "")[:40], e,
            )
            try:
                msgs = await list_messages(
                    access,
                    f"(from:{email} OR to:{email})",
                    max_pages=MATCH_LIST_PAGES,
                    max_msgs=MATCH_MAX_MSGS,
                )
                if search:
                    needle = search.lower()
                    msgs = [m for m in msgs if needle in message_hay(m).lower()]
            except Exception as e2:
                logger.warning("first-pass LIST retry fail email=%s err=%s", email, e2)
                continue
        for m in msgs:
            mid = m.get("id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            out.append({
                **m,
                "_account_id": access,
                "_mailbox_provider": conn.get("provider") or "google",
            })
    return out


async def _phase1_messages(
    mailboxes: list[tuple[dict, str]],
    invoice: dict,
) -> list[dict]:
    """Find the QBO send (or inbound quote) for this invoice."""
    client = (invoice.get("counterparty_email") or "").strip().lower()
    token = pay_url_token(invoice.get("pay_url"))
    if token:
        hits = await _search_client_mail(mailboxes, client, search=token)
        tids = waterfall_threads(hits, invoice)
        if tids:
            return [m for m in hits if m.get("thread_id") in set(tids)]

    ref = invoice_ref(invoice)
    if ref:
        hits = await _search_client_mail(mailboxes, client, search=ref)
        tids = waterfall_threads(hits, invoice)
        if tids:
            return [m for m in hits if m.get("thread_id") in set(tids)]

    amt_tok = _amount_search_token(invoice)
    if amt_tok:
        hits = await _search_client_mail(mailboxes, client, search=amt_tok)
        tids = waterfall_threads(hits, invoice)
        if tids:
            return [m for m in hits if m.get("thread_id") in set(tids)]
    return []


async def _phase2_extra_messages(
    mailboxes: list[tuple[dict, str]],
    invoice: dict,
    *,
    known_tids: set[str],
    after: str | None,
) -> list[dict]:
    if not after:
        return []
    client = (invoice.get("counterparty_email") or "").strip().lower()
    later: list[dict] = []
    token = pay_url_token(invoice.get("pay_url"))
    if token:
        later.extend(await _search_client_mail(
            mailboxes, client, search=token, after=after,
        ))
    ref = invoice_ref(invoice)
    if ref:
        later.extend(await _search_client_mail(
            mailboxes, client, search=ref, after=after,
        ))
    extra_tids = extra_thread_ids(later, invoice, known=known_tids)
    return [m for m in later if m.get("thread_id") in set(extra_tids)]


async def _attach_threads(
    db,
    invoice: dict,
    thread_ids: list[str],
    anchor_id: Optional[str],
    now_iso: str,
) -> None:
    if not thread_ids:
        return
    primary = thread_ids[0]
    patch: dict[str, Any] = {
        "source_thread_id": primary,
        "conversation_thread_ids": thread_ids,
        "conversation_matched_at": now_iso,
        "updated_at": now_iso,
    }
    src = str(invoice.get("source_message_id") or "")
    if anchor_id and (src.startswith("qbo:") or src.startswith("xero:") or src.startswith("freshbooks:")):
        patch["gmail_anchor_message_id"] = anchor_id
    elif anchor_id and not src:
        patch["gmail_anchor_message_id"] = anchor_id
    await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": patch})
    await db.invoice_events.insert_one({
        "user_id": invoice["user_id"],
        "invoice_id": invoice["_id"],
        "action": "conversation_matched",
        "at": now_iso,
        "meta": {
            "source_thread_id": primary,
            "conversation_thread_ids": thread_ids,
            "mailbox_anchor_message_id": anchor_id,
            "invoicing_id": invoice.get("qbo_id") or invoice.get("xero_id") or invoice.get("freshbooks_id"),
        },
    })


async def _set_job(db, job_id, **fields) -> None:
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db[JOBS].update_one({"_id": job_id}, {"$set": fields})


async def get_conversation_job_status(db, user_id) -> dict[str, Any] | None:
    job = await db[JOBS].find_one(
        {"user_id": user_id},
        sort=[("started_at", -1)],
    )
    if not job:
        return None
    return {
        "job_id": str(job["_id"]),
        "status": job.get("status") or "idle",
        "phase": job.get("phase") or "idle",
        "kind": job.get("kind") or "first_pass",
        "total": int(job.get("total") or 0),
        "examined": int(job.get("examined") or 0),
        "matched": int(job.get("matched") or 0),
        "status_total": int(job.get("status_total") or 0),
        "status_done": int(job.get("status_done") or 0),
        "reevaluated": int(job.get("reevaluated") or 0),
        "skipped_no_email": int(job.get("skipped_no_email") or 0),
        "skipped_no_thread": int(job.get("skipped_no_thread") or 0),
        "errors": int(job.get("errors") or 0),
        "error": job.get("error"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "items": list(job.get("items") or []),
    }


async def enqueue_conversation_first_pass(
    db,
    user_id,
    *,
    invoice_ids: list | None = None,
) -> dict[str, Any]:
    """Start first-pass in the background. Idempotent if already running.

    No-op until a mailbox is connected so invoicing import can finish first.
    """
    mailboxes = await mailbox_tokens_for_user(db, user_id)
    if not mailboxes:
        return {"job_id": None, "status": "skipped", "skipped": "no_mailbox", "deduped": False}

    existing = await db[JOBS].find_one({
        "user_id": user_id,
        "status": {"$in": ["queued", "running"]},
    })
    if existing:
        return {
            "job_id": str(existing["_id"]),
            "status": existing.get("status"),
            "deduped": True,
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    seed = await _open_invoicing_invoices(db, user_id, invoice_ids)
    res = await db[JOBS].insert_one({
        "user_id": user_id,
        "kind": "first_pass",
        "status": "queued",
        "phase": "queued",
        "total": len(seed),
        "examined": 0,
        "matched": 0,
        "status_total": 0,
        "status_done": 0,
        "reevaluated": 0,
        "invoice_ids": [str(x) for x in (invoice_ids or [])] or None,
        "items": [_item_snapshot(inv) for inv in seed],
        "started_at": now_iso,
        "updated_at": now_iso,
    })
    job_id = res.inserted_id
    asyncio.create_task(_run_first_pass_job(db, user_id, job_id, invoice_ids=invoice_ids))
    return {"job_id": str(job_id), "status": "queued", "deduped": False}


async def _run_first_pass_job(
    db,
    user_id,
    job_id,
    *,
    invoice_ids: list | None = None,
) -> None:
    try:
        await _set_job(db, job_id, status="running", phase="matching")
        counts = await run_conversation_first_pass(
            db, user_id, invoice_ids=invoice_ids, job_id=job_id,
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        await _set_job(
            db, job_id,
            status="complete",
            phase="complete",
            examined=counts.get("examined", 0),
            matched=counts.get("matched", 0),
            reevaluated=counts.get("reevaluated", 0),
            status_done=counts.get("status_done", 0),
            status_total=counts.get("status_total", 0),
            skipped_no_email=counts.get("skipped_no_email", 0),
            skipped_no_thread=counts.get("skipped_no_thread", 0),
            already_matched=counts.get("already_matched", 0),
            errors=counts.get("errors", 0),
            finished_at=now_iso,
        )
    except Exception as e:
        logger.exception("first-pass job fail user=%s: %s", user_id, e)
        await _set_job(
            db, job_id,
            status="error",
            phase="error",
            error=str(e)[:500],
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


def _has_message_bodies(messages: list[dict]) -> bool:
    return any((m.get("body") or "").strip() for m in messages)


async def _decide_from_messages(
    db, user_id, inv: dict, messages: list[dict], my_email: str, now_iso: str,
) -> dict[str, Any]:
    """OpenAI on messages we already have. No mailbox list."""
    if not messages:
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {"conversation_status_at": now_iso, "updated_at": now_iso}},
        )
        return {"skipped": "no_messages"}

    if not _has_message_bodies(messages):
        logger.warning("first-pass decide EMPTY-BODIES inv=%s", inv["_id"])
        return {"skipped": "empty_bodies"}

    if not os.environ.get("OPENAI_API_KEY"):
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {"conversation_status_at": now_iso, "updated_at": now_iso}},
        )
        return {"skipped": "no_openai_key"}

    client = (inv.get("counterparty_email") or "").lower()
    conv_ids = [m["id"] for m in messages if m.get("id")]
    processed_ids = await invoice_processed_message_ids(db, user_id, inv, conv_ids)
    tracked = build_tracked_state(inv, processed_ids)
    prepared = build_reeval_input(
        my_email=my_email,
        client_email=client,
        messages=messages,
        tracked_state=tracked,
        anchor_ids=[inv.get("source_message_id")] if inv.get("source_message_id") else None,
    )
    result = await extract_reeval_with_rulebook(client, prepared)
    if not result:
        logger.warning("first-pass AI-EMPTY inv=%s", inv["_id"])
        return {"skipped": "ai_empty"}

    considered = [m["id"] for m in messages if m.get("id")]
    applied = await apply_rulebook_result(
        db, user_id, inv, result, messages,
        my_email=my_email, now_iso=now_iso, considered_ids=considered,
    )
    await mark_processed(db, user_id, considered)
    await db.invoices.update_one(
        {"_id": inv["_id"]},
        {"$set": {"conversation_status_at": now_iso, "updated_at": now_iso}},
    )
    return {"reevaluated": 1, **applied}


async def run_conversation_first_pass(
    db,
    user_id,
    *,
    invoice_ids: list | None = None,
    job_id=None,
) -> dict[str, Any]:
    counts = {
        "examined": 0,
        "matched": 0,
        "skipped_no_email": 0,
        "skipped_no_thread": 0,
        "already_matched": 0,
        "reevaluated": 0,
        "status_done": 0,
        "status_total": 0,
        "errors": 0,
    }

    async def _progress(**kwargs):
        if job_id is not None:
            await _set_job(db, job_id, **kwargs)

    invoices = await _open_invoicing_invoices(db, user_id, invoice_ids)
    if invoice_ids and not invoices:
        return counts

    total = len(invoices)
    items = [_item_snapshot(inv) for inv in invoices]
    item_ix = {it["invoice_id"]: i for i, it in enumerate(items)}

    async def _mark(inv, state: str, detail: str, **extra):
        iid = str(inv.get("_id") or "")
        i = item_ix.get(iid)
        if i is not None:
            items[i] = {**items[i], "state": state, "detail": detail}
        await _progress(items=items, **extra)

    await _progress(phase="matching", status="running", total=total, examined=0, matched=0, items=items)

    if not invoices:
        await _progress(status="complete", phase="complete", total=0, examined=0)
        return counts

    mailboxes = await mailbox_tokens_for_user(db, user_id)
    if not mailboxes:
        counts["skipped"] = "no_mailbox"
        await _progress(status="complete", phase="complete")
        return counts

    my_email = (mailboxes[0][0].get("email") or "").lower()
    fallback_access = mailboxes[0][1]
    now_iso = datetime.now(timezone.utc).isoformat()

    pending: list[dict] = []
    decide_units: list[tuple[dict, list[dict]]] = []

    for inv in invoices:
        if inv.get("source_thread_id"):
            counts["already_matched"] += 1
            counts["examined"] += 1
            await _mark(
                inv, "already", "Already matched",
                examined=counts["examined"], already_matched=counts["already_matched"],
            )
            if not inv.get("conversation_status_at"):
                decide_units.append((inv, []))  # fetch thread once in decide phase
            continue
        if not _has_real_client_email(inv):
            counts["skipped_no_email"] += 1
            counts["examined"] += 1
            await _mark(
                inv, "no_email", "No client email on this invoice",
                examined=counts["examined"], skipped_no_email=counts["skipped_no_email"],
            )
            continue
        pending.append(inv)

    for inv in pending:
        try:
            await _mark(inv, "checking", f"Matching invoice {inv.get('invoice_ref') or ''}…")
            phase1 = await _phase1_messages(mailboxes, inv)
            if not phase1:
                counts["skipped_no_thread"] += 1
                counts["examined"] += 1
                await _mark(
                    inv, "no_thread", "No matching thread",
                    examined=counts["examined"], skipped_no_thread=counts["skipped_no_thread"],
                )
                continue
            tids = waterfall_threads(phase1, inv)
            pile = [m for m in phase1 if m.get("thread_id") in set(tids)]
            anchor_msg = pick_anchor_message(pile, inv, my_email=my_email)
            primary = (anchor_msg or {}).get("thread_id") or (tids[0] if tids else None)
            if not primary:
                counts["skipped_no_thread"] += 1
                counts["examined"] += 1
                await _mark(
                    inv, "no_thread", "No matching thread",
                    examined=counts["examined"], skipped_no_thread=counts["skipped_no_thread"],
                )
                continue
            known = set(tids)
            extra_msgs = await _phase2_extra_messages(
                mailboxes, inv,
                known_tids=known,
                after=anchor_after_query_value(anchor_msg),
            )
            extra_tids = extra_thread_ids(extra_msgs, inv, known=known)
            ordered = [primary] + [t for t in list(tids) + extra_tids if t != primary]
            account = _account_for_thread(pile + extra_msgs, primary, fallback_access)
            thread_msgs: list[dict] = []
            seen_ids: set[str] = set()
            for tid in ordered:
                acc = _account_for_thread(pile + extra_msgs, tid, account)
                try:
                    full = await list_thread_full(acc, tid)
                except Exception as e:
                    logger.info("first-pass thread full skip tid=%s err=%s", tid[:12], e)
                    full = [m for m in pile + extra_msgs if m.get("thread_id") == tid]
                for m in full:
                    mid = m.get("id")
                    if mid and mid not in seen_ids:
                        seen_ids.add(mid)
                        thread_msgs.append(m)
            await _attach_threads(
                db, inv, ordered, (anchor_msg or {}).get("id"), now_iso,
            )
            inv["source_thread_id"] = primary
            inv["conversation_thread_ids"] = ordered
            counts["matched"] += 1
            counts["examined"] += 1
            await _mark(
                inv, "matched", "Thread found",
                examined=counts["examined"], matched=counts["matched"],
            )
            decide_units.append((inv, thread_msgs))
        except Exception as e:
            logger.exception("first-pass match fail inv=%s: %s", inv.get("_id"), e)
            counts["errors"] += 1
            counts["examined"] += 1
            await _mark(
                inv, "error", "Could not match this invoice",
                examined=counts["examined"], errors=counts["errors"],
            )

    # --- Decide status from messages already in hand (no second inbox crawl) ---
    resolved: list[tuple[dict, list[dict]]] = []
    for inv, msgs in decide_units:
        if msgs:
            resolved.append((inv, msgs))
            continue
        tids = list(inv.get("conversation_thread_ids") or [])
        if inv.get("source_thread_id") and inv["source_thread_id"] not in tids:
            tids = [inv["source_thread_id"], *tids]
        fetched: list[dict] = []
        seen: set[str] = set()
        for tid in tids:
            if not tid:
                continue
            try:
                full = await list_thread_full(fallback_access, tid)
            except Exception as e:
                logger.warning("first-pass decide thread fetch inv=%s err=%s", inv["_id"], e)
                full = []
            for m in full:
                mid = m.get("id")
                if mid and mid not in seen:
                    seen.add(mid)
                    fetched.append(m)
        resolved.append((inv, fetched))

    need_ai: list[tuple[dict, list[dict]]] = []
    for inv, msgs in resolved:
        if _has_message_bodies(msgs):
            need_ai.append((inv, msgs))
            continue
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {"conversation_status_at": now_iso, "updated_at": now_iso}},
        )
        iid = str(inv.get("_id") or "")
        i = item_ix.get(iid)
        if i is not None:
            items[i] = {**items[i], "state": "ready", "detail": "No message bodies"}

    counts["status_total"] = len(need_ai)
    if need_ai:
        await _progress(
            phase="deciding_status",
            status="running",
            examined=counts["examined"],
            matched=counts["matched"],
            status_total=counts["status_total"],
            status_done=0,
            items=items,
        )

        sem = asyncio.Semaphore(SEED_AI_CONCURRENCY)
        lock = asyncio.Lock()

        async def _one(unit: tuple[dict, list[dict]]):
            inv, messages = unit
            async with sem:
                iid = str(inv.get("_id") or "")
                i = item_ix.get(iid)
                done = reev = errs = 0
                if i is not None:
                    items[i] = {**items[i], "state": "updating", "detail": "Updating status from the conversation…"}
                try:
                    result = await _decide_from_messages(
                        db, user_id, inv, messages, my_email, now_iso,
                    )
                    async with lock:
                        counts["status_done"] += 1
                        if result.get("reevaluated"):
                            counts["reevaluated"] += 1
                        done = counts["status_done"]
                        reev = counts["reevaluated"]
                        errs = counts["errors"]
                    if i is not None:
                        items[i] = {**items[i], "state": "ready", "detail": "Conversation updated"}
                except Exception as e:
                    logger.exception("first-pass decide fail inv=%s: %s", inv.get("_id"), e)
                    async with lock:
                        counts["errors"] += 1
                        counts["status_done"] += 1
                        done = counts["status_done"]
                        reev = counts["reevaluated"]
                        errs = counts["errors"]
                    if i is not None:
                        items[i] = {**items[i], "state": "error", "detail": "Could not update status"}
                await _progress(
                    status_done=done,
                    reevaluated=reev,
                    errors=errs,
                    items=items,
                )

        await asyncio.gather(*[_one(u) for u in need_ai])

    await _progress(
        status="complete",
        phase="complete",
        examined=counts["examined"],
        matched=counts["matched"],
        status_done=counts["status_done"],
        status_total=counts["status_total"],
        reevaluated=counts["reevaluated"],
        errors=counts["errors"],
        items=items,
    )
    logger.info("first-pass DONE user=%s counts=%s", user_id, {
        k: counts[k] for k in counts if k != "matched_ids"
    })
    return counts
