"""First-pass and Sync now share one current-state rule: after the newest message."""
from datetime import datetime, timezone
from pathlib import Path

from reeval_rulebook import RULEBOOK_PATH, build_tracked_state

_SEED = RULEBOOK_PATH.parent / "rulebook_seed_scan.txt"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reeval_prompt_is_same_job_for_first_pass_and_sync():
    text = _text(RULEBOOK_PATH)
    assert "First-pass (onboarding / newly" in text
    assert "SAME job" in text
    assert "CURRENT STATE = AFTER THE NEWEST MESSAGE (every status)" in text
    assert "A promise always supersedes prior status once made" not in text
    assert "governing signal" not in text
    assert "not specific to promised" in text
    assert "as_of_date" in text


def test_seed_scan_prompt_current_state_is_after_newest():
    text = _text(_SEED)
    assert "CURRENT STATE = AFTER THE NEWEST MESSAGE (every status)" in text
    assert "not specific to promised" in text
    assert "governing signal" not in text
    assert "the promise always governs over both" not in text


def test_tracked_state_includes_as_of_date():
    tracked = build_tracked_state(
        {"amount": 100, "status": "invoiced", "currency": "USD"},
        ["m1"],
    )
    assert tracked["as_of_date"] == datetime.now(timezone.utc).date().isoformat()
    assert tracked["processed_message_ids"] == ["m1"]
