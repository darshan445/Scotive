"""Hourly + manual incremental sync — per-invoice pipeline (windowed).

Invoices enter the ledger from the connected invoicing tool (QuickBooks CDC /
import). Gmail/Outlook is used to re-evaluate tracked invoices — not to
discover new invoices from sent mail.

  QBO CDC / webhooks     → new and changed invoices
  First-pass (onboarding / new invoice) → conversation_first_pass
  Tracked invoices       → list_thread_full on known threads (same as the
                           drawer). Any message not yet shown to the rulebook
                           is re-evaluated — owner or client, no language
                           gate. New unmatched threads still use windowed
                           from:client + the InvoiceLink → DocNumber →
                           amount → dates ladder.

Message ids already on the invoice timeline (events / reeval_seen) are not
sent to the model again.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from gmail_client import (
    list_messages,
    list_thread_full,
    mailbox_tokens_for_user,
)
from client_sweep import (
    CONSUMER_DOMAINS,
    _extract_email_addr,
    _sender_domain,
)
from conversation_first_pass import _attach_threads, _has_real_client_email
from invoice_mail_match import extra_thread_ids, invoice_ref, pay_url_token, pick_anchor_message
from gmail_sync import (
    _onboarding_allows_incremental,
    incremental_window_start,
)
from invoice_event_idempotency import dedupe_stored_invoice_events
from invoice_lifecycle import apply_past_due_transitions, apply_promise_broken_transitions
from ledger_reconcile import (
    OPEN_INVOICE_STATUSES,
    dedupe_existing_invoices,
    parse_email_date,
)
from post_chase import run_post_chase_tick
from apply_conversation_status import (
    apply_rulebook_result,
    invoice_processed_message_ids as _invoice_processed_message_ids,
    mark_processed as _mark_processed,
)
from reeval_rulebook import (
    build_reeval_input,
    build_tracked_state,
    extract_reeval_with_rulebook,
)
from seed_ai import (
    SEED_AI_CONCURRENCY,
    _merge_client_messages,
)

logger = logging.getLogger("scotive.incremental_sync")

CLIENT_QUERY_CHUNK = 15
MAX_CLIENT_MSGS = 60
# Verbose re-eval diagnostics (AI inputs/outputs, window decisions).
REEVAL_DEBUG = os.environ.get("SYNC_REEVAL_DEBUG", "").lower() in ("1", "true", "yes")


def _invoice_thread_ids(inv: dict) -> list[str]:
    """QBO-send thread plus later matched threads. Order preserved, no dups."""
    out: list[str] = []
    seen: set[str] = set()
    for tid in [inv.get("source_thread_id"), *(inv.get("conversation_thread_ids") or [])]:
        if tid and tid not in seen:
            seen.add(tid)
            out.append(tid)
    return out


def _msg_for_invoice_client(msg: dict, inv: dict) -> bool:
    sender = _extract_email_addr(msg.get("from", ""))
    if not sender:
        return False
    email = (inv.get("counterparty_email") or "").lower()
    key = (inv.get("client_identity_key") or email or "").lower()
    if sender == email or (key and sender in key):
        return True
    dom = _sender_domain(sender)
    if dom and dom not in CONSUMER_DOMAINS and key and dom in key:
        return True
    return False


async def _fetch_invoice_thread_messages(
    access: str,
    inv: dict,
    *,
    extra_tid: str | None = None,
) -> list[dict]:
    """Full bodies for every thread attached to this invoice."""
    tids = _invoice_thread_ids(inv)
    if extra_tid and extra_tid not in tids:
        tids.append(extra_tid)
    out: list[dict] = []
    seen: set[str] = set()
    for tid in tids:
        try:
            full = await list_thread_full(access, tid)
        except Exception as e:
            logger.warning(
                "incremental thread fetch fail inv=%s tid=%s err=%s",
                inv.get("_id"), (tid or "")[:12], e,
            )
            continue
        for m in full:
            mid = m.get("id")
            if mid and mid not in seen:
                seen.add(mid)
                out.append(m)
    return out


async def _append_conversation_threads(
    db, invoice: dict, extra_tids: list[str], now_iso: str,
) -> None:
    """Add threads without replacing the QBO-send source_thread_id."""
    extra = [t for t in extra_tids if t]
    if not extra:
        return
    await db.invoices.update_one(
        {"_id": invoice["_id"]},
        {
            "$addToSet": {"conversation_thread_ids": {"$each": extra}},
            "$set": {"updated_at": now_iso, "conversation_matched_at": now_iso},
        },
    )
    existing = list(invoice.get("conversation_thread_ids") or [])
    src = invoice.get("source_thread_id")
    if src and src not in existing:
        existing = [src, *existing]
    for tid in extra:
        if tid not in existing:
            existing.append(tid)
    invoice["conversation_thread_ids"] = existing


async def reeval_after_user_outbound_send(
    db,
    user_id,
    inv: dict,
    *,
    access: str,
    my_email: str,
    subject: str,
    body: str,
    gmail_message_id: str | None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Run Stage 4 right after Scotive sends, same as Sync now on that thread.

    Open invoices always go to the rulebook. No money/verb gate — a no-diff
    chase is the model's job, not regex.
    """
    out: dict[str, Any] = {"triggered": False, "applied": False}
    if not inv or not inv.get("_id"):
        out["skipped"] = "no_invoice"
        return out
    if inv.get("status") not in OPEN_INVOICE_STATUSES:
        out["skipped"] = "not_open"
        return out
    if not os.environ.get("OPENAI_API_KEY"):
        out["skipped"] = "no_ai"
        return out

    my = (my_email or "").strip().lower()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    mid = (gmail_message_id or "").strip() or f"scotive-send:{inv['_id']}:{int(now.timestamp())}"
    msg = {
        "id": mid,
        "subject": subject or "",
        "body": body or "",
        "snippet": (body or "")[:240],
        "from": my,
        "thread_id": thread_id or inv.get("source_thread_id"),
        "date": now.strftime("%a, %d %b %Y %H:%M:%S +0000"),
    }
    out["triggered"] = True
    logger.info(
        "reeval POST-SEND inv=%s msg=%s status=%s",
        inv["_id"], mid, inv.get("status"),
    )

    thread_msgs = await _fetch_invoice_thread_messages(access, inv, extra_tid=thread_id)
    combined = _merge_client_messages([], thread_msgs, [])
    # Ensure the just-sent body is present even if Gmail thread lag omits it.
    if not any(m.get("id") == mid for m in combined):
        combined = list(combined) + [msg]
    else:
        # Prefer the body we just sent (fresher than a thin Gmail snippet).
        combined = [
            {**m, "body": body or m.get("body"), "subject": subject or m.get("subject")}
            if m.get("id") == mid else m
            for m in combined
        ]
    if not any((m.get("body") or "").strip() for m in combined):
        logger.warning("reeval post-send EMPTY-BODIES inv=%s", inv["_id"])
        out["skipped"] = "empty_bodies"
        return out

    client = (inv.get("counterparty_email") or "").lower()
    conv_ids = [m["id"] for m in combined if m.get("id")]
    processed_ids = await _invoice_processed_message_ids(db, user_id, inv, conv_ids)
    if mid in processed_ids:
        has_event = await db.invoice_events.find_one({
            "user_id": user_id,
            "invoice_id": inv["_id"],
            "meta.message_id": mid,
        }, {"_id": 1})
        if not has_event:
            processed_ids = [x for x in processed_ids if x != mid]

    tracked = build_tracked_state(inv, processed_ids)
    prepared = build_reeval_input(
        my_email=my,
        client_email=client,
        messages=combined,
        tracked_state=tracked,
        anchor_ids=[inv.get("source_message_id")] if inv.get("source_message_id") else None,
    )
    result = await extract_reeval_with_rulebook(client, prepared)
    if not result:
        out["skipped"] = "ai_empty"
        logger.warning("reeval post-send AI-EMPTY inv=%s", inv["_id"])
        return out

    applied = await apply_rulebook_result(
        db, user_id, inv, result, combined,
        my_email=my, now_iso=now_iso, considered_ids=[mid],
    )
    await _mark_processed(db, user_id, [mid])
    out["applied"] = bool(applied.get("state_changes"))
    out["events"] = applied.get("events") or []
    out["status"] = applied.get("status")
    logger.info(
        "reeval post-send APPLY inv=%s status=%s events=%s",
        inv["_id"], out.get("status"), out["events"],
    )
    return out


