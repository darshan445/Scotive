"""Gmail sync metadata for settings UI."""
from __future__ import annotations

from gmail_sync import INCREMENTAL_LOOKBACK


def attach_scan_metadata(settings: dict) -> dict:
    """Read-only fields for settings UI."""
    out = dict(settings)
    out["sync_lookback"] = INCREMENTAL_LOOKBACK
    out["sync_interval_hours"] = 1
    return out
