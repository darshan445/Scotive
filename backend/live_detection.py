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
    ignored = set(state.get("seed_ignored_message_ids") or [])
    # Hold back pending seed candidates until the user reviews them on the dashboard.
    async for doc in db.seed_candidates.find(
        {"user_id": user_id, "status": "pending"},
        {"message_id": 1},
    ):
        mid = doc.get("message_id")
        if mid:
            ignored.add(mid)
    return ignored


async def _onboarding_allows_live(db, user_id) -> bool:
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    if state.get("curation_complete") or state.get("dashboard_unlocked") or state.get("watching_sent_mail"):
        return True
    if state.get("awaiting_curation"):
        return False
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
    """Retired — invoices come from the invoicing tool, not sent PDFs."""
    _ = (db, user_id, access, my_email)
    return []


async def run_live_detection_tick(db, user_id) -> dict[str, Any]:
    """Retired — do not create ledger rows from sent mail."""
    _ = (db, user_id)
    return {"detected_count": 0, "new_invoices": [], "skipped": "retired"}


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