# ---------------------------------------------------------------------------
# Processed-message registry — every ingested Gmail id is stored exactly once
# ---------------------------------------------------------------------------

async def _processed_ids(db, user_id, message_ids: list[str]) -> set[str]:
    if not message_ids:
        return set()
    out: set[str] = set()
    async for row in db.processed_messages.find({
        "user_id": user_id,
        "message_id": {"$in": message_ids},
    }):
        out.add(row.get("message_id"))
    return out


# ---------------------------------------------------------------------------
# Known-vs-new split (by Gmail message id / thread already in the ledger)
# ---------------------------------------------------------------------------

async def _split_known_new(
    db, user_id, messages: list[dict],
) -> tuple[list[dict], dict]:
    """Sent emails already tracked skip the AI gate; the rest are new candidates.

    Returns (new_msgs, triggered) where triggered maps a tracked invoice _id to
    the new (not-yet-processed) sent messages seen in its thread this window.
    """
    new_msgs: list[dict] = []
    triggered: dict[Any, list[dict]] = {}
    for msg in messages:
        inv = await db.invoices.find_one(
            {"user_id": user_id, "source_message_id": msg["id"]}, {"_id": 1},
        )
        if not inv and msg.get("thread_id"):
            inv = await db.invoices.find_one(
                {
                    "user_id": user_id,
                    "$or": [
                        {"source_thread_id": msg["thread_id"]},
                        {"conversation_thread_ids": msg["thread_id"]},
                    ],
                },
                {"_id": 1},
            )
        if inv:
            triggered.setdefault(inv["_id"], []).append(msg)
        else:
            new_msgs.append(msg)
    return new_msgs, triggered


