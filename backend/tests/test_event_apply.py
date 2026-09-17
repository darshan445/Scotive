"""Model fields are the ledger. new_events are timeline chips only."""
from __future__ import annotations

import asyncio

from apply_conversation_status import apply_rulebook_result
from reeval_rulebook import apply_promise_date_resolution, build_reeval_input, sort_messages_oldest_first


class _AIter:
    def __init__(self, rows):
        self._rows = list(rows)
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._i]
        self._i += 1
        return row


def _row_matches(row: dict, filt: dict) -> bool:
    for k, v in filt.items():
        if k == "meta.message_id":
            if (row.get("meta") or {}).get("message_id") != v:
                return False
        elif row.get(k) != v:
            return False
    return True


class _Coll:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.inserted = []

    async def update_one(self, filt, update, upsert=False):
        row = next((r for r in self.rows if _row_matches(r, filt)), None)
        if row is None:
            if not upsert:
                return
            row = dict(filt)
            row.update(update.get("$setOnInsert") or {})
            self.rows.append(row)
        if "$set" in update:
            row.update(update["$set"])
        add = update.get("$addToSet") or {}
        for key, spec in add.items():
            each = list(spec.get("$each") or []) if isinstance(spec, dict) else [spec]
            cur = list(row.get(key) or [])
            for v in each:
                if v not in cur:
                    cur.append(v)
            row[key] = cur

    async def insert_one(self, doc):
        self.inserted.append(doc)
        self.rows.append(doc)

    async def find_one(self, filt, proj=None):
        return next((r for r in self.rows if _row_matches(r, filt)), None)

    def find(self, query, proj=None):
        rows = []
        for row in self.rows:
            if query.get("user_id") and row.get("user_id") != query.get("user_id"):
                continue
            if query.get("invoice_id") and row.get("invoice_id") != query.get("invoice_id"):
                continue
            if query.get("action") and row.get("action") != query.get("action"):
                continue
            rows.append(row)
        return _AIter(rows)


class _DB:
    def __init__(self, inv):
        self.invoices = _Coll([inv])
        self.invoice_events = _Coll()
        self.processed_messages = _Coll()


NOW = "2026-09-16T14:35:00Z"
MSGS = [
    {
        "id": "m-corr",
        "date": "Wed, 16 Sep 2026 19:35:00 +0530",
        "from": "me@studio.com",
        "body": "Understood, adjusting to $1200",
        "subject": "Re: 1051",
        "thread_id": "t1",
    },
    {
        "id": "m-prom",
        "date": "Wed, 16 Sep 2026 19:36:00 +0530",
        "from": "ap@client.com",
        "body": "I'll pay after two Fridays",
        "subject": "Re: 1051",
        "thread_id": "t1",
    },
    {
        "id": "m-retract",
        "date": "Wed, 16 Sep 2026 20:12:00 +0530",
        "from": "me@studio.com",
        "body": "I was right, $1242",
        "subject": "Re: 1051",
        "thread_id": "t1",
    },
]


def _inv(**extra):
    row = {
        "_id": "inv1",
        "status": "disputed",
        "amount": 1242,
        "paid_amount": 0,
        "promise_date": None,
        "disputed_claim_amount": 1200,
        "chasing_paused": True,
        "invoice_ref": "1051",
        "invoice_ref_normalized": "1051",
    }
    row.update(extra)
    return row


def test_payload_is_oldest_first():
    newest_first = list(reversed(MSGS))
    ordered = sort_messages_oldest_first(newest_first)
    assert [m["id"] for m in ordered] == ["m-corr", "m-prom", "m-retract"]
    payload = build_reeval_input(
        my_email="me@studio.com",
        client_email="ap@client.com",
        messages=newest_first,
        tracked_state={"status": "disputed", "processed_message_ids": []},
    )
    assert [m["id"] for m in payload["messages"]] == ["m-corr", "m-prom", "m-retract"]


def test_correction_then_promise_keeps_model_promised():
    """Screenshot loop: correction chip must not wipe the model's promised status."""
    inv = _inv()
    db = _DB(inv)
    result = {
        "status": "promised",
        "amount": 1200,
        "promise_date": "2026-09-26",
        "disputed_claim_amount": None,
        "new_events": [
            {
                "type": "amount_correction",
                "message_id": "m-corr",
                "quote": "adjusting to $1200",
                "data": {"amount": 1200},
            },
            {
                "type": "promise",
                "message_id": "m-prom",
                "quote": "I'll pay after two Fridays",
                "data": {"date": "2026-09-26"},
            },
        ],
    }
    applied = asyncio.run(apply_rulebook_result(
        db, "u1", inv, result, MSGS[:2],
        my_email="me@studio.com", now_iso=NOW,
    ))
    assert inv["status"] == "promised"
    assert inv["amount"] == 1200.0
    assert inv["promise_date"] == "2026-09-26"
    assert inv.get("disputed_claim_amount") is None
    assert inv["chasing_paused"] is True
    assert applied["events"] == ["correction", "promise"]
    actions = [e["action"] for e in db.invoice_events.inserted]
    assert actions == ["invoice_corrected", "payment_promise"]


