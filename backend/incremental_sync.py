"""Hourly + manual incremental sync — per-invoice pipeline (windowed).

Mirrors the onboarding per-invoice flow, adjusted to the sync window:

  bulk sent-mail fetch (window) → cheap filter
    → registry check (processed_messages / ledger by Gmail message id)
    → known invoice? skip the AI gate : AI gate for genuinely new sends
  New invoice emails  → full thread + out-of-thread context → rulebook_seed_scan
                        Extract → ledger row streamed (instant UI).
  Tracked invoices    → re-evaluated when the window holds new client
                        activity (in-thread reply or out-of-thread mention),
                        or when the USER sends an amount-correction message in
                        the tracked thread; rulebook_reeval sees the whole
                        conversation + tracked_state and writes only new_events.
                        Plain follow-ups/chases with no correction language stay
                        skipped (skipped_no_activity).

Every ingested Gmail message id is recorded in `processed_messages` so no
message is gated/analyzed twice across overlapping windows.
"""
from __future__ import annotations

import asyncio
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
    _EVENT_APPLY_ORDER,
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
from reeval_rulebook import (
    build_reeval_input,
    build_tracked_state,
    extract_reeval_with_rulebook,
    normalize_reeval_status,
    rulebook_events_to_write_events,
)
from seed_ai import (
    SEED_AI_CONCURRENCY,
    _merge_client_messages,
    run_seed_ai_extraction,
)
from seed_scan import _ignored_ids, collapse_followups_incremental

logger = logging.getLogger("scotive.incremental_sync")

# Recent mail: slightly lower bar than onboarding curation (user already confirmed historical)
INCREMENTAL_CONFIDENCE_MIN = 0.5
CLIENT_QUERY_CHUNK = 15
MAX_CLIENT_MSGS = 60
# Verbose re-eval diagnostics (AI inputs/outputs, window decisions).
REEVAL_DEBUG = os.environ.get("SYNC_REEVAL_DEBUG", "").lower() in ("1", "true", "yes")

# Money language in the user's OWN words (quoted history stripped).
AMOUNT_LANGUAGE_RE = re.compile(
    r"(?:[$₹€£]\s*\d)"
    r"|(?:\d[\d,]*(?:\.\d{1,2})?\s*(?:[$₹€£]|(?:usd|inr|eur|rs\.?|dollars?|rupees?|bucks?)\b))"
    r"|(?:\b(?:usd|inr|eur|rs\.?)\s*\d)",
    re.I,
)
# Correction / acceptance intent — required with amount language so plain
# chases ("reminder: $600 still due") do not trigger a re-eval AI call.
# Includes soft dispute-acceptance ("Confirmed, $1,850 it is.", "Agreed — $950.").
CORRECTION_INTENT_RE = re.compile(
    r"(?i)\b(?:"
    r"revis(?:e|ing|ed)|correct(?:ing|ed|ion)?|"
    r"confirm(?:ed|ing)?|agreed?|you'?re right|"
    r"that'?s (?:right|correct|fine|it)|"
    r"actually|miscounted|my mistake|"
    r"let'?s make it|should (?:be|have been)|"
    r"update(?:d)?\s+(?:to|the\s+amount)|"
    r"chang(?:e|ing|ed)\s+(?:to|the\s+amount)|"
    r"new\s+(?:total|amount)|adjust(?:ing|ed)?|"
    r"make\s+it\s+[$₹€£]?\d|down\s+to\s+[$₹€£]?\d|"
    r"it is\b"
    r")\b"
)


def _msg_own_text(msg: dict) -> str:
    return f"{msg.get('subject') or ''}\n" + preprocess_body(
        msg.get("body") or msg.get("snippet") or "", 4000,
    )


def _is_amount_correction(msg: dict) -> bool:
    """True when the user's own words revise the invoice amount (not a chase)."""
    text = _msg_own_text(msg)
    return bool(AMOUNT_LANGUAGE_RE.search(text) and CORRECTION_INTENT_RE.search(text))