# ---------------------------------------------------------------------------
# Re-evaluation of tracked invoices (rulebook_reeval)
# Windowed hourly job — not used at onboarding. First-pass is conversation_first_pass.
# ---------------------------------------------------------------------------

async def _fetch_new_client_mail(
    access: str,
    open_invoices: list[dict],
    my_email: str,
    window_start: datetime,
) -> list[dict]:
    """Windowed client mail with bodies (quotes + pay href), not meta_only."""
    addrs = sorted({
        (inv.get("counterparty_email") or "").lower()
        for inv in open_invoices if inv.get("counterparty_email")
    })
    doms = sorted({
        _sender_domain(a) for a in addrs
        if _sender_domain(a) and _sender_domain(a) not in CONSUMER_DOMAINS
    })
    window = f"after:{int(window_start.timestamp())}"

    queries: list[str] = []
    for i in range(0, len(addrs), CLIENT_QUERY_CHUNK):
        chunk = addrs[i:i + CLIENT_QUERY_CHUNK]
        queries.append(f"from:({' OR '.join(chunk)}) {window}")
    for i in range(0, len(doms), CLIENT_QUERY_CHUNK):
        chunk = doms[i:i + CLIENT_QUERY_CHUNK]
        queries.append(f"from:({' OR '.join(chunk)}) {window}")
    # Unmatched open invoices: still windowed, but search the invoice keys
    # so a quoted summary / pay href is in the pile (Intuit-From, no Sent copy).
    for inv in open_invoices:
        if inv.get("source_thread_id"):
            continue
        client = (inv.get("counterparty_email") or "").strip().lower()
        if not client or "@" not in client:
            continue
        token = pay_url_token(inv.get("pay_url"))
        ref = invoice_ref(inv)
        if token:
            queries.append(f"from:{client} {token} {window}")
        if ref:
            queries.append(f"from:{client} {ref} {window}")

    seen: set[str] = set()
    kept_raw: list[dict] = []
    for q in queries:
        try:
            for msg in await list_messages(access, q, max_pages=2, max_msgs=MAX_CLIENT_MSGS):
                mid = msg.get("id")
                if mid and mid not in seen:
                    seen.add(mid)
                    kept_raw.append(msg)
        except Exception as e:
            logger.warning("incremental client-mail LIST fail q=%r err=%s", q[:60], e)

    kept_raw = kept_raw[:MAX_CLIENT_MSGS]
    if not kept_raw:
        return []

    my = my_email.lower()
    kept: list[dict] = []
    for msg in kept_raw:
        if _extract_email_addr(msg.get("from", "")) == my:
            continue
        dt = parse_email_date(msg.get("date"))
        if dt and dt < window_start:
            continue
        kept.append(msg)
    return kept


