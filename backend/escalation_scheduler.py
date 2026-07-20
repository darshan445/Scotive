"""Escalation ladder scheduler (F9b).

Reads user_settings.escalation_offsets and generates chase drafts on the right
day for every open invoice with a due_date. Drafts land in `chase_drafts` and
are NEVER auto-sent — the user must approve each one.

Design:
  offsets = [-3, 0, 3, 10]  # days relative to due_date
  For each open invoice with a due_date:
    d = today - due_date         # negative before due, positive after
    step_index = index of matching offset (exact match)
    If no draft exists for (invoice_id, step_index) → generate + store.
  Bonus step: promise_broken with promise_date in the past → firm-tone draft
  quoting the client's own words. Uses a dedicated step_index = "promise_broken".

The generator uses the same OpenRouter model as the manual draft endpoint,
plus optional late-fee wording on the final step when `late_fee_enabled`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from bson import ObjectId

from scan_pipeline import OPENROUTER_URL, OPENROUTER_MODEL

logger = logging.getLogger("scotive.escalation")

# Open statuses that are still worth chasing
CHASEABLE_STATUSES = ("invoiced", "overdue", "promise_broken", "partially_paid")

# How the 4-slot ladder maps to labels (index-aligned with default offsets)
STEP_LABELS = ["pre_due_nudge", "due_reminder", "firm_followup", "final_notice"]


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


def _tone_for_step(step_index, status):
    """Tone based on step position, with escalation. `step_index` can also be
    the string "promise_broken" for the special broken-promise draft.
    """
    if step_index == "promise_broken":
        return "firm"
    if status == "promise_broken":
        return "firm"
    if step_index == 0:
        return "friendly"
    if step_index == 1:
        return "friendly"
    if step_index == 2:
        return "firm"
    return "final"


def _step_label(step_index):
    if step_index == "promise_broken":
        return "promise_broken"
    if 0 <= step_index < len(STEP_LABELS):
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
    """Ask the LLM for a short professional chase email. Returns {subject, body}.

    Never raises — returns None on failure so the scheduler can skip and retry.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    sign_rule = (
        f"Always end the body with a short professional sign-off (e.g. Best regards,) "
        f"then the sender's name on its own line, exactly: {signer_name}. "
        if signer_name
        else "Always end the body with a short professional sign-off and the sender's name. "
    )
    system = (
        "You draft short, professional payment follow-up emails for a small business owner. "
        "Under 120 words. Plain professional tone. No 'hope this finds you well'. "
        "Always include invoice ref (if any), amount, due date. "
        "On a broken promise, quote the client's own stated date verbatim. "
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
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": os.environ.get("FRONTEND_URL", "https://scotive.app"),
                    "X-Title": "Scotive",
                },
                json={
                    "model": OPENROUTER_MODEL,
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
            content = r.json()["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:  # pragma: no cover
        logger.warning("Escalation draft error: %s", e)
        return None


async def _draft_exists(db, user_id, invoice_id, step_key) -> bool:
    doc = await db.chase_drafts.find_one(
        {"user_id": user_id, "invoice_id": invoice_id, "step_key": step_key,
         "status": {"$in": ["queued", "sent"]}},
        {"_id": 1},
    )
    return doc is not None


async def run_escalation_tick(db, user_id) -> dict:
    """Generate any missing chase drafts for this user based on today's date + config."""
    from feature_flags import chasing_timing_enabled
    from invoice_lifecycle import apply_stale_transitions

    counts = {"drafts_generated": 0, "skipped_existing": 0, "invoices_scanned": 0, "stale": 0}
    if not chasing_timing_enabled():
        counts["disabled"] = True
        return counts
    counts["stale"] = await apply_stale_transitions(db, user_id)

    settings = await db.user_settings.find_one({"user_id": user_id}) or {}
    offsets = settings.get("escalation_offsets", [-3, 0, 3, 10])
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

        # Post-chase ladder handles follow-ups after the user has sent one.
        if inv.get("watching_for_reply") or inv.get("last_chase_at") or inv.get("ladder_exhausted"):
            continue

        # ---- Regular offset-driven ladder --------------------------------
        due = _parse_date(inv.get("due_date"))
        if due:
            days_since_due = (today - due).days
            for i, off in enumerate(offsets):
                if days_since_due != off:
                    continue
                floor = int(inv.get("escalation_step_floor") or 0)
                if i < floor:
                    continue
                step_key = f"offset_{i}"
                if await _draft_exists(db, user_id, inv["_id"], step_key):
                    counts["skipped_existing"] += 1
                    continue
                tone = _tone_for_step(i, inv.get("status"))
                label = _step_label(i)
                draft = await generate_draft(
                    inv, tone, label, late_fee_text, signer_name=signer_name,
                )
                if not draft:
                    continue
                await db.chase_drafts.insert_one({
                    "user_id": user_id,
                    "invoice_id": inv["_id"],
                    "step_key": step_key,
                    "step_index": i,
                    "step_label": label,
                    "offset_days": off,
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
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                })
                counts["drafts_generated"] += 1

        # ---- Broken-promise ladder step ----------------------------------
        if inv.get("status") == "promise_broken":
            step_key = "promise_broken"
            if await _draft_exists(db, user_id, inv["_id"], step_key):
                counts["skipped_existing"] += 1
                continue
            promise = _parse_date(inv.get("promise_date"))
            if promise and promise > today:
                continue  # promise still in the future — nothing to escalate
            draft = await generate_draft(
                inv, "firm", "promise_broken", None, signer_name=signer_name,
            )
            if not draft:
                continue
            await db.chase_drafts.insert_one({
                "user_id": user_id,
                "invoice_id": inv["_id"],
                "step_key": step_key,
                "step_index": None,
                "step_label": "promise_broken",
                "offset_days": None,
                "tone": "firm",
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
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })
            counts["drafts_generated"] += 1

    return counts


async def escalate_all_users(db) -> dict:
    from feature_flags import chasing_timing_enabled

    totals = {"users": 0, "drafts_generated": 0}
    if not chasing_timing_enabled():
        totals["disabled"] = True
        return totals
    async for conn in db.gmail_connections.find({"status": "connected"}):
        uid = conn.get("user_id")
        if not uid:
            continue
        try:
            c = await run_escalation_tick(db, uid)
            totals["users"] += 1
            totals["drafts_generated"] += c.get("drafts_generated", 0)
        except Exception as e:
            logger.exception("Escalation failed for user %s: %s", uid, e)
    return totals
