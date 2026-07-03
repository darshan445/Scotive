"""Historical scan pipeline.

Phases: queued -> fetching -> filtering -> extracting -> building -> complete | error
"""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

# Open-invoice statuses used by receipt reconciliation
_OPEN_STATUSES = ("invoiced", "overdue", "promised", "partially_paid", "promise_broken")

# Receipt reconciliation thresholds
AMOUNT_TOLERANCE_PCT = 0.02  # ±2%
AMOUNT_TOLERANCE_ABS = 1.00  # $1 absolute floor for small amounts
NAME_SIMILARITY_MIN = 0.6
PARTIAL_MIN_PCT = 0.10       # receipt must be ≥10% of invoice to count as partial (avoids noise)

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
- "partial_payment" = client sent part of an invoice; extract that partial amount, not the full invoice.
- "receipt" = a processor (Stripe/PayPal/bank) OR the client confirming a payment came in. Set counterparty_name to the PAYER name (the client that paid), not the processor. amount = payment amount received.
- "payment_claim" = client says they paid but no processor confirmation.
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
    CONFIDENCE_THRESHOLD = 0.75
    now_iso = datetime.now(timezone.utc).isoformat()
    invoices_created = 0
    review_created = 0
    receipts_created = 0
    for msg, ext in results:
        if not ext.get("is_money_related"):
            continue
        kind = ext.get("kind") or "none"

        # --- Receipt branch: goes into db.receipts, not db.invoices --------
        if kind == "receipt":
            amount = ext.get("amount")
            if amount in (None, 0):
                continue
            existing_r = await db.receipts.find_one({"user_id": user_id, "source_message_id": msg["id"]})
            if existing_r:
                continue
            await db.receipts.insert_one({
                "user_id": user_id,
                "amount": float(amount),
                "currency": ext.get("currency") or "USD",
                "payer_name": ext.get("counterparty_name"),
                "processor_from": msg.get("from"),
                "source_message_id": msg["id"],
                "source_thread_id": msg.get("thread_id"),
                "source_subject": msg.get("subject"),
                "source_date": msg.get("date"),
                "evidence_sentence": ext.get("evidence_sentence"),
                "confidence": float(ext.get("confidence") or 0),
                "match_status": "unmatched",  # unmatched | matched | ambiguous | user_confirmed | rejected
                "matched_invoice_id": None,
                "candidate_invoice_ids": [],
                "created_at": now_iso,
            })
            receipts_created += 1
            continue

        if kind not in ("invoice_sent", "payment_promise", "partial_payment"):
            continue
        amount = ext.get("amount")
        if amount in (None, 0):
            continue
        counterparty_email = (ext.get("counterparty_email") or _extract_email_addr(msg.get("from", ""))).lower()
        conn = await db.gmail_connections.find_one({"user_id": user_id})
        my_email = (conn or {}).get("email", "").lower()
        if counterparty_email == my_email:
            to_addr = _extract_email_addr(msg.get("to", ""))
            counterparty_email = to_addr.lower()

        status = "invoiced"
        if kind == "payment_promise":
            status = "promised"
        elif kind == "partial_payment":
            status = "partially_paid"

        confidence = float(ext.get("confidence") or 0)
        base_doc = {
            "user_id": user_id,
            "counterparty_email": counterparty_email,
            "counterparty_name": ext.get("counterparty_name"),
            "amount": float(amount),
            "balance_remaining": float(amount),
            "paid_amount": 0.0,
            "currency": ext.get("currency") or "USD",
            "invoice_ref": ext.get("invoice_ref"),
            "due_date": ext.get("due_date"),
            "promise_date": ext.get("promise_date"),
            "status": status,
            "kind": kind,
            "source_message_id": msg["id"],
            "source_thread_id": msg.get("thread_id"),
            "source_subject": msg.get("subject"),
            "source_from": msg.get("from"),
            "source_date": msg.get("date"),
            "evidence_sentence": ext.get("evidence_sentence"),
            "confidence": confidence,
            "created_at": now_iso,
        }

        if confidence < CONFIDENCE_THRESHOLD:
            existing_r = await db.review_items.find_one({"user_id": user_id, "source_message_id": msg["id"]})
            if not existing_r:
                await db.review_items.insert_one({**base_doc, "review_status": "pending"})
                review_created += 1
            continue

        existing = await db.invoices.find_one({"user_id": user_id, "source_message_id": msg["id"]})
        if not existing:
            await db.invoices.insert_one(base_doc)
            invoices_created += 1

    counts["invoices_created"] = invoices_created
    counts["review_items"] = review_created
    counts["receipts_created"] = receipts_created

    # PHASE 6: reconcile unmatched receipts against open invoices
    try:
        recon = await reconcile_receipts(db, user_id)
        counts["receipts_matched"] = recon.get("matched", 0)
        counts["receipts_ambiguous"] = recon.get("ambiguous", 0)
    except Exception as e:  # pragma: no cover
        logger.warning("Receipt reconcile failed: %s", e)

    await _update_job(db, job_id, {
        "status": "complete",
        "phase": "complete",
        "counts": counts,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Continuous incremental sync (F9a)
# ---------------------------------------------------------------------------
INCREMENTAL_LOOKBACK_DAYS = 3   # first-run cushion
INCREMENTAL_OVERLAP_HOURS = 24  # re-check the last day on every sync
INCREMENTAL_MAX_MESSAGES = 40   # per-tick cap so a single user can't hog the loop


async def _extract_and_write(db, user_id, msg, ext, my_email, now_iso, CONFIDENCE_THRESHOLD=0.75):
    """Persist a single AI extraction outcome. Returns (invoice_created, receipt_created, review_created)."""
    if not ext.get("is_money_related"):
        return (0, 0, 0)
    kind = ext.get("kind") or "none"

    if kind == "receipt":
        amount = ext.get("amount")
        if amount in (None, 0):
            return (0, 0, 0)
        existing = await db.receipts.find_one({"user_id": user_id, "source_message_id": msg["id"]})
        if existing:
            return (0, 0, 0)
        await db.receipts.insert_one({
            "user_id": user_id,
            "amount": float(amount),
            "currency": ext.get("currency") or "USD",
            "payer_name": ext.get("counterparty_name"),
            "processor_from": msg.get("from"),
            "source_message_id": msg["id"],
            "source_thread_id": msg.get("thread_id"),
            "source_subject": msg.get("subject"),
            "source_date": msg.get("date"),
            "evidence_sentence": ext.get("evidence_sentence"),
            "confidence": float(ext.get("confidence") or 0),
            "match_status": "unmatched",
            "matched_invoice_id": None,
            "candidate_invoice_ids": [],
            "created_at": now_iso,
        })
        return (0, 1, 0)

    if kind not in ("invoice_sent", "payment_promise", "partial_payment"):
        return (0, 0, 0)
    amount = ext.get("amount")
    if amount in (None, 0):
        return (0, 0, 0)

    counterparty_email = (ext.get("counterparty_email") or _extract_email_addr(msg.get("from", ""))).lower()
    if counterparty_email == (my_email or "").lower():
        counterparty_email = _extract_email_addr(msg.get("to", "")).lower()

    status = "invoiced"
    if kind == "payment_promise":
        status = "promised"
    elif kind == "partial_payment":
        status = "partially_paid"

    confidence = float(ext.get("confidence") or 0)
    base_doc = {
        "user_id": user_id,
        "counterparty_email": counterparty_email,
        "counterparty_name": ext.get("counterparty_name"),
        "amount": float(amount),
        "balance_remaining": float(amount),
        "paid_amount": 0.0,
        "currency": ext.get("currency") or "USD",
        "invoice_ref": ext.get("invoice_ref"),
        "due_date": ext.get("due_date"),
        "promise_date": ext.get("promise_date"),
        "status": status,
        "kind": kind,
        "source_message_id": msg["id"],
        "source_thread_id": msg.get("thread_id"),
        "source_subject": msg.get("subject"),
        "source_from": msg.get("from"),
        "source_date": msg.get("date"),
        "evidence_sentence": ext.get("evidence_sentence"),
        "confidence": confidence,
        "created_at": now_iso,
    }

    if confidence < CONFIDENCE_THRESHOLD:
        existing_r = await db.review_items.find_one({"user_id": user_id, "source_message_id": msg["id"]})
        if existing_r:
            return (0, 0, 0)
        await db.review_items.insert_one({**base_doc, "review_status": "pending"})
        return (0, 0, 1)

    existing = await db.invoices.find_one({"user_id": user_id, "source_message_id": msg["id"]})
    if existing:
        return (0, 0, 0)
    await db.invoices.insert_one(base_doc)
    return (1, 0, 0)


async def _already_processed(db, user_id, message_id: str) -> bool:
    """True if we've already stored this message in any bucket."""
    for coll in ("invoices", "receipts", "review_items"):
        if await db[coll].find_one({"user_id": user_id, "source_message_id": message_id}, {"_id": 1}):
            return True
    return False


async def run_incremental_sync(db, user_id) -> dict:
    """One tick of continuous sync. Idempotent, safe to call on a timer."""
    counts = {"fetched": 0, "filtered_in": 0, "ai_extracted": 0,
              "invoices_created": 0, "receipts_created": 0, "review_items": 0,
              "receipts_matched": 0, "receipts_ambiguous": 0}
    state = await db.gmail_sync_state.find_one({"user_id": user_id})
    conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        return {**counts, "skipped": "no_connection"}

    my_email = conn.get("email") or ""

    try:
        access = await get_access_token(db, user_id)
    except GmailAuthError:
        await db.gmail_sync_state.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "last_sync_status": "auth_error",
                      "last_synced_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        return {**counts, "skipped": "auth_error"}

    # Determine window: last_message_epoch - overlap, or lookback default on first run
    now = datetime.now(timezone.utc)
    last_epoch = (state or {}).get("last_message_epoch")
    if last_epoch:
        since_ts = int(last_epoch) - INCREMENTAL_OVERLAP_HOURS * 3600
    else:
        since_ts = int((now - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)).timestamp())
    query = f"after:{since_ts} -category:promotions -category:social -category:forums"

    # Fetch IDs (only need one page, cap tightly)
    try:
        ids = await list_message_ids(access, query, max_pages=1)
    except Exception as e:
        logger.warning("Sync list failed: %s", e)
        return {**counts, "error": "list_failed"}
    counts["fetched"] = len(ids)

    # Filter out ones we already processed
    fresh_ids = []
    for mid in ids:
        if not await _already_processed(db, user_id, mid):
            fresh_ids.append(mid)
        if len(fresh_ids) >= INCREMENTAL_MAX_MESSAGES:
            break

    if not fresh_ids:
        await db.gmail_sync_state.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "last_sync_status": "ok",
                      "last_synced_at": now.isoformat(),
                      "last_message_epoch": int(now.timestamp())}},
            upsert=True,
        )
        return counts

    # Cheap filter + AI + write
    survivors: list[dict] = []
    newest_epoch = last_epoch or since_ts
    for mid in fresh_ids:
        msg = await get_message(access, mid)
        if not msg:
            continue
        # Track newest date so next tick starts after it
        d = msg.get("date")
        if d:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(d)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                newest_epoch = max(newest_epoch, int(dt.timestamp()))
            except Exception:
                pass
        if cheap_filter(msg):
            survivors.append(msg)

    counts["filtered_in"] = len(survivors)

    if survivors:
        sem = asyncio.Semaphore(AI_CONCURRENCY)

        async def _one(m):
            async with sem:
                return (m, await extract_with_ai(m))

        pairs = await asyncio.gather(*[_one(m) for m in survivors])
        now_iso = datetime.now(timezone.utc).isoformat()
        for m, ext in pairs:
            if not ext:
                continue
            counts["ai_extracted"] += 1
            inv, rec, rev = await _extract_and_write(db, user_id, m, ext, my_email, now_iso)
            counts["invoices_created"] += inv
            counts["receipts_created"] += rec
            counts["review_items"] += rev

    # Reconcile any new receipts against open invoices
    try:
        recon = await reconcile_receipts(db, user_id)
        counts["receipts_matched"] = recon.get("matched", 0)
        counts["receipts_ambiguous"] = recon.get("ambiguous", 0)
    except Exception as e:
        logger.warning("Sync reconcile failed: %s", e)

    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "last_sync_status": "ok",
                  "last_synced_at": now.isoformat(),
                  "last_message_epoch": int(newest_epoch),
                  "last_counts": counts}},
        upsert=True,
    )
    return counts


