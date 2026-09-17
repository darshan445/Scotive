"""Ledger identity, invoice upsert, due-date fallback, and currency-aware totals."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from pymongo.errors import DuplicateKeyError

# Must match client_sweep.CONSUMER_DOMAINS
CONSUMER_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.co.uk",
    "outlook.com", "hotmail.com", "live.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "proton.me", "zoho.com", "yandex.com",
}

RE_SUBJ_PREFIX = re.compile(r"^(?:(?:re|fwd|fw)\s*:\s*)+", re.I)

INVOICE_NUM_PATTERNS = [
    re.compile(
        r"(?:payment\s+)?reminder\s+(?:for\s+)?(?:invoice\s*)?[#:]?\s*([\w/\-]+)",
        re.I,
    ),
    re.compile(
        r"(?:follow[\s\-]?up|chaser?|nudge)\s+(?:for\s+)?(?:invoice\s*)?[#:]?\s*([\w/\-]+)",
        re.I,
    ),
    re.compile(r"for\s+invoice\s+[#:]?\s*([A-Z0-9]{6,})", re.I),
    re.compile(r"INV[/\-][\d/\-]+", re.I),
    re.compile(r"invoice\s*[#:]\s*([\w/\-]+)", re.I),
    re.compile(r"invoice\s+#(\d[\w/\-]*)", re.I),
    re.compile(r"invoice\s+(?:no\.?|number|num\.?)\s*([\w/\-]+)", re.I),
    re.compile(r"#(\d{4,})", re.I),
]

INVOICE_REF_STOPWORDS = frozenset({
    "FOR", "THE", "A", "AN", "TO", "OF", "AND", "OR", "YOUR", "MY", "OUR", "THIS", "THAT",
})

FOLLOWUP_SUBJECT_RE = re.compile(
    r"(?:payment\s+)?reminder|follow[\s\-]?up|second\s+notice|final\s+notice|"
    r"overdue\s+(?:invoice|payment)?|outstanding\s+balance|kindly\s+(?:pay|clear|remit)|"
    r"chase|chaser|nudge|still\s+unpaid|past\s+due|friendly\s+reminder|"
    r"balance\s+due|amount\s+outstanding",
    re.I,
)

OPEN_INVOICE_STATUSES = (
    "invoiced", "overdue", "promised", "partially_paid", "promise_broken", "disputed",
    "paid_unconfirmed",
)

QUOTE_PATTERNS = [
    re.compile(r"(?ms)^\s*On .+ wrote:\s*$"),
    re.compile(r"(?ms)^-{3,}\s*Original Message\s*-{3,}"),
    re.compile(r"(?ms)^From:.+\n(?:Sent|Date):.+\n(?:To|Cc):.+\nSubject:"),
    re.compile(r"(?ms)^_{8,}\s*$"),
    re.compile(r"(?ms)^\s*From:\s*.+\r?\nSent:\s*.+\r?\nTo:\s*.+\r?\nSubject:"),
]

AMOUNT_TOLERANCE_PCT = 0.02
AMOUNT_TOLERANCE_ABS = 1.0

# Newest Gmail message first; fall back to record created_at for manual rows.
INVOICE_MONGO_SORT = [("source_date", -1), ("created_at", -1)]
REVIEW_MONGO_SORT = [("source_date", -1), ("created_at", -1)]


def parse_email_date(raw: Any) -> Optional[datetime]:
    """Parse Gmail RFC 2822 or ISO timestamps for sorting."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def normalize_source_date(raw: Any) -> Optional[str]:
    dt = parse_email_date(raw)
    return dt.isoformat() if dt else (str(raw).strip() if raw else None)


def email_sort_key(doc: dict) -> float:
    for field in ("source_date", "created_at"):
        dt = parse_email_date(doc.get(field))
        if dt:
            return dt.timestamp()
    return 0.0


def sort_by_email_date(items: list[dict]) -> list[dict]:
    return sorted(items, key=email_sort_key, reverse=True)


_PROMISE_SORT_STATUSES = frozenset({"promised", "promise_broken"})


