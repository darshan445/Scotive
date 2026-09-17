"""Friendly cadence: when to auto-send vs queue Firm, plus pay-link helpers.

Ladder (default offsets [-3, 0, 7, 9]):
  0–2  Friendly — send from the owner's mailbox while the client is silent
  last Firm — queue a draft; the owner edits and sends
"""
from __future__ import annotations

from typing import Optional

DEFAULT_OFFSETS = [-3, 0, 7, 9]

# Statuses where Friendly may still auto-send (unpaid + ignoring).
FRIENDLY_AUTO_STATUSES = frozenset({"invoiced", "overdue"})


def last_friendly_index(offsets: list) -> int:
    """Highest Friendly step. Last offset is always Firm for the owner to send."""
    n = len(offsets or [])
    if n <= 1:
        return 0
    return n - 2


def firm_index(offsets: list) -> Optional[int]:
    n = len(offsets or [])
    if n == 0:
        return None
    if n == 1:
        return 0
    return n - 1


def extract_qbo_pay_url(invoice: dict | None) -> Optional[str]:
    """Customer-facing pay/view URL from a QBO Invoice entity."""
    if not invoice:
        return None
    for key in ("InvoiceLink", "invoiceLink"):
        raw = invoice.get(key)
        if isinstance(raw, str):
            url = raw.strip()
            if url.startswith("http"):
                return url
    return None


def invoice_pay_url(inv: dict | None) -> Optional[str]:
    if not inv:
        return None
    raw = (inv.get("pay_url") or "").strip()
    if raw.startswith("http"):
        return raw
    return None


def ensure_pay_link(body: str, pay_url: Optional[str]) -> str:
    """Append the existing pay URL when the model omitted it."""
    url = (pay_url or "").strip()
    text = body or ""
    if not url.startswith("http"):
        return text
    if url in text:
        return text
    return text.rstrip() + f"\n\nYou can pay here: {url}\n"


def pay_link_prompt_lines(inv: dict | None) -> tuple[str, str]:
    """(system extra, user-message line) for draft generation."""
    url = invoice_pay_url(inv)
    if url:
        return (
            "Always include invoice ref (if any), amount, due date, and the payment URL given below — never invent a different link. ",
            f"Payment URL (include verbatim): {url}",
        )
    return (
        "Always include invoice ref (if any), amount, due date. If no payment URL is provided, do not invent one. ",
        "Payment URL: n/a",
    )


def client_is_silent(inv: dict) -> bool:
    """True when Friendly cadence may run — unpaid and no client reply on this invoice."""
    status = inv.get("status") or "invoiced"
    if status not in FRIENDLY_AUTO_STATUSES:
        return False
    if inv.get("chasing_paused") or inv.get("tracking_paused"):
        return False
    if inv.get("needs_reply"):
        return False
    if inv.get("payment_claim_pending") or status == "paid_unconfirmed":
        return False
    if inv.get("last_client_reply_at"):
        return False
    if inv.get("client_ever_replied"):
        return False
    return True


def owner_took_over(inv: dict, offsets: list) -> bool:
    """Owner already sent a Follow-up themselves (not an auto Friendly)."""
    if not inv.get("last_chase_at"):
        return False
    current = inv.get("current_escalation_step")
    if current is None:
        return True
    try:
        return int(current) > last_friendly_index(offsets)
    except (TypeError, ValueError):
        return True


def pick_cadence_action(
    days_since_due: int,
    offsets: list,
    sent_steps: set[int],
    *,
    silent: bool,
    auto_send: bool,
    owner_took_over_chase: bool,
) -> tuple[str, Optional[int]]:
    """Decide one cadence action for today.

    Returns (action, step_index):
      skip | send_friendly | queue_friendly | queue_firm
    """
    offs = [int(o) for o in (offsets or [])]
    if not offs or owner_took_over_chase or not silent:
        return "skip", None

    lf = last_friendly_index(offs)
    fi = firm_index(offs)

    if fi is not None and days_since_due >= offs[fi]:
        if fi not in sent_steps:
            return "queue_firm", fi
        return "skip", None

    due = [
        i for i in range(lf + 1)
        if i < len(offs) and days_since_due >= offs[i] and i not in sent_steps
    ]
    if not due:
        return "skip", None
    i = due[-1]
    if auto_send:
        return "send_friendly", i
    return "queue_friendly", i


def sent_steps_from_invoice(inv: dict) -> set[int]:
    raw = inv.get("cadence_sent_steps") or []
    out: set[int] = set()
    for x in raw:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out