def _states_amount(msg: dict) -> bool:
    """True when the user's own words state a money amount (tests / diagnostics)."""
    return bool(AMOUNT_LANGUAGE_RE.search(_msg_own_text(msg)))


def _should_trigger_user_reeval(msg: dict, inv: dict) -> bool:
    """User send that should open Stage 4 without new client activity.

    Explicit correction/acceptance language always qualifies. While a dispute
    is open, any amount-stating user reply also qualifies — acceptance of the
    client's figure is often soft ("Confirmed, $1,850 it is.") and must not
    be buried as a chase.
    """
    if _is_amount_correction(msg):
        return True
    if (
        (inv.get("status") == "disputed" or inv.get("disputed_claim_amount") is not None)
        and _states_amount(msg)
    ):
        return True
    return False


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
    """Run the same Stage 4 path as Gmail dispute-accept / amount-correction.

    Used right after Scotive sends a chase/reply so ledger amount/status update
    without waiting for the next incremental sync. Plain chases (no correction
    / dispute-acceptance language) are skipped — identical gate to sync.
    """
    out: dict[str, Any] = {"triggered": False, "applied": False}
    if not inv or not inv.get("_id"):
        out["skipped"] = "no_invoice"
        return out
    if inv.get("status") not in OPEN_INVOICE_STATUSES:
        out["skipped"] = "not_open"
        return out
    if not os.environ.get("OPENROUTER_API_KEY"):
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
    if not _should_trigger_user_reeval(msg, inv):
        out["skipped"] = "not_correction"
        return out

    out["triggered"] = True
    logger.info(
        "reeval POST-SEND inv=%s msg=%s status=%s",
        inv["_id"], mid, inv.get("status"),
    )

    thread_msgs: list[dict] = []
    tid = inv.get("source_thread_id") or thread_id
    if tid:
        try:
            thread_msgs = await get_thread_messages(access, tid)
        except Exception as e:
            logger.warning("reeval post-send thread fetch fail inv=%s err=%s", inv["_id"], e)

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

    await _mark_reeval_seen(db, inv["_id"], [mid])
    await _mark_processed(db, user_id, [mid])

    events = rulebook_events_to_write_events(
        result,
        invoice_ref=inv.get("invoice_ref_normalized") or inv.get("invoice_ref"),
    )
    for e in events:
        if e.get("type") == "correction" and e.get("old_amount") is None:
            e["old_amount"] = float(inv.get("amount") or 0)

    if not events:
        await _apply_reeval_top_level(db, inv, result, now_iso)
        out["events"] = []
        return out

    events = sorted(
        events,
        key=lambda e: (_EVENT_APPLY_ORDER.get(e.get("type") or "", 99), e.get("message_id") or ""),
    )
    messages_by_id = {m["id"]: m for m in combined if m.get("id")}
    for ev in events:
        await _write_event(
            db, user_id, inv["_id"], ev, messages_by_id, now_iso,
            my_email=my,
        )
    inv_after = await db.invoices.find_one({"_id": inv["_id"]}) or inv
    await _apply_reeval_top_level(db, inv_after, result, now_iso)
    out["applied"] = True
    out["events"] = [e.get("type") for e in events]
    logger.info(
        "reeval post-send APPLY inv=%s events=%s",
        inv["_id"], out["events"],
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
# Re-evaluation of tracked invoices (rulebook_reeval)
# ---------------------------------------------------------------------------

async def _invoice_processed_message_ids(
    db, user_id, inv: dict, conversation_ids: list[str] | None = None,
) -> list[str]:
    """Message ids already applied to this invoice's timeline.

    ONLY source + invoice_events (+ reeval_seen). Do NOT merge the global
    `processed_messages` registry — that marks "seen for new-invoice gating"
    and would hide user amount-corrections that Stage 2 already registered
    before Stage 4 runs.
    """
    _ = conversation_ids  # reserved for callers; not merged into processed set
    seen: set[str] = set()
    src = inv.get("source_message_id")
    if src:
        seen.add(src)
    for mid in inv.get("reeval_seen_message_ids") or []:
        if mid:
            seen.add(mid)
    async for ev in db.invoice_events.find(
        {"user_id": user_id, "invoice_id": inv["_id"]},
        {"meta.message_id": 1},
    ):
        mid = (ev.get("meta") or {}).get("message_id")
        if mid:
            seen.add(mid)
    return sorted(seen)


async def _mark_reeval_seen(db, inv_id, message_ids: list[str]) -> None:
    """Remember messages considered in a reeval pass (even when new_events was empty)."""
    mids = [m for m in message_ids if m]
    if not mids:
        return
    await db.invoices.update_one(
        {"_id": inv_id},
        {"$addToSet": {"reeval_seen_message_ids": {"$each": mids}}},
    )


async def _apply_reeval_top_level(
    db, inv: dict, result: dict, now_iso: str,
) -> None:
    """Apply residual top-level fields the event writer may not cover."""
    patch: dict[str, Any] = {"last_activity_at": now_iso}
    changed = False

    new_due = result.get("due_date")
    if new_due and new_due != inv.get("due_date"):
        patch["due_date"] = new_due
        patch["due_date_assumed"] = (result.get("due_date_status") or "") == "missing"
        if result.get("due_date_status"):
            patch["due_date_status"] = result["due_date_status"]
        changed = True

    new_ref = result.get("invoice_ref")
    cur_ref = inv.get("invoice_ref_normalized") or inv.get("invoice_ref")
    if new_ref and str(new_ref).strip() and str(new_ref).strip().lower() != "null":
        from ledger_reconcile import is_plausible_invoice_ref, normalize_invoice_ref
        if str(new_ref).upper().replace(" ", "") != str(cur_ref or "").upper().replace(" ", ""):
            norm = normalize_invoice_ref(new_ref, inv.get("source_subject"))
            if norm and is_plausible_invoice_ref(norm):
                patch["invoice_ref"] = new_ref if is_plausible_invoice_ref(str(new_ref)) else norm
                patch["invoice_ref_normalized"] = norm
                changed = True

    # Post-process may clear a resolved dispute claim after correction.
    if (
        result.get("disputed_claim_amount") is None
        and inv.get("disputed_claim_amount") is not None
        and any(
            e.get("type") == "amount_correction"
            for e in (result.get("new_events") or [])
        )
    ):
        patch["disputed_claim_amount"] = None
        changed = True

    if changed:
        patch["status_updated_at"] = now_iso
        await db.invoices.update_one({"_id": inv["_id"]}, {"$set": patch})


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
    # below reveals new client activity, or the user's own message may carry an
    # amount correction worth re-evaluating (any open status — not only disputed).
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
            correction_trigger = None
            if not new_client:
                # No new client activity — re-evaluate when the user sent an
                # amount-correction / dispute-acceptance message. Plain chases skip.
                correction_trigger = next(
                    (m for m in (unit.get("user_msgs") or [])
                     if _extract_email_addr(m.get("from", "")) == my_email.lower()
                     and _should_trigger_user_reeval(m, inv)),
                    None,
                )
                if not correction_trigger:
                    stats["skipped_no_activity"] += 1
                    # Only bury chase/follow-ups with no money language. Amount-
                    # bearing user msgs that failed the intent gate stay eligible
                    # so a later sync (or gate fix) can still re-eval them.
                    chase_ids = [
                        m["id"] for m in (unit.get("user_msgs") or [])
                        if m.get("id") and not _states_amount(m)
                    ]
                    processed.extend(chase_ids)
                    await _mark_reeval_seen(db, inv["_id"], chase_ids)
                    if REEVAL_DEBUG:
                        logger.info(
                            "reeval SKIP inv=%s reason=no_activity user_msgs=%s",
                            inv["_id"],
                            [m.get("id") for m in (unit.get("user_msgs") or [])],
                        )
                    return
                logger.info(
                    "reeval TRIGGER inv=%s reason=user_amount_correction msg=%s status=%s",
                    inv["_id"], correction_trigger.get("id"), inv.get("status"),
                )

            client = (inv.get("counterparty_email") or "").lower()
            conv_ids = [m["id"] for m in combined if m.get("id")]
            processed_ids = await _invoice_processed_message_ids(db, user_id, inv, conv_ids)
            # Unbury a correction trigger that was previously marked reeval_seen
            # without ever writing an invoice_event (false-negative intent gate).
            if correction_trigger and correction_trigger.get("id"):
                tid = correction_trigger["id"]
                if tid in processed_ids:
                    has_event = await db.invoice_events.find_one({
                        "user_id": user_id,
                        "invoice_id": inv["_id"],
                        "meta.message_id": tid,
                    }, {"_id": 1})
                    if not has_event:
                        processed_ids = [x for x in processed_ids if x != tid]
                        logger.info(
                            "reeval UNBURY inv=%s msg=%s reason=seen_without_event",
                            inv["_id"], tid,
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
                    [(m.get("id"), m.get("date")) for m in combined],
                )
            result = await extract_reeval_with_rulebook(client, prepared)

        if not result:
            logger.warning(
                "reeval AI-EMPTY inv=%s thread=%s new_client=%s",
                inv["_id"], inv.get("source_thread_id"),
                [m.get("id") for m in new_client],
            )
            return

        stats["reevaluated"] += 1
        # Messages considered this pass (client activity + correction trigger +
        # any event message_ids). Mark as applied to THIS invoice so the next
        # sync does not re-emit; also mark globally so Stage 2 skips them.
        considered: list[str] = [m["id"] for m in new_client if m.get("id")]
        if correction_trigger and correction_trigger.get("id"):
            considered.append(correction_trigger["id"])
        for ev in result.get("new_events") or []:
            if ev.get("message_id"):
                considered.append(ev["message_id"])
        # Unprocessed user msgs from triggered that we inspected this pass
        for m in unit.get("user_msgs") or []:
            if m.get("id"):
                considered.append(m["id"])
        processed.extend(considered)
        await _mark_reeval_seen(db, inv["_id"], considered)

        events = rulebook_events_to_write_events(
            result,
            invoice_ref=inv.get("invoice_ref_normalized") or inv.get("invoice_ref"),
        )
        for e in events:
            if e.get("type") == "correction" and e.get("old_amount") is None:
                e["old_amount"] = float(inv.get("amount") or 0)
        if not events:
            logger.info(
                "reeval NO-DIFF inv=%s status=%s→%s amount=%s→%s promise=%s→%s events_raw=%s",
                inv["_id"], inv.get("status"),
                normalize_reeval_status(result.get("status")),
                inv.get("amount"), result.get("amount"),
                inv.get("promise_date"), result.get("promise_date"),
                len(result.get("new_events") or []),
            )
            await _apply_reeval_top_level(db, inv, result, now_iso)
            return

        events = sorted(
            events,
            key=lambda e: (_EVENT_APPLY_ORDER.get(e.get("type") or "", 99), e.get("message_id") or ""),
        )
        messages_by_id = {m["id"]: m for m in combined}
        for ev in events:
            await _write_event(
                db, user_id, inv["_id"], ev, messages_by_id, now_iso,
                my_email=my_email,
            )
        # Reload for top-level patch after events mutated the row
        inv_after = await db.invoices.find_one({"_id": inv["_id"]}) or inv
        await _apply_reeval_top_level(db, inv_after, result, now_iso)
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
        # Tracked-thread sends (triggered) must NOT be marked processed before
        # Stage 4 — otherwise amount-corrections land in processed_message_ids
        # and the reeval rulebook emits nothing for them.
        processed_now: list[str] = []
        if new_msgs:
            _, ai_stats = await run_seed_ai_extraction(
                access, new_msgs, my_email,
                user_id=user_id, job_id=user_id, now_iso=now_iso,
                confidence_min=INCREMENTAL_CONFIDENCE_MIN,
                on_unit=_write_unit,
                use_seed_rulebook=True,
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

        # ---- Stage 4: re-evaluate tracked invoices with new client activity -
        reeval_stats = await _reevaluate_tracked(
            db, user_id, access, my_email, window_start,
            triggered, now_iso,
        )
        counts.update(reeval_stats)
        # Stage 4 marks triggered/correction message ids via its own processed list

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
