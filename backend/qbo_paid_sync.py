"""Module 5 — When QuickBooks reports an invoice paid, mark Scotive Paid.

No confirm-payment gate for this QBO-driven transition. Clears pending claim UI.
Does not sync QBO partial Balance (v1: full paid only).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from invoice_lifecycle import clear_payment_claim_fields, clear_stale_fields
from ledger_reconcile import OPEN_INVOICE_STATUSES
from post_chase import ack_followup_prompts
from qbo_client import (
    create_payment_against_invoice,
    fetch_invoices_by_ids,
    resolve_undeposited_funds_account_id,
)
from qbo_oauth import QboAuthError, get_qbo_access_token

logger = logging.getLogger("scotive.qbo_paid")


def build_full_mark_paid_patch(inv: dict, now_iso: str) -> dict[str, Any]:
    """Same money fields as manual full mark_paid (no claim confirm branch)."""
    patch: dict[str, Any] = {
        "status": "paid",
        "paid_at": now_iso,
        "balance_remaining": 0.0,
        "paid_amount": float(inv.get("amount") or 0),
        "chasing_paused": False,
        "tracking_paused": False,
        "watching_for_reply": False,
        "ladder_exhausted": False,
        "last_activity_at": now_iso,
        "status_updated_at": now_iso,
        "disputed_claim_amount": None,
    }
    clear_payment_claim_fields(patch)
    clear_stale_fields(patch)
    return patch


def _qbo_balance(invoice: dict) -> Optional[float]:
    try:
        return float(invoice.get("Balance"))
    except (TypeError, ValueError):
        return None


def _qbo_paid_date(invoice: dict) -> Optional[str]:
    """Best-effort paid date from QBO metadata / DueDate fallback."""
    meta = invoice.get("MetaData") or {}
    for key in ("LastUpdatedTime", "CreateTime"):
        raw = meta.get(key)
        if raw and isinstance(raw, str) and len(raw) >= 10:
            return raw[:10]
    return None


async def mark_invoice_paid_from_qbo(
    db,
    user_id,
    inv: dict,
    *,
    now_iso: str,
    qbo_invoice: Optional[dict] = None,
) -> bool:
    """Mark one ledger row Paid from QBO. Returns False if already paid."""
    if inv.get("status") == "paid":
        return False

    patch = build_full_mark_paid_patch(inv, now_iso)
    patch["paid_via"] = "quickbooks"
    paid_date = _qbo_paid_date(qbo_invoice or {}) or now_iso[:10]
    patch["qbo_paid_date"] = paid_date
    patch["evidence_sentence"] = f"Paid in QuickBooks · {paid_date}"

    undo_snapshot = {
        "status": inv.get("status"),
        "balance_remaining": inv.get("balance_remaining"),
        "paid_amount": inv.get("paid_amount"),
        "paid_at": inv.get("paid_at"),
        "chasing_paused": inv.get("chasing_paused", False),
        "tracking_paused": inv.get("tracking_paused", False),
        "payment_claim_amount": inv.get("payment_claim_amount"),
        "payment_claim_pending": inv.get("payment_claim_pending"),
        "payment_claim_quote": inv.get("payment_claim_quote"),
        "status_before_claim": inv.get("status_before_claim"),
        "claim_balance_before": inv.get("claim_balance_before"),
        "claim_paid_before": inv.get("claim_paid_before"),
        "disputed_claim_amount": inv.get("disputed_claim_amount"),
        "paid_via": inv.get("paid_via"),
        "qbo_paid_date": inv.get("qbo_paid_date"),
        "evidence_sentence": inv.get("evidence_sentence"),
    }

    await db.invoices.update_one({"_id": inv["_id"]}, {"$set": patch})
    await db.invoice_events.insert_one({
        "user_id": user_id,
        "invoice_id": inv["_id"],
        "action": "qbo_paid",
        "at": now_iso,
        "undo_snapshot": undo_snapshot,
        "meta": {
            "qbo_id": inv.get("qbo_id"),
            "qbo_paid_date": paid_date,
            "source": "quickbooks",
            "balance_before": inv.get("balance_remaining"),
        },
    })
    await ack_followup_prompts(db, user_id, [str(inv["_id"])])
    return True


async def sync_qbo_paid_status(db, user_id) -> dict[str, Any]:
    """Poll QBO for open ledger rows with qbo_id; Balance <= 0 → Paid (no confirm)."""
    counts = {
        "examined": 0,
        "marked_paid": 0,
        "still_unpaid": 0,
        "missing_in_qbo": 0,
        "skipped": 0,
        "errors": 0,
    }

    conn = await db.qbo_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        counts["skipped"] = "no_qbo"
        return counts

    realm_id = conn.get("realm_id")
    if not realm_id:
        counts["skipped"] = "no_realm"
        return counts

    open_qbo = []
    async for inv in db.invoices.find({
        "user_id": user_id,
        "qbo_id": {"$type": "string"},
        "status": {"$in": list(OPEN_INVOICE_STATUSES)},
    }):
        open_qbo.append(inv)

    if not open_qbo:
        return counts

    try:
        access = await get_qbo_access_token(db, user_id)
    except QboAuthError as e:
        logger.warning("qbo.paid auth fail user=%s err=%s", user_id, e)
        counts["skipped"] = "qbo_auth"
        return counts

    ids = [str(inv["qbo_id"]) for inv in open_qbo if inv.get("qbo_id")]
    try:
        by_id = await fetch_invoices_by_ids(
            access, realm_id, ids, env=conn.get("env"),
        )
    except Exception as e:
        logger.exception("qbo.paid fetch fail user=%s: %s", user_id, e)
        counts["errors"] += 1
        return counts

    now_iso = datetime.now(timezone.utc).isoformat()
    for inv in open_qbo:
        counts["examined"] += 1
        qbo_id = str(inv.get("qbo_id") or "")
        qbo_inv = by_id.get(qbo_id)
        if not qbo_inv:
            counts["missing_in_qbo"] += 1
            continue
        bal = _qbo_balance(qbo_inv)
        if bal is None:
            counts["errors"] += 1
            continue
        if bal > 0.005:
            counts["still_unpaid"] += 1
            continue
        try:
            ok = await mark_invoice_paid_from_qbo(
                db, user_id, inv, now_iso=now_iso, qbo_invoice=qbo_inv,
            )
            if ok:
                counts["marked_paid"] += 1
        except Exception as e:
            logger.exception("qbo.paid mark fail inv=%s: %s", inv.get("_id"), e)
            counts["errors"] += 1

    if counts["marked_paid"]:
        logger.info("qbo.paid DONE user=%s counts=%s", user_id, counts)
    return counts


async def push_scotive_paid_to_qbo(
    db,
    user_id,
    inv: dict,
    *,
    amount: float,
    now_iso: str,
) -> dict[str, Any]:
    """After Scotive Received / mark-paid: zero (or reduce) that invoice's Balance in QBO.

    QBO has no Invoice.Status=Paid write — the Accounting API only drops Balance by
    creating a Payment linked to the Invoice (bookkeeping, not a Scotive payment UX).
    """
    qbo_id = inv.get("qbo_id")
    if not qbo_id:
        return {"ok": False, "skipped": "no_qbo_id"}

    conn = await db.qbo_connections.find_one({"user_id": user_id, "status": "connected"})
    if not conn:
        return {"ok": False, "skipped": "no_qbo"}

    realm_id = conn.get("realm_id")
    if not realm_id:
        return {"ok": False, "skipped": "no_realm"}

    try:
        apply_amt = round(float(amount), 2)
    except (TypeError, ValueError):
        return {"ok": False, "skipped": "bad_amount"}
    if apply_amt <= 0.005:
        return {"ok": False, "skipped": "zero_amount"}

    try:
        access = await get_qbo_access_token(db, user_id)
    except QboAuthError as e:
        logger.warning("qbo.push_paid auth fail user=%s err=%s", user_id, e)
        return {"ok": False, "skipped": "qbo_auth", "error": str(e)}

    env = conn.get("env")
    by_id = await fetch_invoices_by_ids(access, realm_id, [str(qbo_id)], env=env)
    qbo_inv = by_id.get(str(qbo_id))
    if not qbo_inv:
        return {"ok": False, "skipped": "invoice_missing_in_qbo"}

    bal = _qbo_balance(qbo_inv)
    if bal is None:
        return {"ok": False, "skipped": "bad_qbo_balance"}
    if bal <= 0.005:
        # Already paid in QBO — nothing to push
        return {"ok": True, "skipped": "already_paid_in_qbo", "qbo_balance": bal}

    apply_amt = min(apply_amt, round(bal, 2))
    cust_ref = qbo_inv.get("CustomerRef") or {}
    customer_id = str(cust_ref.get("value") or inv.get("qbo_customer_id") or "")
    if not customer_id:
        return {"ok": False, "skipped": "no_customer"}

    deposit_id = conn.get("qbo_deposit_account_id")
    if not deposit_id:
        deposit_id = await resolve_undeposited_funds_account_id(access, realm_id, env=env)
        if deposit_id:
            await db.qbo_connections.update_one(
                {"user_id": user_id},
                {"$set": {"qbo_deposit_account_id": deposit_id, "updated_at": now_iso}},
            )
    if not deposit_id:
        return {"ok": False, "skipped": "no_deposit_account", "error": "Undeposited Funds account not found"}

    try:
        payment = await create_payment_against_invoice(
            access, realm_id,
            customer_id=customer_id,
            invoice_id=str(qbo_id),
            amount=apply_amt,
            deposit_account_id=str(deposit_id),
            txn_date=now_iso[:10],
            private_note="Confirmed paid in Scotive (Gmail / Received)",
            env=env,
        )
    except Exception as e:
        logger.exception("qbo.push_paid Payment create fail inv=%s: %s", inv.get("_id"), e)
        return {"ok": False, "error": str(e)[:300]}

    payment_id = str((payment or {}).get("Id") or "")
    patch = {
        "updated_at": now_iso,
        "qbo_last_payment_push_at": now_iso,
    }
    if payment_id:
        patch["qbo_payment_id"] = payment_id
        existing = list(inv.get("qbo_payment_ids") or [])
        if payment_id not in existing:
            existing.append(payment_id)
        patch["qbo_payment_ids"] = existing

    await db.invoices.update_one({"_id": inv["_id"]}, {"$set": patch})
    await db.invoice_events.insert_one({
        "user_id": user_id,
        "invoice_id": inv["_id"],
        "action": "qbo_payment_pushed",
        "at": now_iso,
        "meta": {
            "qbo_id": str(qbo_id),
            "qbo_payment_id": payment_id,
            "amount": apply_amt,
            "qbo_balance_before": bal,
        },
    })
    logger.info(
        "qbo.push_paid OK inv=%s qbo_id=%s payment=%s amount=%s",
        inv.get("_id"), qbo_id, payment_id, apply_amt,
    )
    return {"ok": True, "qbo_payment_id": payment_id, "amount": apply_amt}
