"""Unified Gmail sync — one job for onboarding (90d) and incremental (1h).

Used by:
- POST /seed/start (onboarding, 90 days → curation candidates)
- POST /scan/sync (manual, last hour → ledger)
- Background loop every SYNC_INTERVAL_SECONDS (default 1h, last hour → ledger)
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from gmail_client import GmailAuthError, get_access_token, get_messages_batch, list_message_ids
from client_sweep import (
    CONSUMER_DOMAINS,
    _sender_domain,
    anchor_recipients,
    load_blocklist,
    merge_candidates_by_domain,
    persist_client_state,
)
from ledger_reconcile import (
    client_identity_key,
    dedupe_existing_invoices,
    normalize_invoice_ref,
    normalize_source_date,
    normalize_subject,
    parse_email_date,
    upsert_sweep_invoice,
)
from prior_chase import enrich_candidates_with_prior_chases
from seed_ai import run_seed_ai_extraction
from seed_scan import (
    SEED_DAYS,
    _client_display_name,
    _ignored_ids,
    _parse_msg_date,
    build_ledger_invoice_from_candidate,
    collapse_followups_incremental,
    extract_amount_currency,
    extract_due_date,
)
from sent_mail_filter import seed_cheap_filter

logger = logging.getLogger("scotive.gmail_sync")

SyncMode = Literal["onboarding", "incremental"]

INCREMENTAL_LOOKBACK = os.environ.get("SYNC_LOOKBACK", "1h")
MAX_LIST_PAGES_ONBOARDING = 8
MAX_LIST_PAGES_INCREMENTAL = 2


_LOOKBACK_UNIT_SECONDS = {"h": 3600, "d": 86400, "w": 604800, "m": 2592000, "y": 31536000}


def _lookback_seconds(raw: str) -> int:
    m = re.fullmatch(r"(\d+)\s*([hdwmy]?)", (raw or "").strip().lower())
    if not m:
        return 3600
    return int(m.group(1)) * _LOOKBACK_UNIT_SECONDS[m.group(2) or "h"]


def incremental_window_start(last_synced_at: str | None) -> datetime:
    """Start of the incremental window, anchored on the last successful sync
    (15 min overlap; 24h first run; capped at 7 days)."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=_lookback_seconds(INCREMENTAL_LOOKBACK))
    last = parse_email_date(last_synced_at) if last_synced_at else None
    if last:
        start = min(start, last - timedelta(minutes=15))
    else:
        start = min(start, now - timedelta(hours=24))
    return max(start, now - timedelta(days=7))


def sync_window_clause(mode: SyncMode, *, last_synced_at: str | None = None) -> str:
    if mode == "onboarding":
        return f"newer_than:{SEED_DAYS}d"
    # Gmail's newer_than: only accepts d/m/y units — "newer_than:1h" is invalid and
    # silently matches nothing. Use after:<epoch>.
    return f"after:{int(incremental_window_start(last_synced_at).timestamp())}"


def sent_mail_queries(mode: SyncMode, window: str | None = None) -> list[str]:
    w = window or sync_window_clause(mode)
    return [
        f"in:sent {w} has:attachment (invoice OR payment OR bill OR \"amount due\")",
        f'in:sent {w} subject:(invoice OR payment OR "amount due" OR outstanding OR "balance due")',
        (
            f'in:sent {w} ("please pay" OR "payment due" OR "net 30" OR "net 15" OR '
            f'"net 45" OR "balance due" OR "total amount" OR "kindly clear" OR "payment link")'
        ),
        (
            f'in:sent {w} ("transfer" OR "work done" OR "as discussed" OR "completed the" OR '
            f'"please transfer" OR "kindly transfer" OR "send payment" OR "payment for")'
        ),
        # body-language catch-all: invoices with plain subjects and no attachment
        # ("Retainer — August" with the amount only in the body). Cheap filter prunes noise.
        f"in:sent {w} (invoice OR retainer OR \"due on\" OR \"amount owed\")",
        f'in:sent {w} (USD OR INR OR EUR OR "Rs." OR "Rs ")',
    ]


async def _onboarding_allows_incremental(db, user_id) -> bool:
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    if state.get("curation_complete"):
        return True
    n = await db.invoices.count_documents({"user_id": user_id})
    return n > 0


