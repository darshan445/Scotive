"""Module 4 — Attach Gmail conversations to QBO invoices.

Uses the same bulk Gmail list/batch pattern as seed/incremental, then hands
off to existing in-thread + out-of-thread re-eval (rulebook_reeval). Does not
replace or rewrite amount/status logic.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from client_sweep import (
    AMOUNT_TOKEN_RE,
    _extract_email_addr,
    parse_email_date,
    preprocess_body,
)
from gmail_client import GmailAuthError, get_access_token, get_messages_batch, list_message_ids
from ledger_reconcile import OPEN_INVOICE_STATUSES, amounts_close
from post_track_enrichment import _gmail_after_date, _invoice_anchor_dt

logger = logging.getLogger("scotive.qbo_conversation")

MATCH_LIST_PAGES = 4
MATCH_MAX_MSGS = 80


def _has_real_client_email(inv: dict) -> bool:
    email = (inv.get("counterparty_email") or "").strip().lower()
    if not email or "@" not in email:
        return False
    if email.startswith("qbo:"):
        return False
    return True


def _score_thread(msgs: list[dict], invoice: dict) -> int:
    """Higher = better match for this invoice among client threads."""
    hay = " ".join(
        " ".join([
            m.get("subject") or "",
            preprocess_body(m.get("body") or "", 3000),
            m.get("snippet") or "",
        ])
        for m in msgs
    )
    hay_upper = hay.upper()
    score = 0
    ref = (invoice.get("invoice_ref_normalized") or invoice.get("invoice_ref") or "").strip()
    if ref and ref.upper() in hay_upper:
        score += 100
    amt = invoice.get("amount")
    if amt is not None:
        for m in AMOUNT_TOKEN_RE.finditer(hay):
            num = re.sub(r"[^\d.]", "", m.group().replace(",", ""))
            try:
                if amounts_close(float(num), float(amt)):
                    score += 40
                    break
            except ValueError:
                pass
    # Prefer real conversations (both directions) over one-sided noise
    senders = {_extract_email_addr(m.get("from", "")) for m in msgs}
    client = (invoice.get("counterparty_email") or "").lower()
    if client and any(s == client for s in senders):
        score += 10
    if len(msgs) > 1:
        score += 5
    return score


async def _bulk_client_messages(
    access: str,
    client_email: str,
    after: str,
    *,
    invoice_ref: str | None = None,
) -> list[dict]:
    """Same list_message_ids → get_messages_batch pattern as seed/incremental."""
    email = client_email.lower().strip()
    queries = [f"(from:{email} OR to:{email}) after:{after}"]
    # Optional tightener — still constrained to client + after date
    if invoice_ref:
        safe = re.sub(r"[^\w.\-#/]", " ", invoice_ref).strip()
        if safe:
            queries.append(f"(from:{email} OR to:{email}) after:{after} ({safe})")

    seen: set[str] = set()
    ids: list[str] = []
    for q in queries:
        try:
            page_ids = await list_message_ids(access, q, max_pages=MATCH_LIST_PAGES)
        except Exception as e:
            logger.warning("qbo.conv LIST FAIL email=%s q=%r err=%s", email, q[:80], e)
            continue
        for mid in page_ids:
            if mid not in seen:
                seen.add(mid)
                ids.append(mid)

    ids = ids[:MATCH_MAX_MSGS]
    if not ids:
        return []
    try:
        return await get_messages_batch(access, ids)
    except Exception as e:
        logger.warning("qbo.conv BATCH FAIL email=%s err=%s", email, e)
        return []


def _pick_best_thread(
    messages: list[dict],
    invoice: dict,
    *,
    my_email: str,
) -> tuple[Optional[str], Optional[str]]:
    """Group bulk results by thread; return (thread_id, anchor_message_id)."""
    client = (invoice.get("counterparty_email") or "").lower()
    my = (my_email or "").lower()
    anchor_dt = _invoice_anchor_dt(invoice)

    by_thread: dict[str, list[dict]] = {}
    for msg in messages:
        tid = msg.get("thread_id")
        if not tid:
            continue
        msg_dt = parse_email_date(msg.get("date"))
        if msg_dt and msg_dt < anchor_dt:
            continue
        # Keep messages involving the client (in or out)
        frm = _extract_email_addr(msg.get("from", ""))
        to_raw = msg.get("to") or ""
        involves_client = frm == client or client in (to_raw or "").lower()
        involves_me = frm == my or my in (to_raw or "").lower()
        if not (involves_client or involves_me):
            continue
        by_thread.setdefault(tid, []).append(msg)

    if not by_thread:
        return None, None

    best_tid = None
    best_score = -1
    best_anchor = None
    for tid, msgs in by_thread.items():
        score = _score_thread(msgs, invoice)
        if score > best_score:
            best_score = score
            best_tid = tid
            # Prefer earliest message on/after invoice date as anchor
            ordered = sorted(
                msgs,
                key=lambda m: (parse_email_date(m.get("date")) or datetime(1970, 1, 1, tzinfo=timezone.utc)),
            )
            best_anchor = ordered[0].get("id") if ordered else None

    # Require some signal when multiple threads exist (avoid random attach)
    if len(by_thread) > 1 and best_score < 10:
        logger.info(
            "qbo.conv SKIP ambiguous inv=%s threads=%s best_score=%s",
            invoice.get("_id"), len(by_thread), best_score,
        )
        return None, None

    return best_tid, best_anchor


async def _attach_thread(db, invoice: dict, thread_id: str, anchor_id: Optional[str], now_iso: str) -> None:
    patch: dict[str, Any] = {
        "source_thread_id": thread_id,
        "conversation_matched_at": now_iso,
        "updated_at": now_iso,
    }
    # Keep synthetic qbo source_message_id for identity; store Gmail anchor separately.
    if anchor_id and not str(invoice.get("source_message_id") or "").startswith("qbo:"):
        pass
    elif anchor_id:
        patch["gmail_anchor_message_id"] = anchor_id
    await db.invoices.update_one({"_id": invoice["_id"]}, {"$set": patch})
    await db.invoice_events.insert_one({
        "user_id": invoice["user_id"],
        "invoice_id": invoice["_id"],
        "action": "qbo_conversation_matched",
        "at": now_iso,
        "meta": {
            "source_thread_id": thread_id,
            "gmail_anchor_message_id": anchor_id,
            "qbo_id": invoice.get("qbo_id"),
        },
    })


async def _set_job(db, job_id, **fields) -> None:
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.qbo_pipeline_jobs.update_one({"_id": job_id}, {"$set": fields})


async def get_qbo_pipeline_status(db, user_id) -> dict[str, Any] | None:
    """Latest QBO conversation pipeline job for dashboard progress."""
    job = await db.qbo_pipeline_jobs.find_one(
        {"user_id": user_id},
        sort=[("started_at", -1)],
    )
    if not job:
        return None
    return {
        "job_id": str(job["_id"]),
        "status": job.get("status") or "idle",
        "phase": job.get("phase") or "idle",
        "total": int(job.get("total") or 0),
        "examined": int(job.get("examined") or 0),
        "matched": int(job.get("matched") or 0),
        "reevaluated": int(job.get("reevaluated") or 0),
        "skipped_no_email": int(job.get("skipped_no_email") or 0),
        "skipped_no_thread": int(job.get("skipped_no_thread") or 0),
        "errors": int(job.get("errors") or 0),
        "error": job.get("error"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }


async def enqueue_qbo_conversation_match(
    db,
    user_id,
    *,
    invoice_ids: list | None = None,
) -> dict[str, Any]:
    """Start conversation match + re-eval in the background. Idempotent if already running."""
    import asyncio

    existing = await db.qbo_pipeline_jobs.find_one({
        "user_id": user_id,
        "status": {"$in": ["queued", "running"]},
    })
    if existing:
        return {
            "job_id": str(existing["_id"]),
            "status": existing.get("status"),
            "deduped": True,
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    res = await db.qbo_pipeline_jobs.insert_one({
        "user_id": user_id,
        "status": "queued",
        "phase": "queued",
        "total": 0,
        "examined": 0,
        "matched": 0,
        "reevaluated": 0,
        "invoice_ids": [str(x) for x in (invoice_ids or [])] or None,
        "started_at": now_iso,
        "updated_at": now_iso,
    })
    job_id = res.inserted_id
    asyncio.create_task(_run_pipeline_job(db, user_id, job_id, invoice_ids=invoice_ids))
    return {"job_id": str(job_id), "status": "queued", "deduped": False}


async def _run_pipeline_job(
    db,
    user_id,
    job_id,
    *,
    invoice_ids: list | None = None,
) -> None:
    try:
        await _set_job(db, job_id, status="running", phase="matching")
        counts = await match_qbo_invoice_conversations(
            db, user_id, invoice_ids=invoice_ids, reeval=True, job_id=job_id,
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        await _set_job(
            db, job_id,
            status="complete",
            phase="complete",
            examined=counts.get("examined", 0),
            matched=counts.get("matched", 0),
            reevaluated=counts.get("reevaluated", 0),
            skipped_no_email=counts.get("skipped_no_email", 0),
            skipped_no_thread=counts.get("skipped_no_thread", 0),
            already_matched=counts.get("already_matched", 0),
            errors=counts.get("errors", 0),
            total=counts.get("examined", 0),
            finished_at=now_iso,
        )
    except Exception as e:
        logger.exception("qbo.pipeline job fail user=%s: %s", user_id, e)
        await _set_job(
            db, job_id,
            status="error",
            phase="error",
            error=str(e)[:500],
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


async def match_qbo_invoice_conversations(
    db,
    user_id,
    *,
    invoice_ids: list | None = None,
    reeval: bool = True,
    job_id=None,
) -> dict[str, Any]:
    """Find Gmail threads for QBO rows missing conversation; then existing re-eval.

    Returns counts: examined, matched, skipped_no_email, skipped_no_thread, reevaluated, errors.
    Set reeval=False when the caller will run Stage 4 itself (e.g. incremental).
    Optional job_id writes progress for the dashboard banner.
    """
    counts = {
        "examined": 0,
        "matched": 0,
        "skipped_no_email": 0,
        "skipped_no_thread": 0,
        "already_matched": 0,
        "reevaluated": 0,
        "errors": 0,
    }

    async def _progress(**kwargs):
        if job_id is not None:
            await _set_job(db, job_id, **kwargs)

    query: dict[str, Any] = {
        "user_id": user_id,
        "qbo_id": {"$type": "string"},
        "status": {"$in": list(OPEN_INVOICE_STATUSES)},
    }
    if invoice_ids:
        from bson import ObjectId
        oids = []
        for raw in invoice_ids:
            try:
                oids.append(ObjectId(str(raw)) if not hasattr(raw, "binary") else raw)
            except Exception:
                continue
        if not oids:
            return counts
        query["_id"] = {"$in": oids}

    invoices = []
    async for inv in db.invoices.find(query):
        invoices.append(inv)

    total = len(invoices)
    await _progress(phase="matching", total=total, examined=0, matched=0)

    if not invoices:
        return counts

    gmail = await db.gmail_connections.find_one({"user_id": user_id})
    if not gmail or gmail.get("status") not in ("connected", "send_missing"):
        counts["skipped"] = "no_gmail"
        return counts

    try:
        access = await get_access_token(db, user_id)
    except GmailAuthError as e:
        logger.warning("qbo.conv auth fail user=%s err=%s", user_id, e)
        counts["skipped"] = "gmail_auth"
        return counts

    my_email = (gmail.get("email") or "").lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    newly_matched: list[dict] = []
    matched_ids: list[str] = []

    for inv in invoices:
        counts["examined"] += 1
        if inv.get("source_thread_id"):
            counts["already_matched"] += 1
            await _progress(
                examined=counts["examined"],
                matched=counts["matched"],
                already_matched=counts["already_matched"],
            )
            continue
        if not _has_real_client_email(inv):
            counts["skipped_no_email"] += 1
            await _progress(examined=counts["examined"])
            continue

        email = (inv.get("counterparty_email") or "").strip().lower()
        after = _gmail_after_date(_invoice_anchor_dt(inv))
        ref = inv.get("invoice_ref_normalized") or inv.get("invoice_ref")
        try:
            msgs = await _bulk_client_messages(access, email, after, invoice_ref=ref)
            tid, anchor = _pick_best_thread(msgs, inv, my_email=my_email)
            if not tid:
                counts["skipped_no_thread"] += 1
                await _progress(examined=counts["examined"])
                continue
            await _attach_thread(db, inv, tid, anchor, now_iso)
            inv["source_thread_id"] = tid
            newly_matched.append(inv)
            matched_ids.append(str(inv["_id"]))
            counts["matched"] += 1
            await _progress(
                examined=counts["examined"],
                matched=counts["matched"],
            )
        except Exception as e:
            logger.exception("qbo.conv match fail inv=%s: %s", inv.get("_id"), e)
            counts["errors"] += 1
            await _progress(examined=counts["examined"], errors=counts["errors"])

    if newly_matched and reeval:
        await _progress(phase="deciding_status", matched=counts["matched"])
        # Hand off to existing Stage-4 re-eval (in-thread + OOT + rulebook). No new logic.
        from incremental_sync import _reevaluate_tracked

        window_start = min(_invoice_anchor_dt(inv) for inv in newly_matched)
        triggered = {inv["_id"]: [] for inv in newly_matched}
        try:
            reeval_stats = await _reevaluate_tracked(
                db, user_id, access, my_email, window_start, triggered, now_iso,
            )
            counts["reevaluated"] = reeval_stats.get("reevaluated", 0)
            counts["reeval"] = reeval_stats
            await _progress(reevaluated=counts["reevaluated"])
        except Exception as e:
            logger.exception("qbo.conv reeval fail user=%s: %s", user_id, e)
            counts["errors"] += 1
            await _progress(errors=counts["errors"])
    elif newly_matched:
        counts["reeval_deferred"] = len(newly_matched)

    counts["matched_ids"] = matched_ids
    logger.info("qbo.conv DONE user=%s counts=%s", user_id, {
        k: counts[k] for k in counts if k not in ("reeval", "matched_ids")
    })
    return counts
