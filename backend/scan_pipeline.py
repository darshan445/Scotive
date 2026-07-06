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

# Known money/processor senders — ALWAYS keep, even if user never replied.
# Excludes SaaS vendors that bill the user (those are `VENDOR_DOMAINS` below).
PAYMENT_SENDER_DOMAINS = {
    "stripe.com", "paypal.com", "quickbooks.com", "intuit.com",
    "freshbooks.com", "waveapps.com", "zoho.com", "square.com",
    "chase.com", "bankofamerica.com", "wellsfargo.com", "wise.com",
    "gocardless.com", "xero.com", "mercury.com",
}

# Vendors/SaaS that bill THE USER for services the user consumes.
# Emails FROM these domains are subscription/hosting bills, NOT invoices the
# user sent to a client. We surface them in the review queue at best (never
# straight into the ledger) so the user can consciously ignore or file them.
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
    # Match subdomains like billing.cloudflare.com
    for v in VENDOR_DOMAINS:
        if sender_domain.endswith("." + v):
            return True
    return False

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


def _msg_label(msg: dict) -> str:
    """Compact one-liner for pipeline logs."""
    subj = (msg.get("subject") or "")[:80]
    sender = _extract_email_addr(msg.get("from", ""))
    return f"id={msg.get('id','?')} from={sender!r} subj={subj!r}"


def cheap_filter_detail(msg: dict) -> tuple[bool, str]:
    """Return (keep, reason) for cheap noise filters."""
    sender = _extract_email_addr(msg.get("from", ""))
    domain = _sender_domain(sender)
    haystack = " ".join([msg.get("subject", ""), msg.get("snippet", ""), sender])

    if domain in PAYMENT_SENDER_DOMAINS:
        return True, "payment_processor_domain"
    if msg.get("has_attachment"):
        return True, "pdf_attachment"
    if NOISE_RE.search(sender):
        subj = msg.get("subject", "").lower()
        if not any(k in subj for k in ("invoice", "receipt", "payment", "past due")):
            return False, "noise_sender"
    if MONEY_RE.search(haystack):
        return True, "money_keyword"
    if AMOUNT_RE.search(haystack):
        return True, "dollar_amount"
    return False, "no_money_signal"