def invoice_action_date(doc: dict) -> Optional[datetime]:
    """Date that drives chase priority: promise when promised, else due."""
    status = doc.get("status") or ""
    if status in _PROMISE_SORT_STATUSES and doc.get("promise_date"):
        return parse_email_date(doc.get("promise_date"))
    return parse_email_date(doc.get("due_date"))


def sort_by_due_promise_date(items: list[dict]) -> list[dict]:
    """Nearest due/promise first; undated rows last (newest sent first among those)."""

    def key(doc: dict) -> tuple:
        d = invoice_action_date(doc)
        if d:
            return (0, d.timestamp(), doc.get("counterparty_email") or "")
        return (1, -email_sort_key(doc), doc.get("counterparty_email") or "")

    return sorted(items, key=key)


def sender_domain(email: str) -> str:
    return email.split("@")[-1].lower() if "@" in email else ""


def client_identity_key(email: str) -> str:
    """Business clients keyed by domain; consumer mail keyed by full address."""
    em = (email or "").lower().strip()
    dom = sender_domain(em)
    if not dom or dom in CONSUMER_DOMAINS:
        return f"email:{em}"
    return f"domain:{dom}"


def pick_primary_email(emails: list[str]) -> str:
    """Prefer billing/finance addresses, else shortest local-part."""
    if not emails:
        return ""
    priority = ("billing", "accounts", "finance", "ap", "ar", "iam", "hello", "contact")

    def rank(e: str) -> tuple:
        local = e.split("@")[0].lower()
        for i, p in enumerate(priority):
            if local.startswith(p) or p in local:
                return (i, len(local), e)
        return (len(priority), len(local), e)

    return sorted({e.lower() for e in emails}, key=rank)[0]


def pick_display_name(names: list[Optional[str]]) -> Optional[str]:
    """Choose cleanest non-empty client name."""
    cleaned = []
    for n in names:
        if not n or not str(n).strip():
            continue
        s = re.sub(r"\s+", " ", str(n).strip())
        if len(s) >= 2:
            cleaned.append(s)
    if not cleaned:
        return None
    # Prefer Title Case-ish names over ALL CAPS slugs
    cleaned.sort(key=lambda x: (x.isupper(), -len(x), x))
    return cleaned[0]


def normalize_subject(subject: str | None) -> str:
    if not subject:
        return ""
    s = subject.strip()
    while True:
        n = RE_SUBJ_PREFIX.sub("", s, count=1).strip()
        if n == s:
            break
        s = n
    return s


def is_invoice_followup(subject: str | None, *, raw_subject: str | None = None) -> bool:
    """True when a sent message is a chase/reminder, not a first invoice."""
    raw = (raw_subject or subject or "").strip()
    if raw and RE_SUBJ_PREFIX.match(raw):
        return True
    subj = normalize_subject(subject or raw_subject or "")
    if not subj:
        return False
    return bool(FOLLOWUP_SUBJECT_RE.search(subj))


def _extract_contextual_hex_ref(text: str) -> Optional[str]:
    """Long alphanumeric refs (e.g. payment links) when subject mentions invoice/reminder."""
    if not text:
        return None
    low = text.lower()
    if not any(k in low for k in ("invoice", "reminder", "payment", "inv ", "inv#", "inv-")):
        return None
    m = re.search(r"\b([A-F0-9]{10,})\b", text, re.I)
    if m:
        return m.group(1).upper()
    return None


def is_plausible_invoice_ref(val: str | None) -> bool:
    """Reject subject fragments like 'FOR' from 'Invoice for month June'."""
    if not val or not str(val).strip():
        return False
    v = str(val).strip().upper().replace(" ", "")
    if v in INVOICE_REF_STOPWORDS:
        return False
    if len(v) < 2:
        return False
    if re.fullmatch(r"[A-Z]+", v) and len(v) <= 5 and not v.startswith("INV"):
        return False
    return True