async def _map_window_threads(
    db,
    open_invoices: list[dict],
    client_msgs: list[dict],
    *,
    my_email: str,
    now_iso: str,
) -> tuple[dict[str, dict], dict[Any, dict], dict[str, int]]:
    """Attach windowed client mail to invoices. In-thread first, then waterfall.

    A reply on source_thread_id or conversation_thread_ids is in-thread.
    A new thread uses InvoiceLink → DocNumber → amount → dates. No
    'only one open invoice' shortcut. Extra threads are appended, not
    swapped for the QBO-send thread.
    """
    stats = {"threads_appended": 0, "first_matched": 0, "unmapped": 0}
    by_thread: dict[str, dict] = {}
    for inv in open_invoices:
        for tid in _invoice_thread_ids(inv):
            by_thread[tid] = inv

    units: dict[Any, dict] = {}

    def _unit(inv: dict) -> dict:
        return units.setdefault(inv["_id"], {"inv": inv, "oot": []})

    unmapped: list[dict] = []
    for msg in client_msgs:
        tid = msg.get("thread_id")
        if tid and tid in by_thread:
            _unit(by_thread[tid])["oot"].append(msg)
            continue
        unmapped.append(msg)

    claimed = set(by_thread)
    for inv in open_invoices:
        if not _has_real_client_email(inv):
            continue
        pile = [m for m in unmapped if _msg_for_invoice_client(m, inv)]
        if not pile:
            continue
        known = set(_invoice_thread_ids(inv)) | claimed
        extra = extra_thread_ids(pile, inv, known=known)
        if not extra:
            continue
        hit_msgs = [m for m in pile if m.get("thread_id") in set(extra)]
        if inv.get("source_thread_id"):
            await _append_conversation_threads(db, inv, extra, now_iso)
        else:
            anchor = pick_anchor_message(hit_msgs, inv, my_email=my_email)
            primary = (anchor or {}).get("thread_id") or extra[0]
            ordered = [primary] + [t for t in extra if t != primary]
            await _attach_threads(db, inv, ordered, (anchor or {}).get("id"), now_iso)
            inv["source_thread_id"] = primary
            inv["conversation_thread_ids"] = ordered
            stats["first_matched"] += 1
        for tid in extra:
            claimed.add(tid)
            by_thread[tid] = inv
        _unit(inv)["oot"].extend(hit_msgs)
        stats["threads_appended"] += len(extra)

    mapped_ids = {m.get("id") for u in units.values() for m in u.get("oot") or []}
    for msg in unmapped:
        if msg.get("id") in mapped_ids:
            continue
        if msg.get("thread_id") in by_thread:
            continue
        stats["unmapped"] += 1
        logger.info(
            "incremental client-msg UNMAPPED id=%s from=%s",
            msg.get("id"), _extract_email_addr(msg.get("from", "")),
        )
    return by_thread, units, stats


