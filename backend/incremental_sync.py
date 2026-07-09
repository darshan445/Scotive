"""Hourly + manual incremental sync — per-invoice pipeline (windowed).

Mirrors the onboarding per-invoice flow, adjusted to the sync window:

  bulk sent-mail fetch (window) → cheap filter
    → registry check (processed_messages / ledger by Gmail message id)
    → known invoice? skip the AI gate : AI gate for genuinely new sends
  New invoice emails  → full thread + out-of-thread context → one AI decision
                        per conversation → ledger row streamed (instant UI).
  Tracked invoices    → re-evaluated when the window holds new client
                        activity (in-thread reply or out-of-thread mention),
                        or when the USER sends an amount-bearing message in
                        the thread of a DISPUTED invoice (accepting/correcting
                        the amount resolves the dispute); the AI sees the whole
                        conversation + current tracked state, and the result is
                        written only when it changes the stored state
                        (surfaces in "Needs you today").

Every ingested Gmail message id is recorded in `processed_messages` so no
message is gated/analyzed twice across overlapping windows.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from gmail_client import (
    GmailAuthError,
    get_access_token,
    get_messages_batch,
    get_thread_messages,
    list_message_ids,
)
from client_sweep import (
    CONSUMER_DOMAINS,
    _extract_email_addr,
    _sender_domain,
    _write_event,
    load_blocklist,
    preprocess_body,
)
from gmail_sync import (
    _candidates_to_ledger,
    _onboarding_allows_incremental,
    fetch_filtered_sent_mail,
    incremental_window_start,
    run_gmail_sync,
)
from invoice_event_idempotency import dedupe_stored_invoice_events
from invoice_lifecycle import apply_past_due_transitions, apply_promise_broken_transitions
from ledger_reconcile import (
    OPEN_INVOICE_STATUSES,
    dedupe_existing_invoices,
    parse_email_date,
)
from post_chase import run_post_chase_tick
from post_track_enrichment import _out_of_thread_relevance
from prior_chase import enrich_candidates_with_prior_chases
from seed_ai import (
    SEED_AI_CONCURRENCY,
    SEED_INVOICE_PROMPT,
    _merge_client_messages,
    _normalize_enriched_status,
    extract_client_invoices_with_ai,
    run_seed_ai_extraction,
)
from seed_scan import _ignored_ids, collapse_followups_incremental

logger = logging.getLogger("scotive.incremental_sync")

# Recent mail: slightly lower bar than onboarding curation (user already confirmed historical)
INCREMENTAL_CONFIDENCE_MIN = 0.5
# Re-evaluating an already-tracked invoice changes stored state — higher bar.
REEVAL_CONFIDENCE_MIN = 0.65
CLIENT_QUERY_CHUNK = 15
MAX_CLIENT_MSGS = 60
# Verbose re-eval diagnostics (AI inputs/outputs, window decisions).
REEVAL_DEBUG = os.environ.get("SYNC_REEVAL_DEBUG", "").lower() in ("1", "true", "yes")

# Money language in the user's OWN words (quoted history stripped) — gates the
# dispute-correction re-eval so plain follow-ups stay skipped.
AMOUNT_LANGUAGE_RE = re.compile(
    r"(?:[$₹€£]\s*\d)"
    r"|(?:\d[\d,]*(?:\.\d{1,2})?\s*(?:[$₹€£]|(?:usd|inr|eur|rs\.?|dollars?|rupees?|bucks?)\b))"
    r"|(?:\b(?:usd|inr|eur|rs\.?)\s*\d)",
    re.I,
)


def _states_amount(msg: dict) -> bool:
    text = f"{msg.get('subject') or ''}\n" + preprocess_body(
        msg.get("body") or msg.get("snippet") or "", 4000,
    )
    return bool(AMOUNT_LANGUAGE_RE.search(text))


def _find_amount_message(
    combined: list[dict], my_email: str, amount: float,
) -> Optional[dict]:
    """Newest user-sent message whose own text states `amount` (correction anchor)."""
    pat = re.compile(rf"(?<![\d.]){re.escape(f'{amount:g}')}(?:\.0{{1,2}})?(?!\d)")
    best, best_dt = None, None
    for m in combined:
        if _extract_email_addr(m.get("from", "")) != my_email.lower():
            continue
        text = preprocess_body(m.get("body") or m.get("snippet") or "", 4000)
        if not pat.search(text.replace(",", "")):
            continue
        dt = parse_email_date(m.get("date"))
        if best is None or (dt and best_dt and dt > best_dt) or (dt and not best_dt):
            best, best_dt = m, dt
    return best


def _amount_sentence(msg: dict, amount: float) -> Optional[str]:
    """The user's own line stating the corrected amount — audit quote."""
    text = preprocess_body(msg.get("body") or msg.get("snippet") or "", 4000)
    for line in text.splitlines():
        if f"{amount:g}" in line.replace(",", ""):
            return line.strip()[:200]
    return None


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