async def sync_all_users(db) -> dict:
    """Iterate every connected user and run one incremental sync tick per user."""
    totals = {"users": 0, "invoices_created": 0, "receipts_created": 0,
              "receipts_matched": 0, "review_items": 0}
    async for conn in db.gmail_connections.find({"status": "connected"}):
        uid = conn.get("user_id")
        if not uid:
            continue
        try:
            c = await run_incremental_sync(db, uid)
            totals["users"] += 1
            for k in ("invoices_created", "receipts_created", "receipts_matched", "review_items"):
                totals[k] += c.get(k, 0)
        except Exception as e:
            logger.exception("Sync failed for user %s: %s", uid, e)
    return totals


# ---------------------------------------------------------------------------
# Receipt reconciliation
# ---------------------------------------------------------------------------
def _name_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _amount_close(receipt_amt: float, invoice_balance: float) -> tuple[bool, bool]:
    """Return (is_close_to_full, is_valid_partial).

    - is_close_to_full: receipt within tolerance of remaining balance → treat as full-payment closure
    - is_valid_partial: receipt is smaller than balance by more than tolerance AND ≥ PARTIAL_MIN_PCT
    """
    if invoice_balance <= 0 or receipt_amt <= 0:
        return (False, False)
    tol = max(invoice_balance * AMOUNT_TOLERANCE_PCT, AMOUNT_TOLERANCE_ABS)
    if abs(receipt_amt - invoice_balance) <= tol:
        return (True, False)
    if receipt_amt < invoice_balance - tol and receipt_amt >= invoice_balance * PARTIAL_MIN_PCT:
        return (False, True)
    # Receipt bigger than balance → not a clean match (overpayment / wrong invoice)
    return (False, False)