async def _reevaluate_tracked(
    db,
    user_id,
    access: str,
    my_email: str,
    window_start: datetime,
    now_iso: str,
) -> dict[str, Any]:
    """Re-eval every open invoice with known threads, plus newly mapped ones.

    Known threads are listed in full (drawer path). Unseen messages — owner
    or client — go to the rulebook. No money/verb gate and no bury-on-skip.
    Windowed from:client is only for attaching new unmatched threads.
    """
    stats = {
        "client_messages": 0, "reevaluated": 0, "state_changes": 0,
        "skipped_no_activity": 0, "corrections": 0,
        "threads_appended": 0, "first_matched": 0,
    }

    open_invoices = []
    async for inv in db.invoices.find({
        "user_id": user_id,
        "status": {"$in": list(OPEN_INVOICE_STATUSES)},
    }):
        open_invoices.append(inv)
    if not open_invoices:
        return stats

    client_msgs = await _fetch_new_client_mail(access, open_invoices, my_email, window_start)
    fresh_ids = [m["id"] for m in client_msgs]
    already = await _processed_ids(db, user_id, fresh_ids)
    client_msgs = [m for m in client_msgs if m["id"] not in already]
    stats["client_messages"] = len(client_msgs)
    if REEVAL_DEBUG:
        logger.info(
            "reeval WINDOW start=%s new_client=%s already_processed=%s",
            window_start.isoformat(),
            [(m.get("id"), _extract_email_addr(m.get("from", "")), m.get("date"))
             for m in client_msgs],
            sorted(already),
        )

    _by_thread, units, map_stats = await _map_window_threads(
        db, open_invoices, client_msgs, my_email=my_email, now_iso=now_iso,
    )
    stats["threads_appended"] = map_stats["threads_appended"]
    stats["first_matched"] = map_stats["first_matched"]

    for inv in open_invoices:
        if _invoice_thread_ids(inv):
            units.setdefault(inv["_id"], {"inv": inv, "oot": []})

    if not units:
        return stats

    run_ai = bool(os.environ.get("OPENAI_API_KEY"))
    if not run_ai:
        stats["skipped_reeval"] = "no_openai_key"
        return stats

    sem = asyncio.Semaphore(SEED_AI_CONCURRENCY)
    processed: list[str] = []

    async def _one(unit: dict):
        inv = unit["inv"]
        async with sem:
            thread_msgs = await _fetch_invoice_thread_messages(access, inv)
            combined = _merge_client_messages([], thread_msgs, unit.get("oot") or [])
            if not any((m.get("body") or "").strip() for m in combined):
                logger.warning("reeval EMPTY-BODIES inv=%s", inv["_id"])
                return

            client = (inv.get("counterparty_email") or "").lower()
            conv_ids = [m["id"] for m in combined if m.get("id")]
            processed_ids = await _invoice_processed_message_ids(db, user_id, inv, conv_ids)
            new_msgs = [m for m in combined if m.get("id") and m["id"] not in processed_ids]
            if not new_msgs:
                stats["skipped_no_activity"] += 1
                if REEVAL_DEBUG:
                    logger.info("reeval SKIP inv=%s reason=no_unseen_messages", inv["_id"])
                return

            logger.info(
                "reeval TRIGGER inv=%s unseen=%s status=%s",
                inv["_id"], [m.get("id") for m in new_msgs], inv.get("status"),
            )
            tracked = build_tracked_state(inv, processed_ids)
            prepared = build_reeval_input(
                my_email=my_email,
                client_email=client,
                messages=combined,
                tracked_state=tracked,
                anchor_ids=[inv.get("source_message_id")] if inv.get("source_message_id") else None,
            )
            if REEVAL_DEBUG:
                logger.info(
                    "reeval AI-INPUT inv=%s tracked=%s msgs=%s",
                    inv["_id"],
                    {k: tracked[k] for k in (
                        "invoice_ref", "amount", "status", "promise_date",
                        "paid_amount", "disputed_claim_amount",
                    )},
                    [(m.get("id"), m.get("date")) for m in prepared.get("messages") or []],
                )
            result = await extract_reeval_with_rulebook(client, prepared)

        if not result:
            logger.warning(
                "reeval AI-EMPTY inv=%s thread=%s unseen=%s",
                inv["_id"], inv.get("source_thread_id"),
                [m.get("id") for m in new_msgs],
            )
            return

        considered: list[str] = [m["id"] for m in new_msgs if m.get("id")]
        prev_status = inv.get("status")
        applied = await apply_rulebook_result(
            db, user_id, inv, result, combined,
            my_email=my_email, now_iso=now_iso, considered_ids=considered,
        )
        processed.extend(considered)
        stats["reevaluated"] += 1
        if applied.get("state_changes"):
            stats["state_changes"] += 1
        stats["corrections"] += sum(1 for t in (applied.get("events") or []) if t == "correction")
        logger.info(
            "reeval APPLY inv=%s status=%s→%s events=%s",
            inv["_id"],
            prev_status,
            applied.get("status"),
            applied.get("events"),
        )

    await asyncio.gather(*[_one(u) for u in units.values()])
    await _mark_processed(db, user_id, processed)
    return stats


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def run_incremental_pipeline(db, user_id) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    counts: dict[str, Any] = {
        "mode": "incremental",
        "fetched": 0, "kept": 0, "dropped": 0,
        "candidates": 0, "invoices_created": 0, "new_invoices": [],
        "reevaluated": 0, "state_changes": 0, "skipped_no_activity": 0,
        "corrections": 0,
    }

    if not await _onboarding_allows_incremental(db, user_id):
        return {**counts, "skipped": "awaiting_onboarding"}
    mailboxes = await mailbox_tokens_for_user(db, user_id)
    if not mailboxes:
        return {**counts, "skipped": "no_connection"}

    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    if state.get("sync_running"):
        return {**counts, "skipped": "already_running"}
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"sync_running": True, "updated_at": now_iso}},
        upsert=True,
    )

    try:
        window_start = incremental_window_start(state.get("last_synced_at"))
        my_email = ""
        access = mailboxes[0][1]
        for conn, token in mailboxes:
            box_email = (conn.get("email") or "").lower()
            if box_email:
                my_email = box_email
                access = token
                break

        counts["fetched"] = 0
        counts["kept"] = 0
        counts["dropped"] = 0
        counts["candidates"] = 0
        counts["invoices_created"] = 0
        counts["new_invoices"] = []
        counts["live_detected"] = 0

        # Module 6: CDC poll backup (new/changed QBO invoices + paid) — webhooks are primary.
        try:
            from qbo_sync import sync_qbo_cdc
            counts["qbo_cdc"] = await sync_qbo_cdc(db, user_id)
        except Exception as e:
            logger.exception("incremental qbo CDC failed: %s", e)
            counts["qbo_cdc"] = {"errors": 1}
            # Still run paid + conversation if CDC blew up mid-way
            try:
                from qbo_paid_sync import sync_qbo_paid_status
                counts["qbo_paid"] = await sync_qbo_paid_status(db, user_id)
            except Exception as e2:
                logger.exception("incremental qbo paid sync failed: %s", e2)
                counts["qbo_paid"] = {"errors": 1}
            try:
                from qbo_conversation import enqueue_qbo_conversation_match
                counts["qbo_conversation"] = await enqueue_qbo_conversation_match(db, user_id)
            except Exception as e3:
                logger.exception("incremental qbo conversation enqueue failed: %s", e3)
                counts["qbo_conversation"] = {"errors": 1}
        else:
            # CDC path already runs paid + conversation; keep keys for callers
            cdc = counts.get("qbo_cdc") or {}
            if "qbo_paid" in cdc:
                counts["qbo_paid"] = cdc["qbo_paid"]
            if "conversation_match" in cdc:
                counts["qbo_conversation"] = cdc["conversation_match"]

        cdc = counts.get("qbo_cdc") or {}
        qbo_new = int(cdc.get("created") or 0)
        counts["invoices_created"] = qbo_new
        counts["live_detected"] = qbo_new

        # ---- Stage 4: known threads + windowed unmatched client mail --------
        reeval_stats = await _reevaluate_tracked(
            db, user_id, access, my_email, window_start, now_iso,
        )
        counts.update(reeval_stats)
        if not os.environ.get("OPENAI_API_KEY"):
            counts["skipped_reeval"] = counts.get("skipped_reeval") or "no_openai_key"

        await dedupe_existing_invoices(db, user_id, now_iso)

        # ---- Finish: sync state ---------------------------------------------
        await db.gmail_sync_state.update_one(
            {"user_id": user_id},
            {"$set": {
                "last_synced_at": now_iso,
                "last_detected_at": now_iso,
                "last_sync_status": "ok",
                "last_live_detection_count": qbo_new,
                "watching_sent_mail": True,
            }},
            upsert=True,
        )
        logger.info("incremental DONE user=%s counts=%s", user_id, {
            k: counts[k] for k in (
                "fetched", "kept", "candidates", "invoices_created",
                "reevaluated", "state_changes", "skipped_no_activity",
                "threads_appended", "first_matched",
            ) if k in counts
        })
        return counts
    finally:
        await db.gmail_sync_state.update_one(
            {"user_id": user_id},
            {"$set": {"sync_running": False,
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )


async def run_incremental_sync(db, user_id) -> dict[str, Any]:
    """One incremental pass — triggered by Sync now or the hourly background loop."""
    from scan_pipeline import reconcile_receipts

    result = await run_incremental_pipeline(db, user_id)
    if result.get("skipped"):
        return result
    result["past_due_flipped"] = await apply_past_due_transitions(db, user_id)
    result["promise_broken_flipped"] = await apply_promise_broken_transitions(db, user_id)
    try:
        recon = await reconcile_receipts(db, user_id)
        result["receipts_matched"] = recon.get("matched", 0)
    except Exception as e:
        logger.warning("incremental reconcile failed user=%s err=%s", user_id, e)
    result["events_deduped"] = await dedupe_stored_invoice_events(db, user_id)
    result["post_chase"] = await run_post_chase_tick(db, user_id)
    try:
        from escalation_scheduler import run_escalation_tick
        result["cadence"] = await run_escalation_tick(db, user_id)
    except Exception as e:
        logger.warning("cadence tick failed user=%s err=%s", user_id, e)
        result["cadence"] = {"error": str(e)[:200]}
    return result


async def sync_all_users(db) -> dict[str, Any]:
    """Hourly background job: incremental sync for every connected user post-onboarding."""
    totals: dict[str, Any] = {
        "users": 0,
        "invoices_created": 0,
        "state_changes": 0,
        "skipped": 0,
    }
    seen_users: set = set()
    async for conn in db.gmail_connections.find({"status": "connected"}):
        uid = conn.get("user_id")
        if not uid or uid in seen_users:
            continue
        seen_users.add(uid)
        try:
            result = await run_incremental_sync(db, uid)
            if result.get("skipped"):
                totals["skipped"] += 1
                continue
            totals["users"] += 1
            totals["invoices_created"] += result.get("invoices_created", 0)
            totals["state_changes"] += result.get("state_changes", 0)
        except Exception as e:
            logger.exception("incremental sync FAILED user=%s err=%s", uid, e)
    return totals