async def _mark_processed(db, user_id, message_ids) -> None:
    now = datetime.now(timezone.utc)
    for mid in message_ids:
        if not mid:
            continue
        await db.processed_messages.update_one(
            {"user_id": user_id, "message_id": mid},
            {"$setOnInsert": {"user_id": user_id, "message_id": mid, "at": now}},
            upsert=True,
        )


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
                {"user_id": user_id, "source_thread_id": msg["thread_id"]}, {"_id": 1},
            )
        if inv:
            triggered.setdefault(inv["_id"], []).append(msg)
        else:
            new_msgs.append(msg)
    return new_msgs, triggered


# ---------------------------------------------------------------------------
# Re-evaluation of tracked invoices (only on new client activity)
# ---------------------------------------------------------------------------

def _pick_reeval_row(result: dict, inv: dict) -> Optional[dict]:
    """Match the AI's invoice row to the tracked invoice (by ref, else single row)."""
    rows = result.get("invoices") or []
    if not rows:
        return None
    ref = (inv.get("invoice_ref_normalized") or "").upper()
    if ref:
        for row in rows:
            row_ref = str(row.get("invoice_number") or "").upper().replace(" ", "")
            if row_ref and (row_ref == ref or row_ref.lstrip("#") == ref):
                return row
    if len(rows) == 1:
        return rows[0]
    return None


