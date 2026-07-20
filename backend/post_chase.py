"""Post-follow-up behavior: watching for replies + time-based ladder drafts."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from escalation_scheduler import (
    STEP_LABELS,
    _step_label,
    _tone_for_step,
    generate_draft,
)

logger = logging.getLogger("scotive.post_chase")

DEFAULT_FOLLOW_UP_INTERVAL_DAYS = 3

CLIENT_REPLY_ACTIONS = frozenset({
    "payment_promise",
    "payment_claim",
    "partial_payment",
    "dispute",
    "receipt",
    "receipt_matched",
    "receipt_matched_manual",
})


def _parse_dt(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


async def get_follow_up_interval_days(db, user_id) -> int:
    s = await db.user_settings.find_one({"user_id": user_id}) or {}
    val = s.get("follow_up_interval_days")
    if val is not None:
        return max(1, int(val))
    return DEFAULT_FOLLOW_UP_INTERVAL_DAYS


async def mark_chase_sent(
    db,
    user_id,
    invoice_id,
    *,
    step_index: int | None,
    now_iso: str,
) -> None:
    """After user sends a follow-up — watch for client reply; stay past-due in ledger."""
    inv = await db.invoices.find_one({"_id": invoice_id, "user_id": user_id})
    if not inv:
        return
    patch: dict[str, Any] = {
        "last_followup_sent_at": now_iso,
        "last_chase_at": now_iso,
        "last_activity_at": now_iso,
        "watching_for_reply": True,
        "ladder_exhausted": False,
        "needs_reply": False,
    }
    if step_index is not None:
        patch["current_escalation_step"] = int(step_index)
    await db.invoices.update_one({"_id": invoice_id}, {"$set": patch})
    await db.invoice_events.insert_one({
        "user_id": user_id,
        "invoice_id": invoice_id,
        "action": "chase_sent",
        "at": now_iso,
        "meta": {"step_index": step_index},
    })


async def clear_watching_on_client_event(db, invoice_id, now_iso: str) -> None:
    await db.invoices.update_one(
        {"_id": invoice_id},
        {"$set": {
            "watching_for_reply": False,
            "last_client_reply_at": now_iso,
        }},
    )


async def _queued_draft_exists(db, user_id, invoice_id) -> bool:
    doc = await db.chase_drafts.find_one({
        "user_id": user_id,
        "invoice_id": invoice_id,
        "status": "queued",
    })
    return doc is not None


async def _next_step_index(inv: dict) -> int:
    floor = int(inv.get("escalation_step_floor") or 0)
    current = inv.get("current_escalation_step")
    if current is None:
        return floor
    return int(current) + 1


async def run_post_chase_tick(db, user_id) -> dict[str, Any]:
    """If no client reply since last chase, queue the next ladder draft + user prompt."""
    counts = {"prompts_created": 0, "ladder_exhausted": 0, "skipped": 0}
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    interval_days = await get_follow_up_interval_days(db, user_id)
    settings = await db.user_settings.find_one({"user_id": user_id}) or {}
    late_fee_text = settings.get("late_fee_text") if settings.get("late_fee_enabled") else None

    from gmail_oauth import ensure_gmail_account_name
    signer_name = await ensure_gmail_account_name(db, user_id)

    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    pending = list(state.get("pending_followup_prompts") or [])
    pending_ids = {p.get("invoice_id") for p in pending}

    async for inv in db.invoices.find({
        "user_id": user_id,
        "watching_for_reply": True,
        "chasing_paused": {"$ne": True},
        "tracking_paused": {"$ne": True},
        "ladder_exhausted": {"$ne": True},
        "status": {"$in": ["overdue", "promise_broken", "invoiced", "partially_paid"]},
    }):
        inv_id = inv["_id"]
        last_chase = _parse_dt(inv.get("last_followup_sent_at") or inv.get("last_chase_at"))
        if not last_chase:
            counts["skipped"] += 1
            continue
        if (now - last_chase).total_seconds() < interval_days * 86400:
            counts["skipped"] += 1
            continue
        if await _queued_draft_exists(db, user_id, inv_id):
            counts["skipped"] += 1
            continue

        next_step = await _next_step_index(inv)
        if next_step >= len(STEP_LABELS):
            await db.invoices.update_one(
                {"_id": inv_id},
                {"$set": {"ladder_exhausted": True, "watching_for_reply": False}},
            )
            counts["ladder_exhausted"] += 1
            continue

        step_key = f"followup_{next_step}"
        existing_key = await db.chase_drafts.find_one({
            "user_id": user_id,
            "invoice_id": inv_id,
            "step_key": step_key,
            "status": {"$in": ["queued", "sent", "dismissed"]},
        })
        if existing_key:
            counts["skipped"] += 1
            continue

        tone = _tone_for_step(next_step, inv.get("status"))
        label = _step_label(next_step)
        draft = await generate_draft(
            inv, tone, label, late_fee_text, signer_name=signer_name,
        )
        if not draft:
            counts["skipped"] += 1
            continue

        ins = await db.chase_drafts.insert_one({
            "user_id": user_id,
            "invoice_id": inv_id,
            "step_key": step_key,
            "step_index": next_step,
            "step_label": label,
            "offset_days": None,
            "tone": tone,
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "to": inv.get("counterparty_email"),
            "thread_id": inv.get("source_thread_id"),
            "counterparty_name": inv.get("counterparty_name"),
            "invoice_ref": inv.get("invoice_ref"),
            "amount": inv.get("balance_remaining") or inv.get("amount"),
            "currency": inv.get("currency") or "USD",
            "due_date": inv.get("due_date"),
            "status": "queued",
            "source": "post_chase_ladder",
            "generated_at": now_iso,
        })

        inv_id_str = str(inv_id)
        if inv_id_str not in pending_ids:
            pending.append({
                "invoice_id": inv_id_str,
                "draft_id": str(ins.inserted_id),
                "counterparty_name": inv.get("counterparty_name"),
                "counterparty_email": inv.get("counterparty_email"),
                "amount": inv.get("amount"),
                "currency": inv.get("currency") or "USD",
                "step_label": label,
                "prompted_at": now_iso,
            })
            pending_ids.add(inv_id_str)
            counts["prompts_created"] += 1

    if counts["prompts_created"]:
        await db.gmail_sync_state.update_one(
            {"user_id": user_id},
            {"$set": {"pending_followup_prompts": pending}},
            upsert=True,
        )
    return counts


async def ack_followup_prompts(db, user_id, invoice_ids: list[str] | None = None) -> dict:
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    prompts = list(state.get("pending_followup_prompts") or [])
    if invoice_ids:
        id_set = set(invoice_ids)
        prompts = [p for p in prompts if p.get("invoice_id") not in id_set]
    else:
        prompts = []
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"pending_followup_prompts": prompts}},
        upsert=True,
    )
    return {"ok": True, "remaining": len(prompts)}
