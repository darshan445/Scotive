"""Date-driven invoice lifecycle transitions (overdue, promise broken, stale)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from bson import ObjectId

logger = logging.getLogger("scotive.lifecycle")

STALE_DAYS = int(os.environ.get("STALE_INVOICE_DAYS", "120"))
STALE_ELIGIBLE = ("invoiced", "overdue", "promised", "partially_paid", "promise_broken", "disputed")


def parse_activity_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                return None
    return None


def effective_prior_status(inv: dict) -> str:
    """Status to restore when leaving stale or denying a payment claim."""
    if inv.get("status") == "stale":
        return inv.get("status_before_stale") or "overdue"
    return inv.get("status") or "invoiced"


def payment_claim_amount_value(inv: dict | None) -> float | None:
    """Claimed sent amount awaiting user confirmation, if any."""
    if not inv:
        return None
    raw = inv.get("payment_claim_amount")
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if val > 0.005 else None


def has_pending_payment_claim(inv: dict | None) -> bool:
    """True while a client payment claim still needs Received / Not yet."""
    if not inv:
        return False
    if inv.get("payment_claim_pending"):
        return True
    # Legacy full says-paid rows used status alone.
    return inv.get("status") == "paid_unconfirmed"


def outstanding_balance(inv: dict | None) -> float:
    """Amount that counts toward Outstanding / You're Owed.

    Unconfirmed payment claims (full or partial) never reduce this — use the
    pre-claim snapshot when present, otherwise restore any claim amount that
    was already subtracted from balance_remaining (legacy / receipt paths).
    """
    if not inv:
        return 0.0
    amt = float(inv.get("amount") or 0)
    bal = float(
        inv.get("balance_remaining")
        if inv.get("balance_remaining") is not None
        else amt
    )
    if not has_pending_payment_claim(inv):
        return bal

    if inv.get("claim_balance_before") is not None:
        return max(0.0, float(inv["claim_balance_before"]))

    if inv.get("claim_paid_before") is not None:
        return max(0.0, round(amt - float(inv["claim_paid_before"] or 0), 2))

    claim = payment_claim_amount_value(inv)
    if claim is not None:
        # Claim was booked into paid_amount / carved out of balance — add back.
        if bal + 0.005 < amt and abs((bal + claim) - amt) <= max(0.02, amt * 0.001):
            return round(bal + claim, 2)
        if bal <= 0.005:
            return max(claim, amt) if abs(claim - amt) <= 0.02 else round(bal + claim, 2)
        return bal

    # Legacy full says-paid with balance already zeroed, no claim fields.
    if inv.get("status") == "paid_unconfirmed" and bal <= 0.005:
        return amt
    return bal


def clear_payment_claim_fields(patch: dict, *, keep_amount: bool = False) -> None:
    """Clear pending-claim bookkeeping from an invoice patch."""
    if not keep_amount:
        patch["payment_claim_amount"] = None
    patch["payment_claim_pending"] = False
    patch["payment_claim_quote"] = None
    patch["status_before_claim"] = None
    patch["claim_balance_before"] = None
    patch["claim_paid_before"] = None


async def migrate_unconfirmed_client_partial_claims(db, user_id) -> int:
    """Move client-claimed partials wrongly booked into paid_amount into the claim bucket.

    Heuristic: last client partial_payment event with no later mark_paid / receipt
    confirmation, and paid_amount matching that event amount.
    """
    updated = 0
    async for inv in db.invoices.find({
        "user_id": user_id,
        "status": {"$in": ["partially_paid", "disputed"]},
        "paid_amount": {"$gt": 0.005},
        "payment_claim_pending": {"$ne": True},
    }):
        events = []
        async for e in db.invoice_events.find(
            {"user_id": user_id, "invoice_id": inv["_id"]},
            sort=[("at", 1)],
        ):
            events.append(e)

        last_partial = None
        confirmed_after = False
        for e in events:
            action = e.get("action")
            if action == "partial_payment":
                last_partial = e
                confirmed_after = False
            elif action in ("mark_paid", "receipt_matched", "user_confirmed_match"):
                confirmed_after = True
            elif action == "invoice_corrected":
                # User-stated anchor / correction — leave confirmed money alone.
                confirmed_after = True

        if not last_partial or confirmed_after:
            continue

        meta = last_partial.get("meta") or {}
        try:
            claim_amt = float(meta.get("amount") or 0)
        except (TypeError, ValueError):
            claim_amt = 0.0
        paid = float(inv.get("paid_amount") or 0)
        if claim_amt <= 0.005 or abs(paid - claim_amt) > 0.02:
            continue

        amt = float(inv.get("amount") or 0)
        new_paid = round(max(paid - claim_amt, 0), 2)
        new_bal = round(max(amt - new_paid, 0), 2)
        has_dispute = inv.get("disputed_claim_amount") is not None
        due = _parse_date(inv.get("due_date"))
        today = datetime.now(timezone.utc).date()
        prior = "overdue" if (due and due < today) else "invoiced"
        new_status = "disputed" if has_dispute else "paid_unconfirmed"

        patch = {
            "paid_amount": new_paid,
            "balance_remaining": new_bal,
            "payment_claim_amount": claim_amt,
            "payment_claim_pending": True,
            "payment_claim_quote": meta.get("quote"),
            "status_before_claim": prior,
            "claim_balance_before": new_bal,
            "claim_paid_before": new_paid,
            "status": new_status,
            "chasing_paused": True,
            "paid_at": None,
        }
        if has_dispute and inv.get("disputed_claim_amount") is not None:
            patch["disputed_claim_amount"] = inv["disputed_claim_amount"]

        await db.invoices.update_one({"_id": inv["_id"]}, {"$set": patch})
        updated += 1

    if updated:
        logger.info("migrated unconfirmed client partials user=%s count=%s", user_id, updated)
    return updated


async def resolve_last_activity(db, inv: dict) -> datetime | None:
    """Best-effort last meaningful activity on an invoice."""
    for key in ("last_activity_at", "status_updated_at", "source_date", "created_at"):
        dt = parse_activity_dt(inv.get(key))
        if dt:
            return dt
    try:
        ev = await db.invoice_events.find_one(
            {"invoice_id": inv["_id"]},
            sort=[("at", -1)],
        )
        if ev:
            return parse_activity_dt(ev.get("at"))
    except Exception:
        pass
    return None


async def touch_invoice_activity(db, invoice_id, at: str | None = None) -> None:
    now_iso = at or datetime.now(timezone.utc).isoformat()
    await db.invoices.update_one(
        {"_id": invoice_id if isinstance(invoice_id, ObjectId) else ObjectId(invoice_id)},
        {"$set": {"last_activity_at": now_iso}},
    )


def clear_stale_fields(patch: dict) -> None:
    patch["stale_prompt_pending"] = False
    patch["stale_prompt_acknowledged"] = True
    patch["status_before_stale"] = None
    patch["stale_since"] = None


async def apply_past_due_transitions(db, user_id) -> int:
    """Flip invoiced → overdue the moment due_date is before today (no grace buffer).

    Skips tracking_paused invoices — overdue flip runs on resume via the next tick.
    """
    today = datetime.now(timezone.utc).date()
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = 0
    async for inv in db.invoices.find({
        "user_id": user_id,
        "status": "invoiced",
        "due_date": {"$nin": [None, ""]},
        "tracking_paused": {"$ne": True},
    }):
        due = _parse_date(inv.get("due_date"))
        if not due or due >= today:
            continue
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "status": "overdue",
                "status_updated_at": now_iso,
                "last_activity_at": now_iso,
            }},
        )
        updated += 1

    # Self-heal the reverse: overdue rows whose due date is today or later
    # (bad revert fallbacks, due-date edits) flip back to invoiced.
    async for inv in db.invoices.find({
        "user_id": user_id,
        "status": "overdue",
        "due_date": {"$nin": [None, ""]},
        "tracking_paused": {"$ne": True},
    }):
        due = _parse_date(inv.get("due_date"))
        if not due or due < today:
            continue
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "status": "invoiced",
                "status_updated_at": now_iso,
                "last_activity_at": now_iso,
            }},
        )
        updated += 1

    if updated:
        logger.info("past_due transitions user=%s count=%s", user_id, updated)
    return updated


async def apply_promise_broken_transitions(db, user_id) -> int:
    """Flip promised → promise_broken when promise_date is before today (no grace)."""
    today = datetime.now(timezone.utc).date()
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = 0
    async for inv in db.invoices.find({
        "user_id": user_id,
        "status": "promised",
        "promise_date": {"$nin": [None, ""]},
        "tracking_paused": {"$ne": True},
    }):
        pd = _parse_date(inv.get("promise_date"))
        if not pd or pd >= today:
            continue
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "status": "promise_broken",
                "status_updated_at": now_iso,
                "last_activity_at": now_iso,
            }},
        )
        updated += 1
    if updated:
        logger.info("promise_broken transitions user=%s count=%s", user_id, updated)
    return updated


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except Exception:
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except Exception:
                return None
    return None


async def apply_stale_transitions(db, user_id) -> int:
    """Mark open invoices with no activity for STALE_DAYS as stale (one-time prompt)."""
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    stale_count = 0

    async for inv in db.invoices.find({
        "user_id": user_id,
        "status": {"$in": list(STALE_ELIGIBLE)},
        "tracking_paused": {"$ne": True},
    }):
        last = await resolve_last_activity(db, inv)
        if not last:
            continue
        days_idle = (now - last).days
        if days_idle < STALE_DAYS:
            continue

        prev = inv.get("status") or "invoiced"
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "status": "stale",
                "status_before_stale": prev,
                "stale_since": now_iso,
                "stale_prompt_pending": True,
                "chasing_paused": True,
                "status_updated_at": now_iso,
                "last_activity_at": inv.get("last_activity_at") or last.isoformat(),
            }},
        )
        await db.invoice_events.insert_one({
            "user_id": user_id,
            "invoice_id": inv["_id"],
            "action": "went_stale",
            "at": now_iso,
            "meta": {"previous_status": prev, "days_inactive": days_idle},
        })
        stale_count += 1

    if stale_count:
        logger.info("stale transitions user=%s count=%s", user_id, stale_count)
    return stale_count


async def apply_stale_for_all_users(db) -> dict:
    users = 0
    stale = 0
    async for doc in db.gmail_tokens.find({}, {"user_id": 1}):
        uid = doc.get("user_id")
        if not uid:
            continue
        users += 1
        stale += await apply_stale_transitions(db, uid)
    return {"users": users, "stale": stale}
