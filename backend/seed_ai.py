"""AI extraction for onboarding seed scan — clients + invoices from sent mail."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

import httpx

from client_sweep import preprocess_body
from gmail_client import fetch_attachment_bytes
from ledger_reconcile import is_invoice_followup, is_plausible_invoice_ref, normalize_invoice_ref, normalize_subject
from pdf_extract import extract_pdf_text, is_pdf_part

logger = logging.getLogger("scotive.seed_ai")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("SEED_AI_MODEL", "openai/gpt-4o-mini")
SEED_AI_CONCURRENCY = int(os.environ.get("SEED_AI_CONCURRENCY", "4"))
SEED_CONFIDENCE_MIN = float(os.environ.get("SEED_CONFIDENCE_MIN", "0.65"))
MAX_MESSAGES_PER_CLIENT = 25

SEED_CLIENT_PROMPT = """You analyse SENT emails from a small business owner (USER) to ONE client.
Each message includes subject, body, attachment names, and extracted PDF text when available.

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
    "confidence": number
  }],
  "discarded_message_ids": [string]
}

Rules:
- ONLY money the USER is owed by this CLIENT (accounts receivable). Ignore vendor bills the user pays.
- Informal payment requests ARE invoices: e.g. "work done, please transfer 200 USD", "as discussed, send payment", completed project + amount with no PDF. Treat as invoice_sent with the stated amount.
- Use PDF text as the primary source for amount, invoice number, and due date when present.
- due_date: only when explicitly stated in the email, PDF, or net terms (e.g. "due March 15", "payment due by…", "due is 5 jul 2026", "net 30"). Resolve relative phrases from the MESSAGE DATE ("tomorrow", "this Friday", "end of this week", "next week", etc.). null if not stated — never guess from send date or defaults.
- Reminders, payment chasers, Re:/Fwd: follow-ups, and "payment reminder" emails are NOT separate invoices.
  For those, either omit from invoices[] or point message_id at the ORIGINAL invoice send only once.
- One row per distinct invoice_number per client. Same invoice_number = same invoice. Use null invoice_number when none is stated.
- discarded_message_ids: promos, proposals without a payment amount, general chatter, unrelated forwards, duplicate reminders.
- Do not invent amounts or dates. Omit uncertain rows instead of guessing.
- confidence 0.0-1.0 for each invoice row.
"""


def _format_message_block(msg: dict) -> str:
    pdf_text = (msg.get("pdf_text") or "").strip()
    body = preprocess_body(msg.get("body") or msg.get("snippet") or "", 2800)
    atts = ", ".join(msg.get("attachment_names") or []) or "(none)"
    return (
        f"=== MESSAGE id={msg['id']} ===\n"
        f"DATE: {msg.get('date', '')}\n"
        f"SUBJECT: {msg.get('subject', '')}\n"
        f"ATTACHMENTS: {atts}\n"
        f"BODY:\n{body}\n"
        f"PDF_TEXT:\n{pdf_text or '(none)'}\n"
    )


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


async def extract_client_invoices_with_ai(
    client_email: str,
    messages: list[dict],
    my_email: str,
) -> Optional[dict[str, Any]]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("seed.ai SKIP client=%s reason=no_openrouter_key", client_email)
        return None

    blocks = [_format_message_block(m) for m in messages]
    user_content = (
        f"USER_EMAIL: {my_email}\n"
        f"CLIENT_EMAIL: {client_email}\n\n"
        + "\n".join(blocks)
    )[:14000]

    try:
        async with httpx.AsyncClient(timeout=90.0) as c:
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
                    "max_tokens": 1200,
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
    confidence_min: float | None = None,
) -> list[dict]:
    """Map AI invoice rows to seed_candidates documents."""
    from seed_scan import _client_display_name, _parse_msg_date, extract_due_date
    from ledger_reconcile import client_identity_key, normalize_source_date

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

        inv_num = inv.get("invoice_number")
        norm_ref = normalize_invoice_ref(inv_num, src.get("subject"))
        if not norm_ref:
            norm_ref = normalize_invoice_ref(None, src.get("subject"))
        if norm_ref:
            if norm_ref in seen_refs:
                continue
            seen_refs.add(norm_ref)

        sent_dt = _parse_msg_date(src)
        from promise_dates import resolve_stated_date
        due_date = resolve_stated_date(
            inv.get("due_date"),
            message_body=src.get("body") or src.get("snippet"),
            message_dt=sent_dt,
            message=src,
        )
        if not due_date:
            due_date = extract_due_date(src, sent_dt)
        age_days = 0
        if sent_dt:
            from datetime import datetime, timezone
            age_days = (datetime.now(timezone.utc) - sent_dt).days

        cp_name = client_name or _client_display_name(src, client_email)
        src_date = normalize_source_date(src.get("date")) or now_iso

        out.append({
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
            "status": "pending",
            "created_at": now_iso,
        })
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
    """Enrich PDFs, group by client, AI extract, return seed candidate rows."""
    await enrich_messages_pdfs(access, messages)
    by_client = group_messages_by_client(messages, my_email)
    messages_by_id = {m["id"]: m for m in messages}

    sem = asyncio.Semaphore(SEED_AI_CONCURRENCY)
    all_candidates: list[dict] = []
    stats = {"clients": len(by_client), "ai_ok": 0, "ai_fail": 0, "messages_in": len(messages)}

    async def _one(client: str, msgs: list[dict]):
        async with sem:
            result = await extract_client_invoices_with_ai(client, msgs, my_email)
        if not result:
            stats["ai_fail"] += 1
            return
        stats["ai_ok"] += 1
        rows = invoices_to_candidates(
            client, result, messages_by_id,
            user_id=user_id, job_id=job_id, now_iso=now_iso,
            confidence_min=confidence_min,
        )
        all_candidates.extend(rows)

    await asyncio.gather(*[_one(c, m) for c, m in by_client.items()])
    return all_candidates, stats
