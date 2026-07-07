"""Unified Gmail sync — one job for onboarding (90d) and incremental (1h).

Used by:
- POST /seed/start (onboarding, 90 days → curation candidates)
- POST /scan/sync (manual, last hour → ledger)
- Background loop every SYNC_INTERVAL_SECONDS (default 1h, last hour → ledger)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal

from gmail_client import GmailAuthError, get_access_token, get_message, list_message_ids
from client_sweep import anchor_recipients, load_blocklist
from ledger_reconcile import (
    client_identity_key,
    dedupe_existing_invoices,
    enrich_invoice_doc,
    normalize_invoice_ref,
    normalize_source_date,
    normalize_subject,
    upsert_sweep_invoice,
)
from seed_ai import run_seed_ai_extraction
from seed_scan import (
    SEED_DAYS,
    _client_display_name,
    _collapse_seed_followups,
    _ignored_ids,
    _parse_msg_date,
    extract_amount_currency,
    extract_due_date,
)
from sent_mail_filter import seed_cheap_filter

logger = logging.getLogger("scotive.gmail_sync")

SyncMode = Literal["onboarding", "incremental"]

INCREMENTAL_LOOKBACK = os.environ.get("SYNC_LOOKBACK", "1h")
MAX_LIST_PAGES_ONBOARDING = 8
MAX_LIST_PAGES_INCREMENTAL = 2


def sync_window_clause(mode: SyncMode) -> str:
    if mode == "onboarding":
        return f"newer_than:{SEED_DAYS}d"
    return f"newer_than:{INCREMENTAL_LOOKBACK}"


def sent_mail_queries(mode: SyncMode) -> list[str]:
    w = sync_window_clause(mode)
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
        f'in:sent {w} ($ OR USD OR INR OR EUR OR "Rs." OR "Rs ")',
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
) -> tuple[list[dict], dict[str, int]]:
    seen: set[str] = set()
    messages: list[dict] = []
    stats = {"fetched": 0, "kept": 0, "dropped": 0}
    max_pages = MAX_LIST_PAGES_ONBOARDING if mode == "onboarding" else MAX_LIST_PAGES_INCREMENTAL

    for q in sent_mail_queries(mode):
        ids = await list_message_ids(access, q, max_pages=max_pages)
        logger.info("sync QUERY mode=%s %r ids=%s", mode, q[:80], len(ids))
        for mid in ids:
            if mid in seen or mid in ignored:
                continue
            seen.add(mid)
            stats["fetched"] += 1
            msg = await get_message(access, mid)
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
    """Write candidate-shaped rows to the ledger. Returns (created_count, new_invoices, due_date_prompts)."""
    from invoice_lifecycle import _parse_date

    today = datetime.now(timezone.utc).date()
    created = 0
    new_invoices: list[dict] = []
    due_date_prompts: list[dict] = []
    for doc in candidates:
        mid = doc.get("message_id")
        if not mid:
            continue
        due_date = doc.get("due_date")
        status = "invoiced"
        due_dt = _parse_date(due_date)
        if due_dt and due_dt < today:
            status = "overdue"
        inv_doc = enrich_invoice_doc({
            "user_id": user_id,
            "counterparty_email": doc["counterparty_email"],
            "counterparty_name": doc.get("counterparty_name"),
            "client_identity_key": doc.get("client_identity_key"),
            "amount": doc["amount"],
            "balance_remaining": float(doc["amount"]),
            "paid_amount": 0.0,
            "currency": doc.get("currency") or "USD",
            "invoice_ref": doc.get("invoice_ref"),
            "invoice_ref_normalized": doc.get("invoice_ref_normalized"),
            "due_date": due_date,
            "due_date_assumed": False,
            "promise_date": None,
            "status": status,
            "kind": "invoice_sent",
            "escalation_step_floor": int(doc.get("escalation_step_floor") or 0),
            "source_message_id": mid,
            "source_thread_id": doc.get("source_thread_id"),
            "source_subject": doc.get("source_subject"),
            "source_from": doc.get("source_from"),
            "source_date": doc.get("source_date"),
            "evidence_sentence": None,
            "confidence": float(doc.get("confidence") or 1.0),
            "created_at": now_iso,
        }, doc["counterparty_email"])
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
    return created, new_invoices, due_date_prompts


async def run_gmail_sync(
    db,
    user_id,
    mode: SyncMode,
    *,
    job_id=None,
    confidence_min: float | None = None,
) -> dict[str, Any]:
    """Single sync entrypoint. Onboarding → seed candidates; incremental → ledger (auto-track)."""
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

        messages, filter_stats = await fetch_filtered_sent_mail(
            access, my_email, blocklist, ignored, mode,
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
        candidates: list[dict] = []
        ai_stats: dict[str, int] = {}

        if os.environ.get("OPENROUTER_API_KEY"):
            await _set_job_phase("ai", counts)
            candidates, ai_stats = await run_seed_ai_extraction(
                access,
                messages,
                my_email,
                user_id=user_id,
                job_id=job_id or user_id,
                now_iso=now_iso,
                confidence_min=confidence_min,
            )
        else:
            logger.warning("sync FALLBACK mode=%s reason=no_openrouter_key", mode)
            candidates = _regex_fallback_candidates(
                messages, my_email,
                user_id=user_id, job_id=job_id or user_id,
                now_iso=now_iso,
            )

        candidates = _collapse_seed_followups(candidates)
        from prior_chase import enrich_candidates_with_prior_chases
        enrich_candidates_with_prior_chases(candidates, messages, my_email)
        counts.update(ai_stats)
        counts["candidates"] = len(candidates)

        if mode == "onboarding":
            if not job_id:
                raise ValueError("onboarding sync requires job_id")
            await db.seed_candidates.delete_many({"user_id": user_id, "job_id": job_id})
            if candidates:
                for c in candidates:
                    c["job_id"] = job_id
                await db.seed_candidates.insert_many(candidates)

            if candidates and os.environ.get("OPENROUTER_API_KEY"):
                await _set_job_phase("conversation_enrichment", counts)
                try:
                    from post_track_enrichment import run_pre_curation_enrichment
                    enrich_stats = await run_pre_curation_enrichment(db, user_id, job_id)
                    counts["conversation_enrichment"] = enrich_stats
                except Exception as e:
                    logger.exception("sync pre_curation enrichment FAILED user=%s err=%s", user_id, e)
                    counts["conversation_enrichment_error"] = str(e)[:200]

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
            created, new_invoices, due_prompts = await _candidates_to_ledger(
                db, user_id, candidates, now_iso,
            )
            counts["invoices_created"] = created
            counts["new_invoices"] = new_invoices
            counts["live_detected"] = created

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