def cheap_filter(msg: dict) -> bool:
    """Return True if the message survives cheap noise filters."""
    keep, _reason = cheap_filter_detail(msg)
    return keep


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
- CRITICAL DIRECTION CHECK: We only track invoices the USER SENT to their clients (money owed TO the user). We do NOT track subscription bills, vendor invoices, or SaaS charges the user PAYS (money the user OWES to vendors).
- "invoice_sent" = the USER sent an invoice to their own client for services/products the USER provides. The user's email appears as the sender/FROM (or the user's business is named as the biller). If the email is FROM a well-known vendor (Cloudflare, Vultr, AWS, Anthropic, OpenAI, GitHub, Google Workspace, Microsoft, Adobe, Slack, Notion, Linear, Figma, Vercel, Netlify, Heroku, DigitalOcean, hosting/SaaS/subscription providers of any kind) to the user, set is_money_related=false and kind="none" — the user is the CUSTOMER, not the vendor.
- "payment_promise" = a CLIENT of the user said they will pay the user by a date. Never applies to vendor dunning notices ("we will retry your payment").
- "partial_payment" = a client sent part of an invoice the user issued.
- "receipt" = a payment processor confirms someone PAID THE USER. Set counterparty_name to the PAYER (the client who paid). If the "receipt" is from a vendor charging the user (e.g. "your Anthropic subscription of $23.60 was charged"), that is NOT a receipt of money received — set is_money_related=false and kind="none".
- "payment_claim" = a client says they paid the user but no processor confirmation.
- If the user's own email address appears as the counterparty (they'd be invoicing themselves), set is_money_related=false and kind="none".
- Set is_money_related=false and kind="none" for: subscription renewal notices, "payment failed" from a vendor to the user, "your invoice is available" from a SaaS to the user, project chatter, newsletters, meeting requests, general work talk.
- Do not invent amounts, dates, or names. Return null when unsure.
- When direction is ambiguous, lower the confidence below 0.75 so the item lands in the review queue.
"""


async def extract_with_ai(msg: dict, my_email: str = "") -> Optional[dict]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("pipeline.ai SKIP %s reason=no_openrouter_key", _msg_label(msg))
        return None

    user_content = (
        f"USER_EMAIL: {my_email or 'unknown'}\n"
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
                logger.warning(
                    "pipeline.ai FAIL %s status=%s body=%s",
                    _msg_label(msg), r.status_code, r.text[:200],
                )
                return None
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            logger.info(
                "pipeline.ai OK %s -> money=%s kind=%s amount=%s conf=%s cp=%s",
                _msg_label(msg),
                parsed.get("is_money_related"),
                parsed.get("kind"),
                parsed.get("amount"),
                parsed.get("confidence"),
                parsed.get("counterparty_email") or parsed.get("counterparty_name"),
            )
            return parsed
    except Exception as e:
        logger.warning("pipeline.ai ERROR %s err=%s", _msg_label(msg), e)
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
    """Deprecated — use onboarding seed (90d) via POST /seed/start."""
    logger.warning("run_historical_scan deprecated user=%s job=%s months=%s", user_id, job_id, months)
    from gmail_sync import run_onboarding_sync
    await run_onboarding_sync(db, user_id, job_id)


# ---------------------------------------------------------------------------
# Continuous incremental sync (F9a)
# ---------------------------------------------------------------------------
INCREMENTAL_LOOKBACK_DAYS = 3   # first-run cushion
INCREMENTAL_OVERLAP_HOURS = 24  # re-check the last day on every sync
INCREMENTAL_MAX_MESSAGES = 40   # per-tick cap so a single user can't hog the loop


async def _extract_and_write(db, user_id, msg, ext, my_email, now_iso, CONFIDENCE_THRESHOLD=0.75):
    """Persist a single AI extraction outcome. Returns (invoice_created, receipt_created, review_created)."""
    label = _msg_label(msg)

    def _drop(reason: str, **fields):
        extra = " ".join(f"{k}={v!r}" for k, v in fields.items()) if fields else ""
        logger.info("pipeline.write DROP %s reason=%s %s", label, reason, extra)
        return (0, 0, 0)

    if not ext.get("is_money_related"):
        return _drop("not_money_related", kind=ext.get("kind"), confidence=ext.get("confidence"))
    kind = ext.get("kind") or "none"

    sender_email = _extract_email_addr(msg.get("from", ""))
    sender_domain = _sender_domain(sender_email)
    my_email_lc = (my_email or "").lower()
    my_domain = _sender_domain(my_email_lc)

    if _is_vendor(sender_domain) and kind in ("invoice_sent", "payment_promise", "partial_payment", "receipt"):
        amount = ext.get("amount")
        if amount in (None, 0):
            return _drop("vendor_domain_no_amount", kind=kind, sender_domain=sender_domain)
        existing_r = await db.review_items.find_one({"user_id": user_id, "source_message_id": msg["id"]})
        if existing_r:
            return _drop("duplicate_review_item", kind=kind)
        await db.review_items.insert_one({
            "user_id": user_id,
            "counterparty_email": sender_email,
            "counterparty_name": ext.get("counterparty_name"),
            "amount": float(amount),
            "currency": ext.get("currency") or "USD",
            "kind": kind,
            "status": "invoiced",
            "source_message_id": msg["id"],
            "source_thread_id": msg.get("thread_id"),
            "source_subject": msg.get("subject"),
            "source_from": msg.get("from"),
            "source_date": msg.get("date"),
            "evidence_sentence": ext.get("evidence_sentence"),
            "confidence": float(ext.get("confidence") or 0),
            "review_status": "pending",
            "review_reason": "vendor_domain",
            "created_at": now_iso,
        })
        logger.info("pipeline.write REVIEW %s reason=vendor_domain kind=%s amount=%s", label, kind, amount)
        return (0, 0, 1)

    if kind == "receipt":
        amount = ext.get("amount")
        if amount in (None, 0):
            return _drop("receipt_no_amount")
        payer_name = (ext.get("counterparty_name") or "").lower()
        if my_email_lc and (my_email_lc in payer_name or (my_domain and my_domain in payer_name)):
            return _drop("receipt_self_payer", payer=payer_name)
        existing = await db.receipts.find_one({"user_id": user_id, "source_message_id": msg["id"]})
        if existing:
            return _drop("duplicate_receipt")
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
        logger.info("pipeline.write RECEIPT %s amount=%s payer=%s", label, amount, ext.get("counterparty_name"))
        return (0, 1, 0)

    if kind not in ("invoice_sent", "payment_promise", "partial_payment"):
        return _drop("unsupported_kind", kind=kind)
    amount = ext.get("amount")
    if amount in (None, 0):
        return _drop("invoice_no_amount", kind=kind, confidence=ext.get("confidence"))

    counterparty_email = (ext.get("counterparty_email") or sender_email).lower()
    if counterparty_email == my_email_lc:
        counterparty_email = _extract_email_addr(msg.get("to", "")).lower()
    if counterparty_email == my_email_lc or (my_domain and _sender_domain(counterparty_email) == my_domain):
        return _drop("counterparty_is_self", cp=counterparty_email, kind=kind)

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
            return _drop("duplicate_review_item", kind=kind)
        await db.review_items.insert_one({**base_doc, "review_status": "pending", "review_reason": "low_confidence"})
        logger.info(
            "pipeline.write REVIEW %s reason=low_confidence kind=%s amount=%s conf=%.2f cp=%s",
            label, kind, amount, confidence, counterparty_email,
        )
        return (0, 0, 1)

    existing = await db.invoices.find_one({"user_id": user_id, "source_message_id": msg["id"]})
    if existing:
        return _drop("duplicate_invoice", kind=kind)
    await db.invoices.insert_one(base_doc)
    logger.info(
        "pipeline.write INVOICE %s kind=%s amount=%s status=%s conf=%.2f cp=%s due=%s",
        label, kind, amount, status, confidence, counterparty_email, ext.get("due_date"),
    )
    return (1, 0, 0)


async def _already_processed(db, user_id, message_id: str) -> bool:
    """True if we've already stored this message in any bucket."""
    from invoice_event_idempotency import message_already_handled
    return await message_already_handled(db, user_id, message_id)


