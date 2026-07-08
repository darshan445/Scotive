"""Resolve relative / informal dates in email text to ISO YYYY-MM-DD.

Anchor = date the message was sent (not sync time). Strips quoted history so
invoice due dates in replies do not override the client's new commitment.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from ledger_reconcile import normalize_explicit_due_date, parse_iso_date, strip_quoted_history

WEEKDAY_NAMES = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)

DAY_AFTER_TOMORROW_RE = re.compile(r"\bday\s+after\s+tomorrow\b", re.I)
TOMORROW_RE = re.compile(r"\btomorrow\b", re.I)
TODAY_RE = re.compile(r"\btoday\b", re.I)
# "within 15 days of deployment" is anchored on the deliverable, not the send date —
# the trailing of/after/from guard keeps those out of send-date resolution.
IN_DAYS_RE = re.compile(r"\b(?:in|within)\s+(\d{1,3})\s+days?\b(?!\s+(?:of|after|from|following)\b)", re.I)
DAYS_FROM_NOW_RE = re.compile(r"\b(\d{1,3})\s+days?\s+(?:from\s+now|out)\b", re.I)
WEEK_OR_TWO_RE = re.compile(r"\b(?:another\s+)?week\s+or\s+two\b|\ba\s+couple\s+(?:of\s+)?weeks\b", re.I)
IN_WEEKS_RE = re.compile(
    r"\b(?:in|within)\s+(a|one|two|three|four|\d{1,2})\s+weeks?\b(?!\s+(?:of|after|from|following)\b)",
    re.I,
)
WITHIN_THE_WEEK_RE = re.compile(r"\bwithin\s+the\s+week\b", re.I)
_WORD_WEEK_COUNTS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4}
NEXT_WEEKDAY_RE = re.compile(
    r"\bnext\s+(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
THIS_WEEKDAY_RE = re.compile(
    r"\b(?:this|coming)\s+(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
BY_WEEKDAY_RE = re.compile(
    r"\b(?:by|on|until|before)\s+(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
BARE_WEEKDAY_RE = re.compile(
    r"\b(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
NEXT_WEEK_RE = re.compile(r"\bnext\s+week\b", re.I)
IN_A_WEEK_RE = re.compile(r"\b(?:in|within)\s+a\s+week\b", re.I)
BEGIN_NEXT_WEEK_RE = re.compile(r"\b(?:beginning|start)\s+of\s+next\s+week\b", re.I)
END_OF_WEEK_RE = re.compile(r"\bend\s+of\s+(?:this\s+)?week\b", re.I)
THIS_WEEKEND_RE = re.compile(r"\bthis\s+weekend\b", re.I)
NEXT_WEEKEND_RE = re.compile(r"\bnext\s+weekend\b", re.I)
NEXT_MONTH_RE = re.compile(r"\bnext\s+month\b", re.I)
END_OF_MONTH_RE = re.compile(r"\bend\s+of\s+(?:the\s+)?month\b", re.I)

RELATIVE_HINT_RE = re.compile(
    r"\b(?:tomorrow|today|day\s+after\s+tomorrow|next\s+week|this\s+week|end\s+of|"
    r"beginning\s+of|weekend|next\s+month|end\s+of\s+month|"
    r"week\s+or\s+two|couple\s+(?:of\s+)?weeks|within\s+the\s+week|"
    r"(?:in|within)\s+\w+\s+weeks?|"
    r"in\s+\d+\s+days?|within\s+\d+\s+days?|"
    r"(?:this|coming|next)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"(?:by|on|until|before)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b)",
    re.I,
)

EXPLICIT_DATE_RE = re.compile(
    r"\b(\d{1,2}[/\-\.]\d{1,2}(?:[/\-\.]\d{2,4})?|"
    r"\d{1,2}[/\-\.][A-Za-z]{3,9}(?:[/\-\.]\d{2,4})?|"
    r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b",
    re.I,
)
DUE_DAY_MON_YEAR_RE = re.compile(
    r"(?:due\s*(?:date|on|by|is)?|payment\s+due|due\s+will\s+be\s+on)\s*[:\s]*"
    r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{2,4})",
    re.I,
)
DAY_MON_YEAR_RE = re.compile(
    r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{2,4})\b",
    re.I,
)
MON_DAY_YEAR_RE = re.compile(
    r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{2,4})\b",
    re.I,
)


def _weekday_index(name: str) -> int:
    return WEEKDAY_NAMES.index(name.lower())


def anchor_from_message(msg: dict | None) -> date | None:
    """Message send date (UTC calendar day)."""
    if not msg:
        return None
    raw = msg.get("date") or msg.get("source_date")
    if not raw:
        return None
    dt = parse_iso_date(str(raw))
    if not dt:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(str(raw))
        except Exception:
            return None
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


def anchor_from_dt(dt: datetime | None) -> date:
    if dt is None:
        return datetime.now(timezone.utc).date()
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc)
    return dt.date()


def fresh_message_text(*parts: str | None) -> str:
    """Client's new words only — drop quoted invoice / thread history."""
    combined = "\n".join(p for p in parts if p and str(p).strip())
    return strip_quoted_history(combined)


