"""State-derived draft tone for Follow up / Reply composers.

Tone is computed from invoice facts + the user's escalation ladder offsets.
Never a user preference or form field. A regenerate note may nudge the
displayed register within this fixed taxonomy for that one generation only —
no persistence.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

# Fixed display labels (UI)
LABEL_FRIENDLY = "Friendly reminder"
LABEL_FIRM = "Firm follow-up"
LABEL_FINAL = "Final notice"
LABEL_CLARIFYING = "Clarifying reply"

# Internal register keys used in LLM instructions
TONE_FRIENDLY = "friendly"
TONE_FIRM = "firm"
TONE_FINAL = "final"
TONE_CLARIFYING = "clarifying"

LABEL_FOR_TONE = {
    TONE_FRIENDLY: LABEL_FRIENDLY,
    TONE_FIRM: LABEL_FIRM,
    TONE_FINAL: LABEL_FINAL,
    TONE_CLARIFYING: LABEL_CLARIFYING,
}

# Index-aligned with Settings ladder: Pre-due / Due-date / Firm / Final
STEP_LABELS = ["pre_due_nudge", "due_reminder", "firm_followup", "final_notice"]
DEFAULT_OFFSETS = [-3, 0, 3, 10]

# Chase register ladder (clarifying is a separate reply track)
CHASE_ORDER = [TONE_FRIENDLY, TONE_FIRM, TONE_FINAL]

TONE_INSTRUCTIONS = {
    TONE_FRIENDLY: (
        "Register: Friendly reminder. Warm, light-touch first contact. Assume goodwill. "
        "Clear ask, no pressure language."
    ),
    TONE_FIRM: (
        "Register: Firm follow-up. Direct and clear about the outstanding amount and any "
        "broken commitments. Still professional — not angry or threatening."
    ),
    TONE_FINAL: (
        "Register: Final notice. Last-step seriousness. State clearly this is a final "
        "follow-up before further action. Still professional — no legal threats you cannot make."
    ),
    TONE_CLARIFYING: (
        "Register: Clarifying reply. You are ANSWERING the client, not chasing payment. "
        "Address their question or dispute. Do not demand payment."
    ),
}

_SOFTEN_HINTS = (
    "soft", "easier", "friendli", "gentl", "lighter", "nicer", "warmer",
    "go easy", "go easier", "less firm", "tone down", "dial back",
)
_HARDEN_HINTS = (
    "firm", "strong", "harder", "tougher", "final", "urgent", "press",
    "more direct", "sharpen", "stronger",
)


def parse_date(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
        except Exception:
            try:
                return datetime.strptime(v[:10], "%Y-%m-%d").date()
            except Exception:
                return None
    return None


def ladder_step_reached(days_since_due: int, offsets: list, floor: int = 0) -> Optional[int]:
    """Highest ladder index whose offset threshold has been reached."""
    reached = None
    for i, off in enumerate(offsets):
        if i < floor:
            continue
        try:
            threshold = int(off)
        except (TypeError, ValueError):
            continue
        if days_since_due >= threshold:
            reached = i
    return reached


def tone_for_ladder_step(step_index: Optional[int]) -> str:
    """Mirror escalation_scheduler: steps 0–1 friendly, 2 firm, 3+ final."""
    if step_index is None:
        return TONE_FRIENDLY
    if step_index <= 1:
        return TONE_FRIENDLY
    if step_index == 2:
        return TONE_FIRM
    return TONE_FINAL


def step_label_for(step_index: Optional[int]) -> Optional[str]:
    if step_index is None:
        return None
    if 0 <= step_index < len(STEP_LABELS):
        return STEP_LABELS[step_index]
    return f"step_{step_index}"


def _result(
    tone: str,
    *,
    step_index: Optional[int] = None,
    step_label: Optional[str] = None,
    is_reply: bool = False,
) -> dict[str, Any]:
    return {
        "tone": tone,
        "tone_label": LABEL_FOR_TONE.get(tone, LABEL_FRIENDLY),
        "step_index": step_index,
        "step_label": step_label,
        "is_reply": is_reply,
    }


def derive_draft_tone(
    inv: dict,
    *,
    offsets: Optional[list] = None,
    dispute_rounds: int = 0,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Derive base tone from invoice state + Settings ladder offsets.

    Priority (most specific first):
      1. Second+ dispute rounds → Firm follow-up (still a reply situation)
      2. needs_reply or first-round dispute → Clarifying reply
      3. promise_broken → Firm follow-up
      4. promised (no break) → Friendly reminder
      5. Ladder position from due_date vs escalation_offsets (and current step)
      6. overdue without due_date → Firm follow-up
      7. Default → Friendly reminder
    """
    offsets = list(offsets if offsets is not None else DEFAULT_OFFSETS)
    today = today or datetime.now(timezone.utc).date()
    status = inv.get("status") or "invoiced"
    needs_reply = bool(inv.get("needs_reply"))
    is_disputed = status == "disputed" or inv.get("disputed_claim_amount") is not None

    # Multi-round disputes escalate past clarifying (acceptance: FS-413 style).
    if is_disputed and dispute_rounds >= 2:
        return _result(
            TONE_FIRM,
            step_index=2,
            step_label="firm_followup",
            is_reply=True,
        )

    if needs_reply or is_disputed:
        return _result(TONE_CLARIFYING, is_reply=True)

    if status == "promise_broken":
        return _result(
            TONE_FIRM,
            step_index=2,
            step_label="promise_broken",
            is_reply=False,
        )

    if status == "promised":
        return _result(
            TONE_FRIENDLY,
            step_label="promised",
            is_reply=False,
        )

    floor = int(inv.get("escalation_step_floor") or 0)
    step_index: Optional[int] = None
    due = parse_date(inv.get("due_date"))
    if due:
        days_since_due = (today - due).days
        step_index = ladder_step_reached(days_since_due, offsets, floor=floor)

    # Post-chase ladder may have advanced beyond the calendar offset match.
    current = inv.get("current_escalation_step")
    if current is not None:
        try:
            cur_i = int(current)
            if step_index is None or cur_i > step_index:
                step_index = cur_i
        except (TypeError, ValueError):
            pass

    if step_index is None and status == "overdue":
        return _result(
            TONE_FIRM,
            step_index=2,
            step_label="firm_followup",
            is_reply=False,
        )

    if step_index is None:
        # Fresh invoiced / no due date yet — first-touch friendly.
        return _result(
            TONE_FRIENDLY,
            step_index=0,
            step_label="pre_due_nudge",
            is_reply=False,
        )

    tone = tone_for_ladder_step(step_index)
    return _result(
        tone,
        step_index=step_index,
        step_label=step_label_for(step_index),
        is_reply=False,
    )


