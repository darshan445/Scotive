"""Client-Sweep scan pipeline.

Pass 1 — Anchor discovery (sent invoices → client list, no AI)
Pass 2 — Client-scoped sweep (threads + sent follow-ups)
Pass 3 — Receipt template parsing (no AI)
Pass 4 — One AI call per client → invoices, events, review queue
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httpx

from gmail_client import (
    GmailAuthError,
    get_access_token,
    get_message,
    list_message_ids,
    parse_email_addresses,
)

from llm_client import (
    OPENAI_URL,
    openai_api_key,
    openai_headers,
    openai_message_content,
    openai_model,
)

logger = logging.getLogger("scotive.sweep")

# Vendors/SaaS that bill the user — not clients
VENDOR_DOMAINS = {
    "cloudflare.com", "notify.cloudflare.com",
    "vultr.com", "digitalocean.com", "linode.com",
    "aws.amazon.com", "amazonaws.com", "amazon.com",
    "googlecloud.com", "cloud.google.com", "workspace.google.com", "google.com",
    "microsoft.com", "azure.com", "office.com",
    "anthropic.com", "openai.com", "cohere.ai", "openrouter.ai",
    "github.com", "gitlab.com", "bitbucket.org",
    "vercel.com", "netlify.com", "heroku.com", "render.com", "fly.io",
    "figma.com", "notion.so", "slack.com", "linear.app",
    "atlassian.com", "adobe.com", "canva.com",
    "shopify.com", "cursor.sh", "cursor.com",
}


def _is_vendor(sender_domain: str) -> bool:
    if not sender_domain:
        return False
    if sender_domain in VENDOR_DOMAINS:
        return True
    for v in VENDOR_DOMAINS:
        if sender_domain.endswith("." + v):
            return True
    return False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AI_CONCURRENCY = int(os.environ.get("SWEEP_AI_CONCURRENCY", "10"))
MAX_CLIENTS_FOR_AI = int(os.environ.get("SWEEP_MAX_CLIENTS", "40"))
MAX_MESSAGES_PER_CLIENT = int(os.environ.get("SWEEP_MAX_MSGS_PER_CLIENT", "15"))
MAX_CHARS_PER_CLIENT = int(os.environ.get("SWEEP_MAX_CHARS_PER_CLIENT", "12000"))
PASS2_ADDR_CHUNK = 25
CONFIDENCE_WRITE = 0.8
CONFIDENCE_REVIEW = 0.75
SHORT_MSG_CHARS = 1500

CONSUMER_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.in", "yahoo.co.uk",
    "outlook.com", "hotmail.com", "live.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "protonmail.com", "proton.me", "zoho.com", "yandex.com",
}

PROCESSOR_DOMAINS = {
    "stripe.com", "paypal.com", "squareup.com", "intuit.com", "freshbooks.com",
    "waveapps.com", "zohobooks.com", "bill.com", "melio.com",
}

BANK_DEPOSIT_DOMAINS = {
    "chase.com", "bankofamerica.com", "wellsfargo.com", "citi.com", "usbank.com",
}

# Amount tokens: ₹$€£, Rs., USD/INR/EUR + number (either order)
AMOUNT_TOKEN_RE = re.compile(
    r"(?:"
    r"(?:[\$€£₹]|Rs\.?|USD|INR|EUR)\s*[\d,]+(?:\.\d{1,2})?"
    r"|[\d,]+(?:\.\d{1,2})?\s*(?:[\$€£₹]|Rs\.?|USD|INR|EUR)"
    r")",
    re.I,
)

MONEY_SIGNAL_RE = re.compile(
    r"invoice|payment|paid|receipt|balance|amount due|past due|overdue|"
    r"outstanding|remit|wire|ach|net\s*\d+|due date|please pay|utr|deposit",
    re.I,
)

NO_REPLY_RE = re.compile(r"no[-_.]?reply|notifications?@", re.I)

from ledger_reconcile import (
    amounts_close,
    client_identity_key,
    find_invoice_by_key,
    find_related_invoice,
    get_default_payment_terms_days,
    is_invoice_followup,
    is_plausible_invoice_ref,
    merge_candidates_by_domain,
    normalize_invoice_ref,
    normalize_subject,
    parse_email_date,
    pick_display_name,
    pick_primary_email,
    strip_quoted_history,
    upsert_sweep_invoice,
    _record_thread_evidence,
)

STATUS_MAP = {
    "INVOICED": "invoiced",
    "OVERDUE": "overdue",
    "PROMISED": "promised",
    "PROMISE_BROKEN": "promise_broken",
    "DISPUTED": "disputed",
    "PARTIALLY_PAID": "partially_paid",
    "PAID_UNCONFIRMED": "invoiced",
    "PAID": "paid",
}

from invoice_event_idempotency import dedupe_ai_events, event_already_recorded

EVENT_KIND_MAP = {
    "promise": "payment_promise",
    "partial_payment": "partial_payment",
    "dispute": "dispute",
    "payment_claimed": "payment_claim",
    "correction": "invoice_corrected",
    "approved": "payment_approved",
    "question": "client_question",
    "due_date_adjusted": "due_date_adjusted",
}

# partial_payment must run before promise on the same message (T7: partial + implicit promise).
# dispute after partial so a disputed+partial invoice keeps disputed_claim_amount while
# status stays disputed with payment_claim_pending (says-paid until user confirms).
# Confirmed partials (user-stated / Received) keep partially_paid.
_EVENT_APPLY_ORDER = {
    "partial_payment": 0,
    "promise": 1,
    "dispute": 2,
    "payment_claimed": 3,
    "correction": 4,
    "approved": 5,
    "due_date_adjusted": 6,
    "question": 7,
}

# Client-only events must come from the client (Gmail From), not the user.
_CLIENT_ONLY_EVENT_TYPES = frozenset({
    "promise", "partial_payment", "dispute", "payment_claimed", "approved",
    "question", "due_date_adjusted",
})
# Corrections are issued by the user revising their own invoice.
_USER_ONLY_EVENT_TYPES = frozenset({"correction"})

CLIENT_SWEEP_PROMPT = """You analyse email threads between a small business owner (USER) and ONE client to build accounts-receivable records.

Return STRICT JSON only. Schema:
{
  "is_receivable_client": bool,
  "client": {"name": string|null, "identities": [string]},
  "invoices": [{
    "invoice_number": string|null,
    "amount": number,
    "currency": "USD"|"INR"|"EUR"|string,
    "issue_date": "YYYY-MM-DD"|null,
    "due_date": "YYYY-MM-DD"|null,
    "status_suggestion": "INVOICED"|"OVERDUE"|"PROMISED"|"PROMISE_BROKEN"|"DISPUTED"|"PARTIALLY_PAID"|"PAID_UNCONFIRMED"|"PAID",
    "balance_remaining": number|null,
    "anchor_message_id": string|null
  }],
  "events": [{
    "invoice_ref": string|null,
    "type": "promise"|"partial_payment"|"dispute"|"payment_claimed"|"correction"|"approved"|"question"|"due_date_adjusted",
    "date": "YYYY-MM-DD"|null,
    "quote": string,
    "message_id": string,
    "confidence": number,
    "amount": number|null,
    "reference": string|null,
    "dispute_kind": "wrong_amount"|"scope"|"quality"|"terms"|"other"|null
  }],
  "unmatched_mentions": [{"text": string, "message_id": string}],
  "confidence_overall": number,
  "truncated_note": string|null
}