def has_relative_date_language(text: str) -> bool:
    return bool(text and RELATIVE_HINT_RE.search(text))


def _next_weekday_on_or_after(anchor: date, weekday: int) -> date:
    days_ahead = (weekday - anchor.weekday()) % 7
    return anchor + timedelta(days=days_ahead)


def _next_weekday_following_week(anchor: date, weekday: int) -> date:
    days_ahead = (weekday - anchor.weekday()) % 7
    return anchor + timedelta(days=days_ahead + 7)


def _friday_of_week(anchor: date) -> date:
    """Friday of anchor's calendar week (Mon–Sun); if Sat/Sun, that week's Friday."""
    days_to_fri = 4 - anchor.weekday()
    if days_to_fri > 0:
        return anchor + timedelta(days=days_to_fri)
    return anchor + timedelta(days=days_to_fri)


def _monday_next_week(anchor: date) -> date:
    days_to_mon = (7 - anchor.weekday()) % 7
    if days_to_mon == 0:
        days_to_mon = 7
    return anchor + timedelta(days=days_to_mon)


def _saturday_this_week(anchor: date) -> date:
    days_to_sat = (5 - anchor.weekday()) % 7
    return anchor + timedelta(days=days_to_sat)


def _parse_day_mon_year(day: str, mon: str, year: str) -> Optional[str]:
    y = int(year)
    if y < 100:
        y += 2000
    token = f"{int(day)}-{mon}-{y}"
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(token, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_mon_day_year(mon: str, day: str, year: str) -> Optional[str]:
    y = int(year)
    if y < 100:
        y += 2000
    token = f"{day}-{mon}-{y}"
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(token, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_explicit_token(token: str, anchor: date) -> Optional[str]:
    token = token.strip()
    m = DAY_MON_YEAR_RE.search(token)
    if m:
        parsed = _parse_day_mon_year(m.group(1), m.group(2), m.group(3))
        if parsed:
            return parsed
    m = MON_DAY_YEAR_RE.search(token)
    if m:
        parsed = _parse_mon_day_year(m.group(1), m.group(2), m.group(3))
        if parsed:
            return parsed
    dt = parse_iso_date(token)
    if dt:
        return dt.date().isoformat()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%b", "%d-%B"):
        try:
            s = token if "%Y" in fmt else f"{token}-{anchor.year}"
            fmt_use = fmt if "%Y" in fmt else fmt + "-%Y"
            return datetime.strptime(s.replace(".", "-"), fmt_use).date().isoformat()
        except ValueError:
            continue
    return None


def extract_explicit_due_from_text(text: str, anchor: date | None = None) -> Optional[str]:
    """Parse due dates like 'due is 3 jul 2026' or 'due on 07/03/2026'."""
    if not text or not text.strip():
        return None
    base = anchor or datetime.now(timezone.utc).date()

    m = DUE_DAY_MON_YEAR_RE.search(text)
    if m:
        parsed = _parse_day_mon_year(m.group(1), m.group(2), m.group(3))
        if parsed:
            return parsed

    parsed = _parse_explicit_in_text(text, base)
    if parsed:
        return parsed
    return None


def _parse_explicit_in_text(text: str, anchor: date) -> Optional[str]:
    m = EXPLICIT_DATE_RE.search(text)
    if not m:
        return None
    return _parse_explicit_token(m.group(1), anchor)


def resolve_relative_date(text: str, anchor: date | None = None) -> Optional[str]:
    """Parse relative / informal dates. Returns YYYY-MM-DD or None."""
    if not text or not text.strip():
        return None
    base = anchor or datetime.now(timezone.utc).date()
    hay = text.lower()

    if DAY_AFTER_TOMORROW_RE.search(hay):
        return (base + timedelta(days=2)).isoformat()
    if TOMORROW_RE.search(hay):
        return (base + timedelta(days=1)).isoformat()

    # Week-count phrases before "today": "paying today, need another week or two"
    # in one sentence must not collapse to today for the week-anchored part.
    if WEEK_OR_TWO_RE.search(hay):
        return (base + timedelta(days=14)).isoformat()
    m = IN_WEEKS_RE.search(hay)
    if m:
        raw = m.group(1).lower()
        n = _WORD_WEEK_COUNTS.get(raw) or int(raw)
        return (base + timedelta(days=n * 7)).isoformat()
    if WITHIN_THE_WEEK_RE.search(hay):
        eow = _friday_of_week(base)
        return (eow if eow > base else base + timedelta(days=7)).isoformat()

    if TODAY_RE.search(hay):
        return base.isoformat()

    m = IN_DAYS_RE.search(hay) or DAYS_FROM_NOW_RE.search(hay)
    if m:
        return (base + timedelta(days=int(m.group(1)))).isoformat()

    m = NEXT_WEEKDAY_RE.search(hay)
    if m:
        wd = _weekday_index(m.group("day"))
        return _next_weekday_following_week(base, wd).isoformat()

    if BEGIN_NEXT_WEEK_RE.search(hay):
        return _monday_next_week(base).isoformat()

    if END_OF_WEEK_RE.search(hay):
        return _friday_of_week(base).isoformat()

    if THIS_WEEKEND_RE.search(hay):
        return _saturday_this_week(base).isoformat()
    if NEXT_WEEKEND_RE.search(hay):
        return (_saturday_this_week(base) + timedelta(days=7)).isoformat()

    if NEXT_WEEK_RE.search(hay) or IN_A_WEEK_RE.search(hay):
        return (base + timedelta(days=7)).isoformat()

    if NEXT_MONTH_RE.search(hay):
        month = base.month + 1
        year = base.year
        if month > 12:
            month = 1
            year += 1
        day = min(base.day, 28)
        return date(year, month, day).isoformat()

    if END_OF_MONTH_RE.search(hay):
        if base.month == 12:
            last = date(base.year, 12, 31)
        else:
            last = date(base.year, base.month + 1, 1) - timedelta(days=1)
        return last.isoformat()

    m = THIS_WEEKDAY_RE.search(hay)
    if m:
        wd = _weekday_index(m.group("day"))
        return _next_weekday_on_or_after(base, wd).isoformat()

    m = BY_WEEKDAY_RE.search(hay)
    if m:
        wd = _weekday_index(m.group("day"))
        return _next_weekday_on_or_after(base, wd).isoformat()

    m = BARE_WEEKDAY_RE.search(hay)
    if m:
        wd = _weekday_index(m.group("day"))
        return _next_weekday_on_or_after(base, wd).isoformat()

    return _parse_explicit_in_text(text, base)


def resolve_stated_date(
    ai_date: str | None,
    *,
    quote: str | None = None,
    message_body: str | None = None,
    message_dt: datetime | None = None,
    message: dict | None = None,
) -> Optional[str]:
    """Resolve a due/promise date: fresh relative text first, then AI, then explicit."""
    anchor = anchor_from_message(message) if message else anchor_from_dt(message_dt)

    # The event's own quote first — one reply can carry different dates for
    # different invoices ("paying #77 today, need another week or two on #81").
    fresh_quote = fresh_message_text(quote)
    if fresh_quote and has_relative_date_language(fresh_quote):
        rel = resolve_relative_date(fresh_quote, anchor)
        if rel:
            return rel

    fresh = fresh_message_text(quote, message_body)

    if fresh and has_relative_date_language(fresh):
        rel = resolve_relative_date(fresh, anchor)
        if rel:
            return rel

    explicit = normalize_explicit_due_date(ai_date)
    if not explicit and ai_date:
        explicit = extract_explicit_due_from_text(str(ai_date), anchor)
    if explicit:
        return explicit

    if fresh:
        rel = resolve_relative_date(fresh, anchor)
        if rel:
            return rel
        explicit_fresh = extract_explicit_due_from_text(fresh, anchor)
        if explicit_fresh:
            return explicit_fresh
        return _parse_explicit_in_text(fresh, anchor)

    return None


def resolve_promise_date(
    ai_date: str | None,
    quote: str | None,
    *,
    message_body: str | None = None,
    anchor: date | None = None,
    message_dt: datetime | None = None,
    message: dict | None = None,
) -> Optional[str]:
    """Backward-compatible wrapper for promise events."""
    if message is None and anchor is not None and message_dt is None:
        message_dt = datetime.combine(anchor, datetime.min.time(), tzinfo=timezone.utc)
    return resolve_stated_date(
        ai_date,
        quote=quote,
        message_body=message_body,
        message_dt=message_dt,
        message=message,
    )
