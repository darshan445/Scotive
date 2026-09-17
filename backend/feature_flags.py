"""Process-wide feature flags from environment variables."""
from __future__ import annotations

import os


def _env_truthy(name: str, default: str = "false") -> bool:
    raw = (os.environ.get(name) or default).strip().lower()
    return raw in ("1", "true", "yes", "on")


def chasing_timing_enabled() -> bool:
    """Cadence scheduler + post-chase Firm drafts.

    On by default. Set ENABLE_CHASING_TIMING=false to pause the loop.
    """
    return _env_truthy("ENABLE_CHASING_TIMING", "true")
