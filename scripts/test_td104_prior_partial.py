"""TD-104 multi-cycle dispute + prior-partial seed tests.

Usage:
  PYTHONPATH=backend python scripts/test_td104_prior_partial.py
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

from client_sweep import _EVENT_APPLY_ORDER, _write_event, apply_client_result  # noqa: E402
from incremental_sync import (  # noqa: E402
    _is_amount_correction,
)
from reeval_rulebook import rulebook_events_to_write_events  # noqa: E402
from ledger_reconcile import (  # noqa: E402
    client_identity_key,
    normalize_invoice_ref,
    upsert_sweep_invoice,
)
from seed_ai import infer_prior_partial_from_text, invoices_to_candidates  # noqa: E402
from seed_scan import build_ledger_invoice_from_candidate  # noqa: E402

USER_EMAIL = "tdarshan336@gmail.com"
CLIENT_EMAIL = "darsh@getscotive.com"
PREFIX = "td104fix-"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _rfc2822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


class Harness:
    def __init__(self, db, user_id: ObjectId):
        self.db = db
        self.user_id = user_id
        self.client_key = client_identity_key(CLIENT_EMAIL)
        self.now = datetime.now(timezone.utc)
        self.results: list[tuple[str, bool, str]] = []
        self._msg_seq = 0
        self._thread_seq = 0

    def _check(self, name: str, ok: bool, detail: Any = "") -> None:
        self.results.append((name, bool(ok), str(detail) if detail is not None else ""))
        mark = "PASS" if ok else "FAIL"
        extra = f" — {detail}" if (not ok and detail not in (None, "")) else ""
        print(f"  [{mark}] {name}{extra}")

    def _next_msg_id(self, tag: str) -> str:
        self._msg_seq += 1
        return f"{PREFIX}{tag}-{self._msg_seq}"

    def _next_thread(self, tag: str) -> str:
        self._thread_seq += 1
        return f"{PREFIX}thread-{tag}-{self._thread_seq}"

    def _msg(self, *, tag, thread_id, from_email, to_email, subject, body, when, msg_id=None):
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

    async def _seed(self, *, ref, amount, due, subject, body, when, thread_id=None,
                    paid=0.0, balance=None, status="invoiced", amount_original=None):
        tid = thread_id or self._next_thread(ref.lower())
        msg = self._msg(
            tag=f"{ref}-sent", thread_id=tid, from_email=USER_EMAIL,
            to_email=CLIENT_EMAIL, subject=subject, body=body, when=when,
        )
        norm = normalize_invoice_ref(ref, subject)
        bal = balance if balance is not None else amount
        doc = {
            "user_id": self.user_id,
            "counterparty_email": CLIENT_EMAIL,
            "counterparty_name": "Scotive Client",
            "client_identity_key": self.client_key,
            "amount": amount,
            "balance_remaining": bal,
            "paid_amount": paid,
            "currency": "USD",
            "invoice_ref": ref,
            "invoice_ref_normalized": norm,
            "due_date": due,
            "due_date_assumed": False,
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
        if amount_original is not None:
            doc["amount_original"] = amount_original
        outcome, inv_id = await upsert_sweep_invoice(
            self.db, self.user_id, doc, now_iso=_iso(self.now),
        )
        assert inv_id and outcome in ("created", "merged"), (outcome, inv_id)
        await self.db.invoice_events.insert_one({
            "user_id": self.user_id,
            "invoice_id": inv_id,
            "action": "invoice_sent",
            "at": _iso(when),
            "meta": {"amount": amount, "message_id": msg["id"]},
        })
        return inv_id, msg, tid

    async def _apply_events(self, inv_id, inv, events, messages, when):
        events = sorted(
            events,
            key=lambda e: (_EVENT_APPLY_ORDER.get(e.get("type") or "", 99), e.get("message_id") or ""),
        )
        for ev in events:
            await _write_event(
                self.db, self.user_id, inv_id, ev, messages, _iso(when),
                my_email=USER_EMAIL,
            )
        return await self.db.invoices.find_one({"_id": inv_id})

    async def _timeline_actions(self, inv_id) -> list[str]:
        out = []
        async for e in self.db.invoice_events.find(
            {"user_id": self.user_id, "invoice_id": inv_id},
        ).sort("at", 1):
            out.append(e.get("action"))
        return out

    # ------------------------------------------------------------------
    def test_correction_phrases(self):
        print("\n== Correction / acceptance language ==")
        cases = [
            ("Fair, adjusting to $1,000.", True),
            ("Confirmed, $950 it is.", True),
            ("Agreed — $950.", True),
            ("Reminder: $1,000 still due.", False),
        ]
        for body, expect in cases:
            msg = {"subject": "Re:", "body": body, "from": USER_EMAIL}
            got = _is_amount_correction(msg)
            self._check(f"correction? {body!r}", got == expect, f"got={got}")

    def test_prior_partial_heuristic(self):
        print("\n== Prior-partial heuristic (Issue 2) ==")
        body = (
            "hiii, just circling back on payment for the TikTok series — total was "
            "$1,200, half upfront which I got, so $600 left whenever's convenient on "
            "your end 🙏 venmo or paypal both work — xx Reese"
        )
        prior = infer_prior_partial_from_text(body, amount=1200)
        self._check("prior inferred", prior is not None, prior)
        if prior:
            self._check("amount_original 1200", prior["amount_original"] == 1200.0, prior)
            self._check("paid 600", prior["paid_amount"] == 600.0, prior)
            self._check("balance 600", prior["balance_remaining"] == 600.0, prior)

        # invoices_to_candidates path (AI returns only total)
        msg = {
            "id": "m1",
            "thread_id": "t1",
            "from": USER_EMAIL,
            "to": CLIENT_EMAIL,
            "subject": "TikTok series payment",
            "body": body,
            "snippet": body[:120],
            "date": _rfc2822(datetime(2026, 7, 1, tzinfo=timezone.utc)),
        }
        result = {
            "client_name": "Reese Client",
            "invoices": [{
                "message_id": "m1",
                "invoice_number": None,
                "amount": 1200,
                "currency": "USD",
                "confidence": 0.95,
                "enriched_status": "invoiced",
                "paid_amount": None,
                "balance_remaining": None,
            }],
        }
        cands = invoices_to_candidates(
            CLIENT_EMAIL,
            result,
            {msg["id"]: msg},
            user_id=ObjectId(),
            job_id="j",
            now_iso=_iso(self.now),
            my_email=USER_EMAIL,
            confidence_min=0.5,
        )
        self._check("candidate produced", len(cands) == 1, len(cands))
        if cands:
            c = cands[0]
            self._check("cand amount 1200", float(c["amount"]) == 1200.0, c.get("amount"))
            self._check("cand paid 600", float(c.get("paid_amount") or 0) == 600.0, c.get("paid_amount"))
            self._check("cand balance 600", float(c.get("balance_remaining") or 0) == 600.0, c.get("balance_remaining"))
            self._check("cand partially_paid", c.get("enriched_status") == "partially_paid", c.get("enriched_status"))
            self._check("cand amount_original", float(c.get("amount_original") or 0) == 1200.0, c.get("amount_original"))

            ledger = build_ledger_invoice_from_candidate(
                c,
                user_id=self.user_id,
                now_iso=_iso(self.now),
                today=datetime(2026, 7, 1, tzinfo=timezone.utc).date(),
            )
            self._check("ledger amount 1200", float(ledger["amount"]) == 1200.0)
            self._check("ledger paid 600", float(ledger["paid_amount"]) == 600.0)
            self._check("ledger balance 600", float(ledger["balance_remaining"]) == 600.0)
            self._check("ledger status partially_paid", ledger["status"] == "partially_paid", ledger["status"])
            self._check(
                "ledger amount_original 1200",
                float(ledger.get("amount_original") or 0) == 1200.0,
                ledger.get("amount_original"),
            )

    def test_td104_events_unit(self):
        print("\n== TD-104 multi-cycle events (unit) ==")
        # Message 4: second dispute claiming 950
        evs4 = rulebook_events_to_write_events({
            "new_events": [{
                "type": "dispute",
                "message_id": "dispute-2",
                "sender": "client",
                "quote": "Actually looking back, I think it was $950",
                "confidence": 0.95,
                "data": {"amount": 950.0},
            }],
        }, invoice_ref="TD-104")
        types4 = [e["type"] for e in evs4]
        self._check("msg4 emits dispute", types4 == ["dispute"], types4)
        self._check("msg4 claim 950", float(evs4[0].get("claimed_amount") or 0) == 950.0)
        self._check("msg4 has message_id", evs4[0].get("message_id") == "dispute-2")

        # Message 5: user accepts 950
        evs5 = rulebook_events_to_write_events({
            "new_events": [{
                "type": "amount_correction",
                "message_id": "corr-2",
                "sender": "user",
                "quote": "Confirmed, $950 it is.",
                "confidence": 0.95,
                "data": {"amount": 950.0},
            }],
        }, invoice_ref="TD-104")
        types5 = [e["type"] for e in evs5]
        self._check("msg5 emits correction", "correction" in types5, types5)
        corr_ev = next(e for e in evs5 if e["type"] == "correction")
        self._check("msg5 amount 950", corr_ev.get("amount") == 950.0)

        # Fresh dispute while already disputed
        evs_r = rulebook_events_to_write_events({
            "new_events": [{
                "type": "dispute",
                "message_id": "d2",
                "sender": "client",
                "quote": "I think it was $950",
                "confidence": 0.95,
                "data": {"amount": 950.0},
            }],
        }, invoice_ref="TD-104")
        self._check("refresh claim while disputed", [e["type"] for e in evs_r] == ["dispute"], evs_r)

    async def test_td104_pipeline(self):
        print("\n== TD-104 full pipeline (5 messages) ==")
        when1 = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        inv_id, sent, tid = await self._seed(
            ref="TD-104",
            amount=1200,
            due="2026-08-10",
            subject="Invoice #TD-104",
            body="Invoice #TD-104 — Design package: $1,200. Due Aug 10, 2026.",
            when=when1,
        )
        inv = await self.db.invoices.find_one({"_id": inv_id})
        self._check("msg1 $1200 INVOICED", inv["status"] == "invoiced" and float(inv["amount"]) == 1200)

        # Message 2 — first dispute
        when2 = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
        d1_id = self._next_msg_id("d1")
        d1 = self._msg(
            tag="d1", thread_id=tid, from_email=CLIENT_EMAIL, to_email=USER_EMAIL,
            subject="Re: Invoice #TD-104",
            body="We discussed $1,000 for this scope.",
            when=when2, msg_id=d1_id,
        )
        row2 = {
            "enriched_status": "disputed",
            "amount": 1200.0,
            "disputed_claim_amount": 1000.0,
            "dispute_kind": "wrong_amount",
            "confidence": 0.95,
            "status_evidence": "We discussed $1,000 for this scope.",
        }
        inv = await self._apply_events(
            inv_id, inv,
            rulebook_events_to_write_events({
                "new_events": [{
                    "type": "dispute",
                    "message_id": d1_id,
                    "sender": "client",
                    "quote": row2["status_evidence"],
                    "confidence": 0.95,
                    "data": {"amount": 1000.0},
                }],
            }, invoice_ref="TD-104"),
            {sent["id"]: sent, d1_id: d1}, when2,
        )
        self._check(
            "msg2 $1200 DISPUTED",
            inv["status"] == "disputed" and float(inv["amount"]) == 1200
            and float(inv.get("disputed_claim_amount") or 0) == 1000,
            f"status={inv.get('status')} amt={inv.get('amount')} claim={inv.get('disputed_claim_amount')}",
        )

        # Message 3 — first correction
        when3 = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
        c1 = self._msg(
            tag="c1", thread_id=tid, from_email=USER_EMAIL, to_email=CLIENT_EMAIL,
            subject="Re: Invoice #TD-104",
            body="Fair, adjusting to $1,000.",
            when=when3,
        )
        row3 = {
            "enriched_status": "invoiced",
            "amount": 1000.0,
            "confidence": 0.95,
            "status_evidence": "",
        }
        inv = await self._apply_events(
            inv_id, inv,
            rulebook_events_to_write_events({
                "new_events": [{
                    "type": "amount_correction",
                    "message_id": c1["id"],
                    "sender": "user",
                    "quote": c1["body"],
                    "confidence": 0.95,
                    "data": {"amount": 1000.0},
                }],
            }, invoice_ref="TD-104"),
            {sent["id"]: sent, d1_id: d1, c1["id"]: c1}, when3,
        )
        self._check(
            "msg3 $1000 INVOICED",
            inv["status"] == "invoiced" and float(inv["amount"]) == 1000
            and not inv.get("disputed_claim_amount"),
            f"status={inv.get('status')} amt={inv.get('amount')} claim={inv.get('disputed_claim_amount')}",
        )

        # Message 4 — SECOND dispute
        when4 = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
        d2_id = self._next_msg_id("d2")
        d2 = self._msg(
            tag="d2", thread_id=tid, from_email=CLIENT_EMAIL, to_email=USER_EMAIL,
            subject="Re: Invoice #TD-104",
            body="Actually looking back, I think it was $950 — can you double check?",
            when=when4, msg_id=d2_id,
        )
        row4 = {
            "enriched_status": "disputed",
            "amount": 1000.0,
            "disputed_claim_amount": 950.0,
            "dispute_kind": "wrong_amount",
            "confidence": 0.95,
            "status_evidence": "I think it was $950",
        }
        inv = await self._apply_events(
            inv_id, inv,
            rulebook_events_to_write_events({
                "new_events": [{
                    "type": "dispute",
                    "message_id": d2_id,
                    "sender": "client",
                    "quote": row4["status_evidence"],
                    "confidence": 0.95,
                    "data": {"amount": 950.0},
                }],
            }, invoice_ref="TD-104"),
            {sent["id"]: sent, d1_id: d1, c1["id"]: c1, d2_id: d2}, when4,
        )
        self._check(
            "msg4 $1000 DISPUTED (2nd cycle)",
            inv["status"] == "disputed" and float(inv["amount"]) == 1000
            and float(inv.get("disputed_claim_amount") or 0) == 950,
            f"status={inv.get('status')} amt={inv.get('amount')} claim={inv.get('disputed_claim_amount')}",
        )

        # Message 5 — second correction
        when5 = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
        c2 = self._msg(
            tag="c2", thread_id=tid, from_email=USER_EMAIL, to_email=CLIENT_EMAIL,
            subject="Re: Invoice #TD-104",
            body="Confirmed, $950 it is.",
            when=when5,
        )
        self._check("msg5 is amount correction", _is_amount_correction(c2))
        row5 = {
            "enriched_status": "invoiced",
            "amount": 950.0,
            "confidence": 0.95,
            "status_evidence": "",
        }
        inv = await self._apply_events(
            inv_id, inv,
            rulebook_events_to_write_events({
                "new_events": [{
                    "type": "amount_correction",
                    "message_id": c2["id"],
                    "sender": "user",
                    "quote": c2["body"],
                    "confidence": 0.95,
                    "data": {"amount": 950.0},
                }],
            }, invoice_ref="TD-104"),
            {sent["id"]: sent, d1_id: d1, c1["id"]: c1, d2_id: d2, c2["id"]: c2}, when5,
        )
        self._check(
            "msg5 $950 INVOICED (final)",
            inv["status"] == "invoiced" and float(inv["amount"]) == 950
            and not inv.get("disputed_claim_amount"),
            f"status={inv.get('status')} amt={inv.get('amount')} claim={inv.get('disputed_claim_amount')}",
        )

        actions = await self._timeline_actions(inv_id)
        disputes = [a for a in actions if a == "dispute"]
        corrections = [a for a in actions if a == "invoice_corrected"]
        self._check("timeline has 2 disputes", len(disputes) == 2, actions)
        self._check("timeline has 2 corrections", len(corrections) == 2, actions)
        # Order: invoice_sent, dispute, correction, dispute, correction
        signal = [a for a in actions if a in ("dispute", "invoice_corrected", "invoice_sent")]
        self._check(
            "timeline order dispute→corr→dispute→corr",
            signal == [
                "invoice_sent", "dispute", "invoice_corrected",
                "dispute", "invoice_corrected",
            ],
            signal,
        )

    async def test_prior_partial_pipeline(self):
        print("\n== Prior-partial pipeline + payment claim on remaining ==")
        when1 = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        body = (
            "hiii, just circling back on payment for the TikTok series — total was "
            "$1,200, half upfront which I got, so $600 left whenever's convenient on "
            "your end 🙏 venmo or paypal both work — xx Reese"
        )
        # Seed via build_ledger path (what confirm/sync writes)
        msg = self._msg(
            tag="pp-sent", thread_id=self._next_thread("pp"),
            from_email=USER_EMAIL, to_email=CLIENT_EMAIL,
            subject="TikTok series payment", body=body, when=when1,
        )
        prior = infer_prior_partial_from_text(body, amount=1200)
        assert prior
        cand = {
            "counterparty_email": CLIENT_EMAIL,
            "counterparty_name": "Reese",
            "client_identity_key": self.client_key,
            "amount": prior["amount_original"],
            "amount_original": prior["amount_original"],
            "paid_amount": prior["paid_amount"],
            "balance_remaining": prior["balance_remaining"],
            "currency": "USD",
            "invoice_ref": "PP-600",
            "invoice_ref_normalized": "PP-600",
            "enriched_status": "partially_paid",
            "message_id": msg["id"],
            "source_thread_id": msg["thread_id"],
            "source_subject": msg["subject"],
            "source_from": msg["from"],
            "source_date": _iso(when1),
            "status_evidence": "half upfront which I got, so $600 left",
            "confidence": 0.95,
            "body": body,
        }
        doc = build_ledger_invoice_from_candidate(
            cand,
            user_id=self.user_id,
            now_iso=_iso(when1),
            today=when1.date(),
        )
        outcome, inv_id = await upsert_sweep_invoice(
            self.db, self.user_id, doc, now_iso=_iso(when1),
        )
        inv = await self.db.invoices.find_one({"_id": inv_id})
        self._check("seed amount_original 1200", float(inv.get("amount_original") or inv["amount"]) == 1200)
        self._check("seed amount 1200", float(inv["amount"]) == 1200)
        self._check("seed paid 600", float(inv["paid_amount"]) == 600)
        self._check("seed balance 600", float(inv["balance_remaining"]) == 600)
        self._check("seed partially_paid", inv["status"] == "partially_paid", inv["status"])

        # Message 2 — client pays the remaining $600
        when2 = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
        reply_id = self._next_msg_id("pp-reply")
        reply = self._msg(
            tag="pp-reply", thread_id=msg["thread_id"],
            from_email=CLIENT_EMAIL, to_email=USER_EMAIL,
            subject="Re: TikTok series payment",
            body="sending the other $600 today!!",
            when=when2, msg_id=reply_id,
        )
        await apply_client_result(
            self.db, self.user_id, CLIENT_EMAIL,
            {
                "is_receivable_client": True,
                "client": {"name": "Reese", "identities": [CLIENT_EMAIL]},
                "invoices": [],
                "events": [{
                    "type": "payment_claimed",
                    "invoice_ref": "PP-600",
                    "quote": "sending the other $600 today!!",
                    "message_id": reply_id,
                    "confidence": 0.95,
                    "amount": 600,
                }],
                "confidence_overall": 0.95,
            },
            {msg["id"]: msg, reply_id: reply},
            USER_EMAIL,
            _iso(when2),
            scoped_invoice_id=inv_id,
            events_only=True,
        )
        inv2 = await self.db.invoices.find_one({"_id": inv_id})
        self._check(
            "reply → paid_unconfirmed on $600 remaining",
            inv2["status"] == "paid_unconfirmed",
            inv2.get("status"),
        )
        # Tracked total stays 1200 with 600 already paid — claim is on the remainder
        self._check("still amount 1200", float(inv2["amount"]) == 1200)
        self._check("still paid 600 (pre-confirm)", float(inv2["paid_amount"]) == 600)
        self._check("still balance 600", float(inv2["balance_remaining"]) == 600)

    async def run(self) -> int:
        self.test_correction_phrases()
        self.test_prior_partial_heuristic()
        self.test_td104_events_unit()
        await self.test_td104_pipeline()
        await self.test_prior_partial_pipeline()
        failed = [r for r in self.results if not r[1]]
        print(f"\n{'=' * 50}")
        print(f"Results: {len(self.results) - len(failed)}/{len(self.results)} passed")
        if failed:
            print("FAILED:")
            for name, _, detail in failed:
                print(f"  - {name}: {detail}")
            return 1
        print("All TD-104 / prior-partial checks passed.")
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
        print(f"ERROR: test user {USER_EMAIL} not found")
        return 2
    user_id = user["_id"]
    refs = ["TD-104", "PP-600"]
    old = [i["_id"] async for i in db.invoices.find({
        "user_id": user_id, "invoice_ref_normalized": {"$in": refs},
    })]
    if old:
        await db.invoice_events.delete_many({"user_id": user_id, "invoice_id": {"$in": old}})
    await db.invoices.delete_many({"user_id": user_id, "invoice_ref_normalized": {"$in": refs}})

    try:
        code = await Harness(db, user_id).run()
        if not args.keep_data:
            created = [i["_id"] async for i in db.invoices.find({
                "user_id": user_id, "invoice_ref_normalized": {"$in": refs},
            })]
            if created:
                await db.invoice_events.delete_many({
                    "user_id": user_id, "invoice_id": {"$in": created},
                })
            await db.invoices.delete_many({
                "user_id": user_id, "invoice_ref_normalized": {"$in": refs},
            })
        return code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
