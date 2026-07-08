"""90-day sent-only seed scan for onboarding curation.

Finds invoice candidates from sent mail — does NOT write to the ledger until
the user confirms via POST /seed/confirm.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from client_sweep import (
    AMOUNT_TOKEN_RE,
    CONSUMER_DOMAINS,
    _parse_msg_date,
    _sender_domain,
    merge_candidates_by_domain,
    persist_client_state,
)
from prior_chase import prior_followup_fields
from ledger_reconcile import (
    client_identity_key,
    enrich_invoice_doc,
    normalize_invoice_ref,
    normalize_source_date,
    normalize_subject,
    upsert_sweep_invoice,
)

logger = logging.getLogger("scotive.seed")

SEED_DAYS = 90

CURRENCY_MAP = {
    "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR", "£": "GBP",
    "₹": "INR", "inr": "INR", "rs": "INR", "rs.": "INR",
}

NET_TERMS_RE = re.compile(r"net\s*(\d+)", re.I)
DUE_ON_RE = re.compile(
    r"(?:due\s*(?:date|on|by|is)?[:\s]+|payment\s+due[:\s]+|due\s+will\s+be\s+on\s+)"
    r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|"
    r"\d{1,2}[/\-\.][A-Za-z]{3,9}(?:[/\-\.]\d{2,4})?|"
    r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}|"
    r"\w+\s+\d{1,2},?\s+\d{4})",
    re.I,
)


def seed_window_clause() -> str:
    return f"newer_than:{SEED_DAYS}d"


def seed_queries() -> list[str]:
    from gmail_sync import sent_mail_queries
    return sent_mail_queries("onboarding")


def _parse_iso_date(raw: str, sent_dt: Optional[datetime] = None) -> Optional[str]:
    from promise_dates import anchor_from_dt, _parse_explicit_token

    raw = raw.strip()
    anchor = anchor_from_dt(sent_dt)
    token = _parse_explicit_token(raw, anchor)
    if token:
        return token
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw.replace(".", "/").strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def extract_amount_currency(msg: dict) -> tuple[Optional[float], str]:
    hay = " ".join([
        msg.get("subject", ""),
        msg.get("body", ""),
        msg.get("snippet", ""),
        " ".join(msg.get("attachment_names") or []),
    ])
    m = AMOUNT_TOKEN_RE.search(hay)
    if not m:
        return None, "USD"
    token = m.group().strip()
    cur = "USD"
    lower = token.lower()
    for sym, code in CURRENCY_MAP.items():
        if sym in token or sym in lower:
            cur = code
            break
    num = re.sub(r"[^\d.]", "", token.replace(",", ""))
    try:
        amount = float(num)
    except ValueError:
        return None, cur
    return (amount if amount > 0 else None), cur


def extract_due_date(msg: dict, sent_dt: Optional[datetime] = None) -> Optional[str]:
    """Extract due date from email/PDF text only — never from default payment terms."""
    from promise_dates import anchor_from_dt, extract_explicit_due_from_text, fresh_message_text, resolve_relative_date

    anchor = anchor_from_dt(sent_dt)
    body_fresh = fresh_message_text(msg.get("body"), msg.get("snippet"))
    hay = " ".join([
        msg.get("subject", ""),
        body_fresh,
        msg.get("pdf_text") or "",
    ])
    explicit = extract_explicit_due_from_text(hay, anchor)
    if explicit:
        return explicit
    dm = DUE_ON_RE.search(hay)
    if dm:
        parsed = _parse_iso_date(dm.group(1), sent_dt)
        if parsed:
            return parsed
    rel = resolve_relative_date(hay, anchor)
    if rel:
        return rel
    nm = NET_TERMS_RE.search(hay)
    if nm and sent_dt:
        days = int(nm.group(1))
        return (sent_dt + timedelta(days=days)).date().isoformat()
    return None


def _client_display_name(msg: dict, client_email: str) -> Optional[str]:
    to_raw = msg.get("to") or ""
    if client_email.lower() in to_raw.lower():
        before = to_raw.split(client_email)[0]
        name = before.strip().strip('"').strip("'").strip("<").strip()
        if name and "@" not in name and len(name) > 1:
            return name[:80]
    local = client_email.split("@")[0]
    if local and local not in CONSUMER_DOMAINS:
        return local.replace(".", " ").replace("_", " ").title()
    return None


def build_ledger_invoice_from_candidate(
    doc: dict,
    *,
    user_id,
    now_iso: str,
    today,
    due_date: str | None = None,
) -> dict:
    """Map a seed/sync candidate (post seed_ai enrichment) to a ledger invoice document."""
    from invoice_lifecycle import _parse_date

    if due_date is None:
        due_date = doc.get("due_date")

    status = doc.get("enriched_status") or "invoiced"
    due_dt = _parse_date(due_date)
    if due_dt and due_dt < today and status in ("invoiced", "overdue"):
        status = "overdue"
    elif due_dt and due_dt >= today and status == "overdue":
        status = "invoiced"

    balance = (
        doc.get("balance_remaining")
        if doc.get("balance_remaining") is not None
        else doc.get("amount") or 0
    )

    return enrich_invoice_doc({
        "user_id": user_id,
        "counterparty_email": doc["counterparty_email"],
        "counterparty_name": doc.get("counterparty_name"),
        "client_identity_key": doc.get("client_identity_key"),
        "amount": doc["amount"],
        "balance_remaining": float(balance),
        "paid_amount": float(doc.get("paid_amount") or 0),
        "currency": doc.get("currency") or "USD",
        "invoice_ref": doc.get("invoice_ref"),
        "invoice_ref_normalized": doc.get("invoice_ref_normalized"),
        "due_date": due_date,
        "due_date_assumed": False,
        "promise_date": doc.get("promise_date"),
        "status": status,
        "kind": "invoice_sent",
        "escalation_step_floor": int(doc.get("escalation_step_floor") or 0),
        "prior_chase_count": int(doc.get("prior_chase_count") or 0),
        **prior_followup_fields(doc),
        "source_message_id": doc.get("message_id"),
        "source_thread_id": doc.get("source_thread_id"),
        "source_subject": doc.get("source_subject"),
        "source_from": doc.get("source_from"),
        "source_date": doc.get("source_date"),
        "evidence_sentence": doc.get("status_evidence"),
        "confidence": float(doc.get("confidence") or 1.0),
        "created_at": now_iso,
    }, doc["counterparty_email"])


async def _ignored_ids(db, user_id) -> set[str]:
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    return set(state.get("seed_ignored_message_ids") or [])


def _collapse_seed_followups(candidates: list[dict]) -> list[dict]:
    """Drop reminder/chaser sends that belong to an earlier candidate for the same invoice."""
    ordered = sorted(candidates, key=lambda c: c.get("source_date") or "")
    index: dict[tuple, dict] = {}
    kept: list[dict] = []

    for c in ordered:
        ref = c.get("invoice_ref_normalized")
        thread = c.get("source_thread_id")
        ck = c.get("client_identity_key")
        subj = c.get("source_subject") or ""
        keys: list[tuple] = []
        if ref:
            keys.append(("ref", ck, ref))
        if thread:
            keys.append(("thread", ck, thread))

        duplicate = False
        for key in keys:
            if key not in index:
                continue
            prior = index[key]
            if is_invoice_followup(subj) or (ref and ref == prior.get("invoice_ref_normalized")):
                duplicate = True
                logger.info(
                    "seed SKIP followup msg=%s client=%s ref=%s",
                    c.get("message_id"), ck, ref,
                )
                break
        if duplicate:
            continue

        for key in keys:
            index[key] = c
        kept.append(c)
    return kept


async def run_seed_scan(db, user_id, job_id) -> None:
    """Onboarding: 90-day sent-mail scan → curation candidates."""
    from gmail_sync import run_onboarding_sync
    await run_onboarding_sync(db, user_id, job_id)


async def get_onboarding_state(db, user_id) -> dict[str, Any]:
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    open_statuses = ("invoiced", "overdue", "promised", "partially_paid", "promise_broken", "disputed")
    open_count = await db.invoices.count_documents({
        "user_id": user_id,
        "status": {"$in": list(open_statuses)},
    })

    if state.get("curation_complete"):
        if open_count == 0:
            return {"phase": "watching", "curation_complete": True}
        return {"phase": "complete", "curation_complete": True}

    inv_count = await db.invoices.count_documents({"user_id": user_id})
    if inv_count > 0 and not state.get("awaiting_curation"):
        if open_count == 0:
            return {"phase": "watching", "curation_complete": True, "legacy": True}
        return {"phase": "complete", "curation_complete": True, "legacy": True}

    job = await db.seed_jobs.find_one({"user_id": user_id}, sort=[("started_at", -1)])
    if not job:
        return {"phase": "needs_seed", "curation_complete": False}

    if job.get("status") in ("queued", "running"):
        phase = job.get("phase") or "fetching"
        return {
            "phase": "scanning",
            "scan_phase": phase,
            "curation_complete": False,
            "job_id": str(job["_id"]),
            "status": job.get("status"),
            "counts": job.get("counts", {}),
        }

    if job.get("status") == "error":
        return {
            "phase": "error",
            "curation_complete": False,
            "error": job.get("error"),
        }

    if job.get("status") == "complete" and not state.get("curation_complete"):
        pending = await db.seed_candidates.count_documents({
            "user_id": user_id, "job_id": job["_id"], "status": "pending",
        })
        return {
            "phase": "curating",
            "curation_complete": False,
            "job_id": str(job["_id"]),
            "candidate_count": pending,
        }

    return {"phase": "needs_seed", "curation_complete": False}


async def list_seed_candidates(db, user_id) -> list[dict]:
    job = await db.seed_jobs.find_one(
        {"user_id": user_id, "status": "complete"},
        sort=[("finished_at", -1)],
    )
    if not job:
        return []
    cursor = db.seed_candidates.find({
        "user_id": user_id,
        "job_id": job["_id"],
        "status": "pending",
    }).sort("source_date", -1)
    rows = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["job_id"] = str(doc["job_id"])
        rows.append(doc)
    return rows


async def confirm_seed_curation(
    db,
    user_id,
    candidate_ids: list[str],
    *,
    track_none: bool = False,
    due_dates: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Track selected candidates; ignore all others forever."""
    from bson import ObjectId
    from invoice_lifecycle import _parse_date, apply_past_due_transitions

    now_iso = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date()
    due_overrides = due_dates or {}
    job = await db.seed_jobs.find_one(
        {"user_id": user_id, "status": "complete"},
        sort=[("finished_at", -1)],
    )
    if not job:
        raise ValueError("No seed job found")

    pending = []
    async for doc in db.seed_candidates.find({
        "user_id": user_id,
        "job_id": job["_id"],
        "status": "pending",
    }):
        pending.append(doc)

    selected_set = set(candidate_ids) if not track_none else set()
    tracked = 0
    ignored_ids: list[str] = []
    tracked_invoice_ids: list[Any] = []

    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    anchor_map: dict[str, list[str]] = dict(state.get("anchor_map") or {})
    domains: set[str] = set(state.get("client_domains") or [])
    email_to_primary: dict[str, str] = dict(state.get("email_to_primary") or {})

    for doc in pending:
        cid = str(doc["_id"])
        mid = doc["message_id"]
        if cid in selected_set:
            if cid in due_overrides:
                due_date = due_overrides[cid] or None
            else:
                due_date = doc.get("due_date")

            inv_doc = build_ledger_invoice_from_candidate(
                doc,
                user_id=user_id,
                now_iso=now_iso,
                today=today,
                due_date=due_date,
            )
            outcome, inv_id = await upsert_sweep_invoice(db, user_id, inv_doc, now_iso=now_iso)
            if inv_id:
                tracked_invoice_ids.append(inv_id)
            if outcome == "created":
                tracked += 1

            email = doc["counterparty_email"].lower()
            if mid and mid not in (anchor_map.get(email) or []):
                anchor_map.setdefault(email, []).append(mid)
            dom = _sender_domain(email)
            if dom and dom not in CONSUMER_DOMAINS:
                domains.add(dom)
            await db.seed_candidates.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": "tracked", "updated_at": now_iso}},
            )
        else:
            ignored_ids.append(mid)
            await db.seed_candidates.update_one(
                {"_id": doc["_id"]},
                {"$set": {"status": "ignored", "updated_at": now_iso}},
            )

    anchor_map, email_to_primary = merge_candidates_by_domain(anchor_map)
    await persist_client_state(db, user_id, anchor_map, domains, email_to_primary)

    existing_ignored = list(state.get("seed_ignored_message_ids") or [])
    merged_ignored = list(dict.fromkeys(existing_ignored + ignored_ids))

    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {
            "curation_complete": True,
            "curation_skipped": track_none or len(selected_set) == 0,
            "awaiting_curation": False,
            "seed_ignored_message_ids": merged_ignored,
            "onboarding_completed_at": now_iso,
            "watching_sent_mail": True,
            "updated_at": now_iso,
        }},
        upsert=True,
    )

    # Safety pass — any invoiced rows with past due dates flip immediately
    past_due_flipped = await apply_past_due_transitions(db, user_id)

    from post_track_enrichment import delete_staging_for_job
    await delete_staging_for_job(db, user_id, job["_id"])

    return {
        "tracked": tracked,
        "ignored": len(ignored_ids),
        "past_due_flipped": past_due_flipped,
        "watching": track_none or len(selected_set) == 0,
    }


async def run_post_curation_enrichment(
    db,
    user_id,
    tracked_invoice_ids: list[Any] | None = None,
) -> dict[str, Any]:
    """Legacy hook — enrichment now runs before curation. No-op on confirm."""
    _ = (db, user_id, tracked_invoice_ids)
    return {"skipped": "enrichment_runs_before_curation"}