Rules:
- Only money the USER is owed by this CLIENT (accounts receivable). Ignore vendor bills.
- Anchor messages are invoices the USER sent. Use them to seed invoice rows.
- Reminders, payment chasers, Re:/Fwd: follow-ups, "second notice", and "payment reminder" emails are NEVER new invoices.
- If the USER sent a reminder about an existing invoice, do NOT add a second row in invoices[] — attach timeline events only, or omit from invoices[].
- anchor_message_id must point to the FIRST original invoice send, not a later reminder.
- Re: / Fwd: replies about an EXISTING invoice are NOT new invoices — attach as events only.
- Extract amounts from the NEW message body only, never from quoted history below "On ... wrote:".
- One row per distinct invoice_number per client. Same invoice_number = same invoice.
- Chronological thread messages may contain promises, partial payments, disputes, payment claims, corrections.
- SENDER DIRECTION (critical): each thread line is labelled "YOU →" (user sent) or "{client} → YOU" (client sent). promise, partial_payment, dispute, payment_claimed, and approved events MUST cite a message where the client sent to the user — never from "YOU →" lines. Reminders, payment chasers, and follow-ups the USER sent are NEVER payment_claimed, promise, dispute, or partial_payment. "correction" MUST cite a "YOU →" message only.
- "correction": the USER later revises an existing invoice's amount (e.g. "corrected: $300", "revised invoice, should be…", "my mistake — it's actually…"). Set amount to the NEW corrected amount and invoice_ref to the invoice being corrected. A correction is NEVER a new invoice row — do not add it to invoices[]. If a corrected due date is stated, put it in date. If the CLIENT later rejects a USER downward correction (e.g. "retain the bill as is", "don't reduce") and asks to keep the original total, do NOT apply the reduction — emit a correction event reverting to the pre-reduction amount, or omit the downward correction event.
- A message can produce MULTIPLE events: e.g. "sent $1,200 (ref TXN...), rest coming next week" = one partial_payment (with amount + reference) AND one promise (for the remainder, date resolved from the message date). "We agreed $1,800 — sending $1,000 now as a partial" = one dispute (claimed amount 1800, quote the agreement phrase) AND one partial_payment ($1,000) — NEVER also emit a question for residual clauses like "will sort the rest after we confirm".
- One client reply can map DIFFERENT events to DIFFERENT invoices — set invoice_ref per event ("paying #77 today, need another week or two on #81" = payment_claimed on #77 AND promise on #81, each with its own quote).
- payment_claimed vs promise — TENSE TEST: has the money already left the client's hands? PAST-TENSE / completed transfers ("just paid", "sent it over on venmo", "paid through the link", "processed already", "sending it right now on venmo" — direct transfer as they write) = payment_claimed. FUTURE or in-process commitments where money has NOT moved yet ("will pay next week", "sending this through AP today — should hit your account within the week", "will process this week", "expect it processed by end of month", "need another week or two") = promise with the date resolved from the message date. Routing into AP/finance or a stated future arrival window is ALWAYS a promise, never payment_claimed.
- "approved": the client acknowledges/approves the invoice or routes it for payment ("approved on our end", "forwarded to AP", "routing to finance for processing"). If the approval ALSO states an arrival window ("should hit your account within the week"), emit BOTH approved AND a promise with the date resolved from that window. A reference that "will be issued" later (e.g. "reference will be PO-88123 once issued") is NOT a payment reference — emit approved, never payment_claimed, and leave reference null until the real reference appears.
- "question": the client asks the USER something that needs an answer — a clarification request ("can you break down the QA line item?"), a logistics question, or UNCERTAINTY about payment ("can you check if this was already paid? I thought we cleared this"). Uncertainty is NEVER payment_claimed; a clarification request is NOT a dispute. Emit question with the quote. Do NOT emit question when the same message already produced dispute, partial_payment, promise, or payment_claimed — those residual phrases are part of the primary signal, not a separate needs-reply item.
- "due_date_adjusted": the client corrects the payment window's anchor or the due date itself ("QA held it until July 6th, so count the payment window from there") — set date to the NEW resolved due date (new anchor + the invoice's stated payment window). This is not a promise and not a dispute.
- dispute_kind: wrong_amount (they say a different figure was agreed), scope, quality, terms, other.
- For promise events, date must be ISO YYYY-MM-DD. Resolve relative phrases using the MESSAGE DATE shown in the thread (not sync time): "this Friday" → that week's Friday on or after the message date; "next Friday" → the Friday after; "tomorrow", "day after tomorrow", "end of this week", "next week", "this weekend", etc. Never copy due dates from quoted invoice text below — only the client's new words count.
- Do not invent amounts. Use null for amounts when unsure.
- If history was truncated, note it in truncated_note and lower confidence.
- Every event must include message_id (use the id= value from the thread line) and a verbatim quote from that message.
"""


def _extract_email_addr(from_header: str) -> str:
    addrs = parse_email_addresses(from_header)
    return addrs[0] if addrs else from_header.strip().lower()


def _sender_domain(email: str) -> str:
    return email.split("@")[-1].lower() if "@" in email else ""


def _client_identity_emails(
    primary_email: str,
    result: dict | None = None,
    email_to_primary: dict[str, str] | None = None,
    counterparty_email: str | None = None,
) -> set[str]:
    emails: set[str] = set()
    for raw in (primary_email, counterparty_email):
        if raw:
            emails.add(raw.lower())
    if result:
        for raw in (result.get("client") or {}).get("identities") or []:
            if raw:
                emails.add(raw.lower())
    etp = email_to_primary or {}
    expanded = set(emails)
    for alias, primary in etp.items():
        a, p = alias.lower(), primary.lower()
        if a in expanded or p in expanded:
            expanded.add(a)
            expanded.add(p)
    return expanded


def _domains_for_clients(client_emails: set[str]) -> set[str]:
    return {
        _sender_domain(e)
        for e in client_emails
        if "@" in e and _sender_domain(e) not in CONSUMER_DOMAINS
    }


def _resolve_event_message(ev: dict, messages_by_id: dict[str, dict]) -> dict:
    """Map an AI event to the Gmail message it cites (by id, then quote)."""
    mid = (ev.get("message_id") or "").strip()
    if mid and mid in messages_by_id:
        return messages_by_id[mid]
    quote = (ev.get("quote") or "").strip()
    if len(quote) >= 12:
        q = quote.lower()
        for m in messages_by_id.values():
            hay = (m.get("body") or m.get("snippet") or "").lower()
            if q in hay or (len(q) >= 20 and q[:40] in hay):
                return m
    return {}


def event_sender_allows_apply(
    ev_type: str,
    msg: dict,
    my_email: str,
    client_emails: set[str] | None = None,
    domains: set[str] | None = None,
    email_to_primary: dict[str, str] | None = None,
) -> bool:
    """Enforce Gmail From direction before applying AI timeline events."""
    if ev_type not in _CLIENT_ONLY_EVENT_TYPES and ev_type not in _USER_ONLY_EVENT_TYPES:
        return True
    if not msg:
        # Can't verify sender — don't block (AI message_id may be wrong).
        return True

    sender = _extract_email_addr(msg.get("from", ""))
    my = my_email.lower()

    if ev_type in _USER_ONLY_EVENT_TYPES:
        return sender == my

    # Client events: reject only when Gmail From is the user (chase/reminder/invoice).
    return sender != my


def window_clause(months: int) -> str:
    return f"newer_than:{max(1, months)}m"


def pass1_queries(months: int) -> list[str]:
    w = window_clause(months)
    return [
        f'in:sent {w} has:attachment (invoice OR payment OR bill OR "amount due")',
        f'in:sent {w} subject:(invoice OR payment OR "amount due" OR outstanding OR "balance due")',
        (
            f'in:sent {w} ("please pay" OR "payment due" OR "net 30" OR "net 15" OR '
            f'"net 45" OR "balance due" OR "total amount" OR "kindly clear" OR "payment link")'
        ),
    ]


def pass3_processor_query(months: int) -> str:
    domains = " OR ".join(f"from:{d}" for d in sorted(PROCESSOR_DOMAINS))
    return f"({domains}) {window_clause(months)}"


def pass3_bank_query(months: int) -> str:
    domains = " OR ".join(f"from:{d}" for d in sorted(BANK_DEPOSIT_DOMAINS))
    return (
        f"({domains}) {window_clause(months)} "
        f'subject:("deposit" OR "payment received" OR "credit alert")'
    )


MONEY_OUT_RE = re.compile(
    r"subscription|subscribed|auto-?renew|renewal|charged your|charge to your|"
    r"your (?:payment|purchase|order|subscription)|receipt for your|invoice from|"
    r"thanks for (?:your )?purchase|you (?:paid|were charged)|billing statement|"
    r"payment method|trial (?:ended|expires)",
    re.I,
)

MONEY_IN_RE = re.compile(
    r"you(?:'ve| have)? received|sent you|payment received|deposit (?:received|of)|"
    r"incoming (?:payment|transfer)|credit alert.*deposit",
    re.I,
)


def _is_money_out_notification(hay: str, msg: dict) -> bool:
    """True when the email is money the user paid out, not a client paying them."""
    if MONEY_IN_RE.search(hay):
        return False
    if MONEY_OUT_RE.search(hay):
        return True
    sender = _extract_email_addr(msg.get("from", ""))
    if _is_vendor(_sender_domain(sender)):
        return True
    return False


def has_amount_token(msg: dict) -> bool:
    hay = " ".join([
        msg.get("subject", ""),
        msg.get("body", ""),
        msg.get("snippet", ""),
        " ".join(msg.get("attachment_names") or []),
    ])
    return bool(AMOUNT_TOKEN_RE.search(hay))


def is_mailing_list(msg: dict) -> bool:
    if msg.get("list_unsubscribe"):
        return True
    to_raw = (msg.get("to") or "").lower()
    if "undisclosed-recipients" in to_raw or "mailing list" in to_raw:
        return True
    return False


def preprocess_body(body: str, max_chars: int = 2000) -> str:
    cleaned = strip_quoted_history(body)
    return cleaned[:max_chars]


def _parse_msg_date(msg: dict) -> Optional[datetime]:
    d = msg.get("date")
    if not d:
        return None
    try:
        dt = parsedate_to_datetime(d)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def format_msg_line(msg: dict, my_email: str) -> str:
    dt = _parse_msg_date(msg)
    date_label = dt.strftime("%b %d, %Y") if dt else "unknown date"
    sender = _extract_email_addr(msg.get("from", ""))
    direction = "YOU →" if sender == my_email.lower() else f"{sender} → YOU"
    subj = normalize_subject(msg.get("subject") or "")
    thread_note = f', thread "{subj[:60]}"' if subj else ""
    body = preprocess_body(msg.get("body") or msg.get("snippet") or "")
    mid = msg.get("id") or ""
    id_note = f"id={mid}, " if mid else ""
    return f"[{date_label}, {id_note}{direction}{thread_note}]: {body}"


async def load_blocklist(db, user_id) -> set[str]:
    blocked: set[str] = set()
    async for doc in db.suppressed_senders.find({"user_id": user_id}):
        em = (doc.get("email") or "").lower()
        if em:
            blocked.add(em)
            blocked.add(_sender_domain(em))
    for v in VENDOR_DOMAINS:
        blocked.add(v)
    return blocked


def anchor_recipients(msg: dict, my_email: str) -> list[str]:
    """Client emails from a sent anchor message."""
    my = my_email.lower()
    recipients = list(dict.fromkeys((msg.get("to_addrs") or []) + (msg.get("cc_addrs") or [])))
    return [r for r in recipients if r != my]


def pass1_filter_anchor(msg: dict, my_email: str, blocklist: set[str]) -> Optional[str]:
    """Return client email if anchor is valid, else None."""
    if is_mailing_list(msg):
        return None
    recipients = anchor_recipients(msg, my_email)
    if not recipients:
        return None
    if len(recipients) > 10:
        return None
    client = recipients[0]
    domain = _sender_domain(client)
    if client in blocklist or domain in blocklist or _is_vendor(domain):
        return None
    if not has_amount_token(msg):
        return None
    return client


def primary_anchor_ids(anchor_ids: list[str], messages: list[dict]) -> list[str]:
    """One anchor per thread — prefer the original invoice over reminders."""
    by_id = {m["id"]: m for m in messages}
    by_thread: dict[str, list[str]] = {}
    for mid in anchor_ids:
        m = by_id.get(mid)
        tid = (m or {}).get("thread_id") or f"_solo_{mid}"
        by_thread.setdefault(tid, []).append(mid)

    kept: list[str] = []
    for mids in by_thread.values():
        if len(mids) == 1:
            kept.append(mids[0])
            continue

        def _rank(mid: str) -> tuple:
            msg = by_id.get(mid) or {}
            subj = msg.get("subject") or ""
            follow = 1 if is_invoice_followup(subj) else 0
            dt = parse_email_date(msg.get("date"))
            ts = dt.timestamp() if dt else 0.0
            return (follow, ts)

        kept.append(sorted(mids, key=_rank)[0])
    return kept


def collapse_ai_invoices(invoices: list[dict], messages_by_id: dict[str, dict]) -> list[dict]:
    """Drop duplicate invoice rows the model emitted for reminders / same ref."""
    seen_refs: set[str] = set()
    collapsed: list[dict] = []
    for inv in invoices or []:
        if inv.get("amount") in (None, 0):
            continue
        anchor_id = inv.get("anchor_message_id")
        src = messages_by_id.get(anchor_id or "")
        subj = (src or {}).get("subject") or ""
        if anchor_id and is_invoice_followup(subj):
            continue
        ref = normalize_invoice_ref(inv.get("invoice_number"), subj or None)
        if ref:
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
        collapsed.append(inv)
    return collapsed


async def pass1_discover_anchors(
    access: str,
    db,
    user_id,
    my_email: str,
    months: int,
) -> tuple[dict[str, list[str]], set[str]]:
    """Returns ({client_email: [anchor_ids]}, business_domains)."""
    blocklist = await load_blocklist(db, user_id)
    seen_ids: set[str] = set()
    candidates: dict[str, list[str]] = {}
    domains: set[str] = set()

    for q in pass1_queries(months):
        ids = await list_message_ids(access, q, max_pages=10)
        logger.info("sweep.pass1 QUERY %r ids=%s", q, len(ids))
        for mid in ids:
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            msg = await get_message(access, mid)
            if not msg:
                continue
            client = pass1_filter_anchor(msg, my_email, blocklist)
            if not client:
                logger.debug("sweep.pass1 DROP id=%s", mid)
                continue
            candidates.setdefault(client, []).append(mid)
            dom = _sender_domain(client)
            if dom and dom not in CONSUMER_DOMAINS:
                domains.add(dom)
            logger.info("sweep.pass1 ANCHOR client=%s id=%s subj=%r", client, mid, (msg.get("subject") or "")[:60])

    return candidates, domains


def chunk_list(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def pass2_collect_ids(
    access: str,
    client_emails: list[str],
    domains: set[str],
    months: int,
) -> list[str]:
    w = window_clause(months)
    all_ids: list[str] = []
    seen: set[str] = set()

    def _addr_q(prefix: str, addrs: list[str]) -> str:
        return " OR ".join(f"{prefix}:{a}" for a in addrs)

    for chunk in chunk_list(client_emails, PASS2_ADDR_CHUNK):
        for q in (
            f"({_addr_q('from', chunk)}) {w}",
            f"in:sent ({_addr_q('to', chunk)}) {w}",
        ):
            ids = await list_message_ids(access, q, max_pages=15)
            logger.info("sweep.pass2 QUERY %r ids=%s", q[:120], len(ids))
            for mid in ids:
                if mid not in seen:
                    seen.add(mid)
                    all_ids.append(mid)

    biz_domains = [d for d in domains if d not in CONSUMER_DOMAINS]
    for chunk in chunk_list(biz_domains, PASS2_ADDR_CHUNK):
        or_part = " OR ".join(f"from:{d}" for d in chunk)
        q = f"({or_part}) {w}"
        ids = await list_message_ids(access, q, max_pages=15)
        logger.info("sweep.pass2 DOMAIN %r ids=%s", q[:120], len(ids))
        for mid in ids:
            if mid not in seen:
                seen.add(mid)
                all_ids.append(mid)

    return all_ids


def assign_client_key(
    msg: dict,
    client_emails: set[str],
    domains: set[str],
    my_email: str,
    email_to_primary: dict[str, str] | None = None,
) -> Optional[str]:
    sender = _extract_email_addr(msg.get("from", ""))
    my = my_email.lower()
    etp = email_to_primary or {}

    def _canonical(email: str) -> str:
        return etp.get(email.lower(), email.lower())

    if sender == my:
        for r in (msg.get("to_addrs") or []):
            if r in client_emails:
                return _canonical(r)
        return None
    if sender in client_emails:
        return _canonical(sender)
    dom = _sender_domain(sender)
    if dom in domains:
        for ce in client_emails:
            if _sender_domain(ce) == dom:
                return _canonical(ce)
    return None


def pass2_filter_message(
    msg: dict,
    seen_ids: set[str],
) -> tuple[str, str]:
    """Return (verdict, reason). verdict: keep | activity | drop."""
    mid = msg.get("id", "")
    if mid in seen_ids:
        return "drop", "duplicate"
    sender = _extract_email_addr(msg.get("from", ""))
    if msg.get("list_unsubscribe") or NO_REPLY_RE.search(sender):
        return "drop", "list_or_noreply"
    body_len = len(preprocess_body(msg.get("body") or ""))
    hay = " ".join([msg.get("subject", ""), msg.get("body", ""), msg.get("snippet", "")])
    if MONEY_SIGNAL_RE.search(hay) or AMOUNT_TOKEN_RE.search(hay):
        return "keep", "money_signal"
    if body_len < SHORT_MSG_CHARS:
        return "keep", "short_reply"
    return "activity", "long_no_money"


def select_messages_for_client(
    messages: list[dict],
    anchor_ids: set[str],
) -> tuple[list[dict], bool]:
    """Sort chronologically, cap count/chars; return (selected, truncated)."""
    def sort_key(m):
        dt = _parse_msg_date(m)
        return dt or datetime.min.replace(tzinfo=timezone.utc)

    ordered = sorted(messages, key=sort_key)
    anchors = [m for m in ordered if m["id"] in anchor_ids]
    rest = [m for m in ordered if m["id"] not in anchor_ids]
    selected: list[dict] = list(anchors)
    total_chars = sum(len(format_msg_line(m, "")) for m in selected)
    truncated = False
    for m in reversed(rest):
        line_len = len(format_msg_line(m, ""))
        if len(selected) >= MAX_MESSAGES_PER_CLIENT or total_chars + line_len > MAX_CHARS_PER_CLIENT:
            truncated = True
            break
        selected.insert(len(anchors), m)
        total_chars += line_len
    selected.sort(key=sort_key)
    return selected, truncated


async def extract_client_with_ai(
    client_email: str,
    messages: list[dict],
    anchor_ids: list[str],
    my_email: str,
    truncated: bool,
    *,
    system_prompt: str | None = None,
    extra_context: str | None = None,
) -> Optional[dict]:
    api_key = openai_api_key()
    if not api_key:
        logger.warning("sweep.pass4 SKIP client=%s reason=no_openai_key", client_email)
        return None

    anchor_set = set(anchor_ids)
    anchor_texts = []
    for m in messages:
        if m["id"] in anchor_set:
            anchor_texts.append(
                f"ANCHOR id={m['id']} subject={m.get('subject','')}\n{preprocess_body(m.get('body') or '', 3500)}"
            )
    thread_lines = [format_msg_line(m, my_email) for m in messages]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    user_content = (
        f"USER_EMAIL: {my_email}\nCLIENT_EMAIL: {client_email}\nTODAY: {today}\n"
        f"TRUNCATED: {truncated}\n"
        + (f"{extra_context}\n" if extra_context else "")
        + f"\n=== ANCHOR INVOICE(S) ===\n" + "\n---\n".join(anchor_texts) + "\n\n"
        f"=== THREAD (chronological) ===\n" + "\n".join(thread_lines)
    )

    prompt = system_prompt or CLIENT_SWEEP_PROMPT

    try:
        async with httpx.AsyncClient(timeout=90.0) as c:
            r = await c.post(
                OPENAI_URL,
                headers=openai_headers(),
                json={
                    "model": openai_model(),
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content[:14000]},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 1200,
                },
            )
            if r.status_code != 200:
                logger.warning("sweep.pass4 FAIL client=%s status=%s", client_email, r.status_code)
                return None
            parsed = json.loads(openai_message_content(r.json()))
            logger.info(
                "sweep.pass4 OK client=%s receivable=%s invoices=%s events=%s conf=%.2f",
                client_email,
                parsed.get("is_receivable_client"),
                len(parsed.get("invoices") or []),
                len(parsed.get("events") or []),
                float(parsed.get("confidence_overall") or 0),
            )
            return parsed
    except Exception as e:
        logger.warning("sweep.pass4 ERROR client=%s err=%s", client_email, e)
        return None


def parse_processor_receipt(msg: dict) -> Optional[dict]:
    """Deterministic receipt extraction from payment processors (money IN only)."""
    hay = " ".join([msg.get("subject", ""), msg.get("body", ""), msg.get("snippet", "")])
    if _is_money_out_notification(hay, msg):
        return None
    m = AMOUNT_TOKEN_RE.search(hay)
    if not m:
        return None
    amount_str = re.sub(r"[^\d.]", "", m.group().replace(",", ""))
    try:
        amount = float(amount_str)
    except ValueError:
        return None
    if amount <= 0:
        return None
    currency = "USD"
    if "INR" in m.group().upper() or "₹" in m.group() or "Rs" in m.group():
        currency = "INR"
    elif "EUR" in m.group().upper() or "€" in m.group():
        currency = "EUR"
    payer = None
    for pat in (
        r"from\s+([A-Za-z0-9 .,&'-]{2,60})",
        r"paid by\s+([A-Za-z0-9 .,&'-]{2,60})",
        r"Customer[:\s]+([A-Za-z0-9 .,&'-]{2,60})",
    ):
        pm = re.search(pat, hay, re.I)
        if pm:
            payer = pm.group(1).strip()
            break
    return {
        "amount": amount,
        "currency": currency,
        "payer_name": payer,
        "evidence_sentence": m.group().strip(),
        "confidence": 0.95,
    }


async def pass3_parse_receipts(
    access: str,
    db,
    user_id,
    months: int,
    now_iso: str,
) -> int:
    created = 0
    queries = [pass3_processor_query(months), pass3_bank_query(months)]
    seen: set[str] = set()
    for q in queries:
        ids = await list_message_ids(access, q, max_pages=10)
        logger.info("sweep.pass3 QUERY %r ids=%s", q[:100], len(ids))
        for mid in ids:
            if mid in seen:
                continue
            seen.add(mid)
            existing = await db.receipts.find_one({"user_id": user_id, "source_message_id": mid})
            if existing:
                continue
            msg = await get_message(access, mid)
            if not msg:
                continue
            parsed = parse_processor_receipt(msg)
            if not parsed:
                continue
            await db.receipts.insert_one({
                "user_id": user_id,
                "amount": parsed["amount"],
                "currency": parsed["currency"],
                "payer_name": parsed.get("payer_name"),
                "processor_from": msg.get("from"),
                "source_message_id": mid,
                "source_thread_id": msg.get("thread_id"),
                "source_subject": msg.get("subject"),
                "source_date": msg.get("date"),
                "evidence_sentence": parsed.get("evidence_sentence"),
                "confidence": parsed.get("confidence", 0.9),
                "match_status": "unmatched",
                "matched_invoice_id": None,
                "candidate_invoice_ids": [],
                "created_at": now_iso,
            })
            created += 1
            logger.info("sweep.pass3 RECEIPT id=%s amount=%s", mid, parsed["amount"])
    return created


def _resolve_invoice_source(
    inv: dict,
    messages_by_id: dict[str, dict],
    my_email: str,
    pass1_anchor_ids: list[str] | None = None,
) -> tuple[str | None, dict | None]:
    """Locate the Gmail message that anchors an invoice row."""
    my_lc = my_email.lower()
    anchor_id = inv.get("anchor_message_id")
    if anchor_id and anchor_id in messages_by_id:
        return anchor_id, messages_by_id[anchor_id]

    norm_ref = normalize_invoice_ref(inv.get("invoice_number"))
    search_ids = list(dict.fromkeys([*(pass1_anchor_ids or []), *messages_by_id.keys()]))
    if norm_ref:
        for mid in search_ids:
            m = messages_by_id.get(mid)
            if not m:
                continue
            subj = normalize_subject(m.get("subject") or "")
            if norm_ref.upper() in subj.upper() and _extract_email_addr(m.get("from", "")) == my_lc:
                return mid, m

    for mid, m in messages_by_id.items():
        if _extract_email_addr(m.get("from", "")) == my_lc:
            return mid, m
    return None, None


async def _load_open_invoice_ids_by_ref(db, user_id, client_key: str) -> dict[str, Any]:
    """Map normalized refs (and fallbacks) to open invoice ids for event linking."""
    from ledger_reconcile import OPEN_INVOICE_STATUSES

    ids_by_ref: dict[str, Any] = {}
    async for inv in db.invoices.find({
        "user_id": user_id,
        "client_identity_key": client_key,
        "status": {"$in": list(OPEN_INVOICE_STATUSES)},
    }):
        ref = inv.get("invoice_ref_normalized")
        if ref:
            ids_by_ref[ref] = inv["_id"]
        ids_by_ref[f"__{inv['_id']}"] = inv["_id"]
    return ids_by_ref


async def apply_client_result(
    db,
    user_id,
    client_email: str,
    result: dict,
    messages_by_id: dict[str, dict],
    my_email: str,
    now_iso: str,
    email_to_primary: dict[str, str] | None = None,
    pass1_anchor_ids: list[str] | None = None,
    *,
    events_only: bool = False,
    scoped_invoice_id: Any | None = None,
) -> tuple[int, int]:
    """Returns (invoices_created, review_created)."""
    if events_only:
        if not result.get("events"):
            return (0, 0)
    elif not result.get("is_receivable_client"):
        logger.info("sweep.write DISCARD client=%s reason=not_receivable", client_email)
        return (0, 0)

    conf = float(result.get("confidence_overall") or 0)
    invoices_created = 0
    review_created = 0
    terms_days = await get_default_payment_terms_days(db, user_id)

    primary_email = (email_to_primary or {}).get(client_email.lower(), client_email.lower())
    client_key = client_identity_key(primary_email)
    cp_name = pick_display_name([(result.get("client") or {}).get("name")])

    invoice_ids_by_ref: dict[str, Any] = await _load_open_invoice_ids_by_ref(db, user_id, client_key)

    if not events_only:
        for inv in collapse_ai_invoices(result.get("invoices") or [], messages_by_id):
            amount = inv.get("amount")
            if amount in (None, 0):
                continue
            anchor_id, src = _resolve_invoice_source(inv, messages_by_id, my_email, pass1_anchor_ids)
            if src and is_invoice_followup(src.get("subject")):
                related = await find_related_invoice(
                    db, user_id, client_key,
                    norm_ref=normalize_invoice_ref(inv.get("invoice_number"), src.get("subject")),
                    thread_id=src.get("thread_id"),
                    amount=float(amount),
                    subject=normalize_subject(src.get("subject")),
                )
                if related:
                    await _record_thread_evidence(
                        db, user_id, related["_id"],
                        now_iso=now_iso,
                        message_id=anchor_id,
                        subject=normalize_subject(src.get("subject")),
                    )
                    ref = related.get("invoice_ref_normalized")
                    if ref:
                        invoice_ids_by_ref[ref] = related["_id"]
                    logger.info(
                        "sweep.write SKIP_FOLLOWUP client=%s ref=%s msg=%s",
                        client_email, ref, anchor_id,
                    )
                    continue
            status_raw = (inv.get("status_suggestion") or "INVOICED").upper()
            status = STATUS_MAP.get(status_raw, "invoiced")
            balance = inv.get("balance_remaining")
            if balance is None:
                balance = float(amount)
            inv_num = inv.get("invoice_number")
            norm_ref = normalize_invoice_ref(inv_num, (src or {}).get("subject"))
            if not norm_ref and src:
                norm_ref = normalize_invoice_ref(None, src.get("subject"))
            doc = {
                "user_id": user_id,
                "counterparty_email": primary_email,
                "client_identity_key": client_key,
                "counterparty_name": cp_name,
                "amount": float(amount),
                "balance_remaining": float(balance),
                "paid_amount": max(0.0, float(amount) - float(balance)),
                "currency": (inv.get("currency") or "USD").upper(),
                "invoice_ref": (inv_num if is_plausible_invoice_ref(inv_num) else None) or norm_ref,
                "invoice_ref_normalized": norm_ref,
                "issue_date": inv.get("issue_date"),
                "due_date": inv.get("due_date"),
                "promise_date": None,
                "status": status,
                "kind": "invoice_sent",
                "source_message_id": anchor_id or f"sweep-{primary_email}-{norm_ref or amount}",
                "source_thread_id": (src or {}).get("thread_id"),
                "source_subject": normalize_subject((src or {}).get("subject")),
                "source_from": (src or {}).get("from"),
                "source_date": (src or {}).get("date"),
                "evidence_sentence": None,
                "confidence": conf,
                "created_at": now_iso,
            }

            needs_review = conf < CONFIDENCE_WRITE or not src
            if needs_review:
                if norm_ref:
                    existing = await find_invoice_by_key(db, user_id, client_key, norm_ref)
                    if existing and amounts_close(float(amount), float(existing.get("amount") or 0)):
                        logger.info(
                            "sweep.write SKIP_REVIEW client=%s ref=%s reason=already_in_ledger",
                            client_email, norm_ref,
                        )
                        if norm_ref:
                            invoice_ids_by_ref[norm_ref] = existing["_id"]
                        continue
                reason = "sweep_low_conf" if conf < CONFIDENCE_WRITE else "missing_anchor"
                existing_r = await db.review_items.find_one({"user_id": user_id, "source_message_id": doc["source_message_id"]})
                if not existing_r:
                    await db.review_items.insert_one({**doc, "review_status": "pending", "review_reason": reason})
                    review_created += 1
                    logger.info(
                        "sweep.write REVIEW client=%s ref=%s reason=%s conf=%.2f has_src=%s",
                        client_email, norm_ref, reason, conf, bool(src),
                    )
                continue

            outcome, inv_id = await upsert_sweep_invoice(db, user_id, doc, now_iso=now_iso)
            if outcome == "created":
                invoices_created += 1
            elif outcome == "review":
                review_created += 1
            if inv_id and norm_ref:
                invoice_ids_by_ref[norm_ref] = inv_id
            elif inv_id:
                invoice_ids_by_ref[f"__{inv_id}"] = inv_id

    if scoped_invoice_id is not None:
        scoped = await db.invoices.find_one({"_id": scoped_invoice_id, "user_id": user_id})
        if scoped:
            ref = scoped.get("invoice_ref_normalized")
            if ref:
                invoice_ids_by_ref[ref] = scoped["_id"]
            invoice_ids_by_ref[f"__{scoped['_id']}"] = scoped["_id"]

    sorted_events = sorted(
        dedupe_ai_events(result.get("events") or []),
        key=lambda e: (_EVENT_APPLY_ORDER.get(e.get("type") or "", 99), e.get("message_id") or ""),
    )
    # Drop question events that share a message_id with a concrete signal
    # (dispute / partial / promise / payment_claimed) — TE-105.
    _CONCRETE = {"dispute", "partial_payment", "promise", "payment_claimed", "correction"}
    concrete_mids = {
        (e.get("message_id") or "").strip()
        for e in sorted_events
        if e.get("type") in _CONCRETE and (e.get("message_id") or "").strip()
    }
    if concrete_mids:
        sorted_events = [
            e for e in sorted_events
            if not (
                e.get("type") == "question"
                and (e.get("message_id") or "").strip() in concrete_mids
            )
        ]
    client_emails = _client_identity_emails(primary_email, result, email_to_primary)
    domains = _domains_for_clients(client_emails)
    for ev in sorted_events:
        ev_conf = float(ev.get("confidence") or 0)
        ev_ref = normalize_invoice_ref(ev.get("invoice_ref"))
        inv_id = scoped_invoice_id if scoped_invoice_id is not None else None
        if not inv_id:
            inv_id = invoice_ids_by_ref.get(ev_ref) if ev_ref else None
        if not inv_id and len(invoice_ids_by_ref) == 1:
            inv_id = next(iter(invoice_ids_by_ref.values()))
        if inv_id and ev_conf >= CONFIDENCE_REVIEW:
            await _write_event(
                db, user_id, inv_id, ev, messages_by_id, now_iso,
                my_email=my_email,
                client_emails=client_emails,
                domains=domains,
                email_to_primary=email_to_primary,
            )
        elif ev_conf < CONFIDENCE_REVIEW:
            review_created += await _event_to_review(db, user_id, primary_email, ev, messages_by_id, now_iso, result)

    for um in result.get("unmatched_mentions") or []:
        review_created += await _unmatched_to_review(db, user_id, primary_email, um, now_iso)

    return invoices_created, review_created


async def _write_event(
    db,
    user_id,
    invoice_id,
    ev: dict,
    messages_by_id: dict,
    now_iso: str,
    force_review: bool = False,
    *,
    my_email: str = "",
    client_emails: set[str] | None = None,
    domains: set[str] | None = None,
    email_to_primary: dict[str, str] | None = None,
):
    from invoice_lifecycle import (
        effective_prior_status,
        has_pending_payment_claim,
    )
    from post_chase import clear_watching_on_client_event
    from promise_dates import resolve_stated_date

    msg_id = ev.get("message_id")
    if await event_already_recorded(
        db, user_id, invoice_id, ev.get("type"),
        message_id=msg_id,
        quote=ev.get("quote"),
    ):
        return

    ev_type = ev.get("type")
    msg = _resolve_event_message(ev, messages_by_id)

    inv = await db.invoices.find_one({"_id": invoice_id})
    if inv and not client_emails:
        client_emails = _client_identity_emails(
            (inv.get("counterparty_email") or "").lower(),
            counterparty_email=inv.get("counterparty_email"),
        )

    if my_email and not event_sender_allows_apply(
        ev_type, msg, my_email, client_emails, domains, email_to_primary,
    ):
        sender = _extract_email_addr(msg.get("from", "")) if msg else ""
        logger.info(
            "sweep.event REJECT inv=%s type=%s reason=wrong_sender from=%s msg=%s",
            invoice_id, ev_type, sender, msg_id,
        )
        return

    if ev_type == "promise":
        ev = dict(ev)
        ev["date"] = resolve_stated_date(
            ev.get("date"),
            quote=ev.get("quote"),
            message_body=msg.get("body") or msg.get("snippet"),
            message=msg,
        )

    activity = {"last_activity_at": now_iso, "status_updated_at": now_iso}
    if ev_type == "promise":
        bal = float(
            inv.get("balance_remaining")
            if inv and inv.get("balance_remaining") is not None
            else (inv or {}).get("amount") or 0
        )
        # Confirmed partial + promise on remainder stays partially_paid (T7).
        # Unconfirmed client claim + promise keeps the claim status.
        keep_partial = inv and inv.get("status") == "partially_paid" and bal > 0.005
        keep_claim = inv and has_pending_payment_claim(inv)
        patch: dict[str, Any] = {
            "promise_date": ev.get("date"),
            "chasing_paused": True,
            **activity,
        }
        if not keep_partial and not keep_claim:
            patch["status"] = "promised"
        await db.invoices.update_one({"_id": invoice_id}, {"$set": patch})
        await clear_watching_on_client_event(db, invoice_id, now_iso)
    elif ev_type == "dispute":
        bal = float(
            inv.get("balance_remaining")
            if inv and inv.get("balance_remaining") is not None
            else (inv or {}).get("amount") or 0
        )
        paid = float((inv or {}).get("paid_amount") or 0)
        pending_claim = inv and has_pending_payment_claim(inv)
        # TE-105: dispute + CONFIRMED partial — keep partially_paid when money
        # already landed. Unconfirmed client claims stay disputed + says-paid.
        keep_partial = (
            inv
            and not pending_claim
            and paid > 0.005
            and bal > 0.005
            and inv.get("status") in ("partially_paid", "disputed", "invoiced", "overdue", "promised")
        )
        patch = {"chasing_paused": True, **activity}
        if keep_partial and inv.get("status") == "partially_paid":
            # Status already partially_paid from earlier event in this batch.
            pass
        elif keep_partial:
            patch["status"] = "partially_paid"
        else:
            patch["status"] = "disputed"
        if pending_claim:
            patch["payment_claim_pending"] = True
            if inv.get("payment_claim_amount") is not None:
                patch["payment_claim_amount"] = inv["payment_claim_amount"]
        if ev.get("claimed_amount") is not None:
            # Reference only — the tracked amount never moves on a client claim.
            patch["disputed_claim_amount"] = float(ev["claimed_amount"])
        elif ev.get("amount") is not None and ev_type == "dispute":
            patch["disputed_claim_amount"] = float(ev["amount"])
        await db.invoices.update_one({"_id": invoice_id}, {"$set": patch})
        await clear_watching_on_client_event(db, invoice_id, now_iso)
    elif ev_type == "partial_payment" and ev.get("amount"):
        # Client-claimed partials go into the claim bucket — never paid_amount
        # until the user confirms receipt (Kestrel says-paid pattern).
        bal = float(
            inv.get("balance_remaining")
            if inv and inv.get("balance_remaining") is not None
            else (inv or {}).get("amount") or 0
        )
        applied = min(float(ev["amount"]), bal if bal > 0.005 else float(ev["amount"]))
        prev_status = effective_prior_status(inv) if inv else "invoiced"
        was_disputed = inv and (
            inv.get("status") == "disputed" or inv.get("disputed_claim_amount") is not None
        )
        patch = {
            "payment_claim_amount": applied,
            "payment_claim_pending": True,
            "payment_claim_quote": ev.get("quote"),
            "status_before_claim": (
                inv.get("status_before_claim")
                if inv and inv.get("status") == "paid_unconfirmed"
                else prev_status
            ),
            "claim_balance_before": bal,
            "claim_paid_before": float((inv or {}).get("paid_amount") or 0),
            "chasing_paused": True,
            **activity,
        }
        if was_disputed:
            patch["status"] = "disputed"
            if inv.get("disputed_claim_amount") is not None:
                patch["disputed_claim_amount"] = inv["disputed_claim_amount"]
        else:
            patch["status"] = "paid_unconfirmed"
        # Do NOT change paid_amount / balance_remaining.
        await db.invoices.update_one({"_id": invoice_id}, {"$set": patch})
        await clear_watching_on_client_event(db, invoice_id, now_iso)
    elif ev_type == "payment_claimed" and inv:
        prev_status = effective_prior_status(inv)
        bal = float(
            inv.get("balance_remaining")
            if inv.get("balance_remaining") is not None
            else inv.get("amount") or 0
        )
        claim_amt = float(ev["amount"]) if ev.get("amount") is not None else bal
        if claim_amt <= 0.005:
            claim_amt = bal
        was_disputed = (
            inv.get("status") == "disputed" or inv.get("disputed_claim_amount") is not None
        )
        patch = {
            "status": "disputed" if was_disputed else "paid_unconfirmed",
            "status_before_claim": prev_status,
            "payment_claim_amount": claim_amt,
            "payment_claim_pending": True,
            "payment_claim_quote": ev.get("quote"),
            "claim_balance_before": bal,
            "claim_paid_before": float(inv.get("paid_amount") or 0),
            "chasing_paused": True,
            **activity,
        }
        if was_disputed and inv.get("disputed_claim_amount") is not None:
            patch["disputed_claim_amount"] = inv["disputed_claim_amount"]
        await db.invoices.update_one({"_id": invoice_id}, {"$set": patch})
        await clear_watching_on_client_event(db, invoice_id, now_iso)
    elif ev_type == "correction" and inv and ev.get("amount") is not None:
        from ledger_reconcile import apply_invoice_correction
        await apply_invoice_correction(
            db, user_id, inv, float(ev["amount"]),
            now_iso=now_iso,
            due_date=ev.get("date"),
            message_id=msg_id,
            subject=msg.get("subject"),
            quote=ev.get("quote"),
            record_event=False,
        )
        activity = {"last_activity_at": now_iso, "status_updated_at": now_iso}
    elif ev_type == "approved":
        # Soft signal: invoice acknowledged / routed for payment. Status unchanged;
        # the flag softens future chase tone and is cleared on payment/confirm.
        await db.invoices.update_one(
            {"_id": invoice_id},
            {"$set": {
                "client_approved": True,
                "approved_at": now_iso,
                "approval_quote": ev.get("quote"),
                **activity,
            }},
        )
        await clear_watching_on_client_event(db, invoice_id, now_iso)
    elif ev_type == "question":
        # Client asked something (clarification / uncertainty) — surface as
        # needs-reply, never a payment-state change.
        await db.invoices.update_one(
            {"_id": invoice_id},
            {"$set": {
                "needs_reply": True,
                "needs_reply_quote": ev.get("quote"),
                "needs_reply_at": now_iso,
                **activity,
            }},
        )
        await clear_watching_on_client_event(db, invoice_id, now_iso)
    elif ev_type == "due_date_adjusted" and inv:
        from ledger_reconcile import parse_iso_date as _parse_iso
        new_due = resolve_stated_date(
            ev.get("date"),
            quote=ev.get("quote"),
            message_body=msg.get("body") or msg.get("snippet"),
            message=msg,
        )
        if new_due:
            patch = {"due_date": new_due, "due_date_assumed": False, **activity}
            due_dt = _parse_iso(new_due)
            if due_dt and inv.get("status") in ("invoiced", "overdue"):
                today = datetime.now(timezone.utc).date()
                patch["status"] = "overdue" if due_dt.date() < today else "invoiced"
            await db.invoices.update_one({"_id": invoice_id}, {"$set": patch})
            ev = {**ev, "date": new_due}
        else:
            await db.invoices.update_one({"_id": invoice_id}, {"$set": activity})
    else:
        await db.invoices.update_one({"_id": invoice_id}, {"$set": {"last_activity_at": now_iso}})
    await db.invoice_events.insert_one({
        "user_id": user_id,
        "invoice_id": invoice_id,
        "action": EVENT_KIND_MAP.get(ev_type, ev_type or "note"),
        "at": now_iso,
        "meta": {
            "quote": ev.get("quote"),
            "message_id": ev.get("message_id"),
            "message_date": msg.get("date"),
            "subject": msg.get("subject"),
            "from": msg.get("from"),
            "thread_id": msg.get("thread_id"),
            "confidence": ev.get("confidence"),
            "date": ev.get("date"),
            "amount": ev.get("amount"),
            "old_amount": ev.get("old_amount"),
            "claimed_amount": ev.get("claimed_amount"),
            "reference": ev.get("reference"),
            "dispute_kind": ev.get("dispute_kind"),
            "invoice_ref": ev.get("invoice_ref"),
        },
    })


async def _event_to_review(db, user_id, client_email, ev, messages_by_id, now_iso, result) -> int:
    mid = ev.get("message_id") or f"ev-{client_email}-{ev.get('type')}"
    if await db.review_items.find_one({"user_id": user_id, "source_message_id": mid}):
        return 0
    msg = messages_by_id.get(ev.get("message_id") or "")
    await db.review_items.insert_one({
        "user_id": user_id,
        "counterparty_email": client_email,
        "counterparty_name": (result.get("client") or {}).get("name"),
        "amount": ev.get("amount"),
        "currency": "USD",
        "kind": EVENT_KIND_MAP.get(ev.get("type"), "payment_promise"),
        "status": "promised" if ev.get("type") == "promise" else "invoiced",
        "source_message_id": mid,
        "source_subject": (msg or {}).get("subject"),
        "source_from": (msg or {}).get("from"),
        "source_date": (msg or {}).get("date"),
        "evidence_sentence": ev.get("quote"),
        "confidence": float(ev.get("confidence") or 0),
        "review_status": "pending",
        "review_reason": "sweep_event",
        "created_at": now_iso,
    })
    return 1


async def _unmatched_to_review(db, user_id, client_email, um, now_iso) -> int:
    mid = um.get("message_id") or f"um-{hash(um.get('text', ''))}"
    if await db.review_items.find_one({"user_id": user_id, "source_message_id": mid}):
        return 0
    await db.review_items.insert_one({
        "user_id": user_id,
        "counterparty_email": client_email,
        "kind": "none",
        "source_message_id": mid,
        "evidence_sentence": um.get("text"),
        "confidence": 0.5,
        "review_status": "pending",
        "review_reason": "sweep_unmatched",
        "created_at": now_iso,
    })
    return 1


async def persist_client_state(
    db, user_id, candidates: dict[str, list[str]], domains: set[str],
    email_to_primary: dict[str, str] | None = None,
):
    identities = list(candidates.keys())
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {
            "client_identities": identities,
            "client_domains": list(domains),
            "anchor_map": candidates,
            "email_to_primary": email_to_primary or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )


async def run_client_sweep_scan(db, user_id, job_id, months: int = 12):
    """Full historical client-sweep. Updates scan_jobs doc."""
    from scan_pipeline import _update_job, reconcile_receipts

    counts: dict[str, Any] = {
        "fetched": 0,
        "filtered_in": 0,
        "ai_extracted": 0,
        "invoices_created": 0,
        "review_items": 0,
        "receipts_created": 0,
        "clients_found": 0,
        "messages_swept": 0,
    }

    try:
        access = await get_access_token(db, user_id)
    except GmailAuthError:
        await _update_job(db, job_id, {"status": "error", "phase": "auth", "error": "Gmail auth failed. Please reconnect."})
        return

    conn = await db.gmail_connections.find_one({"user_id": user_id})
    my_email = ((conn or {}).get("email") or "").lower()
    now_iso = datetime.now(timezone.utc).isoformat()

    logger.info("sweep.START user=%s job=%s months=%s my_email=%s", user_id, job_id, months, my_email)
    await _update_job(db, job_id, {"status": "running", "phase": "fetching", "counts": counts})

    try:
        await _run_client_sweep_scan_body(
            db, user_id, job_id, months, access, my_email, now_iso, counts, _update_job, reconcile_receipts,
        )
    except Exception as e:
        logger.exception("sweep.ERROR user=%s err=%s", user_id, e)
        await _update_job(db, job_id, {
            "status": "error",
            "phase": "error",
            "error": str(e)[:500],
            "counts": counts,
        })


async def _run_client_sweep_scan_body(
    db, user_id, job_id, months, access, my_email, now_iso, counts, _update_job, reconcile_receipts,
):
    candidates, domains = await pass1_discover_anchors(access, db, user_id, my_email, months)
    candidates, email_to_primary = merge_candidates_by_domain(candidates)
    counts["clients_found"] = len(candidates)
    counts["fetched"] = sum(len(v) for v in candidates.values())
    await _update_job(db, job_id, {"phase": "filtering", "counts": counts})

    if not candidates:
        logger.warning("sweep.DONE user=%s no_anchors_found", user_id)
        counts["receipts_created"] = await pass3_parse_receipts(access, db, user_id, months, now_iso)
        await _update_job(db, job_id, {
            "status": "complete", "phase": "complete", "counts": counts,
            "finished_at": now_iso,
        })
        return

    client_emails = list(candidates.keys())[:MAX_CLIENTS_FOR_AI]
    if len(candidates) > MAX_CLIENTS_FOR_AI:
        logger.warning("sweep.CLIENT_CAP total=%s capped=%s", len(candidates), MAX_CLIENTS_FOR_AI)

    # Pass 2 — sweep
    msg_ids = await pass2_collect_ids(access, client_emails, domains, months)
    counts["messages_swept"] = len(msg_ids)
    counts["filtered_in"] = len(msg_ids)
    await _update_job(db, job_id, {"phase": "extracting", "counts": counts})

    client_email_set = set(client_emails)
    by_client: dict[str, list[dict]] = {c: [] for c in client_emails}
    seen_filter: set[str] = set()
    activity_only = 0

    for mid in msg_ids:
        msg = await get_message(access, mid)
        if not msg:
            continue
        ck = assign_client_key(msg, client_email_set, domains, my_email, email_to_primary)
        if not ck or ck not in by_client:
            continue
        verdict, reason = pass2_filter_message(msg, seen_filter)
        if verdict == "drop":
            continue
        seen_filter.add(mid)
        if verdict == "activity":
            activity_only += 1
            continue
        by_client[ck].append(msg)

    logger.info("sweep.pass2 GROUPED clients=%s activity_only=%s", len(by_client), activity_only)

    # Pass 3 — receipts (parallel to AI prep)
    counts["receipts_created"] = await pass3_parse_receipts(access, db, user_id, months, now_iso)

    # Pass 4 — AI per client (phase stays "extracting" until AI finishes)
    sem = asyncio.Semaphore(AI_CONCURRENCY)
    ai_results: list[tuple[str, dict, dict[str, dict]]] = []

    async def _one_client(client: str):
        msgs = by_client.get(client) or []
        anchor_ids = candidates.get(client) or []
        for aid in anchor_ids:
            if not any(m["id"] == aid for m in msgs):
                am = await get_message(access, aid)
                if am:
                    msgs.append(am)
        if not msgs:
            logger.warning("sweep.pass4 SKIP client=%s reason=no_messages", client)
            return
        anchor_ids = primary_anchor_ids(candidates.get(client) or [], msgs)
        selected, truncated = select_messages_for_client(msgs, set(anchor_ids))
        async with sem:
            result = await extract_client_with_ai(client, selected, anchor_ids, my_email, truncated)
        if result:
            ai_results.append((client, result, {m["id"]: m for m in selected}))
            counts["ai_extracted"] = len(ai_results)
            await _update_job(db, job_id, {"phase": "extracting", "counts": counts})

    await asyncio.gather(*[_one_client(c) for c in client_emails])
    counts["ai_extracted"] = len(ai_results)
    logger.info("sweep.pass4 DONE clients=%s ai_ok=%s", len(client_emails), counts["ai_extracted"])
    await _update_job(db, job_id, {"phase": "building", "counts": counts})

    for client, result, msg_map in ai_results:
        inv_c, rev_c = await apply_client_result(
            db, user_id, client, result, msg_map, my_email, now_iso, email_to_primary,
            pass1_anchor_ids=candidates.get(client) or [],
        )
        counts["invoices_created"] += inv_c
        counts["review_items"] += rev_c

    try:
        recon = await reconcile_receipts(db, user_id)
        counts["receipts_matched"] = recon.get("matched", 0)
        counts["receipts_ambiguous"] = recon.get("ambiguous", 0)
    except Exception as e:
        logger.warning("sweep reconcile failed: %s", e)

    from ledger_reconcile import dedupe_existing_invoices, backfill_invoice_keys, backfill_assumed_due_dates, get_default_payment_terms_days
    terms = await get_default_payment_terms_days(db, user_id)
    await backfill_invoice_keys(db, user_id)
    counts["due_dates_assumed"] = await backfill_assumed_due_dates(db, user_id, terms)
    counts["duplicates_merged"] = await dedupe_existing_invoices(db, user_id, now_iso)

    await persist_client_state(db, user_id, candidates, domains, email_to_primary)
    await _update_job(db, job_id, {
        "status": "complete",
        "phase": "complete",
        "counts": counts,
        "finished_at": now_iso,
    })
    logger.info("sweep.DONE user=%s counts=%s", user_id, counts)


async def run_client_sweep_sync(db, user_id, months: int = 12) -> dict:
    """Incremental tick: new anchors + messages from known clients."""
    from scan_pipeline import _already_processed, reconcile_receipts
    counts: dict[str, Any] = {
        "fetched": 0, "filtered_in": 0, "ai_extracted": 0,
        "invoices_created": 0, "receipts_created": 0, "review_items": 0,
        "receipts_matched": 0, "receipts_ambiguous": 0,
    }
    conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        return {**counts, "skipped": "no_connection"}
    my_email = (conn.get("email") or "").lower()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        access = await get_access_token(db, user_id)
    except GmailAuthError:
        return {**counts, "skipped": "auth_error"}

    from live_detection import run_live_detection_tick
    live = await run_live_detection_tick(db, user_id)
    counts["live_detected"] = live.get("detected_count", 0)
    if live.get("new_invoices"):
        counts["new_invoices"] = live["new_invoices"]

    state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    candidates: dict[str, list[str]] = dict(state.get("anchor_map") or {})
    domains: set[str] = set(state.get("client_domains") or [])
    client_emails: set[str] = set(state.get("client_identities") or [])
    email_to_primary: dict[str, str] = dict(state.get("email_to_primary") or {})

    # Discover new anchors in a short window
    w = "newer_than:7d"
    for q in [
        f'in:sent {w} subject:(invoice OR payment OR "amount due")',
        f'in:sent {w} ("please pay" OR "payment due" OR "balance due")',
    ]:
        ids = await list_message_ids(access, q, max_pages=2)
        counts["fetched"] += len(ids)
        blocklist = await load_blocklist(db, user_id)
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
        counts["receipts_created"] = await pass3_parse_receipts(access, db, user_id, months, now_iso)
        await db.gmail_sync_state.update_one(
            {"user_id": user_id},
            {"$set": {"last_sync_status": "ok", "last_synced_at": now_iso}},
            upsert=True,
        )
        return counts

    recent_ids = await pass2_collect_ids(access, list(client_emails), domains, months)

    fresh: list[str] = []
    for mid in recent_ids[:80]:
        if not await _already_processed(db, user_id, mid):
            fresh.append(mid)
    counts["filtered_in"] = len(fresh)

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
        counts["ai_extracted"] += 1
        inv_c, rev_c = await apply_client_result(
            db, user_id, client, result, {m["id"]: m for m in selected}, my_email, now_iso, email_to_primary,
            pass1_anchor_ids=anchor_ids,
        )
        counts["invoices_created"] += inv_c
        counts["review_items"] += rev_c

    counts["receipts_created"] = await pass3_parse_receipts(access, db, user_id, months, now_iso)
    try:
        recon = await reconcile_receipts(db, user_id)
        counts["receipts_matched"] = recon.get("matched", 0)
        counts["receipts_ambiguous"] = recon.get("ambiguous", 0)
    except Exception:
        pass

    from ledger_reconcile import (
        backfill_assumed_due_dates, backfill_invoice_keys, dedupe_existing_invoices,
        get_default_payment_terms_days,
    )
    terms = await get_default_payment_terms_days(db, user_id)
    await backfill_invoice_keys(db, user_id)
    await backfill_assumed_due_dates(db, user_id, terms)
    await dedupe_existing_invoices(db, user_id, now_iso)

    await persist_client_state(db, user_id, candidates, domains, email_to_primary)
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"last_sync_status": "ok", "last_synced_at": now_iso, "last_counts": counts}},
        upsert=True,
    )
    return counts
