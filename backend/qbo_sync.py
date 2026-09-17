"""Module 6 — Incremental QBO sync (CDC poll backup for webhooks).

Pulls Invoice/Payment changes since last CDC cursor, upserts every invoice
(paid and unpaid), runs paid sync, enqueues conversation match for open rows.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from invoice_lifecycle import apply_past_due_transitions
from qbo_client import cdc_changes, fetch_customers_by_ids
from qbo_oauth import QboAuthError, get_qbo_access_token
from qbo_import import (
    map_qbo_invoice_to_doc,
    remove_qbo_invoices_from_ledger,
    upsert_qbo_ledger_invoice,
)

logger = logging.getLogger("scotive.qbo_sync")

CDC_MAX_LOOKBACK_DAYS = 29  # Intuit CDC window is ~30 days
CDC_DEFAULT_LOOKBACK_HOURS = 48


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _cdc_since(conn: dict, now: datetime) -> str:
    """ISO timestamp for CDC changedSince."""
    prev = _parse_iso(conn.get("last_qbo_cdc_at"))
    floor = now - timedelta(days=CDC_MAX_LOOKBACK_DAYS)
    default = now - timedelta(hours=CDC_DEFAULT_LOOKBACK_HOURS)
    start = prev or default
    if start < floor:
        start = floor
    # Overlap a few minutes to avoid missing boundary updates
    start = start - timedelta(minutes=5)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def sync_qbo_cdc(db, user_id) -> dict[str, Any]:
    """CDC poll for Invoice + Payment; webhook backup on Sync now / hourly."""
    counts: dict[str, Any] = {
        "mode": "cdc",
        "invoices_seen": 0,
        "payments_seen": 0,
        "created": 0,
        "updated": 0,
        "merged": 0,
        "skipped": 0,
        "deleted": 0,
    }

    conn = await db.qbo_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        counts["skipped"] = "no_qbo"
        return counts

    realm_id = conn.get("realm_id")
    if not realm_id:
        counts["skipped"] = "no_realm"
        return counts

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    since = _cdc_since(conn, now)

    try:
        access = await get_qbo_access_token(db, user_id)
    except QboAuthError as e:
        logger.warning("qbo.cdc auth fail user=%s err=%s", user_id, e)
        counts["skipped"] = "qbo_auth"
        return counts

    env = conn.get("env")
    try:
        changes = await cdc_changes(
            access, realm_id, ["Invoice", "Payment"], since, env=env,
        )
    except Exception as e:
        logger.exception("qbo.cdc fetch fail user=%s: %s", user_id, e)
        # Fallback: full invoice import once if CDC fails
        try:
            from qbo_import import import_unpaid_invoices
            fallback = await import_unpaid_invoices(db, user_id)
            counts["fallback_import"] = fallback
            counts["error"] = str(e)[:200]
        except Exception as e2:
            counts["errors"] = 1
            counts["error"] = str(e2)[:200]
        return counts

    invoices = changes.get("Invoice") or []
    payments = changes.get("Payment") or []
    counts["invoices_seen"] = len(invoices)
    counts["payments_seen"] = len(payments)

    upsert_rows = []
    deleted_qbo_ids: list[str] = []
    for inv in invoices:
        if (inv.get("status") or "").lower() == "deleted":
            qid = str(inv.get("Id") or "").strip()
            if qid:
                deleted_qbo_ids.append(qid)
            continue
        try:
            float(inv.get("Balance") or 0)
        except (TypeError, ValueError):
            counts["skipped"] += 1
            continue
        upsert_rows.append(inv)

    if deleted_qbo_ids:
        try:
            rem = await remove_qbo_invoices_from_ledger(db, user_id, deleted_qbo_ids)
            counts["deleted"] = rem.get("deleted", 0)
            counts["delete_missing"] = rem.get("missing", 0)
        except Exception as e:
            logger.exception("qbo.cdc delete fail user=%s: %s", user_id, e)
            counts["delete_errors"] = 1

    cust_ids = []
    for inv in upsert_rows:
        cid = ((inv.get("CustomerRef") or {}).get("value"))
        if cid:
            cust_ids.append(str(cid))
    customers = await fetch_customers_by_ids(access, realm_id, cust_ids, env=env)

    open_upserted = 0
    for inv in upsert_rows:
        qbo_id = str(inv.get("Id") or "")
        if not qbo_id:
            counts["skipped"] += 1
            continue
        cid = str(((inv.get("CustomerRef") or {}).get("value")) or "")
        customer = customers.get(cid) if cid else None
        doc = map_qbo_invoice_to_doc(
            inv, customer, user_id=user_id, realm_id=realm_id, now_iso=now_iso,
        )
        try:
            outcome, _ = await upsert_qbo_ledger_invoice(db, user_id, doc, now_iso=now_iso)
            counts[outcome] = counts.get(outcome, 0) + 1
            if doc.get("status") != "paid":
                open_upserted += 1
        except Exception as e:
            logger.exception("qbo.cdc upsert fail qbo_id=%s: %s", qbo_id, e)
            counts["skipped"] += 1

    counts["past_due_flipped"] = await apply_past_due_transitions(db, user_id)

    # Paid path whenever Payment changed or any Invoice touched (Balance may be 0)
    if payments or invoices:
        try:
            from qbo_paid_sync import sync_qbo_paid_status
            counts["qbo_paid"] = await sync_qbo_paid_status(db, user_id)
        except Exception as e:
            logger.exception("qbo.cdc paid sync fail: %s", e)
            counts["qbo_paid"] = {"errors": 1}

    if open_upserted:
        try:
            from qbo_conversation import enqueue_qbo_conversation_match
            counts["conversation_match"] = await enqueue_qbo_conversation_match(db, user_id)
        except Exception as e:
            logger.exception("qbo.cdc conversation enqueue fail: %s", e)

    await db.qbo_connections.update_one(
        {"user_id": user_id},
        {"$set": {
            "last_qbo_cdc_at": now_iso,
            "updated_at": now_iso,
        }},
    )
    logger.info("qbo.cdc DONE user=%s since=%s counts=%s", user_id, since, {
        k: counts[k] for k in (
            "invoices_seen", "payments_seen", "created", "updated", "merged", "skipped",
            "deleted", "delete_missing",
        ) if k in counts
    })
    return counts
