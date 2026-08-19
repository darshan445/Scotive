"""AI extraction for onboarding seed scan — clients + invoices from sent mail."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from client_sweep import (
    CONSUMER_DOMAINS,
    _extract_email_addr,
    _sender_domain,
    assign_client_key,
    format_msg_line,
    parse_email_date,
    preprocess_body,
)
from gmail_client import (
    fetch_attachment_bytes,
    get_messages_batch,
    get_thread_messages,
    list_message_ids,
)
from ledger_reconcile import (
    is_invoice_followup,
    is_plausible_invoice_ref,
    normalize_invoice_ref,
    normalize_source_date,
    normalize_subject,
)
from pdf_extract import extract_pdf_text, is_pdf_part
from post_track_enrichment import (
    _gmail_after_date,
    _invoice_anchor_dt,
    _out_of_thread_relevance,
)

from llm_client import (
    OPENAI_URL,
    openai_api_key,
    openai_headers,
    openai_message_content,
    openai_model,
)

logger = logging.getLogger("scotive.seed_ai")
SEED_AI_CONCURRENCY = int(os.environ.get("SEED_AI_CONCURRENCY", "4"))
SEED_CONFIDENCE_MIN = float(os.environ.get("SEED_CONFIDENCE_MIN", "0.65"))
MAX_MESSAGES_PER_CLIENT = 25
MAX_OOT_FETCH = 80
OOT_LIST_PAGES = 6

CLIENT_REJECTS_REDUCTION_RE = re.compile(
    r"retain\s+(?:the\s+)?(?:current\s+)?(?:bill|invoice)|"
    r"(?:keep|leave)\s+(?:the\s+)?(?:bill|invoice|amount)\s+as\s+is|"
    r"don'?t\s+reduce|do\s+not\s+reduce|"
    r"no\s+need\s+to\s+reduce|"
    r"(?:stick|stay)\s+with\s+(?:the\s+)?(?:original|current)|"
    r"don'?t\s+reduce\s+any",
    re.I,
)
USD_TOTAL_PATTERNS = (
    re.compile(r"Converted to USD[^:]*:\s*\$?\s*([\d,]+\.?\d*)", re.I),
    re.compile(r"Total:[^$\n]*\$([\d,]+\.?\d*)", re.I),
)

VALID_ENRICHED_STATUSES = frozenset({
    "invoiced",
    "overdue",
    "promised",
    "partially_paid",
    "disputed",
    "paid_unconfirmed",
    "promise_broken",
})

_SEED_SCHEMA_AND_RULES = """Return STRICT JSON only:
{
  "client_name": string|null,
  "invoices": [{
    "message_id": string,
    "invoice_number": string|null,
    "amount": number,
    "currency": "USD"|"INR"|"EUR"|string,
    "issue_date": "YYYY-MM-DD"|null,
    "due_date": "YYYY-MM-DD"|null,
    "confidence": number,
    "enriched_status": "invoiced"|"overdue"|"promised"|"partially_paid"|"disputed"|"paid_unconfirmed"|null,
    "promise_date": "YYYY-MM-DD"|null,
    "balance_remaining": number|null,
    "paid_amount": number|null,
    "status_evidence": string|null,
    "client_approved": true|false|null,
    "approval_quote": string|null,
    "needs_reply": true|false|null,
    "needs_reply_quote": string|null,
    "dispute_kind": "wrong_amount"|"scope"|"quality"|"terms"|"other"|null,
    "disputed_claim_amount": number|null
  }],
  "discarded_message_ids": [string]
}

Rules:
- ONLY money the USER is owed by this CLIENT (accounts receivable). Ignore vendor bills the user pays.
- Informal payment requests ARE invoices when the USER sent them with a clear amount.
- Use PDF text as the primary source for amount, invoice number, and due date on the original send when present.
- Read ALL provided messages chronologically — in-thread AND out-of-thread — before deciding each invoice row.
- The LATEST exchange decides amount and status. Never discard post-dispute or post-negotiation replies as chatter — a short late reply ("perfect, will process it by tomorrow") often carries the current status.
- amount = final AGREED total after the full thread negotiation:
  - Start from the original USER invoice send (anchor message_id).
  - A later USER revision (re-sent invoice with a new total, OR an in-thread
    correction like "revising this to $X", "actually it's $X", "correcting to $X",
    "let's make it $X") updates amount to that figure. A proactive USER correction
    does NOT require a prior client dispute — amount changes, status stays
    invoiced/overdue (or whatever the latest CLIENT signal implies) unless a
    dispute is still open and unresolved.
  - If the USER reduces the amount and the CLIENT rejects that reduction (e.g. "retain the bill as is", "don't reduce any efforts", "keep the original amount"), revert to the pre-reduction total — NOT the lowered figure.
  - Client explicit approval of a specific revised total → use that revised amount.
  - The USER accepting the CLIENT's disputed figure IS the agreement — use that figure even before the client replies again. When the USER states several figures across messages ("$750", then "$860", then "$750"), the LAST figure the two sides converge on wins.
  - A CLIENT's claimed figure alone NEVER changes amount. Until the USER accepts or re-sends at the client's figure, amount stays the USER's originally invoiced total; put the client's figure in disputed_claim_amount and their sentence in status_evidence instead.
