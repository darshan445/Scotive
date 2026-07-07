"""Populate Mongo with realistic demo invoices for UI walkthrough.

Creates clients across every major status (past due, promised, broken promise,
disputed, partial, says-paid, gone quiet, watching, chase drafts, review queue,
receipts, and rich timelines).

Usage:
  python scripts/seed_demo_workspace.py                       # seed demo data
  python scripts/seed_demo_workspace.py --email you@x.com     # seed another user
  python scripts/seed_demo_workspace.py --clean               # full reset

--clean removes EVERY invoice-related document for the user (invoices, events,
receipts, review items, chase drafts/sends, seed jobs & candidates, scan jobs,
merge prompts, digest sends, sync state, ...). The user account and Gmail
connection are kept, so on next login the app starts fresh — Gmail onboarding
kicks in and re-seeds from scratch.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DEMO_PREFIX = "demo-"
DEFAULT_EMAIL = "admin@scotive.com"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _date(days_offset: int) -> str:
    today = datetime.now(timezone.utc).date()
    return (today + timedelta(days=days_offset)).isoformat()


def _dt(days_offset: int, hour: int = 12) -> str:
    base = datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0)
    return _iso(base + timedelta(days=days_offset))


# Every collection that stores per-user invoice/workspace data. The user
# account (`users`), Gmail connection (`gmail_connections`) and preferences
# (`user_settings`) are deliberately NOT touched.
WORKSPACE_COLLECTIONS = [
    "invoices",
    "invoice_events",
    "receipts",
    "review_items",
    "chase_drafts",
    "chase_sends",
    "seed_jobs",
    "seed_candidates",
    "scan_jobs",
    "suppressed_senders",
    "client_merges",
    "client_merge_prompts",
    "digest_sends",
    "gmail_sync_state",
]


async def wipe_user_workspace(db, user_id) -> dict:
    """Delete every invoice-related document for this user, across all
    collections. Leaves the account + Gmail connection intact so the next
    login starts the onboarding seed flow from scratch."""
    counts: dict[str, int] = {}
    for coll in WORKSPACE_COLLECTIONS:
        r = await db[coll].delete_many({"user_id": user_id})
        if r.deleted_count:
            counts[coll] = r.deleted_count
    return counts


async def _event(db, user_id, invoice_id, action: str, at: str, meta: dict):
    await db.invoice_events.insert_one({
        "user_id": user_id,
        "invoice_id": invoice_id,
        "action": action,
        "at": at,
        "meta": meta,
    })


async def _invoice(db, user_id, *, doc: dict) -> ObjectId:
    doc = {"user_id": user_id, **doc}
    if "balance_remaining" not in doc:
        doc["balance_remaining"] = float(doc.get("amount") or 0)
    if "paid_amount" not in doc:
        doc["paid_amount"] = 0.0
    res = await db.invoices.insert_one(doc)
    return res.inserted_id


async def seed(db, user_id) -> dict:
    await wipe_user_workspace(db, user_id)
    now_iso = _iso(datetime.now(timezone.utc))
    ids: dict[str, ObjectId] = {}

    # --- 1. Invoiced (due in future) ---
    ids["acme"] = await _invoice(db, user_id, doc={
        "counterparty_email": "billing@acme.com",
        "counterparty_name": "Acme Widgets",
        "amount": 4200.0,
        "currency": "USD",
        "invoice_ref": "DEMO-1001",
        "due_date": _date(18),
        "status": "invoiced",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-acme",
        "source_thread_id": f"{DEMO_PREFIX}thread-acme",
        "source_subject": "Invoice DEMO-1001 — June retainer",
        "source_from": "you@scotive.com",
        "source_date": _dt(-8),
        "evidence_sentence": "Please find attached invoice DEMO-1001 for $4,200, due in 18 days.",
        "confidence": 0.95,
        "created_at": _dt(-8),
        "last_activity_at": _dt(-8),
    })
    await _event(db, user_id, ids["acme"], "invoice_sent", _dt(-8), {
        "message_id": f"{DEMO_PREFIX}inv-acme",
        "message_date": _dt(-8),
        "subject": "Invoice DEMO-1001 — June retainer",
        "quote": "Please find attached invoice DEMO-1001 for $4,200.",
    })

    # --- 2. Past due ---
    ids["beta"] = await _invoice(db, user_id, doc={
        "counterparty_email": "ap@beta.co",
        "counterparty_name": "Beta Services",
        "amount": 1850.0,
        "currency": "USD",
        "invoice_ref": "DEMO-2002",
        "due_date": _date(-14),
        "status": "overdue",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-beta",
        "source_thread_id": f"{DEMO_PREFIX}thread-beta",
        "source_subject": "Invoice DEMO-2002",
        "source_from": "you@scotive.com",
        "source_date": _dt(-28),
        "evidence_sentence": "Invoice DEMO-2002 for $1,850 — payment was due two weeks ago.",
        "confidence": 0.92,
        "created_at": _dt(-28),
        "last_activity_at": _dt(-14),
        "escalation_step_floor": 0,
    })
    await _event(db, user_id, ids["beta"], "invoice_sent", _dt(-28), {
        "message_id": f"{DEMO_PREFIX}inv-beta",
        "message_date": _dt(-28),
        "quote": "Invoice DEMO-2002 for $1,850 — net 14.",
    })

    # --- 3. Promised ---
    ids["gamma"] = await _invoice(db, user_id, doc={
        "counterparty_email": "finance@gamma.io",
        "counterparty_name": "Gamma Inc",
        "amount": 3100.0,
        "currency": "USD",
        "invoice_ref": "DEMO-3003",
        "due_date": _date(-5),
        "promise_date": _date(4),
        "status": "promised",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-gamma",
        "source_thread_id": f"{DEMO_PREFIX}thread-gamma",
        "source_subject": "Invoice DEMO-3003 — Q2 consulting",
        "source_from": "you@scotive.com",
        "source_date": _dt(-20),
        "evidence_sentence": "Invoice DEMO-3003 for $3,100.",
        "confidence": 0.94,
        "created_at": _dt(-20),
        "last_activity_at": _dt(-2),
    })
    await _event(db, user_id, ids["gamma"], "invoice_sent", _dt(-20), {
        "message_id": f"{DEMO_PREFIX}inv-gamma",
        "message_date": _dt(-20),
        "quote": "Invoice DEMO-3003 for $3,100 attached.",
    })
    await _event(db, user_id, ids["gamma"], "payment_promise", _dt(-2), {
        "message_id": f"{DEMO_PREFIX}gamma-promise",
        "message_date": _dt(-2),
        "subject": "Re: Invoice DEMO-3003",
        "quote": "We'll wire this by next Friday — finance approved it.",
        "date": _date(4),
    })

    # --- 4. Promise broken ---
    ids["delta"] = await _invoice(db, user_id, doc={
        "counterparty_email": "accounts@delta.net",
        "counterparty_name": "Delta LLC",
        "amount": 2750.0,
        "currency": "USD",
        "invoice_ref": "DEMO-4004",
        "due_date": _date(-21),
        "promise_date": _date(-6),
        "status": "promise_broken",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-delta",
        "source_thread_id": f"{DEMO_PREFIX}thread-delta",
        "source_subject": "Invoice DEMO-4004",
        "source_from": "you@scotive.com",
        "source_date": _dt(-35),
        "evidence_sentence": "Invoice DEMO-4004 for $2,750.",
        "confidence": 0.93,
        "created_at": _dt(-35),
        "last_activity_at": _dt(-6),
    })
    await _event(db, user_id, ids["delta"], "payment_promise", _dt(-10), {
        "message_id": f"{DEMO_PREFIX}delta-promise",
        "message_date": _dt(-10),
        "quote": "Payment will go out on the 28th.",
        "date": _date(-6),
    })
    await _event(db, user_id, ids["delta"], "chase_sent", _dt(-7), {
        "message_id": f"{DEMO_PREFIX}delta-chase",
        "message_date": _dt(-7),
        "subject": "Re: Invoice DEMO-4004",
        "quote": "Just checking in — the promised date has passed.",
    })

    # --- 5. Disputed ---
    ids["echo"] = await _invoice(db, user_id, doc={
        "counterparty_email": "pay@echo.com",
        "counterparty_name": "Echo Creative",
        "amount": 980.0,
        "currency": "USD",
        "invoice_ref": "DEMO-5005",
        "due_date": _date(-9),
        "status": "disputed",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-echo",
        "source_thread_id": f"{DEMO_PREFIX}thread-echo",
        "source_subject": "Invoice DEMO-5005 — brand assets",
        "source_from": "you@scotive.com",
        "source_date": _dt(-25),
        "evidence_sentence": "Invoice DEMO-5005 for $980.",
        "confidence": 0.91,
        "created_at": _dt(-25),
        "last_activity_at": _dt(-3),
    })
    await _event(db, user_id, ids["echo"], "dispute", _dt(-3), {
        "message_id": f"{DEMO_PREFIX}echo-dispute",
        "message_date": _dt(-3),
        "quote": "We never signed off on the extra revision rounds — disputing this line item.",
        "dispute_kind": "scope",
    })

    # --- 6. Partially paid ---
    ids["foxtrot"] = await _invoice(db, user_id, doc={
        "counterparty_email": "ar@foxtrot.com",
        "counterparty_name": "Foxtrot Media",
        "amount": 2400.0,
        "balance_remaining": 1200.0,
        "paid_amount": 1200.0,
        "currency": "USD",
        "invoice_ref": "DEMO-6006",
        "due_date": _date(-3),
        "status": "partially_paid",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-foxtrot",
        "source_thread_id": f"{DEMO_PREFIX}thread-foxtrot",
        "source_subject": "Invoice DEMO-6006",
        "source_from": "you@scotive.com",
        "source_date": _dt(-18),
        "evidence_sentence": "Invoice DEMO-6006 for $2,400.",
        "confidence": 0.96,
        "created_at": _dt(-18),
        "last_activity_at": _dt(-1),
        "chasing_paused": True,
    })
    rc_partial_id = ObjectId()
    await db.receipts.insert_one({
        "_id": rc_partial_id,
        "user_id": user_id,
        "amount": 1200.0,
        "applied_amount": 1200.0,
        "currency": "USD",
        "payer_name": "Foxtrot Media",
        "processor_from": "receipts@stripe.com",
        "source_message_id": f"{DEMO_PREFIX}rc-foxtrot",
        "source_subject": "Payment received — $1,200.00",
        "source_date": _dt(-1),
        "evidence_sentence": "Stripe: $1,200.00 from Foxtrot Media",
        "confidence": 0.97,
        "match_status": "matched",
        "matched_invoice_id": ids["foxtrot"],
        "match_score": 0.92,
        "created_at": _dt(-1),
    })
    await _event(db, user_id, ids["foxtrot"], "receipt_matched", _dt(-1), {
        "message_id": f"{DEMO_PREFIX}rc-foxtrot",
        "message_date": _dt(-1),
        "quote": "Stripe: $1,200.00 from Foxtrot Media",
        "receipt_id": rc_partial_id,
        "applied_amount": 1200.0,
    })

    # --- 7. Says paid (unconfirmed) ---
    ids["golf"] = await _invoice(db, user_id, doc={
        "counterparty_email": "billing@golf.com",
        "counterparty_name": "Golf Partners",
        "amount": 1500.0,
        "balance_remaining": 0.0,
        "paid_amount": 1500.0,
        "currency": "USD",
        "invoice_ref": "DEMO-7007",
        "due_date": _date(-7),
        "status": "paid_unconfirmed",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-golf",
        "source_thread_id": f"{DEMO_PREFIX}thread-golf",
        "source_from": "you@scotive.com",
        "source_date": _dt(-22),
        "evidence_sentence": "Invoice DEMO-7007 for $1,500.",
        "confidence": 0.9,
        "created_at": _dt(-22),
        "last_activity_at": _dt(-1),
        "payment_claim_quote": "Wire sent this morning — should land today.",
        "status_before_claim": "overdue",
        "chasing_paused": True,
    })
    await _event(db, user_id, ids["golf"], "payment_claim", _dt(-1), {
        "message_id": f"{DEMO_PREFIX}golf-claim",
        "message_date": _dt(-1),
        "quote": "Wire sent this morning — should land today.",
    })

    # --- 8. Gone quiet (stale prompt) ---
    ids["hotel"] = await _invoice(db, user_id, doc={
        "counterparty_email": "ap@hotel.com",
        "counterparty_name": "Hotel Group",
        "amount": 6400.0,
        "currency": "USD",
        "invoice_ref": "DEMO-8008",
        "due_date": _date(-90),
        "status": "stale",
        "status_before_stale": "overdue",
        "stale_prompt_pending": True,
        "stale_since": _dt(-125),
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-hotel",
        "source_thread_id": f"{DEMO_PREFIX}thread-hotel",
        "source_from": "you@scotive.com",
        "source_date": _dt(-130),
        "evidence_sentence": "Invoice DEMO-8008 for $6,400.",
        "confidence": 0.88,
        "created_at": _dt(-130),
        "last_activity_at": _dt(-125),
    })
    await _event(db, user_id, ids["hotel"], "went_stale", _dt(-125), {
        "quote": "No email activity in 120+ days",
    })

    # --- 9. Rich timeline — overdue + watching after chase ---
    ids["india"] = await _invoice(db, user_id, doc={
        "counterparty_email": "wherewasthis.contact@gmail.com",
        "counterparty_name": "India Tech",
        "amount": 5000.0,
        "currency": "INR",
        "invoice_ref": "DEMO-9009",
        "due_date": _date(-10),
        "promise_date": _date(-3),
        "status": "overdue",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-india",
        "source_thread_id": f"{DEMO_PREFIX}thread-india",
        "source_subject": "Invoice for month June",
        "source_from": "you@scotive.com",
        "source_date": _dt(-25),
        "evidence_sentence": "Invoice for month June — ₹5,000 due upon receipt.",
        "confidence": 0.97,
        "created_at": _dt(-25),
        "last_activity_at": _dt(-4),
        "watching_for_reply": True,
        "last_chase_at": _dt(-4),
        "current_escalation_step": 1,
        "escalation_step_floor": 0,
    })
    await _event(db, user_id, ids["india"], "invoice_sent", _dt(-25), {
        "message_id": f"{DEMO_PREFIX}inv-india",
        "message_date": _dt(-25),
        "subject": "Invoice for month June",
        "quote": "Invoice for month June — ₹5,000 due upon receipt.",
    })
    await _event(db, user_id, ids["india"], "payment_promise", _dt(-8), {
        "message_id": f"{DEMO_PREFIX}india-promise",
        "message_date": _dt(-8),
        "quote": "I'll pay this Friday.",
        "date": _date(-3),
    })
    await _event(db, user_id, ids["india"], "chase_sent", _dt(-4), {
        "message_id": f"{DEMO_PREFIX}india-chase",
        "message_date": _dt(-4),
        "subject": "Re: Invoice for month June",
        "quote": "Hi — just following up on the June invoice. Any update on payment?",
    })

    # --- 10. Watching — ladder exhausted ---
    ids["lima"] = await _invoice(db, user_id, doc={
        "counterparty_email": "ops@lima.co",
        "counterparty_name": "Lima Logistics",
        "amount": 890.0,
        "currency": "USD",
        "invoice_ref": "DEMO-1010",
        "due_date": _date(-45),
        "status": "overdue",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-lima",
        "source_thread_id": f"{DEMO_PREFIX}thread-lima",
        "source_from": "you@scotive.com",
        "source_date": _dt(-60),
        "evidence_sentence": "Invoice DEMO-1010 for $890.",
        "confidence": 0.9,
        "created_at": _dt(-60),
        "last_activity_at": _dt(-20),
        "ladder_exhausted": True,
        "last_chase_at": _dt(-20),
    })

    # --- 11. Paid yesterday (Today → Resolved) ---
    ids["juliet"] = await _invoice(db, user_id, doc={
        "counterparty_email": "hello@juliet.studio",
        "counterparty_name": "Juliet Studio",
        "amount": 2200.0,
        "balance_remaining": 0.0,
        "paid_amount": 2200.0,
        "currency": "USD",
        "invoice_ref": "DEMO-1111",
        "due_date": _date(-2),
        "status": "paid",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-juliet",
        "source_from": "you@scotive.com",
        "source_date": _dt(-15),
        "evidence_sentence": "Invoice DEMO-1111 for $2,200.",
        "confidence": 0.95,
        "created_at": _dt(-15),
        "paid_at": _dt(-1),
        "last_activity_at": _dt(-1),
    })
    await _event(db, user_id, ids["juliet"], "mark_paid", _dt(-1), {
        "quote": "Confirmed in bank",
    })

    # --- 12. Paid (older history) ---
    ids["kilo"] = await _invoice(db, user_id, doc={
        "counterparty_email": "team@kilo.agency",
        "counterparty_name": "Kilo Agency",
        "amount": 3600.0,
        "balance_remaining": 0.0,
        "paid_amount": 3600.0,
        "currency": "USD",
        "invoice_ref": "DEMO-1212",
        "due_date": _date(-40),
        "promise_date": _date(-35),
        "status": "paid",
        "kind": "invoice_sent",
        "source_message_id": f"{DEMO_PREFIX}inv-kilo",
        "source_from": "you@scotive.com",
        "source_date": _dt(-55),
        "evidence_sentence": "Invoice DEMO-1212 for $3,600.",
        "confidence": 0.94,
        "created_at": _dt(-55),
        "paid_at": _dt(-32),
        "last_activity_at": _dt(-32),
    })
    await _event(db, user_id, ids["kilo"], "payment_promise", _dt(-38), {
        "message_id": f"{DEMO_PREFIX}kilo-promise",
        "message_date": _dt(-38),
        "quote": "We'll pay by end of month.",
        "date": _date(-35),
    })
    await _event(db, user_id, ids["kilo"], "mark_paid", _dt(-32), {
        "quote": "Receipt matched — paid on time",
    })

    # --- Chase drafts (no AI needed) ---
    draft_specs = [
        (ids["beta"], "offset_1", 1, "firm_followup", "firm", "DEMO-2002"),
        (ids["delta"], "promise_broken", None, "promise_broken", "firm", "DEMO-4004"),
        (ids["india"], "followup_2", 2, "final_notice", "final", "DEMO-9009"),
    ]
    draft_ids = []
    for inv_id, step_key, step_index, step_label, tone, ref in draft_specs:
        inv = await db.invoices.find_one({"_id": inv_id})
        ins = await db.chase_drafts.insert_one({
            "user_id": user_id,
            "invoice_id": inv_id,
            "step_key": step_key,
            "step_index": step_index,
            "step_label": step_label,
            "offset_days": 7 if step_key.startswith("offset") else None,
            "tone": tone,
            "subject": f"Re: Invoice {ref}",
            "body": (
                f"Hi {inv.get('counterparty_name') or 'there'},\n\n"
                f"I'm following up on invoice {ref} for "
                f"{inv.get('currency', 'USD')} {inv.get('balance_remaining') or inv.get('amount'):,.2f}. "
                f"Could you share an update on payment?\n\nThanks"
            ),
            "to": inv.get("counterparty_email"),
            "thread_id": inv.get("source_thread_id"),
            "counterparty_name": inv.get("counterparty_name"),
            "invoice_ref": ref,
            "amount": inv.get("balance_remaining") or inv.get("amount"),
            "currency": inv.get("currency") or "USD",
            "due_date": inv.get("due_date"),
            "status": "queued",
            "source": "demo_seed",
            "generated_at": now_iso,
        })
        draft_ids.append(ins.inserted_id)

    # --- Review queue ---
    await db.review_items.insert_many([
        {
            "user_id": user_id,
            "counterparty_email": "maybe@novaclient.com",
            "counterparty_name": "Nova Client",
            "amount": 750.0,
            "currency": "USD",
            "kind": "invoice_sent",
            "status": "invoiced",
            "source_message_id": f"{DEMO_PREFIX}review-lowconf",
            "source_subject": "June work — please advise",
            "source_from": "maybe@novaclient.com",
            "source_date": _dt(-2),
            "evidence_sentence": "Attached is our time for June — let me know if you need a formal invoice.",
            "confidence": 0.52,
            "review_status": "pending",
            "review_reason": "low_confidence",
            "created_at": _dt(-2),
        },
        {
            "user_id": user_id,
            "counterparty_email": "billing@acme.com",
            "kind": "payment_promise",
            "status": "promised",
            "source_message_id": f"{DEMO_PREFIX}review-sweep",
            "source_subject": "Re: Invoice DEMO-1001",
            "source_from": "billing@acme.com",
            "source_date": _dt(-1),
            "evidence_sentence": "We'll process this with next week's AP run.",
            "confidence": 0.61,
            "review_status": "pending",
            "review_reason": "sweep_event",
            "created_at": _dt(-1),
        },
    ])

    # --- Unmatched receipt ---
    await db.receipts.insert_one({
        "user_id": user_id,
        "amount": 499.0,
        "currency": "USD",
        "payer_name": "Unknown Payer LLC",
        "processor_from": "payments@paypal.com",
        "source_message_id": f"{DEMO_PREFIX}rc-orphan",
        "source_subject": "You received $499.00",
        "source_date": _dt(-3),
        "evidence_sentence": "PayPal: $499.00 from Unknown Payer LLC",
        "confidence": 0.85,
        "match_status": "unmatched",
        "matched_invoice_id": None,
        "candidate_invoice_ids": [],
        "created_at": _dt(-3),
    })

    # --- Gmail sync state: show full dashboard (not onboarding) ---
    followup_prompt = {
        "invoice_id": str(ids["india"]),
        "draft_id": str(draft_ids[2]),
        "counterparty_name": "India Tech",
        "counterparty_email": "wherewasthis.contact@gmail.com",
        "amount": 5000.0,
        "currency": "INR",
        "step_label": "final_notice",
        "prompted_at": now_iso,
    }
    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {
            "curation_complete": True,
            "awaiting_curation": False,
            "watching_sent_mail": True,
            "pending_followup_prompts": [followup_prompt],
            "client_identities": [
                "billing@acme.com", "ap@beta.co", "finance@gamma.io",
                "wherewasthis.contact@gmail.com",
            ],
            "updated_at": now_iso,
        }},
        upsert=True,
    )

    return {
        "invoices": len(ids),
        "chase_drafts": len(draft_ids),
        "review_items": 2,
        "receipts": 2,
        "clients": len(ids),
    }


async def main():
    parser = argparse.ArgumentParser(description="Seed demo workspace data for UI walkthrough")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="User email to seed data for")
    parser.add_argument("--clean", action="store_true",
                        help="Remove ALL invoice-related data for the user (full workspace reset)")
    args = parser.parse_args()

    load_dotenv(ROOT / "backend" / ".env")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "scotive")

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    user = await db.users.find_one({"email": args.email.lower()})
    if not user:
        print(f"User not found: {args.email}")
        print("Log in once or create the account first, then re-run.")
        sys.exit(1)

    if args.clean:
        counts = await wipe_user_workspace(db, user["_id"])
        total = sum(counts.values())
        print(f"Workspace fully reset for {args.email} — {total} documents removed:")
        for coll, n in sorted(counts.items()):
            print(f"  {coll}: {n}")
        if not counts:
            print("  (nothing to remove — already clean)")
        print()
        print("Account and Gmail connection kept. On next login the app starts")
        print("fresh: onboarding will scan and seed invoices from Gmail again.")
        return

    counts = await seed(db, user["_id"])
    print(f"Demo workspace seeded for {args.email}")
    print(f"  {counts['invoices']} invoices across {counts['clients']} clients")
    print(f"  {counts['chase_drafts']} chase drafts, {counts['review_items']} review items, {counts['receipts']} receipts")
    print()
    print("Open the app and refresh:")
    print("  Dashboard → Needs you today (past due, broken promise, confirm, gone quiet)")
    print("  Dashboard → All invoices (all status badges + timelines)")
    print("  Review queue → 2 pending items")
    print("  Clients → click India Tech or Gamma for conversation timelines")
    print()
    print("Full reset anytime: python scripts/seed_demo_workspace.py --clean")


if __name__ == "__main__":
    asyncio.run(main())
