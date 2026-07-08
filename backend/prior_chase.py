"""Infer prior user follow-ups on seed-scan candidates (pre-Scotive chases)."""
from __future__ import annotations

import re
from email.utils import parseaddr
from typing import Optional

from ledger_reconcile import is_invoice_followup, parse_email_date

FINAL_CHASE_RE = re.compile(
    r"final\s+notice|last\s+(?:reminder|chance)|second\s+notice|third\s+notice|"
    r"urgent|immediate\s+payment|legal\s+action",
    re.I,
)
FIRM_CHASE_RE = re.compile(
    r"overdue|past\s+due|outstanding|firm\s+reminder|still\s+unpaid|"
    r"amount\s+outstanding|balance\s+due",
    re.I,
)


def _is_user_chase(msg: dict, invoice_msg: dict, my_email: str) -> bool:
    """Sent mail from the user after the invoice anchor that looks like a follow-up."""
    if msg.get("id") == invoice_msg.get("id"):
        return False
    sender = (parseaddr(msg.get("from") or "")[1] or "").lower()
    if sender != my_email.lower():
        return False
    inv_dt = parse_email_date(invoice_msg.get("source_date") or invoice_msg.get("date"))
    msg_dt = parse_email_date(msg.get("source_date") or msg.get("date"))
    if inv_dt and msg_dt and msg_dt <= inv_dt:
        return False
    subj = msg.get("subject") or ""
    body = " ".join([subj, msg.get("snippet") or "", msg.get("body") or ""])
    if is_invoice_followup(subj):
        return True
    if FINAL_CHASE_RE.search(body) or FIRM_CHASE_RE.search(body):
        return True
    if re.search(r"follow[\s\-]?up|reminder|chase|nudge|kindly\s+(?:pay|remit)", body, re.I):
        return True
    return False


def _related(msg: dict, invoice: dict) -> bool:
    if invoice.get("source_thread_id") and msg.get("thread_id") == invoice.get("source_thread_id"):
        return True
    # Cross-thread: being addressed to the same client is not enough — with several
    # invoices to one client that marks every later send as a chase of every earlier
    # invoice. Require an explicit mention of this invoice's reference.
    inv_client = (invoice.get("counterparty_email") or "").lower()
    msg_to = (msg.get("to") or "").lower()
    if not inv_client or inv_client not in msg_to:
        return False
    ref = invoice.get("invoice_ref_normalized") or invoice.get("invoice_ref")
    if not ref:
        return False
    hay = " ".join([
        msg.get("subject") or "",
        msg.get("snippet") or "",
        msg.get("body") or "",
    ]).upper()
    return str(ref).upper() in hay


def infer_escalation_floor(chase_msgs: list[dict]) -> int:
    """Map prior chase count/tone → first escalation step Scotive should draft (0–3)."""
    n = len(chase_msgs)
    if n == 0:
        return 0
    texts = " ".join(
        (m.get("subject") or "") + " " + (m.get("snippet") or "") for m in chase_msgs
    )
    if FINAL_CHASE_RE.search(texts) or n >= 3:
        return min(3, n)
    if n >= 2 or FIRM_CHASE_RE.search(texts):
        return 2
    return 1


def prior_followup_fields(candidate: dict) -> dict:
    """Map inferred pre-Scotive chases onto invoice follow-up timestamps."""
    ts = candidate.get("last_prior_chase_at")
    if not ts:
        return {}
    return {"last_followup_sent_at": ts, "last_chase_at": ts}


def enrich_candidates_with_prior_chases(
    candidates: list[dict],
    messages: list[dict],
    my_email: str,
) -> None:
    """Annotate seed candidates in-place with prior-chase signals."""
    by_id = {m["id"]: m for m in messages}
    # A message that anchors another tracked invoice is a fresh invoice send,
    # never a chase of a different invoice to the same client.
    anchor_ids = {c.get("message_id") for c in candidates if c.get("message_id")}
    for cand in candidates:
        anchor = by_id.get(cand.get("message_id") or "")
        if not anchor:
            cand["prior_chase_count"] = 0
            cand["escalation_step_floor"] = 0
            cand["likely_still_open"] = False
            continue
        chases = [
            m for m in messages
            if m.get("id") not in anchor_ids
            and _related(m, cand)
            and _is_user_chase(m, anchor, my_email)
        ]
        chases.sort(key=lambda m: (parse_email_date(m.get("date")) or parse_email_date("1970-01-01")).timestamp())
        floor = infer_escalation_floor(chases)
        cand["prior_chase_count"] = len(chases)
        cand["escalation_step_floor"] = floor
        cand["likely_still_open"] = len(chases) > 0
        if chases:
            last_dt = parse_email_date(chases[-1].get("date"))
            if last_dt:
                cand["last_prior_chase_at"] = last_dt.isoformat()