async def fetch_filtered_sent_mail(
    access: str,
    my_email: str,
    blocklist: set[str],
    ignored: set[str],
    mode: SyncMode,
    window: str | None = None,
) -> tuple[list[dict], dict[str, int]]:
    seen: set[str] = set()
    candidate_ids: list[str] = []
    stats = {"fetched": 0, "kept": 0, "dropped": 0}
    max_pages = MAX_LIST_PAGES_ONBOARDING if mode == "onboarding" else MAX_LIST_PAGES_INCREMENTAL

    for q in sent_mail_queries(mode, window):
        ids = await list_message_ids(access, q, max_pages=max_pages)
        logger.info("sync QUERY mode=%s %r ids=%s", mode, q[:80], len(ids))
        for mid in ids:
            if mid in seen or mid in ignored:
                continue
            seen.add(mid)
            candidate_ids.append(mid)

    stats["fetched"] = len(candidate_ids)
    if not candidate_ids:
        return [], stats

    batch = await get_messages_batch(access, candidate_ids)
    by_id = {m["id"]: m for m in batch}

    messages: list[dict] = []
    for mid in candidate_ids:
        msg = by_id.get(mid)
        if not msg:
            continue
        keep, reason, _client = seed_cheap_filter(msg, my_email, blocklist)
        if not keep:
            stats["dropped"] += 1
            logger.debug("sync FILTER DROP id=%s reason=%s", mid, reason)
            continue
        stats["kept"] += 1
        messages.append(msg)
    return messages, stats


def _regex_fallback_candidates(
    messages: list[dict],
    my_email: str,
    *,
    user_id,
    job_id,
    now_iso: str,
) -> list[dict]:
    candidates: list[dict] = []
    for msg in messages:
        client = anchor_recipients(msg, my_email)
        if not client:
            continue
        client_email = client[0].lower()
        amount, currency = extract_amount_currency(msg)
        if not amount:
            continue
        sent_dt = _parse_msg_date(msg)
        due_date = extract_due_date(msg, sent_dt)
        norm_ref = normalize_invoice_ref(None, msg.get("subject"))
        age_days = (datetime.now(timezone.utc) - sent_dt).days if sent_dt else 0
        src_date = normalize_source_date(msg.get("date")) or now_iso
        candidates.append({
            "user_id": user_id,
            "job_id": job_id,
            "message_id": msg["id"],
            "counterparty_email": client_email,
            "counterparty_name": _client_display_name(msg, client_email),
            "client_identity_key": client_identity_key(client_email),
            "amount": amount,
            "currency": currency,
            "invoice_ref": norm_ref,
            "invoice_ref_normalized": norm_ref,
            "source_subject": normalize_subject(msg.get("subject")),
            "source_from": msg.get("from"),
            "source_date": src_date,
            "source_thread_id": msg.get("thread_id"),
            "due_date": due_date,
            "due_date_assumed": False,
            "age_days": age_days,
            "confidence": 0.5,
            "ai_extracted": False,
            "status": "pending",
            "created_at": now_iso,
        })
    return candidates


