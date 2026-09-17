"""Match a ledger invoice to mailbox threads (onboarding first-pass).

Waterfall (no scoring dump of all client mail):
  InvoiceLink (if QBO returned one) → DocNumber → amount → due date → invoice date.
Terms are not used.

US / UK / CA / AU QBO chrome varies (Invoice # vs Invoice no vs Tax Invoice #,
MM/DD vs DD/MM, $ £ €). Match the values, not one label string.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from client_sweep import _extract_email_addr, parse_email_date
from ledger_reconcile import amounts_close

# Short DocNumbers collide with random digits unless an invoice label is nearby.
_SHORT_REF_MAX = 3

_INVOICE_LABEL = (
    r"(?:tax\s+)?invoice\s*(?:number|no\.?|#|num)?"
)

_REF_NEAR_LABEL = re.compile(
    rf"{_INVOICE_LABEL}\s*[:#]?\s*([A-Z0-9][-A-Z0-9/]{{0,20}})",
    re.I,
)

_CURRENCY_PREFIX = r"(?:A\$|C\$|NZ\$|US\$|CA\$|AU\$|CAD|AUD|USD|GBP|EUR|NZD|INR|\$|£|€|₹)"

# 1,263.60 / 1263.60 / 1.263,60 / 1 263.60
_AMOUNT_TOKEN = re.compile(
    rf"{_CURRENCY_PREFIX}\s*([0-9]{{1,3}}(?:[,\s.][0-9]{{3}})*(?:[.,][0-9]{{1,2}})?|[0-9]+(?:[.,][0-9]{{1,2}}))"
    rf"|([0-9]{{1,3}}(?:[,\s.][0-9]{{3}})*(?:[.,][0-9]{{1,2}})|[0-9]+(?:[.,][0-9]{{1,2}}))\s*(?:USD|GBP|EUR|CAD|AUD|NZD|INR|\$|£|€|₹)"
    rf"|([0-9]{{1,3}}(?:,[0-9]{{3}})+\.[0-9]{{2}}|[0-9]+\.[0-9]{{2}})",
    re.I,
)

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_SLASH_DATE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
_MONTH_NAME = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_NAMED_DATE = re.compile(
    rf"\b(\d{{1,2}})\s+({_MONTH_NAME})\s+(\d{{4}})\b"
    rf"|\b({_MONTH_NAME})\s+(\d{{1,2}}),?\s+(\d{{4}})\b",
    re.I,
)
_MONTH_NUM = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def message_hay(msg: dict) -> str:
    """Subject + body + snippet for matching.

    Keep quoted history: Intuit-From replies only carry Invoice # / pay href
    in the quoted QBO summary. Matching must see that; OpenAI still strips
    quotes separately.
    """
    names = " ".join(msg.get("attachment_names") or [])
    return " ".join([
        msg.get("subject") or "",
        (msg.get("body") or "")[:12000],
        msg.get("snippet") or "",
        names,
    ])


def invoice_ref(invoice: dict) -> str:
    return (
        invoice.get("invoice_ref_normalized")
        or invoice.get("invoice_ref")
        or ""
    ).strip()


def pay_url_token(url: str | None) -> Optional[str]:
    """Unique-enough search token from InvoiceLink. None if unusable."""
    raw = (url or "").strip()
    if not raw.startswith("http"):
        return None
    parsed = urlparse(raw)
    path = (parsed.path or "").strip("/")
    last = path.split("/")[-1] if path else ""
    last = last.split("?")[0].strip()
    if len(last) >= 8 and re.search(r"[A-Za-z0-9]", last):
        return last
    if len(raw) >= 12:
        return raw
    return None


def pay_url_in_hay(hay: str, url: str | None) -> bool:
    raw = (url or "").strip()
    if not raw.startswith("http"):
        return False
    if raw in hay:
        return True
    tok = pay_url_token(raw)
    return bool(tok and tok in hay)


def _ref_token_ok(hay: str, ref: str) -> bool:
    if not ref:
        return False
    hay_u = hay.upper()
    ref_u = ref.upper()
    labeled = [m.group(1).upper().replace(" ", "") for m in _REF_NEAR_LABEL.finditer(hay)]
    if any(val == ref_u or val.rstrip(".,") == ref_u for val in labeled):
        return True
    pat = re.compile(rf"(?<![\w]){re.escape(ref_u)}(?![\w])")
    if not pat.search(hay_u):
        return False
    if len(ref_u) > _SHORT_REF_MAX:
        return True
    return bool(_REF_NEAR_LABEL.search(hay))


def ref_in_message(msg: dict, invoice: dict) -> bool:
    return _ref_token_ok(message_hay(msg), invoice_ref(invoice))


def _parse_amount_token(raw: str) -> Optional[float]:
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace("\u00a0", " ").replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        parts = s.split(",")
        if len(parts[-1]) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def amount_in_message(msg: dict, invoice: dict) -> bool:
    amt = invoice.get("amount")
    if amt is None:
        return False
    try:
        target = float(amt)
    except (TypeError, ValueError):
        return False
    hay = message_hay(msg)
    for m in _AMOUNT_TOKEN.finditer(hay):
        token = m.group(1) or m.group(2) or m.group(3) or ""
        parsed = _parse_amount_token(token)
        if parsed is not None and amounts_close(parsed, target):
            return True
    return False


def _year(y: int) -> int:
    if y < 100:
        return 2000 + y if y < 70 else 1900 + y
    return y


def _iso_tuple(raw: str | None) -> Optional[tuple[int, int, int]]:
    if not raw:
        return None
    m = _ISO_DATE.match(str(raw).strip()[:10])
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def date_in_hay(hay: str, iso: str | None) -> bool:
    want = _iso_tuple(iso)
    if not want:
        return False
    y, mo, d = want
    for m in _SLASH_DATE.finditer(hay):
        a, b, c = int(m.group(1)), int(m.group(2)), _year(int(m.group(3)))
        # US MM/DD or UK/AU/CA DD/MM — accept whichever lands on the stored date.
        if (c, a, b) == (y, mo, d) or (c, b, a) == (y, mo, d):
            return True
    for m in _NAMED_DATE.finditer(hay):
        if m.group(1):
            day = int(m.group(1))
            month = _MONTH_NUM.get((m.group(2) or "").lower()[:3], 0)
            year = int(m.group(3))
        else:
            month = _MONTH_NUM.get((m.group(4) or "").lower()[:3], 0)
            day = int(m.group(5))
            year = int(m.group(6))
        if (year, month, day) == (y, mo, d):
            return True
    if iso and iso[:10] in hay:
        return True
    return False


def due_date_in_message(msg: dict, invoice: dict) -> bool:
    return date_in_hay(message_hay(msg), invoice.get("due_date"))


def invoice_date_in_message(msg: dict, invoice: dict) -> bool:
    return date_in_hay(message_hay(msg), invoice.get("source_date"))


def pay_url_in_message(msg: dict, invoice: dict) -> bool:
    return pay_url_in_hay(message_hay(msg), invoice.get("pay_url"))


def _by_thread(messages: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for msg in messages:
        tid = msg.get("thread_id")
        if not tid:
            continue
        out.setdefault(tid, []).append(msg)
    return out


def _threads_matching(messages: list[dict], pred) -> dict[str, list[dict]]:
    by = _by_thread(messages)
    kept: dict[str, list[dict]] = {}
    for tid, msgs in by.items():
        if any(pred(m) for m in msgs):
            kept[tid] = msgs
    return kept


def _apply_filter(
    current: dict[str, list[dict]],
    pred,
) -> dict[str, list[dict]]:
    """If the filter would wipe the set, keep the previous set."""
    nxt = {tid: msgs for tid, msgs in current.items() if any(pred(m) for m in msgs)}
    return nxt if nxt else current


def waterfall_threads(messages: list[dict], invoice: dict) -> list[str]:
    """Narrow an already-fetched pile.

    InvoiceLink or DocNumber hits are this invoice — keep every matching
    thread (QBO send + a later new email that quotes 1047). Amount / dates
    only run when the number and link are missing from the pile.
    """
    if not messages:
        return []
    pool = _by_thread(messages)
    if not pool:
        return []

    url = (invoice.get("pay_url") or "").strip()
    if url.startswith("http"):
        linked = _threads_matching(messages, lambda m: pay_url_in_message(m, invoice))
        if linked:
            return list(linked)

    ref = invoice_ref(invoice)
    if ref:
        numbered = _threads_matching(messages, lambda m: ref_in_message(m, invoice))
        if numbered:
            return list(numbered)

    if invoice.get("amount") is not None:
        pool = _apply_filter(pool, lambda m: amount_in_message(m, invoice))
        if len(pool) == 1:
            return list(pool)

    if invoice.get("due_date"):
        pool = _apply_filter(pool, lambda m: due_date_in_message(m, invoice))
        if len(pool) == 1:
            return list(pool)

    if invoice.get("source_date"):
        pool = _apply_filter(pool, lambda m: invoice_date_in_message(m, invoice))

    return list(pool)


def pick_anchor_message(
    messages: list[dict],
    invoice: dict,
    *,
    my_email: str,
) -> Optional[dict]:
    """QBO Gmail send if present; otherwise the inbound quote (Intuit-From path)."""
    client = (invoice.get("counterparty_email") or "").lower()
    mine = (my_email or "").lower()
    matched = [
        m for m in messages
        if pay_url_in_message(m, invoice) or ref_in_message(m, invoice) or amount_in_message(m, invoice)
    ]
    if not matched:
        matched = list(messages)

    def _dt(m: dict) -> datetime:
        return parse_email_date(m.get("date")) or datetime(1970, 1, 1, tzinfo=timezone.utc)

    from_me = []
    for m in matched:
        frm = _extract_email_addr(m.get("from", ""))
        to_raw = (m.get("to") or "").lower()
        if frm == mine and (not client or client in to_raw or client == _extract_email_addr(m.get("to", ""))):
            from_me.append(m)
    if from_me:
        return min(from_me, key=_dt)
    inbound = [
        m for m in matched
        if _extract_email_addr(m.get("from", "")) == client
    ]
    if inbound:
        return min(inbound, key=_dt)
    return min(matched, key=_dt) if matched else None


def anchor_after_query_value(msg: dict | None) -> Optional[str]:
    """Gmail after: YYYY/MM/DD for mail strictly after the send calendar day is too coarse.

    Return ISO so Unipile `after` can use the send timestamp (exclusive, 1ms nudge
    happens in gmail_client).
    """
    if not msg:
        return None
    dt = parse_email_date(msg.get("date"))
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Inclusive enough for same-second copies: search after (send - 2s)
    dt = dt.astimezone(timezone.utc) - timedelta(seconds=2)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def extra_thread_ids(
    later_messages: list[dict],
    invoice: dict,
    *,
    known: set[str],
) -> list[str]:
    """Phase 2 / windowed sync: other threads that still match this invoice.

    Only threads that actually hit a waterfall key (link → number → amount →
    dates). A lone lunch email must not win because it was the only leftover.
    """
    leftover = [m for m in later_messages if m.get("thread_id") and m["thread_id"] not in known]
    keyed = _keyed_messages(leftover, invoice)
    return [tid for tid in waterfall_threads(keyed, invoice) if tid not in known]


def _keyed_messages(messages: list[dict], invoice: dict) -> list[dict]:
    return [
        m for m in messages
        if pay_url_in_message(m, invoice)
        or ref_in_message(m, invoice)
        or amount_in_message(m, invoice)
        or due_date_in_message(m, invoice)
        or invoice_date_in_message(m, invoice)
    ]
