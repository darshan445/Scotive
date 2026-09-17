"""Write a rulebook result onto a ledger invoice.

The model’s current-state fields are the ledger. new_events are timeline
chips only — they must not change status after the fact.

Used by first-pass (onboarding / new invoice) and by Sync now / hourly
re-eval. Fetching mail is NOT this module’s job.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from client_sweep import EVENT_KIND_MAP
from invoice_event_idempotency import event_already_recorded
from reeval_rulebook import (
    normalize_reeval_status,
    rulebook_events_to_write_events,
)

# Conversation statuses that pause Friendly cadence after the model decides.
_CADENCE_PAUSE_STATUSES = frozenset({
    "promised", "disputed", "partially_paid", "paid_unconfirmed", "promise_broken",
})
# Books (QBO/Xero) own these. Chat must not un-pay or un-write-off.
_BOOKS_LOCKED_STATUSES = frozenset({"paid", "written_off"})
_CLIENT_CHIP_TYPES = frozenset({
    "promise", "dispute", "partial_payment", "payment_claimed", "question", "approved",
})


async def invoice_processed_message_ids(
    db, user_id, inv: dict, conversation_ids: list[str] | None = None,
) -> list[str]:
    """Message ids already applied to this invoice's timeline."""
    _ = conversation_ids
    seen: set[str] = set()
    src = inv.get("source_message_id")
    if src:
        seen.add(src)
    for mid in inv.get("reeval_seen_message_ids") or []:
        if mid:
            seen.add(mid)
    async for ev in db.invoice_events.find(
        {"user_id": user_id, "invoice_id": inv["_id"]},
        {"meta.message_id": 1},
    ):
        mid = (ev.get("meta") or {}).get("message_id")
        if mid:
            seen.add(mid)
    return sorted(seen)


async def mark_processed(db, user_id, message_ids) -> None:
    now = datetime.now(timezone.utc)
    for mid in message_ids:
        if not mid:
            continue
        await db.processed_messages.update_one(
            {"user_id": user_id, "message_id": mid},
            {"$setOnInsert": {"user_id": user_id, "message_id": mid, "at": now}},
            upsert=True,
        )


async def mark_reeval_seen(db, inv_id, message_ids: list[str]) -> None:
    """Remember messages considered in a reeval pass (even when new_events was empty)."""
    mids = [m for m in message_ids if m]
    if not mids:
        return
    await db.invoices.update_one(
        {"_id": inv_id},
        {"$addToSet": {"reeval_seen_message_ids": {"$each": mids}}},
    )


def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _write_timeline_chips(
    db,
    user_id,
    inv: dict,
    events: list[dict],
    messages_by_id: dict[str, dict],
    now_iso: str,
) -> list[str]:
    """Insert invoice_events rows. Do not patch invoice status/amount."""
    written: list[str] = []
    for ev in events:
        ev_type = ev.get("type") or ""
        msg_id = ev.get("message_id")
        if await event_already_recorded(
            db, user_id, inv["_id"], ev_type,
            message_id=msg_id,
            quote=ev.get("quote"),
        ):
            continue
        msg = messages_by_id.get(msg_id or "") or {}
        await db.invoice_events.insert_one({
            "user_id": user_id,
            "invoice_id": inv["_id"],
            "action": EVENT_KIND_MAP.get(ev_type, ev_type or "note"),
            "at": now_iso,
            "meta": {
                "quote": ev.get("quote"),
                "message_id": msg_id,
                "message_date": msg.get("date"),
                "subject": msg.get("subject"),
                "from": msg.get("from"),
                "thread_id": msg.get("thread_id"),
                "confidence": ev.get("confidence"),
                "date": ev.get("date"),
                "amount": ev.get("amount"),
                "old_amount": ev.get("old_amount"),
                "claimed_amount": ev.get("claimed_amount"),
                "reference": ev.get("reference"),
                "dispute_kind": ev.get("dispute_kind"),
                "invoice_ref": ev.get("invoice_ref"),
            },
        })
        written.append(ev_type)
    return written