async def _candidates_to_ledger(
    db,
    user_id,
    candidates: list[dict],
    now_iso: str,
) -> tuple[int, list[dict], list[dict]]:
    """Write enriched candidate rows to the ledger (same fields as curation confirm)."""
    today = datetime.now(timezone.utc).date()
    created = 0
    new_invoices: list[dict] = []
    due_date_prompts: list[dict] = []

    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    anchor_map: dict[str, list[str]] = dict(state.get("anchor_map") or {})
    domains: set[str] = set(state.get("client_domains") or {})
    email_to_primary: dict[str, str] = dict(state.get("email_to_primary") or {})

    for doc in candidates:
        mid = doc.get("message_id")
        if not mid:
            continue
        due_date = doc.get("due_date")
        inv_doc = build_ledger_invoice_from_candidate(
            doc,
            user_id=user_id,
            now_iso=now_iso,
            today=today,
            due_date=due_date,
        )
        outcome, inv_id = await upsert_sweep_invoice(
            db, user_id, inv_doc, now_iso=now_iso,
        )
        if outcome == "created" and inv_id:
            created += 1
            row = await db.invoices.find_one({"_id": inv_id})
            if row:
                payload = {
                    "invoice_id": str(inv_id),
                    "source_message_id": mid,
                    "counterparty_email": row.get("counterparty_email"),
                    "counterparty_name": row.get("counterparty_name"),
                    "amount": row.get("amount"),
                    "currency": row.get("currency") or "USD",
                    "invoice_ref": row.get("invoice_ref"),
                    "source_subject": row.get("source_subject"),
                    "due_date": row.get("due_date"),
                    "detected_at": now_iso,
                    "needs_due_date_prompt": not row.get("due_date"),
                }
                new_invoices.append(payload)
                if not row.get("due_date"):
                    due_date_prompts.append(payload)

        email = (doc.get("counterparty_email") or "").lower()
        if mid and email:
            if mid not in (anchor_map.get(email) or []):
                anchor_map.setdefault(email, []).append(mid)
            dom = _sender_domain(email)
            if dom and dom not in CONSUMER_DOMAINS:
                domains.add(dom)

    if candidates:
        anchor_map, email_to_primary = merge_candidates_by_domain(anchor_map)
        await persist_client_state(db, user_id, anchor_map, domains, email_to_primary)

    return created, new_invoices, due_date_prompts


