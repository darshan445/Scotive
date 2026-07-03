"""Historical scan pipeline.

Phases: queued -> fetching -> filtering -> extracting -> building -> complete | error
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from gmail_client import GmailAuthError, get_access_token, get_message, list_message_ids

logger = logging.getLogger("scotive.scan")

# Hard safety caps to keep AI cost predictable
MAX_MESSAGES_TO_FETCH = 3000  # id-only listing, cheap
MAX_MESSAGES_FOR_AI = 150  # actual bodies + AI calls
AI_CONCURRENCY = 4

# Sender patterns that are noise regardless of what they say
NOISE_SENDER_PATTERNS = [
    r"no[-_.]?reply",
    r"do[-_.]?not[-_.]?reply",
    r"newsletter",
    r"notifications?@",
    r"marketing@",
    r"@mailchimp",
    r"@substack",
    r"@sendgrid\.net",
    r"@mail\.linkedin",
    r"@github\.com",
    r"@medium\.com",
]
NOISE_RE = re.compile("|".join(NOISE_SENDER_PATTERNS), re.I)

# Known money/processor senders — ALWAYS keep, even if user never replied
PAYMENT_SENDER_DOMAINS = {
    "stripe.com", "paypal.com", "quickbooks.com", "intuit.com",
    "freshbooks.com", "waveapps.com", "zoho.com", "square.com",
    "chase.com", "bankofamerica.com", "wellsfargo.com", "wise.com",
    "gocardless.com", "xero.com",
}

# Money-signal keywords in subject or body
MONEY_KEYWORDS = [
    "invoice", "payment", "paid", "receipt", "balance", "amount due",
    "past due", "overdue", "outstanding", "remit", "wire transfer",
    "ach", "net 30", "net 15", "net 60", "due date", "please pay",
    "$", "usd",
]
MONEY_RE = re.compile("|".join(re.escape(k) for k in MONEY_KEYWORDS), re.I)

# Regex for a dollar amount like $1,234.56 or $500
AMOUNT_RE = re.compile(r"\$\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)")


def _extract_email_addr(from_header: str) -> str:
    m = re.search(r"<([^>]+)>", from_header)
    return (m.group(1) if m else from_header).strip().lower()


def _sender_domain(email: str) -> str:
    return email.split("@")[-1].lower() if "@" in email else ""


def cheap_filter(msg: dict) -> bool:
    """Return True if the message survives cheap noise filters."""
    sender = _extract_email_addr(msg.get("from", ""))
    domain = _sender_domain(sender)
    haystack = " ".join([msg.get("subject", ""), msg.get("snippet", ""), sender])

    # Always keep known payment processors
    if domain in PAYMENT_SENDER_DOMAINS:
        return True
    # Always keep PDFs (likely invoices)
    if msg.get("has_attachment"):
        return True
    # Kill obvious noise senders unless money-signal in subject
    if NOISE_RE.search(sender):
        # Only keep if subject SCREAMS invoice/receipt (rare exception)
        subj = msg.get("subject", "").lower()
        if not any(k in subj for k in ("invoice", "receipt", "payment", "past due")):
            return False
    # Keep if there's a money signal anywhere obvious
    if MONEY_RE.search(haystack) or AMOUNT_RE.search(haystack):
        return True
    return False


# ---------------------------------------------------------------------------
# AI extraction via OpenRouter (gpt-4o-mini)
# ---------------------------------------------------------------------------
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "openai/gpt-4o-mini"

EXTRACTION_PROMPT = """You are analysing ONE email from a small business owner's inbox to determine whether it relates to money they are owed by a client (accounts receivable).

Return STRICT JSON only, no prose. Schema:
{
  "is_money_related": bool,
  "kind": "invoice_sent" | "payment_promise" | "partial_payment" | "dispute" | "receipt" | "payment_claim" | "none",
  "counterparty_name": string | null,      // client / vendor name (not the user)
  "counterparty_email": string | null,
  "amount": number | null,                  // dollar amount if any
  "currency": "USD" | null,
  "invoice_ref": string | null,
  "due_date": string | null,                // ISO YYYY-MM-DD if a due date appears
  "promise_date": string | null,            // ISO date if the counterparty committed to a payment date
  "evidence_sentence": string | null,       // the single sentence in the email that justifies your classification
  "confidence": number                      // 0.0-1.0
}

