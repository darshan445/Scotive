"""Process-wide feature flags from environment variables."""
from __future__ import annotations

import os


def _env_truthy(name: str, default: str = "false") -> bool:
    raw = (os.environ.get(name) or default).strip().lower()
    return raw in ("1", "true", "yes", "on")


def chasing_timing_enabled() -> bool:
    """Auto escalation ladder + post-chase follow-up drafts/banners.

    Off by default for MVP (manual draft-from-invoice still works).
    Set ENABLE_CHASING_TIMING=true to turn back on.
    """
    return _env_truthy("ENABLE_CHASING_TIMING", "false")