- balance_remaining / paid_amount: set when client partial payment or remaining balance is clear; else null.
- enriched_status (only when clearly supported by CLIENT messages, never from USER reminders alone):
  - promised: client committed to pay by a FUTURE date or timeframe, or money is routed into a process but has NOT moved yet ("will pay next week", "expect it processed by end of month", "need another week or two", "sending this through AP today — should hit your account within the week", "will process this week") → set promise_date, resolved from the REPLY's message date: "end of month" = last day of that month; "next week" = +7 days; "a week or two" = +14 days; "within the week" = that week's Friday
  - partially_paid: client paid part, balance remains
  - disputed: client disputes amount/terms → set dispute_kind (wrong_amount when they say a different figure was agreed, e.g. "we agreed on $750, can you resend?" → disputed_claim_amount 750, amount stays the USER's invoiced total)
  - MULTI-SIGNAL (critical): one CLIENT message can carry BOTH a dispute AND a partial payment ("We agreed $1,800 — but either way, sending $1,000 now as a partial"). In that case set enriched_status to partially_paid (money moved), ALSO set disputed_claim_amount + dispute_kind, put the dispute sentence in status_evidence (or the clearest claim phrase), set paid_amount / balance_remaining for the partial, and set needs_reply false — do NOT invent a separate clarification question from residual phrases like "will sort the rest after we confirm".
  - DISPUTE RESOLUTION: a wrong_amount dispute ENDS the moment the USER accepts or re-sends at the client's figure ("sure, let's make it $750 then", "corrected invoice attached — $750"). From that message on the invoice is NO LONGER disputed: amount = the agreed figure, and status comes from the LATEST client message — no further client reply → invoiced/null; client acceptance with a payment window ("perfect, will process it by tomorrow") → promised with promise_date resolved from that reply's date. Never return disputed based on an old dispute that a later message resolved.
  - paid_unconfirmed: PAST-TENSE / completed payment claims only, no bank receipt ("sent it over on venmo", "just paid through the link", "processed already", "sending it right now on venmo" — a direct transfer happening as they write). TENSE TEST: has the money already left the client's hands? "Sent/paid/transferred" = paid_unconfirmed; "will send / sending through AP / should arrive" = promised, never paid_unconfirmed. If part was already received, keep balance_remaining at the outstanding portion.
  - overdue: only when due_date is in the past relative to today AND no stronger status applies
  - null / invoiced: open invoice with no client status signal yet
- client_approved: true when the client acknowledges/approves the invoice or routes it for payment ("approved on our end", "forwarded to AP", "routing to finance"). If the approval ALSO states an arrival window ("sending through AP today, should hit your account within the week"), set client_approved true AND enriched_status promised with promise_date resolved from that window — never paid_unconfirmed. A reference that "will be issued" later ("reference will be PO-88123 once issued") is NOT a payment reference. Set approval_quote to the client's sentence.
- needs_reply: true when the client asks the USER something needing an answer — clarification ("can you break down the QA line item?") or UNCERTAINTY about payment ("can you check if this was already paid?"). Uncertainty is NEVER paid_unconfirmed; a clarification request is NOT a dispute. Status stays unchanged. Set needs_reply_quote. NEVER set needs_reply when the same message is already classified as dispute, partial payment, promise, or payment claim — residual clauses in those messages are not standalone questions.
- If the CLIENT corrects the payment-window anchor or due date ("QA held it until July 6th, count from there"), recompute due_date from the NEW anchor plus the invoice's stated window — status stays invoiced, not promised.
- One client reply can set DIFFERENT statuses on DIFFERENT invoice rows — map by invoice number ("paying #77 today, need another week or two on #81" = #77 paid_unconfirmed AND #81 promised with its own promise_date).
- SENDER DIRECTION: lines labelled "YOU →" are user-sent; "{client} → YOU" are client-sent.
  Status signals (promise, dispute, paid_unconfirmed, partial) MUST come from client-sent lines only.
- due_date: when explicitly stated in the invoice (e.g. "due is 3 jul 2026", "due July 3", "due 07/03/2026"). Return ISO YYYY-MM-DD. Resolve relative phrases from the MESSAGE DATE. null only if truly not stated.
- Reminders and payment chasers are NOT separate invoices — one row per distinct invoice per client.
- MULTI-INVOICE EMAILS: a single USER email can state SEVERAL distinct invoices (e.g. "Invoice #77 (June): $600, Invoice #81 (July): $600"). Return ONE ROW PER INVOICE NUMBER, each with its own amount, due date, and status — same message_id on every row. Never combine them into one row or sum their amounts.
- discarded_message_ids: promos, unrelated chatter, duplicate reminders.
- Do not invent amounts or dates. Omit uncertain rows instead of guessing.
- confidence 0.0-1.0 for each invoice row.
"""

SEED_CLIENT_PROMPT = (
    """You analyse invoice-related email between a small business owner (USER) and ONE client.
Context includes:
- USER sent invoice anchors (with PDF text when available)
- FULL threads for those invoices (every reply in-thread)
- OUT-OF-THREAD client mail (separate threads mentioning the same invoices)

"""
    + _SEED_SCHEMA_AND_RULES
)

# Per-conversation variant: ONE invoice email + its thread + related out-of-thread
# mail. Focused context so the model decides one invoice at a time.
SEED_INVOICE_PROMPT = (
    """You analyse ONE invoice conversation between a small business owner (USER) and their client.
Context (chronological, oldest first):
- The USER's invoice email(s) that anchor this conversation (with PDF text when available)
- Every reply in the thread
- Out-of-thread client emails that reference the same invoice

Most conversations contain exactly ONE invoice — return one row for it. A single
email can state MULTIPLE distinct invoices (e.g. "Invoice #77: $600, Invoice #81: $600")
— then return one row per distinct invoice, each with the same message_id.

A CURRENT_TRACKED_STATE line may be included: that is the state stored after the
PREVIOUS sync — possibly STALE background, never ground truth. Re-read the whole
conversation and return the state as of the LATEST message; when newer messages
change the amount or status, return the NEW values instead of restating the
tracked state.

"""
    + _SEED_SCHEMA_AND_RULES
)

SEED_GATE_PROMPT = """You classify ONE email that the USER sent. Decide whether it is the USER billing or requesting payment from a client: an invoice, a payment request with an amount, a retainer bill, a deal recap stating an owed amount, or an invoice notification the USER sent via accounting software (QuickBooks, FreshBooks, Stripe, Wave, Zoho).

NOT invoices: marketing/newsletters, receipts for things the USER bought, vendor bills the USER pays, meeting notes, proposals/quotes with no billing intent, personal mail.

Return STRICT JSON: {"is_invoice": true|false, "confidence": 0.0-1.0}"""


def _format_message_block(msg: dict, *, my_email: str) -> str:
    pdf_text = (msg.get("pdf_text") or "").strip()
    if pdf_text:
        body = preprocess_body(msg.get("body") or msg.get("snippet") or "", 2800)
        atts = ", ".join(msg.get("attachment_names") or []) or "(none)"
        return (
            f"=== ANCHOR MESSAGE id={msg['id']} ===\n"
            f"DATE: {msg.get('date', '')}\n"
            f"SUBJECT: {msg.get('subject', '')}\n"
            f"ATTACHMENTS: {atts}\n"
            f"BODY:\n{body}\n"
            f"PDF_TEXT:\n{pdf_text}\n"
        )
    return format_msg_line(msg, my_email)


def _extract_usd_invoice_total(msg: dict) -> float | None:
    """Pull the invoice total in USD from a USER send (prefers explicit Total / Converted lines)."""
    hay = " ".join([
        msg.get("subject") or "",
        msg.get("body") or "",
        msg.get("snippet") or "",
        msg.get("pdf_text") or "",
    ])
    for pat in USD_TOTAL_PATTERNS:
        m = pat.search(hay)
        if m:
            try:
                val = float(m.group(1).replace(",", ""))
                if val >= 50:
                    return val
            except ValueError:
                continue
    dollars = re.findall(r"\$\s*([\d,]+\.?\d*)", hay)
    if dollars:
        try:
            return float(dollars[-1].replace(",", ""))
        except ValueError:
            pass
    return None


def resolve_negotiated_amount(
    anchor_id: str,
    messages: list[dict],
    my_email: str,
    ai_amount: float,
) -> float:
    """If client rejected a USER downward revision, restore the pre-reduction amount."""
    my_lc = my_email.lower()
    by_id = {m["id"]: m for m in messages if m.get("id")}
    anchor = by_id.get(anchor_id)
    if not anchor:
        return ai_amount

    thread_key = anchor.get("thread_id") or f"_solo_{anchor_id}"
    thread = [
        m for m in messages
        if (m.get("thread_id") or f"_solo_{m['id']}") == thread_key
    ]
    thread.sort(
        key=lambda m: (parse_email_date(m.get("date")) or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp(),
    )

    user_totals: list[tuple[datetime, float]] = []
    for msg in thread:
        if _extract_email_addr(msg.get("from", "")) != my_lc:
            continue
        total = _extract_usd_invoice_total(msg)
        if total is not None and total > 0:
            dt = parse_email_date(msg.get("date")) or datetime(1970, 1, 1, tzinfo=timezone.utc)
            user_totals.append((dt, total))

    if len(user_totals) < 2:
        return ai_amount

    for i in range(len(user_totals) - 1):
        prev_dt, prev_amt = user_totals[i]
        rev_dt, rev_amt = user_totals[i + 1]
        if rev_amt >= prev_amt - 0.01:
            continue
        for msg in thread:
            msg_dt = parse_email_date(msg.get("date"))
            if not msg_dt or msg_dt <= rev_dt:
                continue
            if _extract_email_addr(msg.get("from", "")) == my_lc:
                continue
            body = " ".join([
                msg.get("subject") or "",
                msg.get("body") or "",
                msg.get("snippet") or "",
            ])
            if CLIENT_REJECTS_REDUCTION_RE.search(body):
                logger.info(
                    "seed.negotiation REVERT anchor=%s reduced=%.2f restored=%.2f",
                    anchor_id, rev_amt, prev_amt,
                )
                return prev_amt

    return ai_amount


_AMOUNT_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})?")


def _user_stated_amounts(
    messages: list[dict], my_email: str, thread_id: str | None,
) -> set[float]:
    """Every figure the USER stated in their own words (quoted history stripped),
    subject lines, or attached PDFs — the only figures allowed to become amount."""
    out: set[float] = set()
    my = my_email.lower()
    for m in messages:
        if _extract_email_addr(m.get("from", "")) != my:
            continue
        if thread_id and m.get("thread_id") and m["thread_id"] != thread_id:
            continue
        text = "\n".join([
            preprocess_body(m.get("body") or m.get("snippet") or "", 4000),
            m.get("pdf_text") or "",
            m.get("subject") or "",
        ])
        for tok in _AMOUNT_TOKEN_RE.findall(text):
            try:
                out.add(round(float(tok.replace(",", "")), 2))
            except ValueError:
                pass
    return out


def _draft_invoices_from_sent(sent_msgs: list[dict]) -> list[dict]:
    from seed_scan import extract_amount_currency

    drafts: list[dict] = []
    for msg in sent_msgs:
        amount, currency = extract_amount_currency(msg)
        ref = normalize_invoice_ref(None, msg.get("subject"))
        drafts.append({
            "source_message_id": msg["id"],
            "source_thread_id": msg.get("thread_id"),
            "source_date": normalize_source_date(msg.get("date")),
            "invoice_ref_normalized": ref,
            "invoice_ref": ref,
            "amount": amount,
            "currency": currency or "USD",
        })
    return drafts


async def _fetch_client_threads(access: str, sent_msgs: list[dict]) -> list[dict]:
    thread_ids = {
        m.get("thread_id")
        for m in sent_msgs
        if m.get("thread_id")
    }
    if not thread_ids:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for tid in thread_ids:
        try:
            thread_msgs = await get_thread_messages(access, tid)
        except Exception as e:
            logger.warning("seed.thread FAIL thread=%s err=%s", tid, e)
            continue
        for msg in thread_msgs:
            mid = msg.get("id")
            if mid and mid not in seen:
                seen.add(mid)
                out.append(msg)
    return out


async def _fetch_out_of_thread_client_mail(
    access: str,
    client_email: str,
    draft_invoices: list[dict],
    excluded_thread_ids: set[str],
    my_email: str,
    *,
    domains: set[str] | None = None,
    email_to_primary: dict[str, str] | None = None,
) -> list[dict]:
    if not draft_invoices:
        return []

    domains = domains or set()
    email_to_primary = email_to_primary or {}
    anchor_dt = min(_invoice_anchor_dt(inv) for inv in draft_invoices)
    after = _gmail_after_date(anchor_dt)
    primary = email_to_primary.get(client_email.lower(), client_email.lower())

    queries = [f"from:{primary} after:{after}"]
    dom = _sender_domain(primary)
    if dom and dom not in CONSUMER_DOMAINS:
        queries.append(f"from:{dom} after:{after}")

    seen: set[str] = set()
    candidate_ids: list[str] = []
    for q in queries:
        try:
            ids = await list_message_ids(access, q, max_pages=OOT_LIST_PAGES)
        except Exception as e:
            logger.warning("seed.oot LIST FAIL client=%s err=%s", primary, e)
            continue
        for mid in ids:
            if mid not in seen:
                seen.add(mid)
                candidate_ids.append(mid)

    candidate_ids = candidate_ids[:MAX_OOT_FETCH]
    if not candidate_ids:
        return []

    client_emails = {primary}
    kept: list[dict] = []
    try:
        batch = await get_messages_batch(access, candidate_ids)
    except Exception as e:
        logger.warning("seed.oot BATCH FAIL client=%s err=%s", primary, e)
        return []

    for msg in batch:
        tid = msg.get("thread_id") or ""
        if tid and tid in excluded_thread_ids:
            continue
        msg_dt = parse_email_date(msg.get("date"))
        if msg_dt and msg_dt < anchor_dt:
            continue
        ck = assign_client_key(msg, client_emails, domains, my_email, email_to_primary)
        if not ck:
            continue
        if not _out_of_thread_relevance(msg, draft_invoices):
            continue
        kept.append(msg)
    return kept


def _merge_client_messages(
    sent_msgs: list[dict],
    thread_msgs: list[dict],
    oot_msgs: list[dict],
) -> list[dict]:
    by_id: dict[str, dict] = {}
    for msg in [*sent_msgs, *thread_msgs, *oot_msgs]:
        mid = msg.get("id")
        if not mid:
            continue
        existing = by_id.get(mid)
        if existing and existing.get("pdf_text") and not msg.get("pdf_text"):
            msg = {**msg, "pdf_text": existing["pdf_text"]}
        by_id[mid] = msg
    merged = list(by_id.values())
    merged.sort(key=lambda m: (parse_email_date(m.get("date")) or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp())
    if len(merged) > MAX_MESSAGES_PER_CLIENT * 3:
        merged = merged[-(MAX_MESSAGES_PER_CLIENT * 3):]
    return merged


async def enrich_message_pdfs(access: str, msg: dict) -> None:
    """Download and parse invoice PDFs onto msg['pdf_text']."""
    parts = [p for p in (msg.get("attachment_parts") or []) if is_pdf_part(p)]
    if not parts:
        msg["pdf_text"] = ""
        return
    texts: list[str] = []
    for part in parts[:2]:
        try:
            raw = await fetch_attachment_bytes(access, msg["id"], part["attachment_id"])
            text = extract_pdf_text(raw)
            if text.strip():
                fn = part.get("filename") or "attachment.pdf"
                texts.append(f"[{fn}]\n{text}")
        except Exception as e:
            logger.warning("seed.pdf FAIL msg=%s file=%s err=%s", msg.get("id"), part.get("filename"), e)
    msg["pdf_text"] = "\n\n".join(texts)[:8000]


def _normalize_enriched_status(raw: str | None) -> str | None:
    if not raw:
        return None
    val = str(raw).strip().lower()
    if val in VALID_ENRICHED_STATUSES:
        return val
    if val == "paid":
        return "paid_unconfirmed"
    return None


async def ai_invoice_gate(msg: dict, my_email: str) -> bool:
    """Single-email LLM check: is this the user billing a client? Fails open."""
    api_key = openai_api_key()
    if not api_key:
        return True
    atts = ", ".join(msg.get("attachment_names") or []) or "(none)"
    body = preprocess_body(msg.get("body") or msg.get("snippet") or "", 1500)
    content = (
        f"FROM: {my_email} (the USER)\n"
        f"TO: {msg.get('to', '')}\n"
        f"SUBJECT: {msg.get('subject', '')}\n"
        f"ATTACHMENTS: {atts}\n"
        f"BODY:\n{body}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(
                OPENAI_URL,
                headers=openai_headers(),
                json={
                    "model": openai_model(),
                    "messages": [
                        {"role": "system", "content": SEED_GATE_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 60,
                },
            )
            if r.status_code != 200:
                return True
            parsed = json.loads(openai_message_content(r.json()))
            is_inv = parsed.get("is_invoice")
            conf = float(parsed.get("confidence") or 0)
            if is_inv is False and conf >= 0.5:
                logger.info("seed.gate DROP msg=%s subj=%r conf=%.2f", msg.get("id"), (msg.get("subject") or "")[:60], conf)
                return False
            return True
    except Exception as e:
        logger.warning("seed.gate ERROR msg=%s err=%s (fail open)", msg.get("id"), e)
        return True


async def extract_client_invoices_with_ai(
    client_email: str,
    messages: list[dict],
    my_email: str,
    *,
    anchor_ids: list[str] | None = None,
    system_prompt: str | None = None,
    context_note: str | None = None,
) -> Optional[dict[str, Any]]:
    api_key = openai_api_key()
    if not api_key:
        logger.warning("seed.ai SKIP client=%s reason=no_openai_key", client_email)
        return None

    blocks = [_format_message_block(m, my_email=my_email) for m in messages]
    anchor_note = ""
    if anchor_ids:
        anchor_note = f"INVOICE_ANCHOR_IDS: {', '.join(a for a in anchor_ids if a)}\n"
    extra_note = f"{context_note}\n" if context_note else ""
    user_content = (
        f"USER_EMAIL: {my_email}\n"
        f"CLIENT_EMAIL: {client_email}\n"
        f"{anchor_note}{extra_note}\n"
        + "\n".join(blocks)
    )[:18000]

    try:
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(
                OPENAI_URL,
                headers=openai_headers(),
                json={
                    "model": openai_model(),
                    "messages": [
                        {"role": "system", "content": system_prompt or SEED_CLIENT_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 3000,
                },
            )
            if r.status_code != 200:
                logger.warning("seed.ai FAIL client=%s status=%s", client_email, r.status_code)
                return None
            parsed = json.loads(openai_message_content(r.json()))
            logger.info(
                "seed.ai OK client=%s invoices=%s discarded=%s",
                client_email,
                len(parsed.get("invoices") or []),
                len(parsed.get("discarded_message_ids") or []),
            )
            return parsed
    except Exception as e:
        logger.warning("seed.ai ERROR client=%s err=%s", client_email, e)
        return None


def _has_earlier_original_send(src: dict, messages_by_id: dict[str, dict], my_email: str) -> bool:
    """True when the same thread holds an earlier user-sent message that is not a chaser.

    A reminder-style subject alone must not drop a candidate — accounting tools
    (FreshBooks etc.) send first invoices with subjects like "Reminder: Invoice #X is due".
    """
    tid = src.get("thread_id")
    if not tid:
        return False
    src_dt = parse_email_date(src.get("date"))
    if not src_dt:
        return False
    my = my_email.lower()
    for m in messages_by_id.values():
        if m.get("id") == src.get("id") or m.get("thread_id") != tid:
            continue
        if _extract_email_addr(m.get("from", "")) != my:
            continue
        if is_invoice_followup(m.get("subject")):
            continue
        m_dt = parse_email_date(m.get("date"))
        if m_dt and m_dt < src_dt:
            return True
    return False


def invoices_to_candidates(
    client_email: str,
    ai_result: dict,
    messages_by_id: dict[str, dict],
    *,
    user_id,
    job_id,
    now_iso: str,
    my_email: str,
    confidence_min: float | None = None,
) -> list[dict]:
    """Map AI invoice rows to seed_candidates documents."""
    from seed_scan import _client_display_name, _parse_msg_date, extract_amount_currency, extract_due_date
    from ledger_reconcile import client_identity_key, normalize_source_date
    from promise_dates import resolve_stated_date

    min_conf = confidence_min if confidence_min is not None else SEED_CONFIDENCE_MIN
    client_name = ai_result.get("client_name")
    out: list[dict] = []
    seen_refs: set[str] = set()

    for inv in ai_result.get("invoices") or []:
        conf = float(inv.get("confidence") or 0)
        if conf < min_conf:
            continue
        amount = inv.get("amount")
        if amount in (None, 0):
            continue

        mid = inv.get("message_id")
        src = messages_by_id.get(mid or "")
        if not src:
            continue
        if is_invoice_followup(src.get("subject")) and _has_earlier_original_send(src, messages_by_id, my_email):
            continue

        amount = resolve_negotiated_amount(
            mid,
            list(messages_by_id.values()),
            my_email,
            float(amount),
        )
        amount_reverted = abs(amount - float(inv.get("amount") or 0)) > 0.01

        inv_num = inv.get("invoice_number")
        norm_ref = normalize_invoice_ref(inv_num, src.get("subject"))
        if not norm_ref:
            norm_ref = normalize_invoice_ref(None, src.get("subject"))
        if norm_ref:
            if norm_ref in seen_refs:
                continue
            seen_refs.add(norm_ref)

        sent_dt = _parse_msg_date(src)
        due_date = resolve_stated_date(
            inv.get("due_date"),
            message_body=src.get("body") or src.get("snippet"),
            message_dt=sent_dt,
            message=src,
        )
        if not due_date:
            due_date = extract_due_date(src, sent_dt)
        if not due_date and src.get("thread_id"):
            for m in messages_by_id.values():
                if m.get("thread_id") == src.get("thread_id") and m.get("id") != mid:
                    due_date = extract_due_date(m, _parse_msg_date(m))
                    if due_date:
                        break

        enriched_status = _normalize_enriched_status(inv.get("enriched_status"))
        promise_date = resolve_stated_date(
            inv.get("promise_date"),
            message_dt=sent_dt,
            message=src,
        )
        claimed_amount = inv.get("disputed_claim_amount")
        try:
            claimed_amount = float(claimed_amount) if claimed_amount is not None else None
        except (TypeError, ValueError):
            claimed_amount = None
        if enriched_status == "disputed":
            # CORE RULE: a client's claimed figure never becomes the tracked
            # amount. An unresolved dispute keeps the USER's invoiced total —
            # if the AI's amount isn't stated anywhere in the user's own words,
            # fall back to the anchor email's own total and keep the claim
            # separately for context.
            stated = _user_stated_amounts(
                list(messages_by_id.values()), my_email, src.get("thread_id"),
            )
            if not any(abs(s - float(amount)) <= 0.01 for s in stated):
                original, _cur = extract_amount_currency(src)
                if original:
                    if claimed_amount is None:
                        claimed_amount = float(amount)
                    logger.info(
                        "seed.dispute GUARD anchor=%s ai_amount=%.2f → user_amount=%.2f",
                        mid, float(amount), float(original),
                    )
                    amount = float(original)

        paid_amount = inv.get("paid_amount")
        balance_remaining = inv.get("balance_remaining")
        if paid_amount is not None:
            paid_amount = float(paid_amount)
        if amount_reverted:
            balance_remaining = max(0.0, amount - paid_amount) if paid_amount is not None else amount
        elif balance_remaining is not None:
            balance_remaining = float(balance_remaining)
        elif paid_amount is not None:
            balance_remaining = max(0.0, float(amount) - paid_amount)

        # Client-claimed partials with a coexisting dispute (multi-signal) go to
        # the claim bucket. Pure user-stated partials (haul-video) stay paid_amount.
        payment_claim_amount = None
        if (
            claimed_amount is not None
            and paid_amount is not None
            and paid_amount > 0.005
            and (balance_remaining is None or float(balance_remaining) > 0.005)
            and enriched_status in ("partially_paid", "disputed", "paid_unconfirmed", None)
        ):
            payment_claim_amount = float(paid_amount)
            paid_amount = 0.0
            balance_remaining = float(amount)
            enriched_status = "disputed"

        age_days = 0
        if sent_dt:
            age_days = (datetime.now(timezone.utc) - sent_dt).days

        cp_name = client_name or _client_display_name(src, client_email)
        src_date = normalize_source_date(src.get("date")) or now_iso

        row: dict[str, Any] = {
            "user_id": user_id,
            "job_id": job_id,
            "message_id": mid,
            "counterparty_email": client_email.lower(),
            "counterparty_name": cp_name,
            "client_identity_key": client_identity_key(client_email),
            "amount": float(amount),
            "currency": (inv.get("currency") or "USD").upper(),
            "invoice_ref": (inv_num if is_plausible_invoice_ref(inv_num) else None) or norm_ref,
            "invoice_ref_normalized": norm_ref,
            "source_subject": normalize_subject(src.get("subject")),
            "source_from": src.get("from"),
            "source_date": src_date,
            "source_thread_id": src.get("thread_id"),
            "due_date": due_date,
            "due_date_assumed": False,
            "age_days": age_days,
            "confidence": conf,
            "ai_extracted": True,
            "conversation_enriched": True,
            "status": "pending",
            "created_at": now_iso,
        }
        if enriched_status:
            row["enriched_status"] = enriched_status
        if promise_date:
            row["promise_date"] = promise_date
        if paid_amount is not None:
            row["paid_amount"] = paid_amount
        if balance_remaining is not None:
            row["balance_remaining"] = balance_remaining
        if payment_claim_amount is not None:
            row["payment_claim_amount"] = payment_claim_amount
            row["payment_claim_pending"] = True
        evidence = (inv.get("status_evidence") or "").strip()
        if evidence:
            row["status_evidence"] = evidence[:500]
        if inv.get("client_approved"):
            row["client_approved"] = True
            quote = (inv.get("approval_quote") or "").strip()
            if quote:
                row["approval_quote"] = quote[:500]
        if inv.get("needs_reply"):
            # Suppress needs_reply when the same assessment already carries a
            # concrete dispute/payment signal (TE-105 residual-phrase trap).
            concrete = (
                enriched_status in (
                    "disputed", "partially_paid", "promised", "paid_unconfirmed",
                )
                or claimed_amount is not None
                or paid_amount is not None
                or payment_claim_amount is not None
            )
            if not concrete:
                row["needs_reply"] = True
                quote = (inv.get("needs_reply_quote") or "").strip()
                if quote:
                    row["needs_reply_quote"] = quote[:500]
        if inv.get("dispute_kind"):
            row["dispute_kind"] = str(inv["dispute_kind"]).strip()[:40]
        # Keep claim amount for multi-signal (dispute + partial) rows too.
        if claimed_amount is not None and (
            enriched_status == "disputed"
            or enriched_status == "partially_paid"
            or enriched_status == "paid_unconfirmed"
            or inv.get("dispute_kind")
            or payment_claim_amount is not None
        ):
            row["disputed_claim_amount"] = claimed_amount
        out.append(row)
    return out


def _anchor_scan_text(msg: dict) -> str:
    """Subject + body + pdf for ref detection — HTML-decoded so &#39; ≠ #39."""
    raw = " ".join([
        msg.get("subject") or "",
        preprocess_body(msg.get("body") or msg.get("snippet") or "", 2000),
        msg.get("pdf_text") or "",
    ])
    text = html.unescape(raw)
    # Drop tags; keep text content for patterns like Invoice #77.
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def _bare_hash_ref_ok(raw: str) -> bool:
    """Bare #N refs: require letters or ≥3 digits so &#39; / short noise never qualify."""
    v = (raw or "").strip().upper().replace(" ", "")
    if not v:
        return False
    if re.search(r"[A-Z]", v):
        return True
    return bool(re.fullmatch(r"\d{3,}", v))


def _anchor_invoice_refs(sent_msgs: list[dict]) -> list[str | None]:
    """Detect distinct invoice refs in anchor sends for one-call-per-invoice.

    Returns [None] when a single undifferentiable invoice is present (no
    anchor_invoice_ref needed). Returns multiple refs when the same send
    clearly lists several invoice numbers.

    Scoped to each call's sent_msgs only — local refs/seen, no shared accumulator.
    """
    # invoice WB-77 / Invoice #77 / INV-77 — word-bounded capture
    # Bare #81 — must NOT match HTML entities (&#39;) or mid-number substrings.
    _REF_RE = re.compile(
        r"(?i)(?:invoice\s*#?\s*|inv[#\-\s]*)([A-Z0-9][A-Z0-9\-]{1,20})\b"
        r"|(?<![&A-Za-z0-9])#([A-Z0-9][A-Z0-9\-]{0,20})\b",
    )
    refs: list[str] = []
    seen: set[str] = set()
    for m in sent_msgs:
        text = _anchor_scan_text(m)
        for m_ref in _REF_RE.finditer(text):
            from_invoice_ctx = m_ref.group(1) is not None
            raw = (m_ref.group(1) or m_ref.group(2) or "").strip()
            if not from_invoice_ctx and not _bare_hash_ref_ok(raw):
                continue
            norm = normalize_invoice_ref(raw)
            if not norm or not is_plausible_invoice_ref(norm):
                continue
            if norm not in seen:
                seen.add(norm)
                refs.append(norm)
    if len(refs) <= 1:
        return [None]
    return refs


async def run_seed_ai_extraction(
    access: str,
    messages: list[dict],
    my_email: str,
    *,
    user_id,
    job_id,
    now_iso: str,
    confidence_min: float | None = None,
    on_unit=None,
    use_seed_rulebook: bool = False,
) -> tuple[list[dict], dict[str, int]]:
    """Per-invoice pipeline: AI gate each sent email, then one focused AI decision
    per invoice conversation (thread + out-of-thread mail), streamed via on_unit.

    When use_seed_rulebook=True (onboarding + incremental new invoices), Extract
    LLM uses rulebook_seed_scan.txt + prepared JSON I/O. Otherwise legacy
    SEED_INVOICE_PROMPT.

    on_unit(rows) is awaited as each conversation finalizes so results can be
    written to the DB (and shown in the UI) without waiting for the whole scan.
    """
    sem = asyncio.Semaphore(SEED_AI_CONCURRENCY)
    stats = {
        "messages_in": len(messages),
        "gate_dropped": 0,
        "clients": 0,
        "ai_ok": 0,
        "ai_fail": 0,
        "threads_fetched": 0,
        "oot_kept": 0,
        "seed_rulebook": bool(use_seed_rulebook),
    }

    if use_seed_rulebook:
        from seed_rulebook import reset_llm_io_log
        reset_llm_io_log()

    # Stage 1 — single-email AI gate: is this actually the user billing a client?
    async def _gate(m: dict) -> bool:
        async with sem:
            return await ai_invoice_gate(m, my_email)

    verdicts = await asyncio.gather(*[_gate(m) for m in messages])
    anchors = [m for m, ok in zip(messages, verdicts) if ok]
    stats["gate_dropped"] = len(messages) - len(anchors)

    # Stage 2 — unit = the invoice email's thread (same-thread sends share one conversation)
    units: dict[str, list[dict]] = {}
    for m in anchors:
        units.setdefault(m.get("thread_id") or f"_solo_{m['id']}", []).append(m)

    from client_sweep import anchor_recipients
    stats["clients"] = len({
        (anchor_recipients(m, my_email) or [""])[0].lower() for m in anchors
    } - {""})

    all_candidates: list[dict] = []

    async def _one_unit(tid: str, sent_msgs: list[dict]):
        async with sem:
            recipients = anchor_recipients(sent_msgs[0], my_email)
            if not recipients:
                return
            client = recipients[0].lower()

            for m in sent_msgs:
                await enrich_message_pdfs(access, m)

            thread_msgs = await _fetch_client_threads(access, sent_msgs)
            stats["threads_fetched"] += 1 if thread_msgs else 0

            # Out-of-thread client mail from the invoice date forward
            draft_invoices = _draft_invoices_from_sent(sent_msgs)
            oot_msgs = await _fetch_out_of_thread_client_mail(
                access, client, draft_invoices, {tid}, my_email,
            )
            stats["oot_kept"] += len(oot_msgs)

            # Chronological (oldest → newest) user↔client conversation
            combined = _merge_client_messages(sent_msgs, thread_msgs, oot_msgs)
            messages_by_id = {m["id"]: m for m in combined}
            anchor_ids = [m["id"] for m in sent_msgs if m.get("id")]

            if use_seed_rulebook:
                from seed_rulebook import (
                    build_seed_scan_input,
                    extract_seed_scan_with_rulebook,
                    rulebook_result_to_candidate,
                )
                # One LLM call per invoice (rulebook rule 2)
                refs = _anchor_invoice_refs(sent_msgs)
                unit_rows: list[dict] = []
                any_ok = False
                for ref in refs:
                    prepared = build_seed_scan_input(
                        my_email=my_email,
                        client_email=client,
                        messages=combined,
                        anchor_ids=anchor_ids,
                        anchor_invoice_ref=ref,
                    )
                    result = await extract_seed_scan_with_rulebook(client, prepared)
                    if not result:
                        continue
                    any_ok = True
                    row = rulebook_result_to_candidate(
                        client, result, messages_by_id,
                        user_id=user_id, job_id=job_id, now_iso=now_iso,
                        my_email=my_email, anchor_ids=anchor_ids,
                        confidence_min=confidence_min,
                    )
                    if row:
                        unit_rows.append(row)
                if not any_ok:
                    stats["ai_fail"] += 1
                    return
                stats["ai_ok"] += 1
                if not unit_rows:
                    return
                all_candidates.extend(unit_rows)
                if on_unit:
                    await on_unit(unit_rows)
                return

            # Legacy extract (incremental new-invoice path)
            result = await extract_client_invoices_with_ai(
                client, combined, my_email,
                anchor_ids=anchor_ids,
                system_prompt=SEED_INVOICE_PROMPT,
            )
            if not result:
                stats["ai_fail"] += 1
                return
            stats["ai_ok"] += 1
            rows = invoices_to_candidates(
                client, result, messages_by_id,
                user_id=user_id, job_id=job_id, now_iso=now_iso,
                my_email=my_email,
                confidence_min=confidence_min,
            )
            if not rows:
                return
            all_candidates.extend(rows)
            if on_unit:
                await on_unit(rows)

    await asyncio.gather(*[_one_unit(t, ms) for t, ms in units.items()])
    return all_candidates, stats