def _events_from_reeval(
    inv: dict, row: dict, correction_msg: Optional[dict] = None,
) -> list[dict]:
    """Diff the AI's fresh assessment against the stored invoice → timeline events.

    Only differences become events, so an unchanged conversation writes nothing.
    _write_event then enforces sender direction + idempotency + status semantics.
    """
    evs: list[dict] = []
    conf = float(row.get("confidence") or 0)
    quote = (row.get("status_evidence") or "").strip()
    base = {"invoice_ref": inv.get("invoice_ref_normalized"), "confidence": conf}
    st = _normalize_enriched_status(row.get("enriched_status"))
    cur = inv.get("status")

    # Open dispute + a different agreed total → amount correction on the SAME
    # row (applied first, so a promise in the same exchange lands on the
    # corrected amount). CORE RULE: only an explicit USER action moves the
    # amount, so the event requires a user-sent message stating the figure
    # (correction_msg) — a client claim alone never rewrites the amount.
    # _write_event routes this through apply_invoice_correction: amount +
    # balance update, dispute resolved back to invoiced/overdue. old_amount
    # kept for the timeline audit trail.
    new_amt = row.get("amount")
    old_amt = float(inv.get("amount") or 0)
    corrected = (
        cur == "disputed"
        and new_amt is not None
        and correction_msg is not None
        and abs(float(new_amt) - old_amt) > 0.005
    )
    if corrected:
        if st == "disputed":
            # The AI is restating the dispute the correction just resolved.
            # Document it BEFORE the correction (timeline reads dispute →
            # resolved; idempotent when a dispute event already exists) so the
            # stale verdict can never flip the status back to disputed after
            # the correction lands.
            evs.append({**base, "type": "dispute", "quote": quote,
                        "dispute_kind": row.get("dispute_kind"),
                        "claimed_amount": row.get("disputed_claim_amount")})
        evs.append({
            **base,
            "type": "correction",
            "amount": float(new_amt),
            "old_amount": old_amt,
            "date": row.get("due_date"),
            "message_id": correction_msg.get("id"),
            "quote": _amount_sentence(correction_msg, float(new_amt))
            or quote or "corrected amount agreed in conversation",
        })
        cur = "invoiced"  # status the correction leaves behind; diff below sees it

    if st == "promised":
        pd = row.get("promise_date")
        if cur != "promised" or (pd and pd != inv.get("promise_date")):
            evs.append({**base, "type": "promise", "date": pd, "quote": quote})
    elif st == "disputed" and cur != "disputed" and not corrected:
        # Status only — the client's claimed figure is kept for reference,
        # never written to amount (that takes a user correction).
        evs.append({**base, "type": "dispute", "quote": quote,
                    "dispute_kind": row.get("dispute_kind"),
                    "claimed_amount": row.get("disputed_claim_amount")})
    elif st == "paid_unconfirmed" and cur not in ("paid_unconfirmed", "paid"):
        evs.append({**base, "type": "payment_claimed", "quote": quote})
    elif st == "partially_paid":
        new_paid = row.get("paid_amount")
        if new_paid is None and row.get("balance_remaining") is not None:
            new_paid = float(inv.get("amount") or 0) - float(row["balance_remaining"])
        old_paid = float(inv.get("paid_amount") or 0)
        if new_paid is not None and float(new_paid) > old_paid + 0.005:
            evs.append({**base, "type": "partial_payment",
                        "amount": round(float(new_paid) - old_paid, 2), "quote": quote})

    if row.get("needs_reply") and not inv.get("needs_reply"):
        evs.append({**base, "type": "question",
                    "quote": (row.get("needs_reply_quote") or quote)})
    if row.get("client_approved") and not inv.get("client_approved"):
        evs.append({**base, "type": "approved",
                    "quote": (row.get("approval_quote") or quote)})

    # Due dates: only fill a MISSING one — never clobber a user-curated date.
    new_due = row.get("due_date")
    if new_due and not inv.get("due_date"):
        evs.append({**base, "type": "due_date_adjusted", "date": new_due,
                    "quote": quote or "due date stated in conversation"})
    return evs


async def _fetch_new_client_mail(
    access: str,
    open_invoices: list[dict],
    my_email: str,
    window_start: datetime,
) -> list[dict]:
    """Bulk fetch: client mail in the window for every open-invoice counterparty."""
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

    seen: set[str] = set()
    ids: list[str] = []
    for q in queries:
        try:
            for mid in await list_message_ids(access, q, max_pages=2):
                if mid not in seen:
                    seen.add(mid)
                    ids.append(mid)
        except Exception as e:
            logger.warning("incremental client-mail LIST fail q=%r err=%s", q[:60], e)

    ids = ids[:MAX_CLIENT_MSGS]
    if not ids:
        return []
    try:
        batch = await get_messages_batch(access, ids)
    except Exception as e:
        logger.warning("incremental client-mail BATCH fail err=%s", e)
        return []

    my = my_email.lower()
    kept: list[dict] = []
    for msg in batch:
        if _extract_email_addr(msg.get("from", "")) == my:
            continue
        dt = parse_email_date(msg.get("date"))
        if dt and dt < window_start:
            continue
        kept.append(msg)
    return kept


def _is_new_client_msg(msg: dict, my_email: str, window_start: datetime) -> bool:
    if _extract_email_addr(msg.get("from", "")) == my_email.lower():
        return False
    dt = parse_email_date(msg.get("date"))
    return bool(dt and dt >= window_start)