def _ledger_patch(inv: dict, result: dict, events: list[dict], now_iso: str) -> dict[str, Any]:
    """Model current-state fields. Cadence pause is derived from status."""
    patch: dict[str, Any] = {
        "last_activity_at": now_iso,
        "status_updated_at": now_iso,
        "updated_at": now_iso,
        "conversation_status_at": now_iso,
    }

    status = normalize_reeval_status(result.get("status"))
    if status:
        patch["status"] = status

    new_amt = _float_or_none(result.get("amount"))
    if new_amt is not None:
        paid = float(inv.get("paid_amount") or 0)
        patch["amount"] = new_amt
        patch["balance_remaining"] = round(max(new_amt - paid, 0), 2)

    status_now = patch.get("status") or inv.get("status")
    if status_now == "promised":
        if result.get("promise_date"):
            patch["promise_date"] = result["promise_date"]
        elif inv.get("promise_date"):
            patch["promise_date"] = inv["promise_date"]
    else:
        patch["promise_date"] = None

    if "disputed_claim_amount" in result:
        patch["disputed_claim_amount"] = _float_or_none(result.get("disputed_claim_amount"))

    new_due = result.get("due_date")
    if new_due and new_due != inv.get("due_date"):
        patch["due_date"] = new_due
        patch["due_date_assumed"] = (result.get("due_date_status") or "") == "missing"
        if result.get("due_date_status"):
            patch["due_date_status"] = result["due_date_status"]

    new_ref = result.get("invoice_ref")
    cur_ref = inv.get("invoice_ref_normalized") or inv.get("invoice_ref")
    if new_ref and str(new_ref).strip() and str(new_ref).strip().lower() != "null":
        from ledger_reconcile import is_plausible_invoice_ref, normalize_invoice_ref
        if str(new_ref).upper().replace(" ", "") != str(cur_ref or "").upper().replace(" ", ""):
            norm = normalize_invoice_ref(new_ref, inv.get("source_subject"))
            if norm and is_plausible_invoice_ref(norm):
                patch["invoice_ref"] = new_ref if is_plausible_invoice_ref(str(new_ref)) else norm
                patch["invoice_ref_normalized"] = norm

    # Cadence pause is a product rule after status exists — not an event reducer.
    patch["chasing_paused"] = bool(
        (patch.get("status") or inv.get("status")) in _CADENCE_PAUSE_STATUSES
        or any(e.get("type") == "question" for e in events)
    )

    # Client payment claims are chips + a pending flag. Books paid_amount stays.
    claim_ev = next(
        (e for e in reversed(events)
         if e.get("type") in ("payment_claimed", "partial_payment")),
        None,
    )
    if (patch.get("status") or inv.get("status")) == "paid_unconfirmed" or claim_ev:
        patch["payment_claim_pending"] = True
        if claim_ev and claim_ev.get("amount") is not None:
            patch["payment_claim_amount"] = float(claim_ev["amount"])
    else:
        patch["payment_claim_pending"] = False
        patch["payment_claim_amount"] = None

    question = next((e for e in reversed(events) if e.get("type") == "question"), None)
    if question:
        patch["needs_reply"] = True
        if question.get("quote"):
            patch["needs_reply_quote"] = question["quote"]
            patch["needs_reply_at"] = now_iso
    else:
        patch["needs_reply"] = False

    approved = next((e for e in reversed(events) if e.get("type") == "approved"), None)
    if approved:
        patch["client_approved"] = True
        patch["approved_at"] = now_iso
        if approved.get("quote"):
            patch["approval_quote"] = approved["quote"]

    if any(e.get("type") in _CLIENT_CHIP_TYPES for e in events):
        patch["last_client_reply_at"] = now_iso
        patch["watching_for_reply"] = False
        patch["client_ever_replied"] = True

    return patch


async def apply_rulebook_result(
    db,
    user_id,
    inv: dict,
    result: dict,
    messages: list[dict],
    *,
    my_email: str,
    now_iso: str,
    considered_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Persist OpenAI output: model fields = ledger, new_events = chips."""
    _ = my_email
    considered = list(considered_ids or [])
    for ev in result.get("new_events") or []:
        if ev.get("message_id"):
            considered.append(ev["message_id"])
    await mark_reeval_seen(db, inv["_id"], considered)

    if (inv.get("status") or "") in _BOOKS_LOCKED_STATUSES:
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "conversation_status_at": now_iso,
                "updated_at": now_iso,
            }},
        )
        return {"state_changes": 0, "events": [], "skipped": "books_locked"}

    events = rulebook_events_to_write_events(
        result,
        invoice_ref=inv.get("invoice_ref_normalized") or inv.get("invoice_ref"),
    )
    for e in events:
        if e.get("type") == "correction" and e.get("old_amount") is None:
            e["old_amount"] = float(inv.get("amount") or 0)

    messages_by_id = {m["id"]: m for m in messages if m.get("id")}
    written = await _write_timeline_chips(
        db, user_id, inv, events, messages_by_id, now_iso,
    )

    before = {
        "status": inv.get("status"),
        "amount": inv.get("amount"),
        "promise_date": inv.get("promise_date"),
        "disputed_claim_amount": inv.get("disputed_claim_amount"),
    }
    patch = _ledger_patch(inv, result, events, now_iso)
    await db.invoices.update_one({"_id": inv["_id"]}, {"$set": patch})
    inv.update(patch)
    changed = any(patch.get(k, before[k]) != before[k] for k in before)
    return {
        "state_changes": 1 if changed else 0,
        "events": written,
        "status": patch.get("status") or inv.get("status"),
    }