def normalize_invoice_ref(raw: str | None, subject: str | None = None) -> Optional[str]:
    """Extract canonical invoice number from ref or subject (strips Re:/Fwd:)."""
    for src in (raw, normalize_subject(subject), subject):
        if not src:
            continue
        text = src.strip()
        for pat in INVOICE_NUM_PATTERNS:
            m = pat.search(text)
            if m:
                val = (m.group(1) if m.lastindex else m.group(0)).strip()
                if is_plausible_invoice_ref(val):
                    return val.upper().replace(" ", "")
        hex_ref = _extract_contextual_hex_ref(text)
        if hex_ref:
            return hex_ref
        # Fallback: whole ref after cleaning prefixes
        cleaned = normalize_subject(text)
        if cleaned and len(cleaned) <= 40 and re.search(r"[\d/\-]", cleaned):
            if "invoice" in cleaned.lower():
                continue
            return cleaned.upper()
    return None


def strip_quoted_history(body: str) -> str:
    if not body:
        return ""
    text = body
    for pat in QUOTE_PATTERNS:
        m = pat.search(text)
        if m:
            text = text[: m.start()]
    # Stop at first quoted line (Gmail/Outlook style)
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">"):
            break
        if re.match(r"^On .+ wrote:$", stripped):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def amounts_close(a: float, b: float) -> bool:
    tol = max(abs(a) * AMOUNT_TOLERANCE_PCT, AMOUNT_TOLERANCE_ABS)
    return abs(a - b) <= tol