def test_later_retract_clears_promise_from_model_status():
    """20:12 'I was right, $1242' after a promise → invoiced, not keep-promise."""
    inv = _inv(status="promised", amount=1200, promise_date="2026-09-26",
               disputed_claim_amount=None)
    db = _DB(inv)
    result = {
        "status": "invoiced",
        "amount": 1242,
        "promise_date": None,
        "disputed_claim_amount": None,
        "new_events": [
            {
                "type": "amount_correction",
                "message_id": "m-retract",
                "quote": "I was right, $1242",
                "data": {"amount": 1242},
            },
        ],
    }
    asyncio.run(apply_rulebook_result(
        db, "u1", inv, result, MSGS,
        my_email="me@studio.com", now_iso=NOW,
    ))
    assert inv["status"] == "invoiced"
    assert inv["amount"] == 1242.0
    assert inv["promise_date"] is None
    assert inv["chasing_paused"] is False


def test_events_do_not_override_model_status():
    inv = _inv(status="invoiced", disputed_claim_amount=None)
    db = _DB(inv)
    result = {
        "status": "invoiced",
        "amount": 1242,
        "promise_date": None,
        "disputed_claim_amount": None,
        "new_events": [
            {
                "type": "promise",
                "message_id": "m-prom",
                "quote": "I'll pay after two Fridays",
                "data": {"date": "2026-09-26"},
            },
        ],
    }
    asyncio.run(apply_rulebook_result(
        db, "u1", inv, result, MSGS,
        my_email="me@studio.com", now_iso=NOW,
    ))
    assert inv["status"] == "invoiced"
    assert inv["promise_date"] is None
    assert db.invoice_events.inserted[0]["action"] == "payment_promise"


def test_books_paid_is_not_unpaid_by_chat():
    inv = _inv(status="paid", amount=1242, disputed_claim_amount=None)
    db = _DB(inv)
    result = {
        "status": "promised",
        "amount": 1242,
        "promise_date": "2026-09-26",
        "disputed_claim_amount": None,
        "new_events": [{
            "type": "promise",
            "message_id": "m-prom",
            "quote": "I'll pay Friday",
            "data": {"date": "2026-09-26"},
        }],
    }
    applied = asyncio.run(apply_rulebook_result(
        db, "u1", inv, result, MSGS,
        my_email="me@studio.com", now_iso=NOW,
    ))
    assert applied["skipped"] == "books_locked"
    assert inv["status"] == "paid"
    assert db.invoice_events.inserted == []


def test_partial_claim_does_not_write_books_paid():
    inv = _inv(status="invoiced", disputed_claim_amount=None, paid_amount=0, amount=2400)
    db = _DB(inv)
    result = {
        "status": "partially_paid",
        "amount": 2400,
        "paid_amount": 1200,
        "disputed_claim_amount": 2000,
        "new_events": [
            {
                "type": "dispute",
                "message_id": "m-prom",
                "quote": "I had this at $2,000",
                "data": {"amount": 2000},
            },
            {
                "type": "partial_payment",
                "message_id": "m-prom",
                "quote": "sending $1,200 now",
                "data": {"amount": 1200},
            },
        ],
    }
    asyncio.run(apply_rulebook_result(
        db, "u1", inv, result, MSGS,
        my_email="me@studio.com", now_iso=NOW,
    ))
    assert inv["status"] == "partially_paid"
    assert float(inv["paid_amount"] or 0) == 0
    assert float(inv["amount"]) == 2400
    assert float(inv["balance_remaining"]) == 2400
    assert inv["payment_claim_pending"] is True
    assert float(inv["payment_claim_amount"]) == 1200
    assert float(inv["disputed_claim_amount"]) == 2000


def test_promise_date_resolution_does_not_pin_retracted_promise():
    parsed = apply_promise_date_resolution({
        "status": "invoiced",
        "promise_date": None,
        "new_events": [{
            "type": "promise",
            "data": {
                "relative_phrase": "by July 20",
                "anchor_date": "2026-07-14",
            },
        }],
    })
    assert parsed["status"] == "invoiced"
    assert parsed.get("promise_date") is None
    assert parsed["new_events"][0]["data"]["date"] == "2026-07-20"


def test_promise_date_resolution_fills_when_status_is_promised():
    parsed = apply_promise_date_resolution({
        "status": "promised",
        "promise_date": None,
        "new_events": [{
            "type": "promise",
            "data": {
                "relative_phrase": "by July 20",
                "anchor_date": "2026-07-14",
            },
        }],
    })
    assert parsed["promise_date"] == "2026-07-20"


_CONVERSATION_STATUSES = (
    "invoiced", "overdue", "promised", "disputed",
    "partially_paid", "paid_unconfirmed",
)


def test_model_status_is_ledger_for_every_conversation_state():
    """Apply writes whatever current state the model returned — any status."""
    for status in _CONVERSATION_STATUSES:
        inv = _inv(status="invoiced", disputed_claim_amount=None, promise_date=None)
        db = _DB(inv)
        result = {
            "status": status,
            "amount": 1242,
            "promise_date": "2026-09-26" if status == "promised" else None,
            "disputed_claim_amount": 1100 if status == "disputed" else None,
            "new_events": [],
        }
        asyncio.run(apply_rulebook_result(
            db, "u1", inv, result, MSGS,
            my_email="me@studio.com", now_iso=NOW,
        ))
        assert inv["status"] == status
        if status == "promised":
            assert inv["promise_date"] == "2026-09-26"
            assert inv["chasing_paused"] is True
        else:
            assert inv["promise_date"] is None
        if status == "disputed":
            assert float(inv["disputed_claim_amount"]) == 1100
            assert inv["chasing_paused"] is True
