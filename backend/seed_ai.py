"""AI extraction for onboarding seed scan — clients + invoices from sent mail."""
from __future__ import annotations

import asyncio
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

logger = logging.getLogger("scotive.seed_ai")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("SEED_AI_MODEL", "openai/gpt-4o-mini")
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

SEED_CLIENT_PROMPT = """You analyse invoice-related email between a small business owner (USER) and ONE client.
Context includes:
- USER sent invoice anchors (with PDF text when available)
- FULL threads for those invoices (every reply in-thread)
- OUT-OF-THREAD client mail (separate threads mentioning the same invoices)

Return STRICT JSON only:
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
    "status_evidence": string|null
  }],
  "discarded_message_ids": [string]
}

Rules:
- ONLY money the USER is owed by this CLIENT (accounts receivable). Ignore vendor bills the user pays.
- Informal payment requests ARE invoices when the USER sent them with a clear amount.
- Use PDF text as the primary source for amount, invoice number, and due date on the original send when present.
- Read ALL provided messages chronologically — in-thread AND out-of-thread — before deciding each invoice row.
- amount = final AGREED total after the full thread negotiation:
  - Start from the original USER invoice send (anchor message_id).
  - A later USER revision (re-sent invoice with a new total) updates amount ONLY if the client accepts it.
  - If the USER reduces the amount and the CLIENT rejects that reduction (e.g. "retain the bill as is", "don't reduce any efforts", "keep the original amount"), revert to the pre-reduction total — NOT the lowered figure.
  - Client explicit approval of a specific revised total → use that revised amount.
- balance_remaining / paid_amount: set when client partial payment or remaining balance is clear; else null.
- enriched_status (only when clearly supported by CLIENT messages, never from USER reminders alone):
  - promised: client committed to pay by a date → set promise_date
  - partially_paid: client paid part, balance remains
  - disputed: client disputes amount/terms
  - paid_unconfirmed: client says they paid / processed payment (no bank receipt)
  - overdue: only when due_date is in the past relative to today AND no stronger status applies
  - null / invoiced: open invoice with no client status signal yet
- SENDER DIRECTION: lines labelled "YOU →" are user-sent; "{client} → YOU" are client-sent.
  Status signals (promise, dispute, paid_unconfirmed, partial) MUST come from client-sent lines only.
- due_date: when explicitly stated in the invoice (e.g. "due is 3 jul 2026", "due July 3", "due 07/03/2026"). Return ISO YYYY-MM-DD. Resolve relative phrases from the MESSAGE DATE. null only if truly not stated.
- Reminders and payment chasers are NOT separate invoices — one row per distinct invoice per client.
- discarded_message_ids: promos, unrelated chatter, duplicate reminders.
- Do not invent amounts or dates. Omit uncertain rows instead of guessing.
- confidence 0.0-1.0 for each invoice row.
"""


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


async def enrich_messages_pdfs(access: str, messages: list[dict]) -> None:
    for msg in messages:
        await enrich_message_pdfs(access, msg)


def group_messages_by_client(messages: list[dict], my_email: str) -> dict[str, list[dict]]:
    from client_sweep import anchor_recipients

    groups: dict[str, list[dict]] = {}
    for msg in messages:
        recipients = anchor_recipients(msg, my_email)
        if not recipients:
            continue
        client = recipients[0].lower()
        groups.setdefault(client, []).append(msg)
    for client in groups:
        groups[client].sort(key=lambda m: m.get("date") or "")
        if len(groups[client]) > MAX_MESSAGES_PER_CLIENT:
            groups[client] = groups[client][-MAX_MESSAGES_PER_CLIENT:]
    return groups


def _normalize_enriched_status(raw: str | None) -> str | None:
    if not raw:
        return None
    val = str(raw).strip().lower()
    if val in VALID_ENRICHED_STATUSES:
        return val
    if val == "paid":
        return "paid_unconfirmed"
    return None


async def extract_client_invoices_with_ai(
    client_email: str,
    messages: list[dict],
    my_email: str,
    *,
    anchor_ids: list[str] | None = None,
) -> Optional[dict[str, Any]]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("seed.ai SKIP client=%s reason=no_openrouter_key", client_email)
        return None

    blocks = [_format_message_block(m, my_email=my_email) for m in messages]
    anchor_note = ""
    if anchor_ids:
        anchor_note = f"INVOICE_ANCHOR_IDS: {', '.join(anchor_ids)}\n"
    user_content = (
        f"USER_EMAIL: {my_email}\n"
        f"CLIENT_EMAIL: {client_email}\n"
        f"{anchor_note}\n"
        + "\n".join(blocks)
    )[:18000]

    try:
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": os.environ.get("FRONTEND_URL", "https://scotive.app"),
                    "X-Title": "Scotive",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": [
                        {"role": "system", "content": SEED_CLIENT_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 2000,
                },
            )
            if r.status_code != 200:
                logger.warning("seed.ai FAIL client=%s status=%s", client_email, r.status_code)
                return None
            parsed = json.loads(r.json()["choices"][0]["message"]["content"])
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
    from seed_scan import _client_display_name, _parse_msg_date, extract_due_date
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
        if is_invoice_followup(src.get("subject")):
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
        evidence = (inv.get("status_evidence") or "").strip()
        if evidence:
            row["status_evidence"] = evidence[:500]
        out.append(row)
    return out


async def run_seed_ai_extraction(
    access: str,
    messages: list[dict],
    my_email: str,
    *,
    user_id,
    job_id,
    now_iso: str,
    confidence_min: float | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Enrich PDFs, expand threads + out-of-thread per client, AI extract, return candidates."""
    await enrich_messages_pdfs(access, messages)
    by_client = group_messages_by_client(messages, my_email)

    sem = asyncio.Semaphore(SEED_AI_CONCURRENCY)
    all_candidates: list[dict] = []
    stats = {
        "clients": len(by_client),
        "ai_ok": 0,
        "ai_fail": 0,
        "messages_in": len(messages),
        "threads_fetched": 0,
        "oot_kept": 0,
    }

    async def _one(client: str, sent_msgs: list[dict]):
        thread_msgs = await _fetch_client_threads(access, sent_msgs)
        stats["threads_fetched"] += len({m.get("thread_id") for m in thread_msgs if m.get("thread_id")})

        draft_invoices = _draft_invoices_from_sent(sent_msgs)
        excluded = {m.get("thread_id") for m in sent_msgs if m.get("thread_id")}
        oot_msgs = await _fetch_out_of_thread_client_mail(
            access, client, draft_invoices, excluded, my_email,
        )
        stats["oot_kept"] += len(oot_msgs)

        combined = _merge_client_messages(sent_msgs, thread_msgs, oot_msgs)
        messages_by_id = {m["id"]: m for m in combined}
        anchor_ids = [m["id"] for m in sent_msgs if m.get("id")]

        async with sem:
            result = await extract_client_invoices_with_ai(
                client, combined, my_email, anchor_ids=anchor_ids,
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
        all_candidates.extend(rows)

    await asyncio.gather(*[_one(c, m) for c, m in by_client.items()])
    return all_candidates, stats
