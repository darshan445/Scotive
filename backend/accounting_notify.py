"""Parse invoice-sent notification emails from accounting tools (QB, FreshBooks, Wave, Zoho)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from gmail_client import get_message, list_message_ids, parse_email_addresses
from client_sweep import load_blocklist, pass1_filter_anchor
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

logger = logging.getLogger("scotive.accounting")

ACCOUNTING_DOMAINS = (
    "intuit.com", "quickbooks.com", "freshbooks.com", "waveapps.com",
    "zoho.com", "zohobooks.com", "books.zoho.com",
)

INVOICE_SENT_RE = re.compile(
    r"(?:invoice\s*(?:#|no\.?|number)?\s*[:#]?\s*)([A-Z0-9][\w/\-]+)",
    re.I,
)


def accounting_queries(days: int = 7) -> list[str]:
    w = f"newer_than:{days}d"
    from_clause = " OR ".join(f"from:{d}" for d in ACCOUNTING_DOMAINS)
    return [
        f"({from_clause}) {w} (invoice OR \"invoice #\" OR \"amount due\" OR \"has been sent\")",
        f"in:sent {w} (quickbooks OR freshbooks OR wave OR zoho) invoice",
    ]


def _client_from_accounting_msg(msg: dict, my_email: str) -> Optional[str]:
    """Recipient on an accounting-tool invoice notification = the client."""
    my = my_email.lower()
    for field in ("to_addrs", "cc_addrs"):
        for addr in msg.get(field) or []:
            if addr != my and "@" in addr:
                dom = addr.split("@")[-1].lower()
                if dom not in ACCOUNTING_DOMAINS:
                    return addr.lower()
    # Fallback: parse To header
    for addr in parse_email_addresses(msg.get("to") or ""):
        if addr != my:
            dom = addr.split("@")[-1].lower()
            if dom not in ACCOUNTING_DOMAINS:
                return addr
    return None


def _parse_accounting_invoice(msg: dict, my_email: str) -> Optional[dict]:
    client = _client_from_accounting_msg(msg, my_email)
    if not client:
        return None
    amount, currency = extract_amount_currency(msg)
    if not amount:
        return None
    norm_ref = normalize_invoice_ref(None, msg.get("subject"))
    if not norm_ref:
        m = INVOICE_SENT_RE.search(msg.get("subject") or "") or INVOICE_SENT_RE.search(msg.get("body") or "")
        if m:
            norm_ref = normalize_invoice_ref(m.group(1), msg.get("subject"))
    sent_dt = _parse_msg_date(msg)
    return {
        "client": client,
        "amount": amount,
        "currency": currency,
        "invoice_ref": norm_ref,
        "sent_dt": sent_dt,
    }


async def detect_accounting_invoices(
    db,
    user_id,
    access: str,
    my_email: str,
) -> list[dict[str, Any]]:
    """Find accounting-tool invoice notifications and auto-track."""
    from live_detection import (
        _flip_overdue_if_needed,
        _ignored_message_ids,
        _onboarding_allows_live,
        _should_skip_message,
    )

    if not await _onboarding_allows_live(db, user_id):
        return []

    terms_days = await get_default_payment_terms_days(db, user_id)
    settings = await db.user_settings.find_one({"user_id": user_id}) or {}
    grace_days = int(settings.get("grace_days") or 1)
    ignored = await _ignored_message_ids(db, user_id)
    blocklist = await load_blocklist(db, user_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    seen: set[str] = set()
    new_detections: list[dict[str, Any]] = []

    for q in accounting_queries():
        ids = await list_message_ids(access, q, max_pages=2)
        for mid in ids:
            if mid in seen:
                continue
            seen.add(mid)
            if await _should_skip_message(db, user_id, mid, ignored):
                continue
            msg = await get_message(access, mid)
            if not msg:
                continue
            # Skip if this is user-sent anchor (handled by live_detection)
            if pass1_filter_anchor(msg, my_email, blocklist):
                continue
            parsed = _parse_accounting_invoice(msg, my_email)
            if not parsed:
                continue
            client = parsed["client"]
            sent_dt = parsed["sent_dt"]
            due_date = extract_due_date(msg, sent_dt)
            norm_ref = parsed.get("invoice_ref")
            doc = enrich_invoice_doc({
                "user_id": user_id,
                "counterparty_email": client,
                "counterparty_name": _client_display_name(msg, client),
                "client_identity_key": client_identity_key(client),
                "amount": parsed["amount"],
                "balance_remaining": float(parsed["amount"]),
                "paid_amount": 0.0,
                "currency": parsed["currency"],
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
                "evidence_sentence": "Detected from accounting software notification",
                "confidence": 1.0,
                "created_at": now_iso,
            }, client)
            outcome, inv_id = await upsert_sweep_invoice(
                db, user_id, doc, now_iso=now_iso,
            )
            if outcome == "created" and inv_id:
                await _flip_overdue_if_needed(db, user_id, inv_id, now_iso)
                inv_row = await db.invoices.find_one({"_id": inv_id})
                if inv_row:
                    new_detections.append({
                        "invoice_id": str(inv_id),
                        "source_message_id": mid,
                        "counterparty_email": client,
                        "counterparty_name": inv_row.get("counterparty_name"),
                        "amount": inv_row.get("amount"),
                        "currency": inv_row.get("currency") or "USD",
                        "invoice_ref": inv_row.get("invoice_ref"),
                        "source_subject": inv_row.get("source_subject"),
                        "detected_at": now_iso,
                        "source": "accounting_tool",
                    })
                logger.info(
                    "accounting.DETECTED client=%s amount=%s ref=%s",
                    client, parsed["amount"], norm_ref,
                )
    return new_detections