def apply_note_tone_nudge(tone: str, note: Optional[str]) -> str:
    """One-shot register nudge from a regenerate note. Stays in the fixed set.

    Soften/harden only when the note cleanly maps; otherwise keep base tone
    (no invented taxonomy).
    """
    if not note or not str(note).strip():
        return tone
    n = str(note).lower()
    soften = any(h in n for h in _SOFTEN_HINTS)
    harden = any(h in n for h in _HARDEN_HINTS)

    if tone == TONE_CLARIFYING:
        # Clarifying stays clarifying unless they explicitly ask to chase harder.
        if harden and not soften:
            return TONE_FIRM
        return tone

    if soften and not harden:
        if tone not in CHASE_ORDER:
            return TONE_FRIENDLY
        idx = CHASE_ORDER.index(tone)
        return CHASE_ORDER[max(0, idx - 1)]
    if harden and not soften:
        if tone not in CHASE_ORDER:
            return TONE_FIRM
        idx = CHASE_ORDER.index(tone)
        return CHASE_ORDER[min(len(CHASE_ORDER) - 1, idx + 1)]
    return tone


def tone_instruction(tone: str) -> str:
    return TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS[TONE_FRIENDLY])


def resolve_draft_tone(
    inv: dict,
    *,
    offsets: Optional[list] = None,
    dispute_rounds: int = 0,
    note: Optional[str] = None,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """Base state tone, optionally nudged by a one-time regenerate note."""
    base = derive_draft_tone(
        inv,
        offsets=offsets,
        dispute_rounds=dispute_rounds,
        today=today,
    )
    effective = apply_note_tone_nudge(base["tone"], note)
    out = dict(base)
    out["tone"] = effective
    out["tone_label"] = LABEL_FOR_TONE.get(effective, LABEL_FRIENDLY)
    out["base_tone"] = base["tone"]
    out["base_tone_label"] = base["tone_label"]
    return out