async def reconcile_receipts(db, user_id) -> dict:
    """Match `unmatched` receipts against open invoices for this user.

    Returns: {"matched": N, "ambiguous": M, "partial": P}
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    matched = 0
    ambiguous = 0
    partial = 0

    # Load all open invoices for this user once
    open_invoices: list[dict] = []
    async for inv in db.invoices.find({"user_id": user_id, "status": {"$in": list(_OPEN_STATUSES)}}):
        # Ensure balance_remaining is populated for legacy rows
        if "balance_remaining" not in inv or inv["balance_remaining"] is None:
            inv["balance_remaining"] = float(inv.get("amount") or 0)
        open_invoices.append(inv)

    async for rc in db.receipts.find({"user_id": user_id, "match_status": "unmatched"}):
        rc_amount = float(rc.get("amount") or 0)
        payer = rc.get("payer_name")
        candidates = []
        for inv in open_invoices:
            bal = float(inv.get("balance_remaining") or 0)
            if bal <= 0:
                continue
            close_full, valid_partial = _amount_close(rc_amount, bal)
            if not (close_full or valid_partial):
                continue
            name_sim = max(
                _name_similarity(payer, inv.get("counterparty_name")),
                _name_similarity(payer, inv.get("counterparty_email")),
            )
            amt_score = 1.0 if close_full else max(0.0, 1.0 - abs(rc_amount - bal) / bal)
            score = 0.6 * amt_score + 0.4 * name_sim
            candidates.append({
                "invoice": inv,
                "score": score,
                "name_sim": name_sim,
                "close_full": close_full,
                "valid_partial": valid_partial,
            })

        # Filter: require minimum name similarity OR a very tight full match
        candidates = [
            c for c in candidates
            if c["name_sim"] >= NAME_SIMILARITY_MIN or (c["close_full"] and c["score"] >= 0.7)
        ]

        if not candidates:
            continue

        candidates.sort(key=lambda c: c["score"], reverse=True)
        top = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None

        # If more than one candidate is within 0.05 of top → ambiguous
        if second and (top["score"] - second["score"]) < 0.05:
            await db.receipts.update_one(
                {"_id": rc["_id"]},
                {"$set": {
                    "match_status": "ambiguous",
                    "candidate_invoice_ids": [str(c["invoice"]["_id"]) for c in candidates[:3]],
                    "updated_at": now_iso,
                }},
            )
            ambiguous += 1
            continue

        inv = top["invoice"]
        bal = float(inv.get("balance_remaining") or inv.get("amount") or 0)
        applied = min(rc_amount, bal)
        new_balance = round(bal - applied, 2)
        new_paid = round(float(inv.get("paid_amount") or 0) + applied, 2)

        if top["close_full"] or new_balance <= 0.005:
            new_status = "paid"
            paid_at = now_iso
        else:
            new_status = "partially_paid"
            paid_at = inv.get("paid_at")
            partial += 1

        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "status": new_status,
                "balance_remaining": max(new_balance, 0.0),
                "paid_amount": new_paid,
                "paid_at": paid_at,
                "status_updated_at": now_iso,
            }},
        )
        await db.receipts.update_one(
            {"_id": rc["_id"]},
            {"$set": {
                "match_status": "matched",
                "matched_invoice_id": inv["_id"],
                "applied_amount": applied,
                "match_score": top["score"],
                "updated_at": now_iso,
            }},
        )
        await db.invoice_events.insert_one({
            "user_id": user_id,
            "invoice_id": inv["_id"],
            "action": "receipt_matched",
            "at": now_iso,
            "meta": {
                "receipt_id": rc["_id"],
                "amount": applied,
                "balance_after": max(new_balance, 0.0),
                "payer_name": payer,
                "score": top["score"],
            },
        })
        # Reflect the balance update locally so subsequent receipts see it
        inv["balance_remaining"] = max(new_balance, 0.0)
        inv["status"] = new_status
        matched += 1

    return {"matched": matched, "ambiguous": ambiguous, "partial": partial}
