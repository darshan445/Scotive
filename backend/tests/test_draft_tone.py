"""Unit tests for state-derived draft tone labeling."""
from datetime import date

from draft_tone import (
    LABEL_CLARIFYING,
    LABEL_FINAL,
    LABEL_FIRM,
    LABEL_FRIENDLY,
    apply_note_tone_nudge,
    derive_draft_tone,
    ladder_step_reached,
    resolve_draft_tone,
    tone_for_ladder_step,
)


OFFSETS = [-3, 0, 3, 10]
TODAY = date(2026, 7, 20)


def test_ladder_step_reached_thresholds():
    assert ladder_step_reached(-5, OFFSETS) is None
    assert ladder_step_reached(-3, OFFSETS) == 0
    assert ladder_step_reached(0, OFFSETS) == 1
    assert ladder_step_reached(3, OFFSETS) == 2
    assert ladder_step_reached(10, OFFSETS) == 3
    assert ladder_step_reached(15, OFFSETS) == 3


def test_tone_for_ladder_step():
    assert tone_for_ladder_step(0) == "friendly"
    assert tone_for_ladder_step(1) == "friendly"
    assert tone_for_ladder_step(2) == "firm"
    assert tone_for_ladder_step(3) == "final"


def test_fresh_invoiced_friendly():
    inv = {"status": "invoiced", "due_date": "2026-07-25"}  # due in 5 days — before pre-due
    r = derive_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert r["tone_label"] == LABEL_FRIENDLY
    assert r["is_reply"] is False


def test_pre_due_nudge_friendly():
    # due in 3 days → days_since_due = -3 → step 0
    inv = {"status": "invoiced", "due_date": "2026-07-23"}
    r = derive_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert r["tone"] == "friendly"
    assert r["tone_label"] == LABEL_FRIENDLY
    assert r["step_index"] == 0


def test_due_date_reminder_friendly():
    inv = {"status": "invoiced", "due_date": "2026-07-20"}
    r = derive_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert r["tone_label"] == LABEL_FRIENDLY
    assert r["step_index"] == 1


def test_firm_followup_ladder():
    inv = {"status": "overdue", "due_date": "2026-07-17"}  # 3 days past due
    r = derive_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert r["tone_label"] == LABEL_FIRM
    assert r["step_index"] == 2


def test_final_notice_ladder():
    inv = {"status": "overdue", "due_date": "2026-07-10"}  # 10 days past due
    r = derive_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert r["tone_label"] == LABEL_FINAL
    assert r["step_index"] == 3


def test_promise_broken_firm():
    inv = {
        "status": "promise_broken",
        "due_date": "2026-06-01",
        "promise_date": "2026-07-01",
        "evidence_sentence": "I'll pay by July 1",
    }
    r = derive_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert r["tone_label"] == LABEL_FIRM
    assert r["step_label"] == "promise_broken"


def test_promised_friendly():
    inv = {"status": "promised", "promise_date": "2026-07-25", "due_date": "2026-07-01"}
    r = derive_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert r["tone_label"] == LABEL_FRIENDLY


def test_needs_reply_clarifying():
    inv = {"status": "invoiced", "needs_reply": True, "due_date": "2026-07-01"}
    r = derive_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert r["tone_label"] == LABEL_CLARIFYING
    assert r["is_reply"] is True


def test_first_dispute_clarifying():
    inv = {"status": "disputed", "disputed_claim_amount": 750, "due_date": "2026-07-01"}
    r = derive_draft_tone(inv, offsets=OFFSETS, dispute_rounds=1, today=TODAY)
    assert r["tone_label"] == LABEL_CLARIFYING
    assert r["is_reply"] is True


def test_second_dispute_round_firmer():
    inv = {"status": "disputed", "disputed_claim_amount": 750, "due_date": "2026-07-01"}
    r = derive_draft_tone(inv, offsets=OFFSETS, dispute_rounds=2, today=TODAY)
    assert r["tone_label"] == LABEL_FIRM
    assert r["is_reply"] is True


def test_note_soften_nudge():
    assert apply_note_tone_nudge("firm", "go easier on them") == "friendly"
    assert apply_note_tone_nudge("final", "soften it") == "firm"
    assert apply_note_tone_nudge("friendly", "go easier") == "friendly"


def test_note_harden_nudge():
    assert apply_note_tone_nudge("friendly", "make it firmer") == "firm"
    assert apply_note_tone_nudge("firm", "final notice energy") == "final"


def test_note_unclear_keeps_base():
    assert apply_note_tone_nudge("firm", "mention the revised invoice") == "firm"


def test_resolve_note_nudges_label_not_persisted_base():
    inv = {"status": "promise_broken", "promise_date": "2026-07-01"}
    base = resolve_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert base["tone_label"] == LABEL_FIRM
    soft = resolve_draft_tone(inv, offsets=OFFSETS, note="go easier on them", today=TODAY)
    assert soft["tone_label"] == LABEL_FRIENDLY
    assert soft["base_tone_label"] == LABEL_FIRM
    # Re-resolve without note → back to state-derived firm
    again = resolve_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert again["tone_label"] == LABEL_FIRM


def test_current_escalation_step_advances():
    # Calendar says pre-due, but post-chase has advanced to firm step
    inv = {
        "status": "invoiced",
        "due_date": "2026-07-23",  # step 0 by calendar
        "current_escalation_step": 2,
    }
    r = derive_draft_tone(inv, offsets=OFFSETS, today=TODAY)
    assert r["tone_label"] == LABEL_FIRM
    assert r["step_index"] == 2