async def _reevaluate_tracked(
    db,
    user_id,
    access: str,
    my_email: str,
    window_start: datetime,
    triggered: dict,
    now_iso: str,
) -> dict[str, Any]:
    """Per-invoice re-evaluation for tracked invoices with new activity in the window."""
    stats = {"client_messages": 0, "reevaluated": 0, "state_changes": 0,
             "skipped_no_activity": 0, "corrections": 0}

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

    # Map each new client message to the tracked invoice(s) it belongs to:
    # thread match → out-of-thread ref/amount mention → single-open-invoice shortcut.
    by_thread = {inv.get("source_thread_id"): inv for inv in open_invoices if inv.get("source_thread_id")}
    by_client: dict[str, list[dict]] = {}
    for inv in open_invoices:
        key = inv.get("client_identity_key") or (inv.get("counterparty_email") or "").lower()
        by_client.setdefault(key, []).append(inv)

    units: dict[Any, dict] = {}

    def _unit(inv: dict) -> dict:
        return units.setdefault(inv["_id"], {"inv": inv, "oot": []})

    for msg in client_msgs:
        tid = msg.get("thread_id")
        if tid and tid in by_thread:
            _unit(by_thread[tid])  # thread fetch brings the reply itself
            continue
        sender = _extract_email_addr(msg.get("from", ""))
        dom = _sender_domain(sender)
        matched = False
        for key, invs in by_client.items():
            if sender not in key and (not dom or dom not in key):
                continue
            with_ref = [inv for inv in invs if _out_of_thread_relevance(msg, [inv])]
            targets = with_ref or (invs if len(invs) == 1 else [])
            for inv in targets:
                _unit(inv)["oot"].append(msg)
                matched = True
        if not matched:
            logger.info("incremental client-msg UNMAPPED id=%s from=%s", msg.get("id"), sender)

    # User sends in tracked threads also open a unit — either the thread fetch
    # below reveals new client activity, or (disputed invoices only) the user's
    # own message may carry an amount correction worth re-evaluating.
    open_by_id = {inv["_id"]: inv for inv in open_invoices}
    for inv_id, known_msgs in triggered.items():
        inv = open_by_id.get(inv_id)
        if inv:
            _unit(inv)["user_msgs"] = known_msgs

    if not units:
        return stats

    sem = asyncio.Semaphore(SEED_AI_CONCURRENCY)
    processed: list[str] = []

    async def _one(unit: dict):
        inv = unit["inv"]
        async with sem:
            thread_msgs: list[dict] = []
            if inv.get("source_thread_id"):
                try:
                    thread_msgs = await get_thread_messages(access, inv["source_thread_id"])
                except Exception as e:
                    logger.warning("incremental thread fetch fail inv=%s err=%s", inv["_id"], e)

            combined = _merge_client_messages([], thread_msgs, unit["oot"])
            new_client = [
                m for m in combined
                if _is_new_client_msg(m, my_email, window_start)
                and m["id"] not in already
            ]
            if not new_client:
                # No new client activity — re-evaluate anyway when the user
                # sent an amount-bearing message on a DISPUTED invoice (the
                # correction resolves the dispute). Plain follow-ups still skip.
                correction_trigger = None
                if inv.get("status") == "disputed":
                    correction_trigger = next(
                        (m for m in (unit.get("user_msgs") or [])
                         if _extract_email_addr(m.get("from", "")) == my_email.lower()
                         and _states_amount(m)),
                        None,
                    )
                if not correction_trigger:
                    stats["skipped_no_activity"] += 1
                    if REEVAL_DEBUG:
                        logger.info(
                            "reeval SKIP inv=%s reason=no_activity user_msgs=%s",
                            inv["_id"],
                            [m.get("id") for m in (unit.get("user_msgs") or [])],
                        )
                    return
                logger.info(
                    "reeval TRIGGER inv=%s reason=user_amount_correction_on_dispute msg=%s",
                    inv["_id"], correction_trigger.get("id"),
                )

            context = (
                "CURRENT_TRACKED_STATE: "
                f"ref={inv.get('invoice_ref_normalized') or 'n/a'} "
                f"amount={inv.get('amount')} {inv.get('currency') or 'USD'} "
                f"status={inv.get('status')} "
                f"due={inv.get('due_date') or 'n/a'} "
                f"promise={inv.get('promise_date') or 'n/a'} "
                f"paid={inv.get('paid_amount') or 0}"
            )
            if REEVAL_DEBUG:
                logger.info(
                    "reeval AI-INPUT inv=%s context=%r msgs=%s",
                    inv["_id"], context,
                    [(m.get("id"), m.get("date")) for m in combined],
                )
            result = await extract_client_invoices_with_ai(
                (inv.get("counterparty_email") or "").lower(),
                combined,
                my_email,
                anchor_ids=[inv.get("source_message_id")],
                system_prompt=SEED_INVOICE_PROMPT,
                context_note=context,
            )
        if not result:
            logger.warning(
                "reeval AI-EMPTY inv=%s thread=%s new_client=%s",
                inv["_id"], inv.get("source_thread_id"),
                [m.get("id") for m in new_client],
            )
            return
        if REEVAL_DEBUG:
            logger.info(
                "reeval AI-RESULT inv=%s raw=%s",
                inv["_id"], json.dumps(result, default=str)[:4000],
            )
        stats["reevaluated"] += 1
        processed.extend(m["id"] for m in new_client)

        row = _pick_reeval_row(result, inv)
        if not row:
            logger.info(
                "reeval DROP inv=%s reason=row_match rows=%s refs=%r stored_ref=%r",
                inv["_id"], len(result.get("invoices") or []),
                [r.get("invoice_number") for r in (result.get("invoices") or [])],
                inv.get("invoice_ref_normalized"),
            )
            return
        conf = float(row.get("confidence") or 0)
        if conf < REEVAL_CONFIDENCE_MIN:
            logger.info(
                "reeval DROP inv=%s reason=low_confidence conf=%.2f status=%r amount=%r",
                inv["_id"], conf, row.get("enriched_status"), row.get("amount"),
            )
            return
        correction_msg = None
        if inv.get("status") == "disputed" and row.get("amount") is not None:
            correction_msg = _find_amount_message(combined, my_email, float(row["amount"]))
        events = _events_from_reeval(inv, row, correction_msg=correction_msg)
        if not events:
            logger.info(
                "reeval NO-DIFF inv=%s status=%s→%s amount=%s→%s promise=%s→%s",
                inv["_id"], inv.get("status"),
                _normalize_enriched_status(row.get("enriched_status")),
                inv.get("amount"), row.get("amount"),
                inv.get("promise_date"), row.get("promise_date"),
            )
            return
        messages_by_id = {m["id"]: m for m in combined}
        for ev in events:
            await _write_event(
                db, user_id, inv["_id"], ev, messages_by_id, now_iso,
                my_email=my_email,
            )
        stats["state_changes"] += 1
        stats["corrections"] += sum(1 for e in events if e.get("type") == "correction")
        logger.info(
            "reeval APPLY inv=%s events=%s",
            inv["_id"], [e.get("type") for e in events],
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
    conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        return {**counts, "skipped": "no_connection"}
    if not os.environ.get("OPENROUTER_API_KEY"):
        # No AI available — legacy bulk path still writes regex-extracted rows.
        return await run_gmail_sync(db, user_id, "incremental",
                                    confidence_min=INCREMENTAL_CONFIDENCE_MIN)

    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    if state.get("sync_running"):
        return {**counts, "skipped": "already_running"}
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"sync_running": True, "updated_at": now_iso}},
        upsert=True,
    )

    try:
        try:
            access = await get_access_token(db, user_id)
        except GmailAuthError as e:
            return {**counts, "skipped": "auth_error", "error": str(e)}

        my_email = (conn.get("email") or "").lower()
        ignored = await _ignored_ids(db, user_id)
        blocklist = await load_blocklist(db, user_id)
        window_start = incremental_window_start(state.get("last_synced_at"))
        window = f"after:{int(window_start.timestamp())}"

        # ---- Stage 1: bulk sent-mail fetch (window) + cheap filter ----------
        messages, filter_stats = await fetch_filtered_sent_mail(
            access, my_email, blocklist, ignored, "incremental", window,
        )
        counts.update(filter_stats)

        # ---- Stage 2: registry + known-vs-new split -------------------------
        already = await _processed_ids(db, user_id, [m["id"] for m in messages])
        fresh = [m for m in messages if m["id"] not in already]
        new_msgs, triggered = await _split_known_new(db, user_id, fresh)

        # ---- Stage 3: new invoices — gate + per-conversation AI, streamed ---
        collapse_index: dict = {}
        new_invoices: list[dict] = []
        due_prompts: list[dict] = []
        stream = {"candidates": 0, "created": 0}

        async def _write_unit(rows: list[dict]) -> None:
            enrich_candidates_with_prior_chases(rows, messages, my_email)
            rows = collapse_followups_incremental(collapse_index, rows)
            if not rows:
                return
            stream["candidates"] += len(rows)
            created, unit_new, unit_prompts = await _candidates_to_ledger(
                db, user_id, rows, now_iso,
            )
            stream["created"] += created
            new_invoices.extend(unit_new)
            due_prompts.extend(unit_prompts)

        new_ids = {m["id"] for m in new_msgs}
        processed_now = [m["id"] for m in fresh if m["id"] not in new_ids]
        if new_msgs:
            _, ai_stats = await run_seed_ai_extraction(
                access, new_msgs, my_email,
                user_id=user_id, job_id=user_id, now_iso=now_iso,
                confidence_min=INCREMENTAL_CONFIDENCE_MIN,
                on_unit=_write_unit,
            )
            counts.update(ai_stats)
            # A transient AI failure must not permanently swallow an invoice —
            # leave new sends unmarked so the next run retries them.
            if not ai_stats.get("ai_fail"):
                processed_now.extend(new_ids)
        await _mark_processed(db, user_id, processed_now)

        counts["candidates"] = stream["candidates"]
        counts["invoices_created"] = stream["created"]
        counts["new_invoices"] = new_invoices
        counts["live_detected"] = stream["created"]

        # ---- Stage 4: re-evaluate tracked invoices with new client activity -
        reeval_stats = await _reevaluate_tracked(
            db, user_id, access, my_email, window_start,
            triggered, now_iso,
        )
        counts.update(reeval_stats)

        await dedupe_existing_invoices(db, user_id, now_iso)

        # ---- Finish: detections + sync state --------------------------------
        existing_unread = list(state.get("unread_detections") or [])
        seen_msg = {d.get("source_message_id") for d in existing_unread}
        for det in new_invoices:
            if det.get("source_message_id") not in seen_msg:
                existing_unread.append(det)
                seen_msg.add(det["source_message_id"])

        existing_prompts = list(state.get("pending_due_date_prompts") or [])
        seen_inv = {p.get("invoice_id") for p in existing_prompts}
        for p in due_prompts:
            if p.get("invoice_id") not in seen_inv:
                existing_prompts.append(p)
                seen_inv.add(p.get("invoice_id"))

        await db.gmail_sync_state.update_one(
            {"user_id": user_id},
            {"$set": {
                "last_synced_at": now_iso,
                "last_detected_at": now_iso,
                "last_sync_status": "ok",
                "last_live_detection_count": stream["created"],
                "unread_detections": existing_unread,
                "pending_due_date_prompts": existing_prompts,
                "watching_sent_mail": True,
            }},
            upsert=True,
        )
        logger.info("incremental DONE user=%s counts=%s", user_id, {
            k: counts[k] for k in (
                "fetched", "kept", "candidates", "invoices_created",
                "reevaluated", "state_changes", "skipped_no_activity",
            )
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
    return result


async def sync_all_users(db) -> dict[str, Any]:
    """Hourly background job: incremental sync for every connected user post-onboarding."""
    totals: dict[str, Any] = {
        "users": 0,
        "invoices_created": 0,
        "state_changes": 0,
        "skipped": 0,
    }
    async for conn in db.gmail_connections.find({"status": "connected"}):
        uid = conn.get("user_id")
        if not uid:
            continue
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