async def run_incremental_sync(db, user_id) -> dict:
    from incremental_sync import run_incremental_sync as _run
    return await _run(db, user_id)


async def sync_all_users(db) -> dict:
    from incremental_sync import sync_all_users as _sync_all
    return await _sync_all(db)


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
            # Auto-match → paid (unconfirmed); user confirms in Today / Payments UI
            new_status = "paid_unconfirmed"
            paid_at = None
        else:
            new_status = "partially_paid"
            paid_at = inv.get("paid_at")
            partial += 1

        amt_label = f"{rc.get('currency') or ''} {rc_amount}".strip()
        prev_status = inv.get("status") or "invoiced"
        prev_bal = bal
        prev_paid = float(inv.get("paid_amount") or 0)
        patch: dict = {
            "status": new_status,
            "balance_remaining": max(new_balance, 0.0),
            "paid_amount": new_paid,
            "paid_at": paid_at,
            "status_updated_at": now_iso,
            "chasing_paused": True,
        }
        if new_status == "paid_unconfirmed":
            patch["payment_claim_quote"] = (
                f"Payment of {amt_label} from {payer}"
                if payer
                else f"Processor payment of {amt_label}"
            )
            patch["status_before_claim"] = prev_status
            patch["claim_balance_before"] = prev_bal
            patch["claim_paid_before"] = prev_paid
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": patch},
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
        from post_chase import clear_watching_on_client_event
        await clear_watching_on_client_event(db, inv["_id"], now_iso)
        # Reflect the balance update locally so subsequent receipts see it
        inv["balance_remaining"] = max(new_balance, 0.0)
        inv["status"] = new_status
        matched += 1

    return {"matched": matched, "ambiguous": ambiguous, "partial": partial}
