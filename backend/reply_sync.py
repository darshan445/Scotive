"""Reply intelligence tick — process client thread messages during hourly sync."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from gmail_client import GmailAuthError, get_access_token, get_message, list_message_ids
from client_sweep import (
    AI_CONCURRENCY,
    MAX_CLIENTS_FOR_AI,
    assign_client_key,
    extract_client_with_ai,
    apply_client_result,
    load_blocklist,
    merge_candidates_by_domain,
    pass1_filter_anchor,
    pass2_collect_ids,
    pass2_filter_message,
    persist_client_state,
    primary_anchor_ids,
    select_messages_for_client,
    _sender_domain,
    CONSUMER_DOMAINS,
)

logger = logging.getLogger("scotive.reply_sync")

REPLY_WINDOW = "newer_than:7d"


async def run_reply_intelligence_tick(db, user_id) -> dict[str, Any]:
    """Process recent client messages and apply reply intelligence to open invoices."""
    from scan_pipeline import reconcile_receipts
    from invoice_event_idempotency import message_already_handled

    counts: dict[str, Any] = {
        "messages_fetched": 0,
        "messages_processed": 0,
        "events_applied": 0,
        "receipts_matched": 0,
    }
    conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        return {**counts, "skipped": "no_connection"}

    try:
        access = await get_access_token(db, user_id)
    except GmailAuthError:
        return {**counts, "skipped": "auth_error"}

    my_email = (conn.get("email") or "").lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    candidates: dict[str, list[str]] = dict(state.get("anchor_map") or {})
    domains: set[str] = set(state.get("client_domains") or [])
    client_emails: set[str] = set(state.get("client_identities") or list(candidates.keys()))
    email_to_primary: dict[str, str] = dict(state.get("email_to_primary") or {})

    # Refresh anchors from recent sent mail
    blocklist = await load_blocklist(db, user_id)
    for q in [
        f"in:sent {REPLY_WINDOW} subject:(invoice OR payment OR \"amount due\")",
        f'in:sent {REPLY_WINDOW} ("please pay" OR "payment due" OR "balance due")',
    ]:
        ids = await list_message_ids(access, q, max_pages=2)
        counts["messages_fetched"] += len(ids)
        for mid in ids:
            msg = await get_message(access, mid)
            if not msg:
                continue
            client = pass1_filter_anchor(msg, my_email, blocklist)
            if client and mid not in (candidates.get(client) or []):
                candidates.setdefault(client, []).append(mid)
                client_emails.add(client)
                dom = _sender_domain(client)
                if dom and dom not in CONSUMER_DOMAINS:
                    domains.add(dom)

    candidates, email_to_primary = merge_candidates_by_domain(candidates)
    client_emails = set(candidates.keys())

    if not client_emails:
        return counts

    recent_ids = await pass2_collect_ids(access, list(client_emails), domains, months=1)
    fresh: list[str] = []
    for mid in recent_ids[:80]:
        if not await message_already_handled(db, user_id, mid):
            fresh.append(mid)
    counts["messages_fetched"] += len(fresh)

    by_client: dict[str, list[dict]] = {c: [] for c in client_emails}
    seen: set[str] = set()
    for mid in fresh:
        msg = await get_message(access, mid)
        if not msg:
            continue
        ck = assign_client_key(msg, client_emails, domains, my_email, email_to_primary)
        if not ck:
            continue
        verdict, _ = pass2_filter_message(msg, seen)
        if verdict != "keep":
            continue
        seen.add(mid)
        by_client.setdefault(ck, []).append(msg)
        counts["messages_processed"] += 1

    sem = asyncio.Semaphore(AI_CONCURRENCY)
    for client in list(client_emails)[:MAX_CLIENTS_FOR_AI]:
        msgs = by_client.get(client) or []
        if not msgs:
            continue
        anchor_ids = candidates.get(client) or []
        for aid in anchor_ids:
            if not any(m["id"] == aid for m in msgs):
                am = await get_message(access, aid)
                if am:
                    msgs.append(am)
        anchor_ids = primary_anchor_ids(anchor_ids, msgs)
        selected, truncated = select_messages_for_client(msgs, set(anchor_ids))

        async with sem:
            result = await extract_client_with_ai(client, selected, anchor_ids, my_email, truncated)
        if not result:
            continue
        inv_c, rev_c = await apply_client_result(
            db, user_id, client, result, {m["id"]: m for m in selected}, my_email, now_iso, email_to_primary,
            pass1_anchor_ids=anchor_ids,
        )
        if inv_c or result.get("events"):
            counts["events_applied"] += 1

    try:
        recon = await reconcile_receipts(db, user_id)
        counts["receipts_matched"] = recon.get("matched", 0)
    except Exception as e:
        logger.warning("reply_sync reconcile failed user=%s err=%s", user_id, e)

    await persist_client_state(db, user_id, candidates, domains, email_to_primary)
    return counts
