"""Idempotency helpers for invoice_events — prevent duplicate timeline rows."""
from __future__ import annotations

import re
from typing import Any

from bson import ObjectId

# Maps client_sweep event types → stored invoice_events.action
EVENT_ACTION_MAP = {
    "promise": "payment_promise",
    "partial_payment": "partial_payment",
    "dispute": "dispute",
    "payment_claimed": "payment_claim",
    "approved": "payment_approved",
}


def normalize_event_quote(quote: str | None) -> str:
    if not quote:
        return ""
    return re.sub(r"\s+", " ", str(quote).strip().lower())[:240]


def event_action(ev_type: str | None) -> str:
    return EVENT_ACTION_MAP.get(ev_type or "", ev_type or "note")


def dedupe_ai_events(events: list[dict]) -> list[dict]:
    """Collapse duplicate events from one AI response before writing."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for ev in events or []:
        mid = (ev.get("message_id") or "").strip()
        q = normalize_event_quote(ev.get("quote"))
        ev_type = ev.get("type") or ""

        keys: list[tuple] = []
        if mid:
            keys.append(("mid", mid, ev_type))
        if q:
            keys.append(("quote", ev_type, q))
        if not keys:
            keys.append(("raw", ev_type, id(ev)))

        if any(k in seen for k in keys):
            continue
        for k in keys:
            seen.add(k)
        out.append(ev)
    return out


async def message_already_handled(db, user_id, message_id: str) -> bool:
    """True when this Gmail message is already represented in the ledger."""
    if not message_id:
        return False
    for coll in ("invoices", "receipts", "review_items"):
        if await db[coll].find_one(
            {"user_id": user_id, "source_message_id": message_id},
            {"_id": 1},
        ):
            return True
    if await db.invoice_events.find_one(
        {"user_id": user_id, "meta.message_id": message_id},
        {"_id": 1},
    ):
        return True
    return False


async def event_already_recorded(
    db,
    user_id,
    invoice_id,
    ev_type: str | None,
    *,
    message_id: str | None = None,
    quote: str | None = None,
) -> bool:
    """True when this client event is already on the invoice timeline."""
    action = event_action(ev_type)
    if message_id:
        existing = await db.invoice_events.find_one({
            "user_id": user_id,
            "invoice_id": invoice_id,
            "meta.message_id": message_id,
            "action": action,
        })
        if existing:
            return True

    norm_q = normalize_event_quote(quote)
    if norm_q and action:
        async for row in db.invoice_events.find({
            "user_id": user_id,
            "invoice_id": invoice_id,
            "action": action,
        }):
            if normalize_event_quote((row.get("meta") or {}).get("quote")) == norm_q:
                return True
    return False


async def dedupe_stored_invoice_events(
    db,
    user_id,
    invoice_id: Any | None = None,
) -> int:
    """Delete duplicate invoice_events rows (same message_id or same action+quote)."""
    query: dict[str, Any] = {"user_id": user_id}
    if invoice_id is not None:
        query["invoice_id"] = invoice_id if isinstance(invoice_id, ObjectId) else ObjectId(str(invoice_id))

    rows: list[dict] = []
    async for row in db.invoice_events.find(query).sort("at", 1):
        rows.append(row)

    keep_ids: set[Any] = set()
    seen_mid: set[tuple] = set()
    seen_quote: set[tuple] = set()

    for row in rows:
        meta = row.get("meta") or {}
        mid = (meta.get("message_id") or "").strip()
        action = row.get("action") or ""
        q = normalize_event_quote(meta.get("quote"))

        if mid:
            key = ("mid", mid, action)
            if key in seen_mid:
                continue
            seen_mid.add(key)
            keep_ids.add(row["_id"])
            continue

        if q and action:
            key = ("quote", action, q)
            if key in seen_quote:
                continue
            seen_quote.add(key)
            keep_ids.add(row["_id"])
            continue

        keep_ids.add(row["_id"])

    deleted = 0
    for row in rows:
        if row["_id"] not in keep_ids:
            await db.invoice_events.delete_one({"_id": row["_id"]})
            deleted += 1
    return deleted
