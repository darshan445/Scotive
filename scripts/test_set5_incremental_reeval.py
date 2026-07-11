"""SET 5 — Stage 4 incremental reeval expectations (G1–G5) without live LLM.

Simulates rulebook new_events → _write_event → invoice row/timeline.
Also asserts the processed_message_ids bugfix (user corrections must NOT
be treated as already-processed just because Stage 2 saw them).

Usage:
  PYTHONPATH=backend python scripts/test_set5_incremental_reeval.py
  PYTHONPATH=backend python scripts/test_set5_incremental_reeval.py --keep-data
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

from client_sweep import _EVENT_APPLY_ORDER, _write_event  # noqa: E402
from incremental_sync import (  # noqa: E402
    _invoice_processed_message_ids,
    _is_amount_correction,
    _mark_reeval_seen,
)
from ledger_reconcile import client_identity_key, enrich_invoice_doc  # noqa: E402
from reeval_rulebook import (  # noqa: E402
    apply_promise_date_resolution,
    build_tracked_state,
    enforce_dispute_resolution,
    filter_new_events_to_unprocessed,
    normalize_null_strings,
    rulebook_events_to_write_events,
)

USER_EMAIL = "tdarshan336@gmail.com"
CLIENT_EMAIL = "darsh@getscotive.com"
PREFIX = "set5.reeval-"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class Set5Test:
    def __init__(self, db, user_id):
        self.db = db
        self.user_id = user_id
        self.results: list[tuple[str, bool, Any]] = []
        self._n = 0

    def _check(self, name: str, ok: bool, detail: Any = None) -> None:
        self.results.append((name, bool(ok), detail))
        print(("PASS" if ok else "FAIL"), name, "" if ok else detail)

    def _mid(self, tag: str) -> str:
        self._n += 1
        return f"{PREFIX}{tag}-{self._n}"

    def _msg(
        self, *, mid: str, thread_id: str, from_email: str, to_email: str,
        subject: str, body: str, when: datetime,
    ) -> dict:
        return {
            "id": mid,
            "thread_id": thread_id,
            "from": from_email,
            "to": to_email,
            "subject": subject,
            "body": body,
            "date": _iso(when),
        }

    async def _seed(self, ref: str, amount: float, due: str, subject: str, body: str, when: datetime):
        tid = self._mid(f"t-{ref}")
        mid = self._mid(f"sent-{ref}")
        doc = enrich_invoice_doc({
            "user_id": self.user_id,
            "counterparty_email": CLIENT_EMAIL,
            "counterparty_name": "Client",
            "client_identity_key": client_identity_key(CLIENT_EMAIL),
            "amount": amount,
            "balance_remaining": amount,
            "paid_amount": 0,
            "currency": "USD",
            "invoice_ref": ref,
            "invoice_ref_normalized": ref,
            "due_date": due,
            "status": "invoiced",
            "source_message_id": mid,
            "source_thread_id": tid,
            "source_subject": subject,
            "source_date": _iso(when),
            "created_at": _iso(when),
        }, CLIENT_EMAIL)
        res = await self.db.invoices.insert_one(doc)
        return res.inserted_id, mid, tid

    async def _apply(self, inv_id, inv, result: dict, messages_by_id: dict, when: datetime):
        tracked = build_tracked_state(
            inv,
            await _invoice_processed_message_ids(self.db, self.user_id, inv),
        )
        parsed = normalize_null_strings(dict(result))
        parsed = filter_new_events_to_unprocessed(parsed, tracked)
        parsed = apply_promise_date_resolution(parsed)
        parsed = enforce_dispute_resolution(parsed, tracked)
        events = rulebook_events_to_write_events(
            parsed, invoice_ref=inv.get("invoice_ref_normalized"),
        )
        for e in events:
            if e.get("type") == "correction" and e.get("old_amount") is None:
                e["old_amount"] = float(inv.get("amount") or 0)
        events = sorted(
            events,
            key=lambda e: (_EVENT_APPLY_ORDER.get(e.get("type") or "", 99), e.get("message_id") or ""),
        )
        for ev in events:
            await _write_event(
                self.db, self.user_id, inv_id, ev, messages_by_id, _iso(when),
                my_email=USER_EMAIL,
            )
        from incremental_sync import _apply_reeval_top_level
        inv2 = await self.db.invoices.find_one({"_id": inv_id})
        await _apply_reeval_top_level(self.db, inv2, parsed, _iso(when))
        await _mark_reeval_seen(
            self.db, inv_id,
            [e.get("message_id") for e in (parsed.get("new_events") or []) if e.get("message_id")],
        )
        return await self.db.invoices.find_one({"_id": inv_id}), parsed

    async def _actions(self, inv_id) -> list[str]:
        out = []
        async for e in self.db.invoice_events.find(
            {"user_id": self.user_id, "invoice_id": inv_id}
        ).sort("at", 1):
            out.append(e.get("action"))
        return out

    # ---- G1 ----
    async def test_g1(self):
        print("\n== G1 dispute → correction → promise ==")
        when = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
        inv_id, sent, tid = await self._seed(
            "FS-410", 1450, "2026-08-03",
            "Invoice FS-410", "Landing page redesign: $1,450. Due Aug 3, 2026.", when,
        )
        inv = await self.db.invoices.find_one({"_id": inv_id})

        d_id = self._mid("g1-d")
        dmsg = self._msg(
            mid=d_id, thread_id=tid, from_email=CLIENT_EMAIL, to_email=USER_EMAIL,
            subject="Re: Invoice FS-410",
            body="I think we agreed $1,250 for this scope.",
            when=datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc),
        )
        inv, _ = await self._apply(inv_id, inv, {
            "invoice_ref": "FS-410", "amount": 1450, "status": "disputed",
            "disputed_claim_amount": 1250, "paid_amount": 0, "balance_remaining": 1450,
            "new_events": [{
                "type": "dispute", "message_id": d_id, "sender": "client",
                "quote": "I think we agreed $1,250 for this scope.", "confidence": 0.9,
                "data": {"amount": 1250},
            }],
        }, {sent: {"id": sent}, d_id: dmsg}, datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc))
        self._check("G1 after dispute status", inv["status"] == "disputed", inv.get("status"))
        self._check("G1 amount stays 1450", float(inv["amount"]) == 1450)
        self._check("G1 claim 1250", float(inv.get("disputed_claim_amount") or 0) == 1250)

        c_id = self._mid("g1-c")
        cmsg = self._msg(
            mid=c_id, thread_id=tid, from_email=USER_EMAIL, to_email=CLIENT_EMAIL,
            subject="Re: Invoice FS-410",
            body="You're right, adjusting to $1,250.",
            when=datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc),
        )
        self._check("G1 correction language", _is_amount_correction(cmsg))
        # Simulate the bug class: message is in global processed_messages but NOT yet on timeline
        await self.db.processed_messages.update_one(
            {"user_id": self.user_id, "message_id": c_id},
            {"$setOnInsert": {"user_id": self.user_id, "message_id": c_id, "at": datetime.now(timezone.utc)}},
            upsert=True,
        )
        pids = await _invoice_processed_message_ids(self.db, self.user_id, inv, [sent, d_id, c_id])
        self._check(
            "G1 correction NOT in processed_ids (global alone insufficient)",
            c_id not in pids,
            pids,
        )
        inv, _ = await self._apply(inv_id, inv, {
            "invoice_ref": "FS-410", "amount": 1250, "status": "invoiced",
            "disputed_claim_amount": None, "paid_amount": 0, "balance_remaining": 1250,
            "new_events": [{
                "type": "amount_correction", "message_id": c_id, "sender": "user",
                "quote": "You're right, adjusting to $1,250.", "confidence": 0.9,
                "data": {"amount": 1250},
            }],
        }, {sent: {"id": sent}, d_id: dmsg, c_id: cmsg}, datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc))
        self._check("G1 after correction amount 1250", float(inv["amount"]) == 1250)
        self._check("G1 after correction invoiced", inv["status"] == "invoiced", inv.get("status"))
        self._check("G1 claim cleared", inv.get("disputed_claim_amount") is None)

        p_id = self._mid("g1-p")
        pmsg = self._msg(
            mid=p_id, thread_id=tid, from_email=CLIENT_EMAIL, to_email=USER_EMAIL,
            subject="Re: Invoice FS-410",
            body="Great, I'll get that sent by July 20.",
            when=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
        )
        inv, parsed = await self._apply(inv_id, inv, {
            "invoice_ref": "FS-410", "amount": 1250, "status": "promised",
            "promise_date": None, "disputed_claim_amount": None,
            "paid_amount": 0, "balance_remaining": 1250,
            "new_events": [{
                "type": "promise", "message_id": p_id, "sender": "client",
                "quote": "Great, I'll get that sent by July 20.", "confidence": 0.9,
                "data": {
                    "relative_phrase": "by July 20",
                    "anchor_date": "2026-07-14",
                    "date": None,
                },
            }],
        }, {sent: {"id": sent}, d_id: dmsg, c_id: cmsg, p_id: pmsg},
            datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc))
        self._check("G1 promised", inv["status"] == "promised", inv.get("status"))
        self._check(
            "G1 promise_date 2026-07-20",
            (inv.get("promise_date") or "")[:10] == "2026-07-20",
            inv.get("promise_date"),
        )

    # ---- G2 ----
    async def test_g2(self):
        print("\n== G2 proactive correction ==")
        when = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
        inv_id, sent, tid = await self._seed(
            "FS-411", 980, "2026-08-05",
            "Invoice FS-411", "Photography package: $980. Due Aug 5, 2026.", when,
        )
        inv = await self.db.invoices.find_one({"_id": inv_id})
        c_id = self._mid("g2-c")
        cmsg = self._msg(
            mid=c_id, thread_id=tid, from_email=USER_EMAIL, to_email=CLIENT_EMAIL,
            subject="Re: Invoice FS-411",
            body="Correcting this to $920 — forgot to apply the returning-client discount.",
            when=datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc),
        )
        inv, parsed = await self._apply(inv_id, inv, {
            "invoice_ref": "FS-411", "amount": 920, "status": "invoiced",
            "disputed_claim_amount": None, "paid_amount": 0, "balance_remaining": 920,
            "new_events": [{
                "type": "amount_correction", "message_id": c_id, "sender": "user",
                "quote": "Correcting this to $920", "confidence": 0.9,
                "data": {"amount": 920},
            }],
        }, {sent: {"id": sent}, c_id: cmsg}, datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc))
        self._check("G2 one correction event", len(parsed.get("new_events") or []) == 1)
        self._check("G2 amount 920", float(inv["amount"]) == 920)
        self._check("G2 stays invoiced", inv["status"] == "invoiced")
        self._check("G2 no claim", inv.get("disputed_claim_amount") is None)
        actions = await self._actions(inv_id)
        self._check("G2 timeline has correction", "invoice_corrected" in actions, actions)
        self._check("G2 timeline no dispute", "dispute" not in actions, actions)

    # ---- G3 ----
    async def test_g3(self):
        print("\n== G3 dispute then resend new ref ==")
        when = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
        inv_id, sent, tid = await self._seed(
            "FS-412", 1600, "2026-08-08",
            "Invoice FS-412", "Illustration set: $1,600. Due Aug 8, 2026.", when,
        )
        inv = await self.db.invoices.find_one({"_id": inv_id})
        d_id = self._mid("g3-d")
        dmsg = self._msg(
            mid=d_id, thread_id=tid, from_email=CLIENT_EMAIL, to_email=USER_EMAIL,
            subject="Re: Invoice FS-412",
            body="This should be $1,400 based on the revised scope we discussed — can you resend?",
            when=datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc),
        )
        inv, _ = await self._apply(inv_id, inv, {
            "invoice_ref": "FS-412", "amount": 1600, "status": "disputed",
            "disputed_claim_amount": 1400, "paid_amount": 0, "balance_remaining": 1600,
            "new_events": [{
                "type": "dispute", "message_id": d_id, "sender": "client",
                "quote": "This should be $1,400", "confidence": 0.9,
                "data": {"amount": 1400},
            }],
        }, {sent: {"id": sent}, d_id: dmsg}, datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc))
        self._check("G3 disputed", inv["status"] == "disputed")
        self._check("G3 amount 1600", float(inv["amount"]) == 1600)

        c_id = self._mid("g3-c")
        cmsg = self._msg(
            mid=c_id, thread_id=tid, from_email=USER_EMAIL, to_email=CLIENT_EMAIL,
            subject="Re: Invoice FS-412",
            body="Apologies, here's the corrected one — #FS-412-R: $1,400, same due date.",
            when=datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc),
        )
        inv, _ = await self._apply(inv_id, inv, {
            "invoice_ref": "FS-412-R", "amount": 1400, "status": "invoiced",
            "disputed_claim_amount": None, "paid_amount": 0, "balance_remaining": 1400,
            "due_date": "2026-08-08",
            "new_events": [{
                "type": "amount_correction", "message_id": c_id, "sender": "user",
                "quote": "#FS-412-R: $1,400", "confidence": 0.9,
                "data": {"amount": 1400},
            }],
        }, {sent: {"id": sent}, d_id: dmsg, c_id: cmsg}, datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc))
        self._check("G3 amount 1400", float(inv["amount"]) == 1400)
        self._check("G3 invoiced", inv["status"] == "invoiced")
        self._check(
            "G3 ref FS-412-R",
            (inv.get("invoice_ref_normalized") or "") == "FS-412-R",
            inv.get("invoice_ref_normalized"),
        )
        n = await self.db.invoices.count_documents({
            "user_id": self.user_id,
            "invoice_ref_normalized": {"$in": ["FS-412", "FS-412-R"]},
            "source_thread_id": tid,
        })
        self._check("G3 single row", n == 1, n)

    # ---- G4 ----
    async def test_g4(self):
        print("\n== G4 two dispute-correction rounds ==")
        when = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
        inv_id, sent, tid = await self._seed(
            "FS-413", 2100, "2026-08-12",
            "Invoice FS-413", "Product photography: $2,100. Due Aug 12, 2026.", when,
        )
        inv = await self.db.invoices.find_one({"_id": inv_id})
        msgs = {sent: {"id": sent}}

        async def step(tag, from_e, to_e, body, result, day):
            nonlocal inv
            mid = self._mid(tag)
            m = self._msg(
                mid=mid, thread_id=tid, from_email=from_e, to_email=to_e,
                subject="Re: Invoice FS-413", body=body,
                when=datetime(2026, 7, day, 12, 0, tzinfo=timezone.utc),
            )
            msgs[mid] = m
            for ev in result.get("new_events") or []:
                ev["message_id"] = mid
            inv, _ = await self._apply(
                inv_id, inv, result, msgs,
                datetime(2026, 7, day, 12, 0, tzinfo=timezone.utc),
            )
            return inv

        inv = await step("g4-d1", CLIENT_EMAIL, USER_EMAIL, "We talked about $1,900 for this batch.", {
            "invoice_ref": "FS-413", "amount": 2100, "status": "disputed",
            "disputed_claim_amount": 1900, "paid_amount": 0, "balance_remaining": 2100,
            "new_events": [{"type": "dispute", "sender": "client", "quote": "$1,900",
                            "confidence": 0.9, "data": {"amount": 1900}}],
        }, 12)
        self._check("G4 r1 disputed", inv["status"] == "disputed" and float(inv["amount"]) == 2100)

        inv = await step("g4-c1", USER_EMAIL, CLIENT_EMAIL, "Fair, adjusting to $1,900.", {
            "invoice_ref": "FS-413", "amount": 1900, "status": "invoiced",
            "disputed_claim_amount": None, "paid_amount": 0, "balance_remaining": 1900,
            "new_events": [{"type": "amount_correction", "sender": "user", "quote": "$1,900",
                            "confidence": 0.9, "data": {"amount": 1900}}],
        }, 13)
        self._check("G4 r1 corrected", inv["status"] == "invoiced" and float(inv["amount"]) == 1900)

        inv = await step("g4-d2", CLIENT_EMAIL, USER_EMAIL, "Actually on reflection I think it was $1,850 — can you check?", {
            "invoice_ref": "FS-413", "amount": 1900, "status": "disputed",
            "disputed_claim_amount": 1850, "paid_amount": 0, "balance_remaining": 1900,
            "new_events": [{"type": "dispute", "sender": "client", "quote": "$1,850",
                            "confidence": 0.9, "data": {"amount": 1850}}],
        }, 14)
        self._check(
            "G4 r2 disputed",
            inv["status"] == "disputed" and float(inv["amount"]) == 1900
            and float(inv.get("disputed_claim_amount") or 0) == 1850,
            f"{inv.get('status')} {inv.get('amount')} {inv.get('disputed_claim_amount')}",
        )

        inv = await step("g4-c2", USER_EMAIL, CLIENT_EMAIL, "Confirmed, $1,850 it is.", {
            "invoice_ref": "FS-413", "amount": 1850, "status": "invoiced",
            "disputed_claim_amount": None, "paid_amount": 0, "balance_remaining": 1850,
            "new_events": [{"type": "amount_correction", "sender": "user", "quote": "$1,850",
                            "confidence": 0.9, "data": {"amount": 1850}}],
        }, 15)
        self._check(
            "G4 final",
            inv["status"] == "invoiced" and float(inv["amount"]) == 1850
            and inv.get("disputed_claim_amount") is None,
        )
        actions = await self._actions(inv_id)
        self._check("G4 two disputes", actions.count("dispute") == 2, actions)
        self._check("G4 two corrections", actions.count("invoice_corrected") == 2, actions)

    # ---- G5 ----
    async def test_g5(self):
        print("\n== G5 dispute + partial in one message ==")
        when = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
        inv_id, sent, tid = await self._seed(
            "FS-414", 2400, "2026-08-15",
            "Invoice FS-414", "Event photography coverage: $2,400. Due Aug 15, 2026.", when,
        )
        inv = await self.db.invoices.find_one({"_id": inv_id})
        m_id = self._mid("g5-m")
        m = self._msg(
            mid=m_id, thread_id=tid, from_email=CLIENT_EMAIL, to_email=USER_EMAIL,
            subject="Re: Invoice FS-414",
            body=(
                "I had this at $2,000 in my notes — either way, sending $1,200 now, "
                "we'll reconcile the rest once we confirm the number."
            ),
            when=datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc),
        )
        inv, parsed = await self._apply(inv_id, inv, {
            "invoice_ref": "FS-414", "amount": 2400, "status": "partially_paid",
            "disputed_claim_amount": 2000, "paid_amount": 1200, "balance_remaining": 1200,
            "new_events": [
                {"type": "dispute", "message_id": m_id, "sender": "client",
                 "quote": "I had this at $2,000", "confidence": 0.9, "data": {"amount": 2000}},
                {"type": "partial_payment", "message_id": m_id, "sender": "client",
                 "quote": "sending $1,200 now", "confidence": 0.9, "data": {"amount": 1200}},
            ],
        }, {sent: {"id": sent}, m_id: m}, datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc))
        types = [e["type"] for e in rulebook_events_to_write_events(parsed)]
        self._check("G5 two events", set(types) == {"dispute", "partial_payment"}, types)
        self._check("G5 amount 2400", float(inv["amount"]) == 2400)
        self._check("G5 claim 2000", float(inv.get("disputed_claim_amount") or 0) == 2000)
        self._check("G5 paid 1200", float(inv.get("paid_amount") or 0) == 1200)
        self._check("G5 balance 1200", float(inv.get("balance_remaining") or 0) == 1200)
        self._check("G5 partially_paid", inv["status"] == "partially_paid", inv.get("status"))

    async def run(self) -> int:
        await self.test_g1()
        await self.test_g2()
        await self.test_g3()
        await self.test_g4()
        await self.test_g5()
        failed = [r for r in self.results if not r[1]]
        print(f"\n{'=' * 50}")
        print(f"Results: {len(self.results) - len(failed)}/{len(self.results)} passed")
        if failed:
            print("FAILED:")
            for name, _, detail in failed:
                print(f"  - {name}: {detail}")
            return 1
        print("All SET 5 incremental reeval checks passed.")
        return 0


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-data", action="store_true")
    args = parser.parse_args()

    mongo = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = os.environ.get("DB_NAME") or "scotive"
    client = AsyncIOMotorClient(mongo)
    db = client[db_name]
    user = await db.users.find_one({"email": USER_EMAIL}) or await db.users.find_one({})
    if not user:
        print("No user found in DB")
        return 1
    uid = user["_id"]

    # Cleanup prior set5 rows
    async for inv in db.invoices.find({"user_id": uid, "invoice_ref_normalized": {
        "$in": ["FS-410", "FS-411", "FS-412", "FS-412-R", "FS-413", "FS-414"],
    }}):
        if str(inv.get("source_message_id") or "").startswith(PREFIX) or str(inv.get("source_subject") or "").startswith("Invoice FS-41"):
            await db.invoice_events.delete_many({"invoice_id": inv["_id"]})
            if not args.keep_data:
                await db.invoices.delete_one({"_id": inv["_id"]})
    await db.processed_messages.delete_many({"user_id": uid, "message_id": {"$regex": f"^{PREFIX}"}})

    t = Set5Test(db, uid)
    code = await t.run()
    if not args.keep_data:
        async for inv in db.invoices.find({"user_id": uid, "source_message_id": {"$regex": f"^{PREFIX}"}}):
            await db.invoice_events.delete_many({"invoice_id": inv["_id"]})
            await db.invoices.delete_one({"_id": inv["_id"]})
        await db.processed_messages.delete_many({"user_id": uid, "message_id": {"$regex": f"^{PREFIX}"}})
    client.close()
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