Rules:
- "invoice_sent" = the USER sent an invoice to a client.
- "payment_promise" = client said they will pay by a date.
- "receipt" = a processor (Stripe/PayPal/bank) confirming a payment came in.
- Set is_money_related=false and kind="none" for project chatter, newsletters, meeting requests, general work talk.
- Do not invent amounts, dates, or names. Return null when unsure.
"""


async def extract_with_ai(msg: dict) -> Optional[dict]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    user_content = (
        f"FROM: {msg.get('from','')}\n"
        f"TO: {msg.get('to','')}\n"
        f"SUBJECT: {msg.get('subject','')}\n"
        f"DATE: {msg.get('date','')}\n"
        f"HAS_PDF: {msg.get('has_attachment', False)}\n"
        f"BODY:\n{msg.get('body','')[:3500]}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
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
                        {"role": "system", "content": EXTRACTION_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 400,
                },
            )
            if r.status_code != 200:
                logger.warning("AI call failed: %s %s", r.status_code, r.text[:200])
                return None
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        logger.warning("AI extract error: %s", e)
        return None


# ---------------------------------------------------------------------------
# Scan runner
# ---------------------------------------------------------------------------
async def _update_job(db, job_id, patch: dict):
    patch = {**patch, "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.scan_jobs.update_one({"_id": job_id}, {"$set": patch})


async def _counts_dict(fetched=0, filtered_in=0, ai_extracted=0, invoices_created=0):
    return {
        "fetched": fetched,
        "filtered_in": filtered_in,
        "ai_extracted": ai_extracted,
        "invoices_created": invoices_created,
    }


async def run_historical_scan(db, user_id, job_id, months: int = 12):
    """Long-running task. Updates scan_jobs doc as it progresses."""
    try:
        access = await get_access_token(db, user_id)
    except GmailAuthError:
        await _update_job(db, job_id, {"status": "error", "phase": "auth", "error": "Gmail auth failed. Please reconnect."})
        return

    counts = await _counts_dict()

    # PHASE 1: fetching IDs
    await _update_job(db, job_id, {"status": "running", "phase": "fetching", "counts": counts})
    after_ts = int((datetime.now(timezone.utc) - timedelta(days=months * 30)).timestamp())
    query = f"after:{after_ts} -category:promotions -category:social -category:forums"
    try:
        ids = await list_message_ids(access, query, max_pages=int(MAX_MESSAGES_TO_FETCH / 500) + 1)
    except Exception as e:
        await _update_job(db, job_id, {"status": "error", "phase": "fetching", "error": str(e)})
        return
    ids = ids[:MAX_MESSAGES_TO_FETCH]
    counts["fetched"] = len(ids)
    await _update_job(db, job_id, {"phase": "filtering", "counts": counts})

    # PHASE 2 & 3: fetch each message, apply cheap filter, batch to AI (with cap)
    survivors: list[dict] = []
    fetched_bodies = 0
    for mid in ids:
        # We only need headers/snippet first — but Gmail API single-call gives us both cheaply
        msg = await get_message(access, mid)
        fetched_bodies += 1
        if not msg:
            continue
        if cheap_filter(msg):
            survivors.append(msg)
        # Occasional progress updates every 25 messages
        if fetched_bodies % 25 == 0:
            counts["filtered_in"] = len(survivors)
            await _update_job(db, job_id, {"counts": counts})
        if len(survivors) >= MAX_MESSAGES_FOR_AI:
            break

    counts["filtered_in"] = len(survivors)
    await _update_job(db, job_id, {"phase": "extracting", "counts": counts})

    # PHASE 4: AI extraction (bounded concurrency)
    sem = asyncio.Semaphore(AI_CONCURRENCY)
    results: list[tuple[dict, dict]] = []

    async def _one(m):
        async with sem:
            ext = await extract_with_ai(m)
            if ext:
                results.append((m, ext))
                nonlocal_counts["ai_extracted"] += 1
                if nonlocal_counts["ai_extracted"] % 5 == 0:
                    await _update_job(db, job_id, {"counts": {**counts, "ai_extracted": nonlocal_counts["ai_extracted"]}})

    nonlocal_counts = {"ai_extracted": 0}
    await asyncio.gather(*[_one(m) for m in survivors])
    counts["ai_extracted"] = nonlocal_counts["ai_extracted"]
    await _update_job(db, job_id, {"phase": "building", "counts": counts})

    # PHASE 5: build invoices from money-related results
    now_iso = datetime.now(timezone.utc).isoformat()
    invoices_created = 0
    for msg, ext in results:
        if not ext.get("is_money_related"):
            continue
        kind = ext.get("kind") or "none"
        # Consider invoice_sent + payment_promise as ledger-worthy open items.
        # receipts/partial_payments are informational for now (Feature 6 hooks them).
        if kind not in ("invoice_sent", "payment_promise", "partial_payment"):
            continue
        amount = ext.get("amount")
        if amount in (None, 0):
            continue
        counterparty_email = (ext.get("counterparty_email") or _extract_email_addr(msg.get("from", ""))).lower()
        # Skip if the "counterparty" is actually the user themselves
        conn = await db.gmail_connections.find_one({"user_id": user_id})
        my_email = (conn or {}).get("email", "").lower()
        if counterparty_email == my_email:
            # invoice_sent: the counterparty is in the To: header
            to_addr = _extract_email_addr(msg.get("to", ""))
            counterparty_email = to_addr.lower()

        status = "invoiced"
        if kind == "payment_promise":
            status = "promised"
        elif kind == "partial_payment":
            status = "partially_paid"

        invoice_doc = {
            "user_id": user_id,
            "counterparty_email": counterparty_email,
            "counterparty_name": ext.get("counterparty_name"),
            "amount": float(amount),
            "currency": ext.get("currency") or "USD",
            "invoice_ref": ext.get("invoice_ref"),
            "due_date": ext.get("due_date"),
            "promise_date": ext.get("promise_date"),
            "status": status,
            "kind": kind,
            "source_message_id": msg["id"],
            "source_thread_id": msg.get("thread_id"),
            "source_subject": msg.get("subject"),
            "evidence_sentence": ext.get("evidence_sentence"),
            "confidence": ext.get("confidence"),
            "created_at": now_iso,
        }
        # De-dupe by source_message_id
        existing = await db.invoices.find_one({"user_id": user_id, "source_message_id": msg["id"]})
        if not existing:
            await db.invoices.insert_one(invoice_doc)
            invoices_created += 1

    counts["invoices_created"] = invoices_created
    await _update_job(db, job_id, {
        "status": "complete",
        "phase": "complete",
        "counts": counts,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })
