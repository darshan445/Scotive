"""Friendly cadence scheduler.

Sends Friendly reminders on the due-date ladder while the client is silent.
Queues Firm for the owner to edit and send. Never auto-sends Firm/Final.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from cadence import (
    DEFAULT_OFFSETS,
    client_is_silent,
    ensure_pay_link,
    invoice_pay_url,
    owner_took_over,
    pay_link_prompt_lines,
    pick_cadence_action,
    sent_steps_from_invoice,
)
from draft_tone import STEP_LABELS, tone_for_ladder_step
from llm_client import (
    OPENAI_URL,
    openai_api_key,
    openai_headers,
    openai_message_content,
    openai_model,
)

logger = logging.getLogger("scotive.escalation")

CHASEABLE_STATUSES = ("invoiced", "overdue", "promise_broken", "partially_paid")


def _parse_date(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
        except Exception:
            try:
                return datetime.strptime(v[:10], "%Y-%m-%d").date()
            except Exception:
                return None
    return None


def _tone_for_step(step_index, status, offsets=None):
    if step_index == "promise_broken":
        return "firm"
    if status == "promise_broken":
        return "firm"
    return tone_for_ladder_step(step_index, offsets=offsets)


def _step_label(step_index):
    if step_index == "promise_broken":
        return "promise_broken"
    if isinstance(step_index, int) and 0 <= step_index < len(STEP_LABELS):
        return STEP_LABELS[step_index]
    return f"step_{step_index}"


async def generate_draft(
    inv: dict,
    tone: str,
    step_label: str,
    late_fee_text: Optional[str],
    note: str = "",
    signer_name: Optional[str] = None,
) -> Optional[dict]:
    """Ask the LLM for a short professional chase email. Returns {subject, body}."""
    api_key = openai_api_key()
    if not api_key:
        return None

    sign_rule = (
        f"Always end the body with a short professional sign-off (e.g. Best regards,) "
        f"then the sender's name on its own line, exactly: {signer_name}. "
        if signer_name
        else "Always end the body with a short professional sign-off and the sender's name. "
    )
    facts_rule, pay_line = pay_link_prompt_lines(inv)
    system = (
        "You draft short, professional payment follow-up emails for a small business owner. "
        "Under 120 words. Plain professional tone. No 'hope this finds you well'. "
        + facts_rule
        + "On a broken promise, quote the client's own stated date verbatim. "
        + sign_rule
        + "Never sound templated or AI-written. "
        "Output STRICT JSON: {\"subject\": string, \"body\": string}."
    )

    balance = inv.get("balance_remaining")
    if balance in (None, 0):
        balance = inv.get("amount")

    lines = [
        f"Client: {inv.get('counterparty_name') or inv.get('counterparty_email')}",
        f"Invoice ref: {inv.get('invoice_ref') or 'n/a'}",
        f"Amount owed: {balance} {inv.get('currency', 'USD')}",
        f"Due date: {inv.get('due_date') or 'n/a'}",
        pay_line,
        f"Promise date: {inv.get('promise_date') or 'n/a'}",
        f"Status: {inv.get('status')}",
        f"Step: {step_label}",
        f"Tone: {tone}",
        f"Client's own words (if broken promise): {inv.get('evidence_sentence') or ''}",
    ]
    if signer_name:
        lines.append(f"Sign emails as: {signer_name}")
    if inv.get("client_approved"):
        quote = inv.get("approval_quote")
        lines.append(
            "Client already approved/routed this invoice for payment"
            + (f' — their words: "{quote}"' if quote else "")
            + ". Keep the tone a gentle status check on processing, not an escalation."
        )
    if late_fee_text and step_label == "final_notice":
        lines.append(f"Late-fee wording (may reference verbatim): {late_fee_text}")
    if note:
        lines.append(f"User extra note: {note}")
    user_msg = "\n".join(lines)

    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(
                OPENAI_URL,
                headers=openai_headers(),
                json={
                    "model": openai_model(),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 400,
                },
            )
            if r.status_code != 200:
                logger.warning("Escalation draft AI failed: %s %s", r.status_code, r.text[:200])
                return None
            content = openai_message_content(r.json())
            draft = json.loads(content)
    except Exception as e:  # pragma: no cover
        logger.warning("Escalation draft error: %s", e)
        return None

    if not isinstance(draft, dict):
        return None
    pay_url = invoice_pay_url(inv)
    draft["body"] = ensure_pay_link(draft.get("body") or "", pay_url)
    draft["subject"] = draft.get("subject") or ""
    return draft


async def _draft_exists(db, user_id, invoice_id, step_key) -> bool:
    doc = await db.chase_drafts.find_one(
        {"user_id": user_id, "invoice_id": invoice_id, "step_key": step_key,
         "status": {"$in": ["queued", "sent"]}},
        {"_id": 1},
    )
    return doc is not None


def _draft_doc(user_id, inv, *, step_key, step_index, label, tone, draft, offset_days, status, extra=None):
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "user_id": user_id,
        "invoice_id": inv["_id"],
        "step_key": step_key,
        "step_index": step_index if step_index != "promise_broken" else None,
        "step_label": label,
        "offset_days": offset_days,
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
        "pay_url": invoice_pay_url(inv),
        "status": status,
        "generated_at": now_iso,
    }
    if extra:
        doc.update(extra)
    if status == "sent":
        doc["sent_at"] = now_iso
        doc["auto_sent"] = True
    return doc


async def _record_sent_step(db, inv, step_index: int):
    steps = sent_steps_from_invoice(inv)
    steps.add(int(step_index))
    await db.invoices.update_one(
        {"_id": inv["_id"]},
        {"$set": {"cadence_sent_steps": sorted(steps)}},
    )
    inv["cadence_sent_steps"] = sorted(steps)


async def _queue_followup_prompt(db, user_id, inv, draft_id, label: str):
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    pending = list(state.get("pending_followup_prompts") or [])
    inv_id_str = str(inv["_id"])
    if any(p.get("invoice_id") == inv_id_str for p in pending):
        return
    pending.append({
        "invoice_id": inv_id_str,
        "draft_id": str(draft_id),
        "counterparty_name": inv.get("counterparty_name"),
        "counterparty_email": inv.get("counterparty_email"),
        "amount": inv.get("amount"),
        "currency": inv.get("currency") or "USD",
        "step_label": label,
        "prompted_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"pending_followup_prompts": pending}},
        upsert=True,
    )


async def _apply_action(
    db, user_id, inv, *, action, step_index, offsets, late_fee_text, signer_name,
) -> str:
    """send_friendly | queue_friendly | queue_firm. Returns a counts key or empty."""
    from chase_send import deliver_chase_email

    step_key = f"offset_{step_index}"
    if await _draft_exists(db, user_id, inv["_id"], step_key):
        return "skipped_existing"

    tone = _tone_for_step(step_index, inv.get("status"), offsets=offsets)
    label = _step_label(step_index)
    off = offsets[step_index] if 0 <= step_index < len(offsets) else None
    draft = await generate_draft(inv, tone, label, late_fee_text, signer_name=signer_name)
    if not draft:
        return ""

    if action == "send_friendly":
        sent = await deliver_chase_email(
            db, user_id, inv,
            subject=draft.get("subject", ""),
            body=draft.get("body", ""),
            step_index=step_index,
        )
        if not sent.get("ok"):
            logger.info(
                "cadence auto-send skipped inv=%s reason=%s",
                inv.get("_id"), sent.get("reason"),
            )
            # Fall back to a queued draft so the owner can still send.
            ins = await db.chase_drafts.insert_one(_draft_doc(
                user_id, inv, step_key=step_key, step_index=step_index,
                label=label, tone=tone, draft=draft, offset_days=off, status="queued",
                extra={"auto_send_failed": sent.get("reason")},
            ))
            await _record_sent_step(db, inv, step_index)
            await _queue_followup_prompt(db, user_id, inv, ins.inserted_id, label)
            return "queued_fallback"
        await db.chase_drafts.insert_one(_draft_doc(
            user_id, inv, step_key=step_key, step_index=step_index,
            label=label, tone=tone, draft=draft, offset_days=off, status="sent",
        ))
        await _record_sent_step(db, inv, step_index)
        return "friendly_sent"

    ins = await db.chase_drafts.insert_one(_draft_doc(
        user_id, inv, step_key=step_key, step_index=step_index,
        label=label, tone=tone, draft=draft, offset_days=off, status="queued",
    ))
    await _record_sent_step(db, inv, step_index)
    if action == "queue_firm":
        await _queue_followup_prompt(db, user_id, inv, ins.inserted_id, label)
        return "firm_queued"
    return "drafts_generated"


async def run_escalation_tick(db, user_id) -> dict:
    """Generate / auto-send cadence steps for this user based on due dates."""
    from invoice_lifecycle import apply_stale_transitions

    counts = {
        "drafts_generated": 0,
        "friendly_sent": 0,
        "firm_queued": 0,
        "queued_fallback": 0,
        "skipped_existing": 0,
        "invoices_scanned": 0,
        "stale": 0,
        "paused": 0,
    }
    counts["stale"] = await apply_stale_transitions(db, user_id)

    settings = await db.user_settings.find_one({"user_id": user_id}) or {}
    offsets = list(settings.get("escalation_offsets") or DEFAULT_OFFSETS)
    auto_send = bool(settings.get("friendly_auto_send", True))
    late_fee_enabled = bool(settings.get("late_fee_enabled"))
    late_fee_text = settings.get("late_fee_text") if late_fee_enabled else None

    from gmail_oauth import ensure_gmail_account_name
    signer_name = await ensure_gmail_account_name(db, user_id)

    today = datetime.now(timezone.utc).date()

    async for inv in db.invoices.find({
        "user_id": user_id,
        "status": {"$in": list(CHASEABLE_STATUSES)},
        "chasing_paused": {"$ne": True},
        "tracking_paused": {"$ne": True},
    }):
        counts["invoices_scanned"] += 1

        if inv.get("status") == "promise_broken":
            step_key = "promise_broken"
            if await _draft_exists(db, user_id, inv["_id"], step_key):
                counts["skipped_existing"] += 1
                continue
            promise = _parse_date(inv.get("promise_date"))
            if promise and promise > today:
                continue
            draft = await generate_draft(
                inv, "firm", "promise_broken", None, signer_name=signer_name,
            )
            if not draft:
                continue
            ins = await db.chase_drafts.insert_one(_draft_doc(
                user_id, inv, step_key=step_key, step_index="promise_broken",
                label="promise_broken", tone="firm", draft=draft,
                offset_days=None, status="queued",
            ))
            await _queue_followup_prompt(db, user_id, inv, ins.inserted_id, "promise_broken")
            counts["firm_queued"] += 1
            continue

        silent = client_is_silent(inv)
        if not silent:
            counts["paused"] += 1
            continue

        due = _parse_date(inv.get("due_date"))
        if not due:
            continue
        days_since_due = (today - due).days
        sent = sent_steps_from_invoice(inv)
        action, step_index = pick_cadence_action(
            days_since_due,
            offsets,
            sent,
            silent=True,
            auto_send=auto_send,
            owner_took_over_chase=owner_took_over(inv, offsets),
        )
        if action == "skip" or step_index is None:
            continue
        key = await _apply_action(
            db, user_id, inv,
            action=action,
            step_index=step_index,
            offsets=offsets,
            late_fee_text=late_fee_text,
            signer_name=signer_name,
        )
        if key and key in counts:
            counts[key] += 1
        elif key == "drafts_generated":
            counts["drafts_generated"] += 1

    return counts


async def escalate_all_users(db) -> dict:
    totals = {"users": 0, "drafts_generated": 0, "friendly_sent": 0, "firm_queued": 0}
    seen_users: set = set()
    async for conn in db.gmail_connections.find({"status": "connected"}):
        uid = conn.get("user_id")
        if not uid or uid in seen_users:
            continue
        seen_users.add(uid)
        try:
            c = await run_escalation_tick(db, uid)
            totals["users"] += 1
            totals["drafts_generated"] += c.get("drafts_generated", 0)
            totals["friendly_sent"] += c.get("friendly_sent", 0)
            totals["firm_queued"] += c.get("firm_queued", 0)
        except Exception as e:
            logger.exception("Escalation failed for user %s: %s", uid, e)
    return totals
