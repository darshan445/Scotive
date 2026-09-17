"""Onboarding state + ledger helpers.

Invoices enter the ledger from the connected invoicing tool (QuickBooks today).
Gmail/Outlook is used to match conversations to those invoices — not as a
90-day sent-mail seed.
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
    is_invoice_followup,
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

    base = {
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
        "due_date_assumed": (
            (doc.get("due_date_status") or "") == "missing"
            if doc.get("due_date_status") is not None
            else bool(doc.get("due_date_assumed"))
        ),
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
    }

    if doc.get("client_approved"):
        base["client_approved"] = True
        if doc.get("approval_quote"):
            base["approval_quote"] = doc["approval_quote"]
    if doc.get("due_date_status"):
        base["due_date_status"] = doc["due_date_status"]
    if doc.get("needs_reply"):
        base["needs_reply"] = True
        if doc.get("needs_reply_quote"):
            base["needs_reply_quote"] = doc["needs_reply_quote"]
    if doc.get("dispute_kind"):
        base["dispute_kind"] = doc["dispute_kind"]
    if doc.get("disputed_claim_amount") is not None:
        base["disputed_claim_amount"] = float(doc["disputed_claim_amount"])
    if doc.get("payment_claim_amount") is not None:
        base["payment_claim_amount"] = float(doc["payment_claim_amount"])
        base["payment_claim_pending"] = bool(doc.get("payment_claim_pending", True))
        if doc.get("payment_claim_quote"):
            base["payment_claim_quote"] = doc["payment_claim_quote"]
    # PRD §8: promise and dispute pause chasing; a payment claim awaits confirmation.
    if status in ("promised", "disputed", "paid_unconfirmed") or base.get("payment_claim_pending"):
        base["chasing_paused"] = True
    if status == "paid_unconfirmed" or base.get("payment_claim_pending"):
        # Pre-claim state for "Not yet" reverts — date-driven, never assume overdue.
        if not base.get("status_before_claim"):
            base["status_before_claim"] = "overdue" if (due_dt and due_dt < today) else "invoiced"

    return enrich_invoice_doc(base, doc["counterparty_email"])


async def _ignored_ids(db, user_id) -> set[str]:
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    ignored = set(state.get("seed_ignored_message_ids") or [])
    async for doc in db.seed_candidates.find(
        {"user_id": user_id, "status": "pending"},
        {"message_id": 1},
    ):
        mid = doc.get("message_id")
        if mid:
            ignored.add(mid)
    return ignored


def collapse_followups_incremental(index: dict, candidates: list[dict]) -> list[dict]:
    """Drop reminder/chaser sends that belong to an earlier candidate for the same invoice.

    `index` carries seen (ref/thread, client) keys across calls so streamed units
    dedupe against everything already written.

    Distinct invoice numbers on the SAME thread (multi-invoice email like
    "#M-14 and #J-19") are never collapsed into each other — even when the
    subject matches follow-up language ("Outstanding balances…").
    """
    ordered = sorted(candidates, key=lambda c: c.get("source_date") or "")
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
            prior_ref = prior.get("invoice_ref_normalized")
            # Same thread, different invoice numbers → keep both (multi-invoice send).
            if (
                key[0] == "thread"
                and ref
                and prior_ref
                and ref != prior_ref
            ):
                continue
            if is_invoice_followup(subj) or (ref and ref == prior_ref):
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


def _collapse_seed_followups(candidates: list[dict]) -> list[dict]:
    return collapse_followups_incremental({}, candidates)


async def run_seed_scan(db, user_id, job_id) -> None:
    """Retired — invoices come from the invoicing tool, not a 90-day sent-mail seed."""
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.seed_jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "status": "complete",
            "phase": "retired",
            "counts": {"candidates": 0, "retired": True},
            "finished_at": now_iso,
            "updated_at": now_iso,
        }},
    )
    logger.info("seed scan retired user=%s job=%s", user_id, job_id)


async def unlock_qbo_dashboard(db, user_id) -> None:
    """Unlock the dashboard after mailbox + invoicing tool are connected."""
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {
            "dashboard_unlocked": True,
            "awaiting_curation": False,
            "curation_complete": True,
            "onboarding_completed_at": now_iso,
            "watching_sent_mail": True,
            "updated_at": now_iso,
        }},
        upsert=True,
    )


async def get_onboarding_state(db, user_id) -> dict[str, Any]:
    """Onboarding phases.

    phases:
      connections — mailbox + QuickBooks required; Next imports QBO invoices
      complete / watching — dashboard; conversation match runs in the background
    """
    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    open_statuses = ("invoiced", "overdue", "promised", "partially_paid", "promise_broken", "disputed")
    open_count = await db.invoices.count_documents({
        "user_id": user_id,
        "status": {"$in": list(open_statuses)},
    })
    gmail_conn = await db.gmail_connections.find_one({"user_id": user_id})
    gmail_connected = bool(
        gmail_conn and gmail_conn.get("status") in ("connected", "send_missing")
    )
    qbo_conn = await db.qbo_connections.find_one({"user_id": user_id, "status": "connected"})
    qbo_connected = bool(qbo_conn)
    last_import = (qbo_conn or {}).get("last_invoice_import_at")
    if isinstance(last_import, datetime):
        last_import = last_import.isoformat()
    qbo_progress = (qbo_conn or {}).get("import_progress")
    if not isinstance(qbo_progress, dict):
        qbo_progress = None
    continued = bool(state.get("onboarding_continued_at"))
    qbo_step = state.get("onboarding_qbo_step")
    dashboard_unlocked = bool(
        state.get("dashboard_unlocked")
        or state.get("onboarding_completed_at")
        or state.get("curation_complete")
    )

    base = {
        "gmail_connected": gmail_connected,
        "qbo_connected": qbo_connected,
        "last_invoice_import_at": last_import,
        "qbo_import_progress": qbo_progress,
        "onboarding_qbo_step": qbo_step,
        "onboarding_continued": continued,
        "dashboard_unlocked": dashboard_unlocked,
        "seed_review": None,
    }
    try:
        from qbo_conversation import get_qbo_pipeline_status
        base["qbo_pipeline"] = await get_qbo_pipeline_status(db, user_id)
    except Exception:
        base["qbo_pipeline"] = None

    # Already past onboarding (including legacy Gmail-curation accounts).
    if dashboard_unlocked:
        return {
            **base,
            "phase": "watching" if open_count == 0 else "complete",
            "curation_complete": True,
            "via_qbo": qbo_connected,
        }

    import_done = bool(last_import) or (qbo_progress or {}).get("status") == "complete"
    can_continue = gmail_connected and qbo_connected and import_done
    if not continued or not can_continue:
        return {
            **base,
            "phase": "connections",
            "curation_complete": False,
            "can_continue": can_continue,
        }

    await unlock_qbo_dashboard(db, user_id)
    open_count = await db.invoices.count_documents({
        "user_id": user_id,
        "status": {"$in": list(open_statuses)},
    })
    return {
        **base,
        "dashboard_unlocked": True,
        "phase": "watching" if open_count == 0 else "complete",
        "curation_complete": True,
        "via_qbo": True,
    }


async def continue_onboarding(db, user_id) -> dict[str, Any]:
    """User clicked Next. Requires a mailbox and QuickBooks (invoice source)."""
    gmail_conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not gmail_conn or gmail_conn.get("status") in (None, "revoked", "disconnected"):
        raise ValueError("Connect Gmail or Outlook before continuing.")

    qbo_conn = await db.qbo_connections.find_one({"user_id": user_id, "status": "connected"})
    if not qbo_conn:
        raise ValueError("Connect QuickBooks Online — invoices come from your invoicing tool.")
    progress = qbo_conn.get("import_progress") if isinstance(qbo_conn.get("import_progress"), dict) else {}
    if not qbo_conn.get("last_invoice_import_at") and progress.get("status") != "complete":
        raise ValueError("Wait until QuickBooks invoices are imported.")

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {
            "onboarding_continued_at": now_iso,
            "onboarding_qbo_step": "connected",
            "awaiting_curation": False,
            "updated_at": now_iso,
        }},
        upsert=True,
    )
    await unlock_qbo_dashboard(db, user_id)
    # Connect page already started matching; don't start a second job on Next.
    try:
        from qbo_conversation import enqueue_qbo_conversation_match, get_qbo_pipeline_status
        pipe = await get_qbo_pipeline_status(db, user_id)
        if not pipe or pipe.get("status") in (None, "error", "idle"):
            await enqueue_qbo_conversation_match(db, user_id)
    except Exception:
        logger.exception("conversation match enqueue after continue failed")
    return {"ok": True, "next": "dashboard", "qbo_connected": True}
