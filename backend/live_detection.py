"""Live sent-invoice detection — auto-track new invoices after onboarding.

Runs a fast sent-only scan (no AI). Surfaces detections in sync-state for the UI.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from gmail_client import GmailAuthError, get_access_token, get_message, list_message_ids
from client_sweep import (
    CONSUMER_DOMAINS,
    _sender_domain,
    load_blocklist,
    merge_candidates_by_domain,
    pass1_filter_anchor,
    persist_client_state,
)
from ledger_reconcile import (
    client_identity_key,
    enrich_invoice_doc,
    get_default_payment_terms_days,
    normalize_invoice_ref,
    normalize_source_date,
    normalize_subject,
    upsert_sweep_invoice,
)
from seed_scan import extract_amount_currency, extract_due_date, _client_display_name, _parse_msg_date

logger = logging.getLogger("scotive.live")

LIVE_DETECTION_DAYS = int(os.environ.get("LIVE_DETECTION_DAYS", "3"))


async def _should_skip_message(db, user_id, message_id: str, ignored: set[str]) -> bool:
    if message_id in ignored:
        return True
    for coll in ("invoices", "receipts", "review_items"):
        if await db[coll].find_one({"user_id": user_id, "source_message_id": message_id}, {"_id": 1}):
            return True
    return False


def live_queries() -> list[str]:
    w = f"newer_than:{LIVE_DETECTION_DAYS}d"
    return [
        f"in:sent {w} has:attachment (invoice OR payment OR bill OR \"amount due\")",
        f'in:sent {w} subject:(invoice OR payment OR "amount due" OR outstanding OR "balance due")',
        (
            f'in:sent {w} ("please pay" OR "payment due" OR "net 30" OR "net 15" OR '
            f'"net 45" OR "balance due" OR "total amount" OR "kindly clear" OR "payment link")'
        ),
    ]


async def _ignored_message_ids(db, user_id) -> set[str]:
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    return set(state.get("seed_ignored_message_ids") or [])


async def _onboarding_allows_live(db, user_id) -> bool:
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    if state.get("curation_complete"):
        return True
    n = await db.invoices.count_documents({"user_id": user_id})
    return n > 0


async def _flip_overdue_if_needed(db, user_id, invoice_id, now_iso: str) -> None:
    from invoice_lifecycle import _parse_date
    inv = await db.invoices.find_one({"_id": invoice_id, "user_id": user_id})
    if not inv or inv.get("status") != "invoiced" or not inv.get("due_date"):
        return
    due = _parse_date(inv.get("due_date"))
    if not due:
        return
    today = datetime.now(timezone.utc).date()
    if due < today:
        await db.invoices.update_one(
            {"_id": invoice_id},
            {"$set": {"status": "overdue", "status_updated_at": now_iso}},
        )


def _detection_payload(inv_id, doc: dict, mid: str, now_iso: str) -> dict[str, Any]:
    return {
        "invoice_id": str(inv_id),
        "source_message_id": mid,
        "counterparty_email": doc.get("counterparty_email"),
        "counterparty_name": doc.get("counterparty_name"),
        "amount": doc.get("amount"),
        "currency": doc.get("currency") or "USD",
        "invoice_ref": doc.get("invoice_ref"),
        "source_subject": doc.get("source_subject"),
        "due_date": doc.get("due_date"),
        "detected_at": now_iso,
    }


async def detect_and_track_sent_invoices(
    db,
    user_id,
    access: str,
    my_email: str,
) -> list[dict[str, Any]]:
    """Scan recent sent mail and auto-add new invoices to the ledger."""
    if not await _onboarding_allows_live(db, user_id):
        return []

    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    terms_days = await get_default_payment_terms_days(db, user_id)
    settings = await db.user_settings.find_one({"user_id": user_id}) or {}
    grace_days = int(settings.get("grace_days") or 1)
    ignored = await _ignored_message_ids(db, user_id)
    blocklist = await load_blocklist(db, user_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    candidates: dict[str, list[str]] = dict(state.get("anchor_map") or {})
    domains: set[str] = set(state.get("client_domains") or [])
    email_to_primary: dict[str, str] = dict(state.get("email_to_primary") or {})

    seen_ids: set[str] = set()
    new_detections: list[dict[str, Any]] = []

    for q in live_queries():
        ids = await list_message_ids(access, q, max_pages=2)
        for mid in ids:
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            if await _should_skip_message(db, user_id, mid, ignored):
                continue
            msg = await get_message(access, mid)
            if not msg:
                continue
            client = pass1_filter_anchor(msg, my_email, blocklist)
            if not client:
                continue
            amount, currency = extract_amount_currency(msg)
            if not amount:
                continue

            sent_dt = _parse_msg_date(msg)
            due_date = extract_due_date(msg, sent_dt)
            norm_ref = normalize_invoice_ref(None, msg.get("subject"))
            primary = email_to_primary.get(client.lower(), client.lower())
            client_key = client_identity_key(primary)

            doc = enrich_invoice_doc({
                "user_id": user_id,
                "counterparty_email": primary,
                "counterparty_name": _client_display_name(msg, client),
                "client_identity_key": client_key,
                "amount": amount,
                "balance_remaining": float(amount),
                "paid_amount": 0.0,
                "currency": currency,
                "invoice_ref": norm_ref,
                "invoice_ref_normalized": norm_ref,
                "due_date": due_date,
                "due_date_assumed": False,
                "promise_date": None,
                "status": "invoiced",
                "kind": "invoice_sent",
                "source_message_id": mid,
                "source_thread_id": msg.get("thread_id"),
                "source_subject": normalize_subject(msg.get("subject")),
                "source_from": msg.get("from"),
                "source_date": normalize_source_date(msg.get("date")),
                "evidence_sentence": None,
                "confidence": 1.0,
                "created_at": now_iso,
            }, primary)

            outcome, inv_id = await upsert_sweep_invoice(
                db, user_id, doc, now_iso=now_iso,
            )
            if outcome == "created" and inv_id:
                await _flip_overdue_if_needed(db, user_id, inv_id, now_iso)
                inv_row = await db.invoices.find_one({"_id": inv_id})
                if inv_row:
                    new_detections.append(_detection_payload(inv_id, inv_row, mid, now_iso))
                logger.info(
                    "live.DETECTED client=%s amount=%s ref=%s msg=%s",
                    primary, amount, norm_ref, mid,
                )
            elif outcome == "merged":
                logger.debug("live.MERGE msg=%s ref=%s", mid, norm_ref)

            candidates.setdefault(client.lower(), [])
            if mid not in candidates[client.lower()]:
                candidates[client.lower()].append(mid)
            dom = _sender_domain(client)
            if dom and dom not in CONSUMER_DOMAINS:
                domains.add(dom)

    if new_detections:
        candidates, email_to_primary = merge_candidates_by_domain(candidates)
        await persist_client_state(db, user_id, candidates, domains, email_to_primary)

    return new_detections


async def run_live_detection_tick(db, user_id) -> dict[str, Any]:
    """One live-detection pass. Updates sync-state unread queue for the UI."""
    conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        return {"detected_count": 0, "new_invoices": [], "skipped": "no_connection"}

    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    if not await _onboarding_allows_live(db, user_id):
        return {"detected_count": 0, "new_invoices": [], "skipped": "awaiting_curation"}

    try:
        access = await get_access_token(db, user_id)
    except GmailAuthError:
        return {"detected_count": 0, "new_invoices": [], "skipped": "auth_error"}

    my_email = (conn.get("email") or "").lower()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        new_invoices = await detect_and_track_sent_invoices(db, user_id, access, my_email)
        from accounting_notify import detect_accounting_invoices
        accounting = await detect_accounting_invoices(db, user_id, access, my_email)
        new_invoices = new_invoices + accounting
    except Exception as e:
        logger.exception("live.ERROR user=%s err=%s", user_id, e)
        return {"detected_count": 0, "new_invoices": [], "error": str(e)[:200]}

    existing_unread = list(state.get("unread_detections") or [])
    seen_msg = {d.get("source_message_id") for d in existing_unread}
    for det in new_invoices:
        if det.get("source_message_id") not in seen_msg:
            existing_unread.append(det)
            seen_msg.add(det["source_message_id"])

    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {
            "last_detected_at": now_iso,
            "last_live_detection_count": len(new_invoices),
            "unread_detections": existing_unread,
            "watching_sent_mail": True,
        }},
        upsert=True,
    )

    return {"detected_count": len(new_invoices), "new_invoices": new_invoices}


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
