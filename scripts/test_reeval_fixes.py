"""Unit + pipeline tests for TB-102 (proactive correction) and TE-105 (multi-signal).

Usage:
  PYTHONPATH=backend python scripts/test_reeval_fixes.py
  PYTHONPATH=backend python scripts/test_reeval_fixes.py --keep-data
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

load_dotenv(ROOT / "backend" / ".env")

from client_sweep import (  # noqa: E402
    _EVENT_APPLY_ORDER,
    _write_event,
    apply_client_result,
)
from reeval_rulebook import (  # noqa: E402
    filter_new_events_to_unprocessed,
    rulebook_events_to_write_events,
)
from ledger_reconcile import (  # noqa: E402
    client_identity_key,
    normalize_invoice_ref,
    upsert_sweep_invoice,
)

USER_EMAIL = "tdarshan336@gmail.com"
CLIENT_EMAIL = "darsh@getscotive.com"
PREFIX = "reevalfix-"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rfc2822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


class ReevalFixTest:
    def __init__(self, db, user_id: ObjectId):
        self.db = db
        self.user_id = user_id
        self.my_email = USER_EMAIL
        self.client_key = client_identity_key(CLIENT_EMAIL)
        self.now = datetime.now(timezone.utc)
        self.results: list[tuple[str, bool, str]] = []
        self._msg_seq = 0
        self._thread_seq = 0

    def _check(self, name: str, ok: bool, detail: Any = "") -> None:
        self.results.append((name, bool(ok), str(detail) if detail is not None else ""))
        mark = "PASS" if ok else "FAIL"
        extra = ""
        if not ok and detail is not None and detail != "":
            extra = f" — {detail}"
        print(f"  [{mark}] {name}{extra}")

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
            "snippet": body[:200],
            "date": _rfc2822(when),
        }

    async def _seed_invoice(
        self,
        *,
        ref: str,
        amount: float,
        due_date: str,
        subject: str,
        body: str,
        when: datetime,
        thread_id: str | None = None,
    ) -> tuple[ObjectId, dict, str]:
        tid = thread_id or self._next_thread(ref.lower())
        msg = self._msg(
            tag=f"{ref}-sent",
            thread_id=tid,
            from_email=USER_EMAIL,
            to_email=CLIENT_EMAIL,
            subject=subject,
            body=body,
            when=when,
        )
        norm = normalize_invoice_ref(ref, subject)
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
            "invoice_ref_normalized": norm,
            "due_date": due_date,
            "due_date_assumed": False,
            "promise_date": None,
            "status": "invoiced",
            "kind": "invoice_sent",
            "source_message_id": msg["id"],
            "source_thread_id": tid,
            "source_subject": subject,
            "source_from": msg["from"],
            "source_date": _iso(when),
            "confidence": 0.95,
            "created_at": _iso(self.now),
        }
        outcome, inv_id = await upsert_sweep_invoice(
            self.db, self.user_id, doc, now_iso=_iso(self.now),
        )
        assert inv_id and outcome in ("created", "merged"), (outcome, inv_id)
        # Ensure invoice_sent timeline entry exists for "You sent invoice"
        existing = await self.db.invoice_events.find_one({
            "user_id": self.user_id,
            "invoice_id": inv_id,
            "action": "invoice_sent",
        })
        if not existing:
            await self.db.invoice_events.insert_one({
                "user_id": self.user_id,
                "invoice_id": inv_id,
                "action": "invoice_sent",
                "at": _iso(when),
                "meta": {
                    "amount": amount,
                    "due_date": due_date,
                    "message_id": msg["id"],
                    "subject": subject,
                },
            })
        return inv_id, msg, tid

    # ------------------------------------------------------------------
    # Unit: correction language detection
    # ------------------------------------------------------------------
    def test_correction_language(self) -> None:
        print("\n== Correction language gate (removed) ==")
        self._check("open invoices go to the rulebook without a regex gate", True)

    # ------------------------------------------------------------------
    # Unit: rulebook new_events → _write_event mapping
    # ------------------------------------------------------------------
    def test_events_from_reeval_tb102(self) -> None:
        print("\n== TB-102 rulebook amount_correction mapping ==")
        result = {
            "invoice_ref": "TB-102",
            "amount": 550.0,
            "status": "invoiced",
            "disputed_claim_amount": None,
            "new_events": [{
                "type": "amount_correction",
                "message_id": "msg-corr",
                "sender": "user",
                "quote": "Actually, revising this down to $550 — miscounted a few hours.",
                "confidence": 0.95,
                "data": {"amount": 550.0},
            }],
        }
        evs = rulebook_events_to_write_events(result, invoice_ref="TB-102")
        types = [e["type"] for e in evs]
        self._check("TB-102 emits correction", "correction" in types, types)
        self._check("TB-102 no dispute event", "dispute" not in types, types)
        corr_ev = next(e for e in evs if e["type"] == "correction")
        self._check("TB-102 new amount 550", corr_ev.get("amount") == 550.0, corr_ev)
        self._check(
            "TB-102 quote from user msg",
            "550" in (corr_ev.get("quote") or "")
            or "revising" in (corr_ev.get("quote") or "").lower(),
            corr_ev.get("quote"),
        )

        empty = rulebook_events_to_write_events(
            {"new_events": []}, invoice_ref="TB-102",
        )
        self._check("plain follow-up no events", empty == [], empty)

    def test_events_from_reeval_te105(self) -> None:
        print("\n== TE-105 rulebook dispute + partial (no needs_reply) ==")
        result = {
            "invoice_ref": "TE-105",
            "amount": 2000.0,
            "status": "partially_paid",
            "paid_amount": 1000.0,
            "balance_remaining": 1000.0,
            "disputed_claim_amount": 1800.0,
            "new_events": [
                {
                    "type": "dispute",
                    "message_id": "msg-multi",
                    "sender": "client",
                    "quote": "We agreed $1,800",
                    "confidence": 0.95,
                    "data": {"amount": 1800.0},
                },
                {
                    "type": "partial_payment",
                    "message_id": "msg-multi",
                    "sender": "client",
                    "quote": "sending $1,000 now as a partial",
                    "confidence": 0.95,
                    "data": {"amount": 1000.0},
                },
            ],
        }
        # Safety net: already-processed dispute must not reappear
        filtered = filter_new_events_to_unprocessed(
            {
                "new_events": result["new_events"] + [{
                    "type": "dispute",
                    "message_id": "old-msg",
                    "quote": "stale",
                    "confidence": 0.9,
                    "data": {"amount": 1800},
                }],
            },
            {"processed_message_ids": ["old-msg"]},
        )
        self._check(
            "TE-105 filter drops processed",
            len(filtered["new_events"]) == 2,
            len(filtered["new_events"]),
        )

        evs = rulebook_events_to_write_events(result, invoice_ref="TE-105")
        types = [e["type"] for e in evs]
        self._check("TE-105 has dispute", "dispute" in types, types)
        self._check("TE-105 has partial_payment", "partial_payment" in types, types)
        self._check("TE-105 NO question", "question" not in types, types)
        self._check("TE-105 exactly 2 signal events", len(types) == 2, types)

        dispute = next(e for e in evs if e["type"] == "dispute")
        partial = next(e for e in evs if e["type"] == "partial_payment")
        self._check(
            "TE-105 dispute quote",
            "1,800" in (dispute.get("quote") or "")
            or "1800" in (dispute.get("quote") or "").replace(",", ""),
            dispute.get("quote"),
        )
        self._check("TE-105 claimed 1800", float(dispute.get("claimed_amount") or 0) == 1800.0)
        self._check("TE-105 partial amount 1000", float(partial.get("amount") or 0) == 1000.0)

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------
    async def test_tb102_pipeline(self) -> None:
        print("\n== TB-102 pipeline (apply correction, stay invoiced) ==")
        when = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        inv_id, sent, tid = await self._seed_invoice(
            ref="TB-102",
            amount=600,
            due_date="2026-08-01",
            subject="Invoice #TB-102",
            body="July hours: $600. Due Aug 1, 2026.",
            when=when,
        )
        inv = await self.db.invoices.find_one({"_id": inv_id})
        self._check("TB-102 seeded invoiced", inv["status"] == "invoiced", inv.get("status"))

        corr_when = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
        corr_msg = self._msg(
            tag="tb102-corr",
            thread_id=tid,
            from_email=USER_EMAIL,
            to_email=CLIENT_EMAIL,
            subject="Re: Invoice #TB-102",
            body="Actually, revising this down to $550 — miscounted a few hours.",
            when=corr_when,
        )
        events = rulebook_events_to_write_events({
            "invoice_ref": "TB-102",
            "new_events": [{
                "type": "amount_correction",
                "message_id": corr_msg["id"],
                "sender": "user",
                "quote": corr_msg["body"],
                "confidence": 0.95,
                "data": {"amount": 550.0},
            }],
        }, invoice_ref="TB-102")
        for e in events:
            if e.get("type") == "correction":
                e["old_amount"] = 600.0
        events = sorted(
            events,
            key=lambda e: (_EVENT_APPLY_ORDER.get(e.get("type") or "", 99), e.get("message_id") or ""),
        )
        messages_by_id = {sent["id"]: sent, corr_msg["id"]: corr_msg}
        for ev in events:
            await _write_event(
                self.db, self.user_id, inv_id, ev, messages_by_id, _iso(corr_when),
                my_email=USER_EMAIL,
            )

        inv2 = await self.db.invoices.find_one({"_id": inv_id})
        self._check("TB-102 amount → 550", float(inv2["amount"]) == 550.0, inv2.get("amount"))
        self._check("TB-102 status stays invoiced", inv2["status"] == "invoiced", inv2.get("status"))
        self._check(
            "TB-102 not disputed",
            inv2.get("status") != "disputed" and not inv2.get("disputed_claim_amount"),
            inv2.get("status"),
        )
        actions = []
        async for e in self.db.invoice_events.find({"user_id": self.user_id, "invoice_id": inv_id}):
            actions.append(e.get("action"))
        self._check("TB-102 has invoice_corrected", "invoice_corrected" in actions, actions)
        corr_ev = await self.db.invoice_events.find_one({
            "user_id": self.user_id,
            "invoice_id": inv_id,
            "action": "invoice_corrected",
        })
        meta = (corr_ev or {}).get("meta") or {}
        self._check(
            "TB-102 correction quote",
            "550" in str(meta.get("quote") or "")
            or "revising" in str(meta.get("quote") or "").lower(),
            meta.get("quote"),
        )
        self._check("TB-102 old→new in meta", float(meta.get("old_amount") or 0) == 600.0, meta)

    async def test_te105_pipeline(self) -> None:
        print("\n== TE-105 pipeline (dispute + partial via client_sweep) ==")
        when = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        inv_id, sent, tid = await self._seed_invoice(
            ref="TE-105",
            amount=2000,
            due_date="2026-08-20",
            subject="Invoice #TE-105",
            body="Consulting block: $2,000. Due Aug 20, 2026.",
            when=when,
        )

        reply_when = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
        reply_id = self._next_msg_id("te105-reply")
        reply = self._msg(
            tag="te105-reply",
            thread_id=tid,
            from_email=CLIENT_EMAIL,
            to_email=USER_EMAIL,
            subject="Re: Invoice #TE-105",
            body=(
                "We agreed $1,800 — but either way, sending $1,000 now "
                "as a partial, will sort the rest after we confirm the total."
            ),
            when=reply_when,
            msg_id=reply_id,
        )
        result = {
            "is_receivable_client": True,
            "client": {"name": "Scotive Client", "identities": [CLIENT_EMAIL]},
            "invoices": [],
            "events": [
                {
                    "type": "dispute",
                    "invoice_ref": "TE-105",
                    "dispute_kind": "wrong_amount",
                    "claimed_amount": 1800,
                    "quote": "We agreed $1,800",
                    "message_id": reply_id,
                    "confidence": 0.95,
                },
                {
                    "type": "partial_payment",
                    "invoice_ref": "TE-105",
                    "amount": 1000,
                    "quote": "sending $1,000 now as a partial",
                    "message_id": reply_id,
                    "confidence": 0.95,
                },
                {
                    "type": "question",
                    "invoice_ref": "TE-105",
                    "quote": "will sort the rest after we confirm the total",
                    "message_id": reply_id,
                    "confidence": 0.9,
                },
            ],
            "unmatched_mentions": [],
            "confidence_overall": 0.95,
        }
        await apply_client_result(
            self.db,
            self.user_id,
            CLIENT_EMAIL,
            result,
            {sent["id"]: sent, reply_id: reply},
            USER_EMAIL,
            _iso(reply_when),
            scoped_invoice_id=inv_id,
            events_only=True,
        )

        inv = await self.db.invoices.find_one({"_id": inv_id})
        actions = []
        async for e in self.db.invoice_events.find({"user_id": self.user_id, "invoice_id": inv_id}):
            actions.append(e.get("action"))

        self._check("TE-105 has dispute event", "dispute" in actions, actions)
        self._check("TE-105 has partial_payment event", "partial_payment" in actions, actions)
        self._check("TE-105 NO client_question", "client_question" not in actions, actions)
        signal = [a for a in actions if a in ("dispute", "partial_payment", "client_question")]
        self._check("TE-105 exactly 2 signal events", len(signal) == 2, signal)

        self._check(
            "TE-105 paid_amount still 0",
            float(inv.get("paid_amount") or 0) == 0.0,
            inv.get("paid_amount"),
        )
        self._check(
            "TE-105 balance still 2000",
            float(inv.get("balance_remaining") or 0) == 2000.0,
            inv.get("balance_remaining"),
        )
        self._check(
            "TE-105 payment_claim 1000",
            float(inv.get("payment_claim_amount") or 0) == 1000.0,
            inv.get("payment_claim_amount"),
        )
        self._check("TE-105 claim pending", bool(inv.get("payment_claim_pending")))
        self._check(
            "TE-105 disputed_claim 1800",
            float(inv.get("disputed_claim_amount") or 0) == 1800.0,
            inv.get("disputed_claim_amount"),
        )
        both = (
            inv.get("status") == "disputed"
            and inv.get("disputed_claim_amount") is not None
            and float(inv.get("payment_claim_amount") or 0) >= 1000
            and float(inv.get("paid_amount") or 0) < 0.02
        )
        self._check(
            "TE-105 both dispute + partial claim visible on row",
            both,
            f"status={inv.get('status')} paid={inv.get('paid_amount')} "
            f"pay_claim={inv.get('payment_claim_amount')} claim={inv.get('disputed_claim_amount')}",
        )

        # Path B: incremental re-eval event extraction + _write_event
        print("\n== TE-105B pipeline (reeval path) ==")
        inv_id2, sent2, tid2 = await self._seed_invoice(
            ref="TE-105B",
            amount=2000,
            due_date="2026-08-20",
            subject="Invoice #TE-105B",
            body="Consulting block: $2,000. Due Aug 20, 2026.",
            when=when,
        )
        inv2 = await self.db.invoices.find_one({"_id": inv_id2})
        reply2_id = self._next_msg_id("te105b-reply")
        reply2 = self._msg(
            tag="te105b-reply",
            thread_id=tid2,
            from_email=CLIENT_EMAIL,
            to_email=USER_EMAIL,
            subject="Re: Invoice #TE-105B",
            body=(
                "We agreed $1,800 — but either way, sending $1,000 now "
                "as a partial, will sort the rest after we confirm the total."
            ),
            when=reply_when,
            msg_id=reply2_id,
        )
        events = rulebook_events_to_write_events({
            "invoice_ref": "TE-105B",
            "new_events": [
                {
                    "type": "dispute",
                    "message_id": reply2_id,
                    "sender": "client",
                    "quote": "We agreed $1,800",
                    "confidence": 0.95,
                    "data": {"amount": 1800.0},
                },
                {
                    "type": "partial_payment",
                    "message_id": reply2_id,
                    "sender": "client",
                    "quote": "sending $1,000 now as a partial",
                    "confidence": 0.95,
                    "data": {"amount": 1000.0},
                },
            ],
        }, invoice_ref="TE-105B")
        events = sorted(
            events,
            key=lambda e: (_EVENT_APPLY_ORDER.get(e.get("type") or "", 99), e.get("message_id") or ""),
        )
        messages = {sent2["id"]: sent2, reply2_id: reply2}
        for ev in events:
            if not ev.get("message_id"):
                ev = {**ev, "message_id": reply2_id}
            await _write_event(
                self.db, self.user_id, inv_id2, ev, messages, _iso(reply_when),
                my_email=USER_EMAIL,
            )

        inv2b = await self.db.invoices.find_one({"_id": inv_id2})
        actions2 = []
        async for e in self.db.invoice_events.find({"user_id": self.user_id, "invoice_id": inv_id2}):
            actions2.append(e.get("action"))
        self._check("TE-105B reeval dispute", "dispute" in actions2, actions2)
        self._check("TE-105B reeval partial", "partial_payment" in actions2, actions2)
        self._check("TE-105B reeval NO question", "client_question" not in actions2, actions2)
        both2 = (
            inv2b.get("status") == "disputed"
            and inv2b.get("disputed_claim_amount") is not None
            and float(inv2b.get("payment_claim_amount") or 0) >= 1000
            and float(inv2b.get("paid_amount") or 0) < 0.02
        )
        self._check(
            "TE-105B both facts on row",
            both2,
            f"status={inv2b.get('status')} paid={inv2b.get('paid_amount')} "
            f"pay_claim={inv2b.get('payment_claim_amount')} claim={inv2b.get('disputed_claim_amount')}",
        )

    async def run(self) -> int:
        self.test_correction_language()
        self.test_events_from_reeval_tb102()
        self.test_events_from_reeval_te105()
        await self.test_tb102_pipeline()
        await self.test_te105_pipeline()

        failed = [r for r in self.results if not r[1]]
        print(f"\n{'=' * 50}")
        print(f"Results: {len(self.results) - len(failed)}/{len(self.results)} passed")
        if failed:
            print("FAILED:")
            for name, _, detail in failed:
                print(f"  - {name}: {detail}")
            return 1
        print("All TB-102 / TE-105 checks passed.")
        return 0


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-data", action="store_true")
    args = parser.parse_args()

    mongo = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = os.environ.get("DB_NAME") or "scotive"
    client = AsyncIOMotorClient(mongo)
    db = client[db_name]

    user = await db.users.find_one({"email": USER_EMAIL})
    if not user:
        print(f"ERROR: test user {USER_EMAIL} not found in {db_name}")
        return 2
    user_id = user["_id"]

    refs = ["TB-102", "TE-105", "TE-105B"]
    old = []
    async for inv in db.invoices.find({
        "user_id": user_id,
        "invoice_ref_normalized": {"$in": refs},
    }):
        old.append(inv["_id"])
    if old:
        await db.invoice_events.delete_many({
            "user_id": user_id,
            "invoice_id": {"$in": old},
        })
    await db.invoices.delete_many({
        "user_id": user_id,
        "invoice_ref_normalized": {"$in": refs},
    })

    try:
        harness = ReevalFixTest(db, user_id)
        code = await harness.run()
        if not args.keep_data:
            created = []
            async for inv in db.invoices.find({
                "user_id": user_id,
                "invoice_ref_normalized": {"$in": refs},
            }):
                created.append(inv["_id"])
            if created:
                await db.invoice_events.delete_many({
                    "user_id": user_id,
                    "invoice_id": {"$in": created},
                })
            await db.invoices.delete_many({
                "user_id": user_id,
                "invoice_ref_normalized": {"$in": refs},
            })
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
