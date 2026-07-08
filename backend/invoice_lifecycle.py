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
    """Flip invoiced → overdue the moment due_date is before today (no grace buffer)."""
    today = datetime.now(timezone.utc).date()
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = 0
    async for inv in db.invoices.find({
        "user_id": user_id,
        "status": "invoiced",
        "due_date": {"$nin": [None, ""]},
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

    async for inv in db.invoices.find({"user_id": user_id, "status": {"$in": list(STALE_ELIGIBLE)}}):
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
