"""Unipile after: parsing — YYYY/MM/DD must not become unix epoch 1970."""
from datetime import datetime

from gmail_client import parse_gmail_query


def test_after_slash_date_is_invoice_day_not_epoch_2025():
    parsed = parse_gmail_query(
        "(from:a@b.com OR to:a@b.com) after:2025/09/16"
    )
    after = parsed["after"]
    assert after is not None
    assert after.startswith("2025-09-15T") or after.startswith("2025-09-16T")
    assert "1970-01-01" not in after
    dt = datetime.fromisoformat(after.replace("Z", "+00:00"))
    assert dt.year == 2025


def test_after_hyphen_date():
    parsed = parse_gmail_query("from:a@b.com after:2026-01-02")
    after = parsed["after"]
    assert after.startswith("2026-01-0")
    assert "1970" not in after


def test_after_unix_epoch_still_works():
    # 2025-09-16 00:00:00 UTC
    parsed = parse_gmail_query("after:1757980800")
    after = parsed["after"]
    dt = datetime.fromisoformat(after.replace("Z", "+00:00"))
    assert dt.year == 2025
    assert dt.month == 9


def test_from_or_to_becomes_any_email():
    parsed = parse_gmail_query(
        "(from:client@agency.com OR to:client@agency.com) after:2025/09/16"
    )
    assert parsed["from_addrs"] == ["client@agency.com"]
    assert parsed["to_addrs"] == ["client@agency.com"]
    assert parsed["after"].startswith("2025-09-")