def parse_iso_date(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


def resolve_due_date(
    issue_date: str | None,
    due_date: str | None,
    terms_days: int = 0,
) -> tuple[Optional[str], bool]:
    """Return (due_date ISO date string, assumed_flag). Never invents a due date."""
    if due_date:
        dt = parse_iso_date(due_date)
        if dt:
            return dt.date().isoformat(), False
    return None, False


def normalize_explicit_due_date(due_date: str | None) -> Optional[str]:
    """Parse a due date when explicitly provided; never infer from issue date or terms."""
    if not due_date:
        return None
    dt = parse_iso_date(due_date)
    return dt.date().isoformat() if dt else None


def merge_candidates_by_domain(
    candidates: dict[str, list[str]],
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Merge anchor maps so same-domain emails share one primary client."""
    buckets: dict[str, dict[str, Any]] = {}
    for email, anchors in candidates.items():
        key = client_identity_key(email)
        if key not in buckets:
            buckets[key] = {"emails": [email.lower()], "anchors": list(anchors)}
        else:
            buckets[key]["emails"].append(email.lower())
            buckets[key]["anchors"].extend(anchors)
    merged: dict[str, list[str]] = {}
    email_to_primary: dict[str, str] = {}
    for data in buckets.values():
        primary = pick_primary_email(data["emails"])
        merged[primary] = list(dict.fromkeys(data["anchors"]))
        for e in data["emails"]:
            email_to_primary[e] = primary
    return merged, email_to_primary


def enrich_invoice_doc(doc: dict, counterparty_email: str) -> dict:
    """Ensure identity + normalized ref fields on an invoice document."""
    em = (counterparty_email or doc.get("counterparty_email") or "").lower()
    doc["counterparty_email"] = em
    doc["client_identity_key"] = doc.get("client_identity_key") or client_identity_key(em)
    norm = normalize_invoice_ref(doc.get("invoice_ref"), doc.get("source_subject"))
    if norm and is_plausible_invoice_ref(norm):
        doc["invoice_ref_normalized"] = norm
        if not doc.get("invoice_ref") or not is_plausible_invoice_ref(doc.get("invoice_ref")):
            doc["invoice_ref"] = norm
    elif (
        (doc.get("invoice_ref") and not is_plausible_invoice_ref(doc.get("invoice_ref")))
        or (doc.get("invoice_ref_normalized") and not is_plausible_invoice_ref(doc.get("invoice_ref_normalized")))
    ):
        doc["invoice_ref"] = None
        doc.pop("invoice_ref_normalized", None)
    if doc.get("source_date"):
        normalized = normalize_source_date(doc["source_date"])
        if normalized:
            doc["source_date"] = normalized
    # Single user-facing follow-up timestamp (chase send via app or inferred prior chase).
    if not doc.get("last_followup_sent_at") and doc.get("last_chase_at"):
        doc["last_followup_sent_at"] = doc["last_chase_at"]
    return doc


async def get_default_payment_terms_days(db, user_id) -> int:
    s = await db.user_settings.find_one({"user_id": user_id})
    val = (s or {}).get("default_payment_terms_days")
    if val is not None:
        return int(val)
    return 30


async def find_invoice_by_key(
    db,
    user_id,
    client_key: str,
    invoice_ref_normalized: str,
) -> Optional[dict]:
    if not invoice_ref_normalized:
        return None
    return await db.invoices.find_one({
        "user_id": user_id,
        "client_identity_key": client_key,
        "invoice_ref_normalized": invoice_ref_normalized,
    })


async def find_related_invoice(
    db,
    user_id,
    client_key: str,
    *,
    norm_ref: str | None = None,
    thread_id: str | None = None,
    amount: float | None = None,
    subject: str | None = None,
) -> Optional[dict]:
    """Locate an existing invoice row for a reminder or duplicate send."""
    if norm_ref:
        existing = await find_invoice_by_key(db, user_id, client_key, norm_ref)
        if existing:
            return existing

    if thread_id:
        thread_query: dict[str, Any] = {
            "user_id": user_id,
            "client_identity_key": client_key,
            "source_thread_id": thread_id,
        }
        if norm_ref:
            # Match only the same invoice number on this thread — never a sibling
            # (#M-14 vs #J-19 often share amount + thread).
            inv = await db.invoices.find_one(
                {**thread_query, "invoice_ref_normalized": norm_ref},
                sort=INVOICE_MONGO_SORT,
            )
            if inv:
                return inv
        else:
            inv = await db.invoices.find_one(thread_query, sort=INVOICE_MONGO_SORT)
            if inv:
                if amount is None or amounts_close(amount, float(inv.get("amount") or 0)):
                    return inv

    followup = is_invoice_followup(subject)
    if amount is not None and (followup or not norm_ref):
        query: dict[str, Any] = {
            "user_id": user_id,
            "client_identity_key": client_key,
        }
        if followup:
            query["status"] = {"$in": list(OPEN_INVOICE_STATUSES)}
        cursor = db.invoices.find(query).sort("source_date", -1).limit(25)
        async for inv in cursor:
            if amounts_close(amount, float(inv.get("amount") or 0)):
                return inv
    return None


async def apply_invoice_correction(
    db,
    user_id,
    inv: dict,
    new_amount: float,
    *,
    now_iso: str,
    due_date: str | None = None,
    message_id: str | None = None,
    subject: str | None = None,
    quote: str | None = None,
    record_event: bool = True,
) -> dict:
    """The user revised an existing invoice amount (e.g. "corrected: $300").

    Updates amount/balance on the SAME row — never a second row. Clears a
    dispute claim. Conversation status is not this function's job: first-pass
    and Sync now write status from the model. This path is seed merge of a
    later send with a new amount.
    """
    paid = float(inv.get("paid_amount") or 0)
    new_amt = float(new_amount)
    new_bal = round(max(new_amt - paid, 0), 2)
    due = due_date or inv.get("due_date")
    prev = inv.get("status") or "invoiced"

    if prev in ("paid", "written_off"):
        status = prev
    elif new_bal <= 0.005:
        status = "paid"
    else:
        status = "invoiced"
        d = parse_iso_date(due) if due else None
        if d and d.date() < datetime.now(timezone.utc).date():
            status = "overdue"

    patch: dict[str, Any] = {
        "amount": new_amt,
        "balance_remaining": new_bal,
        "status": status,
        "disputed_claim_amount": None,
        "promise_date": None,
        "chasing_paused": False,
        "status_updated_at": now_iso,
        "last_activity_at": now_iso,
        "updated_at": now_iso,
    }
    if due_date:
        patch["due_date"] = normalize_explicit_due_date(due_date) or inv.get("due_date")
        patch["due_date_assumed"] = False
    await db.invoices.update_one({"_id": inv["_id"]}, {"$set": patch})

    if record_event:
        meta: dict[str, Any] = {
            "old_amount": float(inv.get("amount") or 0),
            "new_amount": new_amt,
        }
        if message_id:
            meta["message_id"] = message_id
        if subject:
            meta["subject"] = subject
        if quote:
            meta["quote"] = quote
        await db.invoice_events.insert_one({
            "user_id": user_id,
            "invoice_id": inv["_id"],
            "action": "invoice_corrected",
            "at": now_iso,
            "meta": meta,
        })
    return patch


async def _thread_evidence_exists(db, user_id, invoice_id, message_id: str | None) -> bool:
    if not message_id:
        return False
    return bool(await db.invoice_events.find_one({
        "user_id": user_id,
        "invoice_id": invoice_id,
        "action": "thread_evidence",
        "meta.message_id": message_id,
    }))


async def _record_thread_evidence(
    db,
    user_id,
    invoice_id,
    *,
    now_iso: str,
    message_id: str | None = None,
    subject: str | None = None,
    quote: str | None = None,
    from_addr: str | None = None,
    extra_meta: dict | None = None,
) -> bool:
    """Record one thread message as evidence. Idempotent per message_id."""
    if message_id and await _thread_evidence_exists(db, user_id, invoice_id, message_id):
        return False
    meta: dict[str, Any] = {}
    if message_id:
        meta["message_id"] = message_id
    if subject:
        meta["subject"] = subject
    if quote:
        meta["quote"] = quote
    if from_addr:
        meta["from"] = from_addr
    if extra_meta:
        meta.update(extra_meta)
    await db.invoice_events.insert_one({
        "user_id": user_id,
        "invoice_id": invoice_id,
        "action": "thread_evidence",
        "at": now_iso,
        "meta": meta,
    })
    return True


async def upsert_sweep_invoice(
    db,
    user_id,
    doc: dict,
    *,
    now_iso: str,
    terms_days: int = 0,
) -> tuple[str, Optional[Any]]:
    """Insert or merge invoice. Returns ('created'|'merged'|'review', invoice_id)."""
    _ = terms_days  # legacy callers; Scotive never infers due dates from terms
    doc = enrich_invoice_doc(dict(doc), doc.get("counterparty_email") or "")
    from client_merge import resolve_client_key_for_user
    em = doc.get("counterparty_email") or ""
    doc["client_identity_key"] = await resolve_client_key_for_user(db, user_id, em)
    client_key = doc["client_identity_key"]
    norm = doc.get("invoice_ref_normalized")

    due = normalize_explicit_due_date(doc.get("due_date"))
    doc["due_date"] = due
    doc["due_date_assumed"] = False

    new_amt = float(doc.get("amount") or 0) if doc.get("amount") is not None else None
    subject = doc.get("source_subject")
    followup = is_invoice_followup(subject)

    existing = None
    if norm:
        existing = await find_invoice_by_key(db, user_id, client_key, norm)
    if not existing:
        existing = await find_related_invoice(
            db, user_id, client_key,
            norm_ref=norm,
            thread_id=doc.get("source_thread_id"),
            amount=new_amt,
            subject=subject,
        )
    # Distinct invoice numbers are never the same invoice — one email/thread can
    # carry several invoices ("#77 and #81"); each gets its own row.
    if (
        existing
        and norm
        and existing.get("invoice_ref_normalized")
        and existing["invoice_ref_normalized"] != norm
    ):
        existing = None

    if existing:
        old_amt = float(existing.get("amount") or 0)
        same_thread = (
            doc.get("source_thread_id")
            and doc.get("source_thread_id") == existing.get("source_thread_id")
        )
        doc_dt = parse_email_date(doc.get("source_date"))
        existing_dt = parse_email_date(existing.get("source_date"))
        is_newer = bool(doc_dt and existing_dt and doc_dt > existing_dt)
        if new_amt is not None and not amounts_close(new_amt, old_amt):
            # Same thread + later send = user revised the invoice ("corrected: $300").
            # Applies even when the subject is Re:/Fwd: — not a payment chase.
            if same_thread and is_newer:
                await apply_invoice_correction(
                    db, user_id, existing, new_amt,
                    now_iso=now_iso,
                    due_date=due,
                    message_id=doc.get("source_message_id"),
                    subject=doc.get("source_subject"),
                    quote=doc.get("evidence_sentence"),
                )
                return "merged", existing["_id"]
            if not followup:
                existing_r = await db.review_items.find_one({
                    "user_id": user_id,
                    "source_message_id": doc["source_message_id"],
                })
                if not existing_r:
                    await db.review_items.insert_one({
                        **doc,
                        "review_status": "pending",
                        "review_reason": "amount_mismatch_duplicate_ref",
                        "existing_invoice_id": str(existing["_id"]),
                        "existing_amount": old_amt,
                    })
                return "review", existing["_id"]
        # Same invoice — merge as thread evidence, never second row
        await _record_thread_evidence(
            db, user_id, existing["_id"],
            now_iso=now_iso,
            message_id=doc.get("source_message_id"),
            subject=doc.get("source_subject"),
            quote=doc.get("evidence_sentence"),
            from_addr=doc.get("source_from"),
            extra_meta={"followup": followup} if followup else None,
        )
        patch: dict[str, Any] = {}
        if not existing.get("due_date") and due:
            patch["due_date"] = due
            patch["due_date_assumed"] = False
        if not existing.get("counterparty_name") and doc.get("counterparty_name"):
            patch["counterparty_name"] = doc["counterparty_name"]
        if not existing.get("invoice_ref_normalized") and norm:
            patch["invoice_ref"] = doc.get("invoice_ref") or norm
            patch["invoice_ref_normalized"] = norm
        if patch:
            patch["updated_at"] = now_iso
            await db.invoices.update_one({"_id": existing["_id"]}, {"$set": patch})
        return "merged", existing["_id"]

    # No related row found — dedupe by source message, unless the existing row
    # for this message carries a different invoice number (multi-invoice email).
    if doc.get("source_message_id"):
        by_msg = await db.invoices.find_one({
            "user_id": user_id,
            "source_message_id": doc["source_message_id"],
        })
        if by_msg and not (
            norm
            and by_msg.get("invoice_ref_normalized")
            and by_msg["invoice_ref_normalized"] != norm
        ):
            return "merged", by_msg["_id"]

    try:
        res = await db.invoices.insert_one(doc)
    except DuplicateKeyError as e:
        # Unique-index race or legacy index still in place — resolve to the row
        # that won instead of surfacing a 500.
        q: dict[str, Any] = {"user_id": user_id, "source_message_id": doc.get("source_message_id")}
        if norm:
            q["invoice_ref_normalized"] = norm
        winner = await db.invoices.find_one(q) or await db.invoices.find_one({
            "user_id": user_id, "source_message_id": doc.get("source_message_id"),
        })
        if not winner and doc.get("qbo_id"):
            winner = await db.invoices.find_one({"user_id": user_id, "qbo_id": doc["qbo_id"]})
        if winner:
            return "merged", winner["_id"]
        raise
    return "created", res.inserted_id


def compute_open_totals(invoices: list[dict], open_statuses: tuple[str, ...]) -> dict[str, Any]:
    """Currency-grouped open balances + distinct client count.

    User-paused invoices (tracking_paused) are excluded from amounts and client count.
    Unconfirmed payment claims never reduce the outstanding figure.
    """
    from invoice_lifecycle import outstanding_balance

    totals_by_currency: dict[str, float] = {}
    client_keys: set[str] = set()
    for doc in invoices:
        if doc.get("tracking_paused"):
            continue
        if doc.get("status") not in open_statuses:
            continue
        bal = outstanding_balance(doc)
        cur = (doc.get("currency") or "USD").upper()
        totals_by_currency[cur] = round(totals_by_currency.get(cur, 0) + bal, 2)
        em = (doc.get("counterparty_email") or "").lower()
        key = doc.get("client_identity_key") or client_identity_key(em)
        client_keys.add(key)
    return {
        "totals_by_currency": totals_by_currency,
        "client_count": len(client_keys),
    }


async def backfill_invoice_keys(db, user_id) -> int:
    """Populate client_identity_key + invoice_ref_normalized on legacy rows."""
    updated = 0
    async for doc in db.invoices.find({"user_id": user_id}):
        before = (doc.get("client_identity_key"), doc.get("invoice_ref_normalized"), doc.get("source_date"))
        enriched = enrich_invoice_doc(dict(doc), doc.get("counterparty_email") or "")
        after = (enriched.get("client_identity_key"), enriched.get("invoice_ref_normalized"), enriched.get("source_date"))
        if before != after or enriched.get("due_date_assumed") is not None:
            patch = {
                k: enriched[k]
                for k in ("client_identity_key", "invoice_ref_normalized", "invoice_ref", "counterparty_email", "source_date")
                if enriched.get(k) and enriched.get(k) != doc.get(k)
            }
            if patch:
                await db.invoices.update_one({"_id": doc["_id"]}, {"$set": patch})
                updated += 1
    return updated


async def backfill_assumed_due_dates(db, user_id, terms_days: int) -> int:
    """No-op — Scotive never invents due dates from payment terms."""
    _ = (db, user_id, terms_days)
    return 0


async def _merge_invoice_dupes(
    db,
    user_id,
    docs: list[dict],
    now_iso: str,
) -> int:
    if len(docs) < 2:
        return 0

    def _rank(d: dict) -> tuple:
        subj = d.get("source_subject") or ""
        follow = 1 if is_invoice_followup(subj) else 0
        dt = parse_email_date(d.get("source_date")) or parse_email_date(d.get("created_at"))
        ts = dt.timestamp() if dt else 0.0
        return (follow, ts)

    docs.sort(key=_rank)
    keep = docs[0]
    keep_id = keep["_id"]
    removed = 0
    for dup in docs[1:]:
        dup_id = dup["_id"]
        await _record_thread_evidence(
            db, user_id, keep_id,
            now_iso=now_iso,
            message_id=dup.get("source_message_id"),
            subject=dup.get("source_subject"),
            extra_meta={
                "merged_from_invoice_id": str(dup_id),
                "amount": dup.get("amount"),
            },
        )
        await db.invoice_events.update_many(
            {"invoice_id": dup_id},
            {"$set": {"invoice_id": keep_id}},
        )
        await db.invoices.delete_one({"_id": dup_id})
        removed += 1
    return removed


async def dedupe_existing_invoices(db, user_id, now_iso: str) -> int:
    """Merge duplicate invoice rows for the same client + ref or thread."""
    removed = 0
    for pipeline in (
        [
            {"$match": {"user_id": user_id, "invoice_ref_normalized": {"$exists": True, "$ne": None}}},
            {"$group": {
                "_id": {"ck": "$client_identity_key", "ref": "$invoice_ref_normalized"},
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1},
            }},
            {"$match": {"count": {"$gt": 1}}},
        ],
        [
            {"$match": {
                "user_id": user_id,
                "source_thread_id": {"$exists": True, "$ne": None},
            }},
            {"$group": {
                "_id": {"ck": "$client_identity_key", "thread": "$source_thread_id"},
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1},
            }},
            {"$match": {"count": {"$gt": 1}}},
        ],
    ):
        async for group in db.invoices.aggregate(pipeline):
            docs = []
            for oid in group["ids"]:
                d = await db.invoices.find_one({"_id": oid})
                if d:
                    docs.append(enrich_invoice_doc(dict(d), d.get("counterparty_email") or ""))
            if len(docs) < 2:
                continue
            group_key = group.get("_id") or {}
            if "thread" in group_key:
                amt = float(docs[0].get("amount") or 0)
                if not all(amounts_close(amt, float(d.get("amount") or 0)) for d in docs[1:]):
                    continue
                # Multi-invoice thread ("#77 and #81", both $600): merge only rows
                # sharing an invoice number — distinct refs stay separate rows.
                distinct_refs = {
                    d.get("invoice_ref_normalized") for d in docs if d.get("invoice_ref_normalized")
                }
                if len(distinct_refs) > 1:
                    by_ref: dict = {}
                    for d in docs:
                        by_ref.setdefault(d.get("invoice_ref_normalized"), []).append(d)
                    for sub in by_ref.values():
                        if len(sub) > 1:
                            removed += await _merge_invoice_dupes(db, user_id, sub, now_iso)
                    continue
            removed += await _merge_invoice_dupes(db, user_id, docs, now_iso)
    return removed
