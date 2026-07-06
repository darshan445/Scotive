"""Build a deduplicated, conversation-style invoice timeline for the UI."""
from __future__ import annotations

from typing import Any, Optional

from ledger_reconcile import parse_email_date
from invoice_event_idempotency import normalize_event_quote

_CLIENT_KINDS = frozenset({
    "payment_promise", "payment_claim", "dispute", "partial_payment",
})
_YOU_KINDS = frozenset({"invoice_sent", "chase_sent", "chase_drafted"})
_KIND_RANK = {
    "mark_paid": 90,
    "receipt": 85,
    "receipt_matched": 85,
    "receipt_matched_manual": 85,
    "payment_promise": 80,
    "payment_claim": 75,
    "partial_payment": 70,
    "dispute": 65,
    "went_stale": 50,
    "manual_add": 40,
    "invoice_sent": 10,
}


def _event_ts(raw: Any) -> float:
    dt = parse_email_date(raw)
    return dt.timestamp() if dt else 0.0


def _actor_for_kind(kind: str | None) -> str:
    if kind in _CLIENT_KINDS:
        return "client"
    if kind in _YOU_KINDS:
        return "you"
    return "system"


def _dedupe_key(ev: dict) -> tuple:
    kind = ev.get("kind") or ""
    quote = normalize_event_quote(ev.get("quote"))
    if kind in _CLIENT_KINDS and quote:
        return ("quote", kind, quote)
    mid = ev.get("message_id")
    if mid:
        return ("mid", mid, kind)
    if quote:
        return ("quote", kind, quote)
    return ("fallback", kind, str(ev.get("date") or ""))


def build_invoice_timeline(inv: dict, receipt_rows: list[dict], event_rows: list[dict]) -> list[dict]:
    """Return timeline events newest-first, deduplicated."""
    events: list[dict] = []

    origin_mid = inv.get("source_message_id")
    events.append({
        "kind": inv.get("kind") or "invoice_sent",
        "actor": "you",
        "date": inv.get("source_date") or inv.get("created_at"),
        "quote": inv.get("evidence_sentence"),
        "subject": inv.get("source_subject"),
        "from": inv.get("source_from"),
        "message_id": origin_mid,
        "thread_id": inv.get("source_thread_id"),
        "amount": inv.get("amount"),
        "due_date": inv.get("due_date"),
        "currency": inv.get("currency"),
    })

    for rc in receipt_rows:
        events.append({
            "kind": "receipt",
            "actor": "system",
            "date": rc.get("source_date") or rc.get("created_at"),
            "quote": rc.get("evidence_sentence"),
            "subject": rc.get("source_subject"),
            "from": rc.get("processor_from"),
            "message_id": rc.get("source_message_id"),
            "thread_id": rc.get("source_thread_id"),
            "amount": rc.get("applied_amount") or rc.get("amount"),
            "currency": rc.get("currency"),
            "payer_name": rc.get("payer_name"),
            "receipt_id": str(rc.get("_id")) if rc.get("_id") else None,
        })

    for ev in event_rows:
        if ev.get("action") == "thread_evidence":
            continue
        meta = ev.get("meta") or {}
        kind = ev.get("action") or "note"
        promise_date = meta.get("date") if kind == "payment_promise" else None
        events.append({
            "kind": kind,
            "actor": _actor_for_kind(kind),
            "date": meta.get("message_date") or ev.get("at"),
            "quote": meta.get("quote"),
            "subject": meta.get("subject"),
            "from": meta.get("from"),
            "message_id": meta.get("message_id"),
            "thread_id": meta.get("thread_id") or inv.get("source_thread_id"),
            "promise_date": promise_date or (inv.get("promise_date") if kind == "payment_promise" else None),
            "amount": meta.get("amount"),
            "meta": meta,
        })

    seen: set[tuple] = set()
    unique: list[dict] = []
    for ev in events:
        key = _dedupe_key(ev)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ev)

    unique.sort(
        key=lambda e: (_event_ts(e.get("date")), _KIND_RANK.get(e.get("kind") or "", 20)),
        reverse=True,
    )
    return unique


def _fmt_short(iso: Any) -> str:
    dt = parse_email_date(iso)
    if not dt:
        return str(iso or "")
    return f"{dt.day} {dt.strftime('%b %Y')}"


def invoice_next_line(inv: dict) -> Optional[str]:
    """Short footer line describing what happens next for this invoice."""
    status = inv.get("status") or "invoiced"
    if status == "paid":
        return "Invoice closed — marked paid"
    if status == "written_off":
        return "Written off — no further chasing"
    if status == "stale":
        return "No activity in 120+ days — review or dismiss"
    if status == "disputed":
        return "Disputed — chasing paused until resolved"
    if status == "paid_unconfirmed":
        return "Client says paid — confirm when the money lands"
    if status == "partially_paid":
        bal = inv.get("balance_remaining")
        cur = inv.get("currency") or "USD"
        if bal is not None:
            return f"Partial payment recorded — {cur} {bal:.2f} still open"
        return "Partial payment recorded — balance still open"
    if status in ("promised", "promise_broken"):
        pd = inv.get("promise_date")
        if pd:
            label = _fmt_short(pd)
            if status == "promise_broken":
                return f"Promise broken — follow up on payment (was {label})"
            if inv.get("chasing_paused"):
                return f"Nothing due until {label} — chasing paused"
            if inv.get("watching_for_reply"):
                return f"Awaiting client reply — promise date {label}"
            return f"Follow up after {label} if unpaid"
        if status == "promise_broken":
            return "Promise broken — follow up on payment"
        return "Payment promised — chasing paused"
    if status == "overdue":
        if inv.get("watching_for_reply"):
            return "Past due — awaiting client reply after your follow-up"
        if inv.get("ladder_exhausted"):
            return "Past due — escalation ladder exhausted"
        return "Past due — draft a chase when you're ready"
    if inv.get("watching_for_reply"):
        return "Awaiting client reply after your follow-up"
    due = inv.get("due_date")
    if due:
        return f"Due {_fmt_short(due)}"
    return "Add a due date to track when payment is expected"
