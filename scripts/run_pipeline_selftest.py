"""Scotive pipeline self-test — T1–T14 without Gmail.

Simulates sent-mail ingestion + reply intelligence + lifecycle transitions
for tdarshan336@gmail.com → darsh@getscotive.com, then asserts expected
statuses, amounts, dates, dedupe, and dashboard stats.

Usage:
  PYTHONPATH=backend python scripts/run_pipeline_selftest.py
  PYTHONPATH=backend python scripts/run_pipeline_selftest.py --keep-data
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

load_dotenv(ROOT / "backend" / ".env")

from client_sweep import apply_client_result, collapse_ai_invoices  # noqa: E402
from digest_sender import collect_today_sections, _totals as digest_totals  # noqa: E402
from invoice_lifecycle import (  # noqa: E402
    apply_past_due_transitions,
    apply_promise_broken_transitions,
)
from ledger_reconcile import (  # noqa: E402
    OPEN_INVOICE_STATUSES,
    client_identity_key,
    compute_open_totals,
    normalize_invoice_ref,
    upsert_sweep_invoice,
)
from promise_dates import resolve_stated_date  # noqa: E402
from seed_demo_workspace import wipe_user_workspace  # noqa: E402

USER_EMAIL = "tdarshan336@gmail.com"
CLIENT_EMAIL = "darsh@getscotive.com"
ACCOUNTS_EMAIL = "accounts@getscotive.com"
PREFIX = "selftest-"

_OPEN = set(OPEN_INVOICE_STATUSES)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rfc2822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


class SelfTest:
    def __init__(self, db, user_id: ObjectId):
        self.db = db
        self.user_id = user_id
        self.my_email = USER_EMAIL
        self.client_key = client_identity_key(CLIENT_EMAIL)
        self.now = datetime.now(timezone.utc)
        self.results: list[tuple[str, bool, str]] = []
        self._msg_seq = 0
        self._thread_seq = 0
        self.invoice_ids: dict[str, ObjectId] = {}

    def _next_msg_id(self, tag: str) -> str:
        self._msg_seq += 1
        return f"{PREFIX}{tag}-{self._msg_seq}"

    def _next_thread(self, tag: str) -> str:
        self._thread_seq += 1
        return f"{PREFIX}thread-{tag}-{self._thread_seq}"

    def _msg(
        self,
        *,
        tag: str,
        thread_id: str,
        from_email: str,
        to_email: str,
        subject: str,
        body: str,
        when: datetime,
        msg_id: str | None = None,
    ) -> dict:
        mid = msg_id or self._next_msg_id(tag)
        return {
            "id": mid,
            "thread_id": thread_id,
            "from": from_email,
            "to": to_email,
            "to_addrs": [to_email.lower()],
            "subject": subject,
            "body": body,
            "snippet": body[:160],
            "date": _rfc2822(when),
        }

    async def _ingest_sent(
        self,
        *,
        tag: str,
        subject: str,
        body: str,
        amount: float,
        due_date: str | None,
        when: datetime,
        thread_id: str | None = None,
    ) -> ObjectId:
        tid = thread_id or self._next_thread(tag)
        msg = self._msg(
            tag=tag,
            thread_id=tid,
            from_email=self.my_email,
            to_email=CLIENT_EMAIL,
            subject=subject,
            body=body,
            when=when,
        )
        ref = normalize_invoice_ref(None, subject)
        today = self.now.date()
        status = "invoiced"
        if due_date:
            try:
                due_d = datetime.strptime(due_date[:10], "%Y-%m-%d").date()
                if due_d < today:
                    status = "overdue"
            except ValueError:
                pass

        doc = {
            "user_id": self.user_id,
            "counterparty_email": CLIENT_EMAIL,
            "counterparty_name": "Scotive Client",
            "client_identity_key": self.client_key,
            "amount": amount,
            "balance_remaining": amount,
            "paid_amount": 0.0,
            "currency": "USD",
            "invoice_ref": ref,
            "invoice_ref_normalized": ref,
            "due_date": due_date,
            "due_date_assumed": False,
            "promise_date": None,
            "status": status,
            "kind": "invoice_sent",
            "source_message_id": msg["id"],
            "source_thread_id": tid,
            "source_subject": subject,
            "source_from": msg["from"],
            "source_date": _iso(when),
            "confidence": 0.95,
            "created_at": _iso(self.now),
        }
        outcome, inv_id = await upsert_sweep_invoice(self.db, self.user_id, doc, now_iso=_iso(self.now))
        assert inv_id and outcome in ("created", "merged"), f"ingest failed tag={tag} outcome={outcome}"
        if ref:
            self.invoice_ids[ref] = inv_id

        if not due_date:
            await self.db.gmail_sync_state.update_one(
                {"user_id": self.user_id},
                {
                    "$push": {
                        "pending_due_date_prompts": {
                            "invoice_id": str(inv_id),
                            "source_message_id": msg["id"],
                            "counterparty_email": CLIENT_EMAIL,
                            "amount": amount,
                            "invoice_ref": ref,
                            "detected_at": _iso(self.now),
                        }
                    }
                },
                upsert=True,
            )
        return inv_id

    async def _apply_reply(
        self,
        *,
        tag: str,
        thread_id: str,
        subject: str,
        body: str,
        when: datetime,
        events: list[dict],
        extra_invoices: list[dict] | None = None,
        from_email: str = CLIENT_EMAIL,
        anchor_ids: list[str] | None = None,
        msg_id: str | None = None,
    ) -> str:
        mid = msg_id or self._next_msg_id(tag)
        for ev in events:
            if not ev.get("message_id"):
                ev["message_id"] = mid
        msg = self._msg(
            tag=tag,
            thread_id=thread_id,
            from_email=from_email,
            to_email=self.my_email,
            subject=subject,
            body=body,
            when=when,
            msg_id=mid,
        )
        messages = {msg["id"]: msg}
        result = {
            "is_receivable_client": True,
            "client": {"name": "Scotive Client", "identities": [CLIENT_EMAIL, ACCOUNTS_EMAIL]},
            "invoices": extra_invoices or [],
            "events": events,
            "confidence_overall": 0.95,
        }
        await apply_client_result(
            self.db,
            self.user_id,
            CLIENT_EMAIL,
            result,
            messages,
            self.my_email,
            _iso(self.now),
            email_to_primary={ACCOUNTS_EMAIL.lower(): CLIENT_EMAIL.lower()},
            pass1_anchor_ids=anchor_ids or [],
        )
        return mid

    async def _apply_user_message(
        self,
        *,
        tag: str,
        thread_id: str,
        subject: str,
        body: str,
        when: datetime,
        events: list[dict],
        msg_id: str | None = None,
    ) -> str:
        """Simulate AI misclassifying a USER-sent chase/reminder (sender guard must reject)."""
        mid = msg_id or self._next_msg_id(tag)
        for ev in events:
            if not ev.get("message_id"):
                ev["message_id"] = mid
        msg = self._msg(
            tag=tag,
            thread_id=thread_id,
            from_email=self.my_email,
            to_email=CLIENT_EMAIL,
            subject=subject,
            body=body,
            when=when,
            msg_id=mid,
        )
        result = {
            "is_receivable_client": True,
            "client": {"name": "Scotive Client", "identities": [CLIENT_EMAIL, ACCOUNTS_EMAIL]},
            "invoices": [],
            "events": events,
            "confidence_overall": 0.95,
        }
        await apply_client_result(
            self.db,
            self.user_id,
            CLIENT_EMAIL,
            result,
            {msg["id"]: msg},
            self.my_email,
            _iso(self.now),
            email_to_primary={ACCOUNTS_EMAIL.lower(): CLIENT_EMAIL.lower()},
        )
        return mid

    async def _get_ref(self, ref: str) -> dict:
        inv = await self.db.invoices.find_one({
            "user_id": self.user_id,
            "invoice_ref_normalized": ref,
        })
        assert inv, f"invoice {ref} not found"
        return inv

    async def _count_invoices(self) -> int:
        return await self.db.invoices.count_documents({"user_id": self.user_id})

    async def _run_lifecycle(self) -> None:
        await apply_past_due_transitions(self.db, self.user_id)
        await apply_promise_broken_transitions(self.db, self.user_id)

    def _check(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail and not ok:
            line += f" — {detail}"
        print(line)

    async def _manual_mark_paid(self, ref: str) -> None:
        inv = await self._get_ref(ref)
        now = _iso(self.now)
        await self.db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "status": "paid",
                "paid_at": now,
                "balance_remaining": 0.0,
                "paid_amount": float(inv.get("amount") or 0),
                "status_updated_at": now,
                "last_activity_at": now,
            }},
        )
        await self.db.invoice_events.insert_one({
            "user_id": self.user_id,
            "invoice_id": inv["_id"],
            "action": "mark_paid",
            "at": now,
            "meta": {},
        })

    async def _manual_write_off(self, ref: str) -> None:
        inv = await self._get_ref(ref)
        now = _iso(self.now)
        await self.db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {"status": "written_off", "status_updated_at": now, "last_activity_at": now}},
        )
        await self.db.invoice_events.insert_one({
            "user_id": self.user_id,
            "invoice_id": inv["_id"],
            "action": "write_off",
            "at": now,
            "meta": {},
        })

    async def run_all(self) -> bool:
        d = self.now.date()
        jul = lambda day: datetime(2026, 7, day, 10, 0, tzinfo=timezone.utc)

        # --- T1: basic invoice, future due ---
        await self._ingest_sent(
            tag="t1",
            subject="Invoice #T1-001",
            body="Hi, invoice for June work attached details below.\nAmount: $1,000. Due: Jul 15, 2026.",
            amount=1000,
            due_date="2026-07-15",
            when=jul(6),
        )
        inv = await self._get_ref("T1-001")
        self._check("T1 status invoiced", inv["status"] == "invoiced", inv["status"])
        self._check("T1 amount", float(inv["amount"]) == 1000)
        self._check("T1 due date", inv.get("due_date") == "2026-07-15")

        # --- T2: past due on entry ---
        await self._ingest_sent(
            tag="t2",
            subject="Invoice #T2-002",
            body="June retainer: $800. Due: Jul 1, 2026.",
            amount=800,
            due_date="2026-07-01",
            when=jul(6),
        )
        inv = await self._get_ref("T2-002")
        self._check("T2 status overdue immediately", inv["status"] == "overdue", inv["status"])

        # --- T2b: user chase/reminder must not become paid_unconfirmed ---
        t2b_thread = self._next_thread("t2b")
        await self._ingest_sent(
            tag="t2b",
            subject="Invoice #T2B-022",
            body="June retainer: $800. Due: Jul 1, 2026.",
            amount=800,
            due_date="2026-07-01",
            when=jul(6),
            thread_id=t2b_thread,
        )
        await self._apply_user_message(
            tag="t2b-rem",
            thread_id=t2b_thread,
            subject="Re: Invoice #T2B-022",
            body=(
                "This is a reminder that Invoice #T2B-022 for the amount of 800.0 USD "
                "is now overdue, with a due date of July 1, 2026."
            ),
            when=jul(6),
            events=[{
                "type": "payment_claimed",
                "invoice_ref": "T2B-022",
                "quote": "Invoice #T2B-022 for the amount of 800.0 USD is now overdue",
                "confidence": 0.95,
            }],
        )
        inv = await self._get_ref("T2B-022")
        self._check("T2b user reminder not paid_unconfirmed", inv["status"] == "overdue", inv["status"])

        # --- T3: promise to pay (Friday from send date) ---
        t3_thread = self._next_thread("t3")
        t3_anchor = self._next_msg_id("t3-anchor")
        await self._ingest_sent(
            tag="t3",
            subject="Invoice #T3-003",
            body="July work: $500. Due: Jul 20, 2026.",
            amount=500,
            due_date="2026-07-20",
            when=jul(6),
            thread_id=t3_thread,
        )
        await self._apply_reply(
            tag="t3-reply",
            thread_id=t3_thread,
            subject="Re: Invoice #T3-003",
            body="Got it — I'll pay this on Friday.",
            when=jul(6),
            anchor_ids=[t3_anchor],
            events=[{
                "type": "promise",
                "invoice_ref": "T3-003",
                "date": None,
                "quote": "I'll pay this on Friday.",
                "message_id": self._next_msg_id("t3-reply"),
                "confidence": 0.95,
            }],
        )
        inv = await self._get_ref("T3-003")
        self._check("T3 status promised", inv["status"] == "promised", inv["status"])
        friday = resolve_stated_date(
            None,
            quote="I'll pay this on Friday.",
            message_dt=jul(6),
        )
        self._check("T3 promise date Friday Jul 10", friday == "2026-07-10", friday)
        self._check("T3 stored promise date", inv.get("promise_date") == "2026-07-10", inv.get("promise_date"))

        # --- T4: broken promise ---
        t4_thread = self._next_thread("t4")
        await self._ingest_sent(
            tag="t4",
            subject="Invoice #T4-004",
            body="Design sprint: $600. Due: Jul 5, 2026.",
            amount=600,
            due_date="2026-07-05",
            when=jul(5),
            thread_id=t4_thread,
        )
        t4_reply_id = self._next_msg_id("t4-reply")
        await self._apply_reply(
            tag="t4-reply",
            thread_id=t4_thread,
            subject="Re: Invoice #T4-004",
            body="Will pay by Jul 6.",
            when=jul(6),
            events=[{
                "type": "promise",
                "invoice_ref": "T4-004",
                "date": "2026-07-06",
                "quote": "Will pay by Jul 6.",
                "message_id": t4_reply_id,
                "confidence": 0.95,
            }],
        )
        await self._run_lifecycle()
        inv = await self._get_ref("T4-004")
        self._check("T4 status promise_broken", inv["status"] == "promise_broken", inv["status"])

        # --- T5: new thread, invoice ref match ---
        t5_thread = self._next_thread("t5")
        await self._ingest_sent(
            tag="t5",
            subject="Invoice #T5-005",
            body="Consulting hours: $1,500. Due Jul 25, 2026.",
            amount=1500,
            due_date="2026-07-25",
            when=jul(6),
            thread_id=t5_thread,
        )
        t5_new_thread = self._next_thread("t5-new")
        t5_reply_id = self._next_msg_id("t5-reply")
        before = await self._count_invoices()
        await self._apply_reply(
            tag="t5-reply",
            thread_id=t5_new_thread,
            subject="quick note",
            body="Hey, unrelated to the invoice — processed T5-005 today, should land in a day or two.",
            when=jul(7),
            events=[{
                "type": "payment_claimed",
                "invoice_ref": "T5-005",
                "quote": "processed T5-005 today, should land in a day or two.",
                "message_id": t5_reply_id,
                "confidence": 0.95,
            }],
        )
        after = await self._count_invoices()
        inv = await self._get_ref("T5-005")
        self._check("T5 no duplicate row", after == before)
        self._check("T5 status paid_unconfirmed", inv["status"] == "paid_unconfirmed", inv["status"])

        # --- T6: dispute → correction, same row ---
        t6_thread = self._next_thread("t6")
        await self._ingest_sent(
            tag="t6",
            subject="Invoice #T6-006",
            body="July maintenance: $400. Due Jul 20, 2026.",
            amount=400,
            due_date="2026-07-20",
            when=jul(6),
            thread_id=t6_thread,
        )
        t6_reply_id = self._next_msg_id("t6-reply")
        await self._apply_reply(
            tag="t6-reply",
            thread_id=t6_thread,
            subject="Re: Invoice #T6-006",
            body="This looks wrong — we agreed $300 this month, scope was reduced. Can you resend?",
            when=jul(7),
            events=[{
                "type": "dispute",
                "invoice_ref": "T6-006",
                "dispute_kind": "wrong_amount",
                "quote": "we agreed $300 this month, scope was reduced",
                "message_id": t6_reply_id,
                "confidence": 0.95,
            }],
        )
        inv = await self._get_ref("T6-006")
        self._check("T6 status disputed", inv["status"] == "disputed", inv["status"])
        t6_corr_id = self._next_msg_id("t6-corr")
        await self._ingest_sent(
            tag="t6-corr",
            subject="Re: Invoice #T6-006",
            body="You're right — corrected: $300, due Jul 20.",
            amount=300,
            due_date="2026-07-20",
            when=jul(7),
            thread_id=t6_thread,
        )
        inv = await self._get_ref("T6-006")
        self._check("T6 corrected amount", float(inv["amount"]) == 300, inv["amount"])
        self._check("T6 back to invoiced", inv["status"] == "invoiced", inv["status"])
        self._check("T6 no duplicate", await self.db.invoices.count_documents({
            "user_id": self.user_id,
            "invoice_ref_normalized": "T6-006",
        }) == 1)

        # --- T7: partial payment + implicit promise ---
        t7_thread = self._next_thread("t7")
        await self._ingest_sent(
            tag="t7",
            subject="Invoice #T7-007",
            body="Project phase 1: $2,000. Due Jul 18, 2026.",
            amount=2000,
            due_date="2026-07-18",
            when=jul(6),
            thread_id=t7_thread,
        )
        t7_reply_id = self._next_msg_id("t7-reply")
        await self._apply_reply(
            tag="t7-reply",
            thread_id=t7_thread,
            subject="Re: Invoice #T7-007",
            body="Sent $1,200 today, ref TXN55009. Rest coming next week.",
            when=jul(7),
            events=[
                {
                    "type": "partial_payment",
                    "invoice_ref": "T7-007",
                    "amount": 1200,
                    "reference": "TXN55009",
                    "quote": "Sent $1,200 today, ref TXN55009.",
                    "message_id": t7_reply_id,
                    "confidence": 0.95,
                },
                {
                    "type": "promise",
                    "invoice_ref": "T7-007",
                    "date": None,
                    "quote": "Rest coming next week.",
                    "message_id": t7_reply_id,
                    "confidence": 0.95,
                },
            ],
        )
        inv = await self._get_ref("T7-007")
        self._check("T7 partially_paid", inv["status"] == "partially_paid", inv["status"])
        self._check("T7 balance 800", float(inv["balance_remaining"]) == 800, inv["balance_remaining"])
        self._check("T7 promise date set", bool(inv.get("promise_date")))
        ev = await self.db.invoice_events.find_one({
            "user_id": self.user_id,
            "invoice_id": inv["_id"],
            "action": "partial_payment",
        })
        self._check("T7 TXN logged", (ev or {}).get("meta", {}).get("reference") == "TXN55009")

        # --- T8: claim paid, no reference ---
        t8_thread = self._next_thread("t8")
        await self._ingest_sent(
            tag="t8",
            subject="Invoice #T8-008",
            body="Copy edits: $250. Due Jul 10, 2026.",
            amount=250,
            due_date="2026-07-10",
            when=jul(6),
            thread_id=t8_thread,
        )
        await self._apply_reply(
            tag="t8-reply",
            thread_id=t8_thread,
            subject="Re: Invoice #T8-008",
            body="Paid this already.",
            when=jul(7),
            events=[{
                "type": "payment_claimed",
                "invoice_ref": "T8-008",
                "quote": "Paid this already.",
                "message_id": self._next_msg_id("t8-reply"),
                "confidence": 0.95,
            }],
        )
        inv = await self._get_ref("T8-008")
        self._check("T8 paid_unconfirmed not paid", inv["status"] == "paid_unconfirmed", inv["status"])

        # --- T9: same-domain second contact ---
        t9_thread = self._next_thread("t9")
        await self._ingest_sent(
            tag="t9",
            subject="Invoice #T9-009",
            body="Retainer: $900. Due Jul 22, 2026.",
            amount=900,
            due_date="2026-07-22",
            when=jul(6),
            thread_id=t9_thread,
        )
        t9_status_before = (await self._get_ref("T9-009"))["status"]
        t9_accounts_msg_id = self._next_msg_id("t9-accounts")
        await self._apply_reply(
            tag="t9-accounts",
            thread_id=self._next_thread("t9-accounts"),
            subject="T9-009 approval",
            body="Hi, this is accounts — approving T9-009 for payment this week.",
            when=jul(7),
            from_email=ACCOUNTS_EMAIL,
            events=[{
                "type": "approved",
                "invoice_ref": "T9-009",
                "quote": "approving T9-009 for payment this week.",
                "message_id": t9_accounts_msg_id,
                "confidence": 0.95,
            }],
        )
        client_keys = set()
        async for row in self.db.invoices.find({"user_id": self.user_id}, {"client_identity_key": 1}):
            client_keys.add(row.get("client_identity_key"))
        self._check("T9 single client entity", len(client_keys) == 1, str(client_keys))
        inv = await self._get_ref("T9-009")
        self._check("T9 status unchanged", inv["status"] == t9_status_before, inv["status"])
        approved_ev = await self.db.invoice_events.find_one({
            "user_id": self.user_id,
            "invoice_id": inv["_id"],
            "action": "payment_approved",
        })
        self._check("T9 approved event logged", approved_ev is not None)

        # --- T10: no due date ---
        await self._ingest_sent(
            tag="t10",
            subject="Invoice for July",
            body="July work — $450, let me know when you can process this.",
            amount=450,
            due_date=None,
            when=jul(7),
        )
        inv = await self.db.invoices.find_one({
            "user_id": self.user_id,
            "amount": 450,
            "due_date": None,
        })
        self._check("T10 tracked without due date", inv is not None)
        self._check("T10 due date empty", not inv.get("due_date"))
        state = await self.db.gmail_sync_state.find_one({"user_id": self.user_id}) or {}
        prompts = state.get("pending_due_date_prompts") or []
        self._check("T10 due date prompt queued", any(p.get("invoice_id") == str(inv["_id"]) for p in prompts))

        # --- T11: write-off manual only (no auto write-off anywhere) ---
        auto_wo = await self.db.invoices.count_documents({
            "user_id": self.user_id,
            "status": "written_off",
        })
        self._check("T11 no auto write-off before manual", auto_wo == 0)
        await self._manual_write_off("T2-002")
        inv = await self._get_ref("T2-002")
        self._check("T11 written_off after manual", inv["status"] == "written_off", inv["status"])

        # --- T12: mark paid manual ---
        await self._manual_mark_paid("T1-001")
        inv = await self._get_ref("T1-001")
        self._check("T12 mark paid instant", inv["status"] == "paid", inv["status"])

        # --- T13: mixed topic, payment with ref ---
        t13_thread = self._next_thread("t13")
        await self._ingest_sent(
            tag="t13",
            subject="Invoice #T13-013",
            body="Homepage revamp: $1,100. Due Jul 30, 2026.",
            amount=1100,
            due_date="2026-07-30",
            when=jul(7),
            thread_id=t13_thread,
        )
        await self._apply_reply(
            tag="t13-reply",
            thread_id=t13_thread,
            subject="Re: Invoice #T13-013",
            body=(
                "Loved the new hero section, looks great! One note on the footer spacing. "
                "Also — paid the invoice today, ref TXN99871."
            ),
            when=jul(7),
            events=[{
                "type": "payment_claimed",
                "invoice_ref": "T13-013",
                "reference": "TXN99871",
                "quote": "paid the invoice today, ref TXN99871.",
                "message_id": self._next_msg_id("t13-reply"),
                "confidence": 0.95,
            }],
        )
        inv = await self._get_ref("T13-013")
        self._check("T13 paid_unconfirmed with ref", inv["status"] == "paid_unconfirmed", inv["status"])
        ev = await self.db.invoice_events.find_one({
            "user_id": self.user_id,
            "invoice_id": inv["_id"],
            "action": "payment_claim",
        })
        self._check("T13 ref extracted", (ev or {}).get("meta", {}).get("reference") == "TXN99871")

        # --- T14: quoted history trap ---
        t14_thread = self._next_thread("t14")
        t1 = await self._get_ref("T1-001")
        quoted = (
            "Noted, thanks.\n\n"
            "On Mon, Jul 6, 2026 tdarshan336@gmail.com wrote:\n"
            "> Hi, invoice for June work attached details below.\n"
            "> Amount: $1,000. Due: Jul 15, 2026."
        )
        before = await self._count_invoices()
        fake_ai_invoices = [{
            "invoice_number": "T1-001",
            "amount": 1000,
            "currency": "USD",
            "due_date": "2026-07-15",
            "status_suggestion": "INVOICED",
            "anchor_message_id": self._next_msg_id("t14-fake"),
        }]
        t14_msg = self._msg(
            tag="t14",
            thread_id=t14_thread,
            from_email=CLIENT_EMAIL,
            to_email=self.my_email,
            subject="Re: Invoice #T1-001",
            body=quoted,
            when=jul(7),
        )
        collapsed = collapse_ai_invoices(fake_ai_invoices, {t14_msg["id"]: t14_msg})
        await self._apply_reply(
            tag="t14",
            thread_id=t14_thread,
            subject="Re: Invoice #T1-001",
            body=quoted,
            when=jul(7),
            extra_invoices=collapsed,
            events=[],
        )
        after = await self._count_invoices()
        self._check("T14 no phantom duplicate", after == before)

        # --- Stats / digest sanity ---
        await self._validate_stats()
        return all(ok for _, ok, _ in self.results)

    async def _validate_stats(self) -> None:
        rows = []
        async for doc in self.db.invoices.find({"user_id": self.user_id}):
            if doc.get("balance_remaining") is None:
                doc["balance_remaining"] = float(doc.get("amount") or 0)
            rows.append(doc)

        agg = compute_open_totals(rows, OPEN_INVOICE_STATUSES)
        open_rows = [r for r in rows if r.get("status") in _OPEN]
        manual_open = round(sum(float(r.get("balance_remaining") or 0) for r in open_rows), 2)
        computed_open = round(sum(agg["totals_by_currency"].values()), 2)
        self._check("Stats open total matches ledger", abs(manual_open - computed_open) < 0.01,
                    f"manual={manual_open} computed={computed_open}")

        sections = await collect_today_sections(self.db, self.user_id)
        totals = digest_totals(sections)
        bucket_ids = set()
        for key in ("due_overdue", "broken_promises", "needs_reply", "confirm_prompts", "watching", "resolved"):
            for inv in sections.get(key) or []:
                bucket_ids.add(str(inv["_id"]))

        paid_unconfirmed = {str(r["_id"]) for r in rows if r.get("status") == "paid_unconfirmed"}
        for pid in paid_unconfirmed:
            self._check(
                f"Digest confirm bucket has {pid[:8]}",
                pid in bucket_ids or any(str(i.get("_id")) == pid for i in sections.get("confirm_prompts") or []),
            )

        self._check("Digest totals struct ok", "watching" in totals and "confirm_prompts" in totals)
        print(f"\n  Stats: {len(open_rows)} open invoices, ${computed_open:,.2f} outstanding, "
              f"{agg['client_count']} client(s)")
        print(f"  Digest: {totals['due_overdue']} past due, {totals['broken_promises']} broken, "
              f"{totals['confirm_prompts']} confirm, {totals['watching']} watching")


async def ensure_user(db, email: str) -> ObjectId:
    user = await db.users.find_one({"email": email})
    if user:
        return user["_id"]
    from server import hash_password  # noqa: WPS433

    doc = {
        "email": email,
        "password_hash": hash_password("SelfTest!Scotive1"),
        "name": "Pipeline Self-Test",
        "role": "user",
        "created_at": datetime.now(timezone.utc),
    }
    res = await db.users.insert_one(doc)
    print(f"Created test user {email} (password: SelfTest!Scotive1)")
    return res.inserted_id


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run Scotive pipeline self-test T1–T14")
    parser.add_argument("--keep-data", action="store_true", help="Do not wipe workspace before/after")
    args = parser.parse_args()

    import os

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "scotive")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    user_id = await ensure_user(db, USER_EMAIL)
    if not args.keep_data:
        wiped = await wipe_user_workspace(db, user_id)
        print(f"Wiped workspace: {wiped or 'already empty'}")

    await db.gmail_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"curation_complete": True, "client_identities": [CLIENT_EMAIL]}},
        upsert=True,
    )

    print(f"\nScotive pipeline self-test — {USER_EMAIL} → {CLIENT_EMAIL}\n")
    runner = SelfTest(db, user_id)
    ok = await runner.run_all()

    print("\n--- Pass/fail sheet ---")
    print("| # | Test | Pass? |")
    print("|---|---|---|")
    for name, passed, _ in runner.results:
        num = name.split()[0] if name.startswith("T") else name
        short = name.split(" ", 1)[-1][:40]
        print(f"| {num} | {short} | {'✓' if passed else '✗'} |")

    if not args.keep_data:
        # Keep data when tests pass so user can inspect UI; wipe only on failure optional
        pass

    client.close()
    if ok:
        print("\nAll pipeline self-tests PASSED.")
        print(f"Log in as {USER_EMAIL} to inspect the UI (data left in place).")
        return 0
    print("\nSome tests FAILED — see details above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
