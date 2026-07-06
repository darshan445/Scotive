"""Hourly + manual incremental Gmail sync (last ~1 hour → ledger, no curation).

Same pipeline as onboarding but writes directly to the ledger — recent sent mail
is treated as the user's invoice without a confirmation step.
Also runs date-driven status transitions (past due, promise broken).
"""
from __future__ import annotations

import logging
from typing import Any

from gmail_sync import run_gmail_sync
from invoice_lifecycle import apply_past_due_transitions, apply_promise_broken_transitions
from post_chase import run_post_chase_tick
from reply_sync import run_reply_intelligence_tick
from invoice_event_idempotency import dedupe_stored_invoice_events

logger = logging.getLogger("scotive.incremental_sync")

# Recent mail: slightly lower bar than onboarding curation (user already confirmed historical)
INCREMENTAL_CONFIDENCE_MIN = 0.5


async def run_incremental_sync(db, user_id) -> dict[str, Any]:
    """One incremental pass — triggered by Sync now or the hourly background loop."""
    result = await run_gmail_sync(
        db,
        user_id,
        "incremental",
        confidence_min=INCREMENTAL_CONFIDENCE_MIN,
    )
    if result.get("skipped"):
        return result
    result["past_due_flipped"] = await apply_past_due_transitions(db, user_id)
    result["promise_broken_flipped"] = await apply_promise_broken_transitions(db, user_id)
    result["reply_sync"] = await run_reply_intelligence_tick(db, user_id)
    result["events_deduped"] = await dedupe_stored_invoice_events(db, user_id)
    result["post_chase"] = await run_post_chase_tick(db, user_id)
    return result


async def sync_all_users(db) -> dict[str, Any]:
    """Hourly background job: incremental sync for every connected user post-onboarding."""
    totals: dict[str, Any] = {
        "users": 0,
        "invoices_created": 0,
        "skipped": 0,
    }
    async for conn in db.gmail_connections.find({"status": "connected"}):
        uid = conn.get("user_id")
        if not uid:
            continue
        try:
            result = await run_incremental_sync(db, uid)
            if result.get("skipped"):
                totals["skipped"] += 1
                continue
            totals["users"] += 1
            totals["invoices_created"] += result.get("invoices_created", 0)
        except Exception as e:
            logger.exception("incremental sync FAILED user=%s err=%s", uid, e)
    return totals