async def run_gmail_sync(
    db,
    user_id,
    mode: SyncMode,
    *,
    job_id=None,
    confidence_min: float | None = None,
) -> dict[str, Any]:
    """Single sync entrypoint. Onboarding → seed candidates; incremental → enriched ledger rows."""
    now_iso = datetime.now(timezone.utc).isoformat()
    counts: dict[str, Any] = {
        "mode": mode,
        "fetched": 0,
        "kept": 0,
        "dropped": 0,
        "candidates": 0,
        "invoices_created": 0,
        "new_invoices": [],
    }

    if mode == "incremental":
        if not await _onboarding_allows_incremental(db, user_id):
            return {**counts, "skipped": "awaiting_onboarding"}

    conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        return {**counts, "skipped": "no_connection"}

    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    if mode == "incremental" and state.get("sync_running"):
        return {**counts, "skipped": "already_running"}

    async def _set_job_phase(phase: str, extra: dict | None = None):
        if not job_id:
            return
        patch: dict[str, Any] = {"phase": phase, "updated_at": now_iso}
        if extra:
            patch["counts"] = extra
        await db.seed_jobs.update_one({"_id": job_id}, {"$set": patch})

    if job_id:
        await db.seed_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "running", "phase": "fetching", "updated_at": now_iso}},
        )
    if mode == "incremental":
        await db.gmail_sync_state.update_one(
            {"user_id": user_id},
            {"$set": {"sync_running": True, "updated_at": now_iso}},
            upsert=True,
        )

    try:
        try:
            access = await get_access_token(db, user_id)
        except GmailAuthError as e:
            if job_id:
                await db.seed_jobs.update_one(
                    {"_id": job_id},
                    {"$set": {"status": "error", "error": str(e), "updated_at": now_iso}},
                )
            return {**counts, "skipped": "auth_error", "error": str(e)}

        my_email = ((conn or {}).get("email") or "").lower()
        ignored = await _ignored_ids(db, user_id)
        blocklist = await load_blocklist(db, user_id)

        window = sync_window_clause(mode, last_synced_at=state.get("last_synced_at"))
        messages, filter_stats = await fetch_filtered_sent_mail(
            access, my_email, blocklist, ignored, mode, window,
        )
        counts.update(filter_stats)
        await _set_job_phase("filtering", counts)

        if not messages:
            if mode == "onboarding" and job_id:
                await db.seed_candidates.delete_many({"user_id": user_id, "job_id": job_id})
                await db.seed_jobs.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "status": "complete",
                        "phase": "curation",
                        "counts": counts,
                        "finished_at": now_iso,
                        "updated_at": now_iso,
                    }},
                )
            elif mode == "incremental":
                await db.gmail_sync_state.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "last_synced_at": now_iso,
                        "last_sync_status": "ok",
                    }},
                    upsert=True,
                )
            logger.info("sync DONE user=%s mode=%s empty", user_id, mode)
            return counts

        await _set_job_phase("enriching", counts)
        ai_stats: dict[str, int] = {}

        if mode == "onboarding":
            if not job_id:
                raise ValueError("onboarding sync requires job_id")
            await db.seed_candidates.delete_many({"user_id": user_id, "job_id": job_id})

        # Streaming write: each finalized invoice conversation lands in the DB
        # immediately so the UI can show it while the scan keeps running.
        collapse_index: dict = {}
        stream = {"candidates": 0, "created": 0}
        new_invoices: list[dict] = []
        due_prompts: list[dict] = []

        async def _write_unit(rows: list[dict]) -> None:
            enrich_candidates_with_prior_chases(rows, messages, my_email)
            rows = collapse_followups_incremental(collapse_index, rows)
            if not rows:
                return
            if mode == "onboarding":
                for c in rows:
                    c["job_id"] = job_id
                await db.seed_candidates.insert_many(rows)
                stream["candidates"] += len(rows)
                await db.seed_jobs.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "counts.candidates": stream["candidates"],
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
            else:
                stream["candidates"] += len(rows)
                created, unit_new, unit_prompts = await _candidates_to_ledger(
                    db, user_id, rows, now_iso,
                )
                stream["created"] += created
                new_invoices.extend(unit_new)
                due_prompts.extend(unit_prompts)

        if os.environ.get("OPENROUTER_API_KEY"):
            await _set_job_phase("ai", counts)
            _, ai_stats = await run_seed_ai_extraction(
                access,
                messages,
                my_email,
                user_id=user_id,
                job_id=job_id or user_id,
                now_iso=now_iso,
                confidence_min=confidence_min,
                on_unit=_write_unit,
            )
        else:
            logger.warning("sync FALLBACK mode=%s reason=no_openrouter_key", mode)
            fallback = _regex_fallback_candidates(
                messages, my_email,
                user_id=user_id, job_id=job_id or user_id,
                now_iso=now_iso,
            )
            if fallback:
                await _write_unit(fallback)

        counts.update(ai_stats)
        counts["candidates"] = stream["candidates"]

        if mode == "onboarding":
            await db.seed_jobs.update_one(
                {"_id": job_id},
                {"$set": {
                    "status": "complete",
                    "phase": "curation",
                    "counts": counts,
                    "finished_at": now_iso,
                    "updated_at": now_iso,
                }},
            )
        else:
            counts["invoices_created"] = stream["created"]
            counts["new_invoices"] = new_invoices
            counts["live_detected"] = stream["created"]

            await dedupe_existing_invoices(db, user_id, now_iso)

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
                    "last_live_detection_count": created,
                    "unread_detections": existing_unread,
                    "pending_due_date_prompts": existing_prompts,
                    "watching_sent_mail": True,
                }},
                upsert=True,
            )

        logger.info("sync DONE user=%s mode=%s counts=%s", user_id, mode, counts)
        return counts
    finally:
        if mode == "incremental":
            await db.gmail_sync_state.update_one(
                {"user_id": user_id},
                {"$set": {"sync_running": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )


async def run_onboarding_sync(db, user_id, job_id) -> dict[str, Any]:
    return await run_gmail_sync(db, user_id, "onboarding", job_id=job_id)


async def ack_detections(db, user_id, detection_ids: list[str] | None = None) -> dict:
    """Clear unread detections (all, or specific invoice_ids)."""
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    unread = list(state.get("unread_detections") or [])
    if detection_ids:
        id_set = set(detection_ids)
        unread = [d for d in unread if d.get("invoice_id") not in id_set]
    else:
        unread = []
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"unread_detections": unread}},
        upsert=True,
    )
    return {"ok": True, "remaining": len(unread)}


async def ack_due_date_prompts(db, user_id, invoice_ids: list[str] | None = None) -> dict:
    """Clear one-time due-date prompts (all, or specific invoice_ids)."""
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    prompts = list(state.get("pending_due_date_prompts") or [])
    if invoice_ids:
        id_set = set(invoice_ids)
        prompts = [p for p in prompts if p.get("invoice_id") not in id_set]
    else:
        prompts = []
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"pending_due_date_prompts": prompts}},
        upsert=True,
    )
    return {"ok": True, "remaining": len(prompts)}
