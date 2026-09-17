"""Unit tests for Friendly cadence + pay-link helpers."""
from cadence import (
    client_is_silent,
    ensure_pay_link,
    extract_qbo_pay_url,
    last_friendly_index,
    owner_took_over,
    pick_cadence_action,
)


OFFSETS = [-3, 0, 7, 9]


def test_last_friendly_is_second_to_last():
    assert last_friendly_index(OFFSETS) == 2
    assert last_friendly_index([-3, 0, 9]) == 1


def test_silent_unpaid_ok():
    assert client_is_silent({"status": "overdue"}) is True
    assert client_is_silent({"status": "invoiced"}) is True


def test_pause_on_reply_and_states():
    assert client_is_silent({"status": "promised"}) is False
    assert client_is_silent({"status": "overdue", "last_client_reply_at": "2026-09-01"}) is False
    assert client_is_silent({"status": "overdue", "needs_reply": True}) is False
    assert client_is_silent({"status": "overdue", "chasing_paused": True}) is False
    assert client_is_silent({"status": "paid_unconfirmed"}) is False
    assert client_is_silent({"status": "disputed"}) is False


def test_owner_manual_followup_stops_auto():
    assert owner_took_over({"last_chase_at": "2026-09-10"}, OFFSETS) is True
    assert owner_took_over(
        {"last_chase_at": "2026-09-10", "current_escalation_step": 1}, OFFSETS,
    ) is False
    assert owner_took_over(
        {"last_chase_at": "2026-09-10", "current_escalation_step": 3}, OFFSETS,
    ) is True


def test_pre_due_sends_friendly():
    action, step = pick_cadence_action(-3, OFFSETS, set(), silent=True, auto_send=True, owner_took_over_chase=False)
    assert action == "send_friendly"
    assert step == 0


def test_due_catches_up_to_latest_friendly_only():
    action, step = pick_cadence_action(0, OFFSETS, set(), silent=True, auto_send=True, owner_took_over_chase=False)
    assert action == "send_friendly"
    assert step == 1  # due, not the missed pre-due


def test_day_7_another_friendly():
    action, step = pick_cadence_action(7, OFFSETS, {0, 1}, silent=True, auto_send=True, owner_took_over_chase=False)
    assert action == "send_friendly"
    assert step == 2


def test_day_8_still_friendly_zone():
    action, step = pick_cadence_action(8, OFFSETS, {0, 1, 2}, silent=True, auto_send=True, owner_took_over_chase=False)
    assert action == "skip"


def test_day_9_queues_firm():
    action, step = pick_cadence_action(9, OFFSETS, {0, 1, 2}, silent=True, auto_send=True, owner_took_over_chase=False)
    assert action == "queue_firm"
    assert step == 3


def test_late_onboard_does_not_blast_friendly():
    action, step = pick_cadence_action(20, OFFSETS, set(), silent=True, auto_send=True, owner_took_over_chase=False)
    assert action == "queue_firm"
    assert step == 3


def test_reply_skips():
    action, _ = pick_cadence_action(0, OFFSETS, set(), silent=False, auto_send=True, owner_took_over_chase=False)
    assert action == "skip"


def test_auto_send_off_queues_friendly():
    action, step = pick_cadence_action(0, OFFSETS, set(), silent=True, auto_send=False, owner_took_over_chase=False)
    assert action == "queue_friendly"
    assert step == 1


def test_extract_and_ensure_pay_link():
    assert extract_qbo_pay_url({"InvoiceLink": "https://qbo.example/pay/1"}) == "https://qbo.example/pay/1"
    assert extract_qbo_pay_url({"InvoiceLink": "not-a-url"}) is None
    body = ensure_pay_link("Please pay invoice 12.", "https://qbo.example/pay/1")
    assert "https://qbo.example/pay/1" in body
    again = ensure_pay_link(body, "https://qbo.example/pay/1")
    assert again.count("https://qbo.example/pay/1") == 1
