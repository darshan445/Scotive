"""Windowed sync: additive threads, onboarding ladder, full bodies."""
from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone

from gmail_client import _html_to_visible_text, _parse_unipile_email
from incremental_sync import (
    _fetch_new_client_mail,
    _invoice_thread_ids,
    _map_window_threads,
    _reevaluate_tracked,
    _split_known_new,
    reeval_after_user_outbound_send,
)


INV_1047 = {
    "_id": "inv-1047",
    "user_id": "u1",
    "invoice_ref": "1047",
    "invoice_ref_normalized": "1047",
    "amount": 1263.60,
    "due_date": "2026-10-16",
    "source_date": "2026-09-16",
    "counterparty_email": "ap@client.com",
    "client_identity_key": "ap@client.com",
    "pay_url": "https://connect.intuit.com/t/AbCdEfGh1234",
    "status": "invoiced",
}


def test_invoice_thread_ids_includes_extras():
    inv = {
        "source_thread_id": "t-qbo",
        "conversation_thread_ids": ["t-qbo", "t-later"],
    }
    assert _invoice_thread_ids(inv) == ["t-qbo", "t-later"]
    assert _invoice_thread_ids({"conversation_thread_ids": ["t-later"]}) == ["t-later"]
    assert _invoice_thread_ids({}) == []


def test_split_known_new_sees_conversation_threads():
    class _Invoices:
        def __init__(self, rows):
            self.rows = rows

        async def find_one(self, query, proj=None):
            uid = query.get("user_id")
            if "source_message_id" in query:
                for row in self.rows:
                    if row.get("user_id") == uid and row.get("source_message_id") == query["source_message_id"]:
                        return {"_id": row["_id"]}
                return None
            for row in self.rows:
                if row.get("user_id") != uid:
                    continue
                for clause in query.get("$or") or []:
                    if clause.get("source_thread_id") and row.get("source_thread_id") == clause["source_thread_id"]:
                        return {"_id": row["_id"]}
                    want = clause.get("conversation_thread_ids")
                    if want and want in (row.get("conversation_thread_ids") or []):
                        return {"_id": row["_id"]}
            return None

    class _DB:
        def __init__(self):
            self.invoices = _Invoices([{
                "_id": "inv1",
                "user_id": "u1",
                "source_thread_id": "t-qbo",
                "conversation_thread_ids": ["t-qbo", "t-later"],
            }])

    db = _DB()
    msgs = [
        {"id": "m-new", "thread_id": "t-later"},
        {"id": "m-other", "thread_id": "t-unrelated"},
    ]
    new_msgs, triggered = asyncio.run(_split_known_new(db, "u1", msgs))
    assert [m["id"] for m in new_msgs] == ["m-other"]
    assert list(triggered) == ["inv1"]
    assert [m["id"] for m in triggered["inv1"]] == ["m-new"]


def test_fetch_and_reeval_use_full_bodies():
    fetch_src = inspect.getsource(_fetch_new_client_mail)
    assert "list_messages(" in fetch_src
    assert "list_messages_meta" not in fetch_src
    from incremental_sync import _fetch_invoice_thread_messages, run_incremental_pipeline
    fetch_threads = inspect.getsource(_fetch_invoice_thread_messages)
    assert "list_thread_full" in fetch_threads
    reeval_src = inspect.getsource(_reevaluate_tracked)
    assert "list_thread_meta" not in reeval_src
    assert "_should_trigger_user_reeval" not in reeval_src
    assert "AMOUNT_LANGUAGE" not in reeval_src
    assert "CORRECTION_INTENT" not in reeval_src
    assert "restore_wiped_promise" not in reeval_src
    assert "_write_event" not in reeval_src
    assert "apply_rulebook_result" in reeval_src
    post_src = inspect.getsource(reeval_after_user_outbound_send)
    assert "_fetch_invoice_thread_messages" in post_src
    assert "not_correction" not in post_src
    assert "_should_trigger_user_reeval" not in post_src
    assert "_write_event" not in post_src
    assert "apply_rulebook_result" in post_src
    pipe_src = inspect.getsource(run_incremental_pipeline)
    assert "fetch_filtered_sent_mail" not in pipe_src
    assert "_split_known_new" not in pipe_src


def test_html_pay_href_survives_strip():
    html = (
        '<p>Pay now</p><a href="https://connect.intuit.com/t/AbCdEfGh1234">Invoice</a>'
    )
    text = _html_to_visible_text(html)
    assert "AbCdEfGh1234" in text
    parsed = _parse_unipile_email({
        "id": "e1",
        "thread_id": "t1",
        "body_plain": "Pay now",
        "body": html,
        "from_attendee": {"identifier": "ap@client.com"},
        "to_attendees": [{"identifier": "me@studio.com"}],
        "subject": "Invoice",
    })
    assert parsed is not None
    assert "AbCdEfGh1234" in parsed["body"]


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


class _FakeColl:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.inserted = []

    async def update_one(self, filt, update, upsert=False):
        row = next((r for r in self.rows if _row_matches(r, filt)), None)
        if row is None:
            if not upsert:
                return
            row = dict(filt)
            set_on = update.get("$setOnInsert") or {}
            row.update(set_on)
            self.rows.append(row)
        if "$set" in update:
            row.update(update["$set"])
        add_set = update.get("$addToSet") or {}
        for key, spec in add_set.items():
            each = list(spec.get("$each") or []) if isinstance(spec, dict) else [spec]
            cur = list(row.get(key) or [])
            for v in each:
                if v not in cur:
                    cur.append(v)
            row[key] = cur

    async def find_one(self, filt, proj=None):
        return next((r for r in self.rows if _row_matches(r, filt)), None)

    def find(self, query, proj=None):
        status_in = (query.get("status") or {}).get("$in")
        want_ids = None
        mid_q = query.get("message_id")
        if isinstance(mid_q, dict) and "$in" in mid_q:
            want_ids = set(mid_q["$in"])
        rows = []
        for row in self.rows:
            if query.get("user_id") and row.get("user_id") != query.get("user_id"):
                continue
            if query.get("invoice_id") and row.get("invoice_id") != query.get("invoice_id"):
                continue
            if status_in and row.get("status") not in status_in:
                continue
            if want_ids is not None and row.get("message_id") not in want_ids:
                continue
            rows.append(row)
        return _AIter(rows)

    async def insert_one(self, doc):
        self.inserted.append(doc)


class _FakeDB:
    def __init__(self, invoices):
        self.invoices = _FakeColl(invoices)
        self.invoice_events = _FakeColl()
        self.processed_messages = _FakeColl()


def test_map_appends_new_thread_keeps_qbo_send():
    inv = {
        **INV_1047,
        "source_thread_id": "t-qbo",
        "conversation_thread_ids": ["t-qbo"],
    }
    db = _FakeDB([inv])
    quote = {
        "id": "m-new",
        "thread_id": "t-new",
        "from": "ap@client.com",
        "to": "me@studio.com",
        "subject": "1047",
        "body": "Invoice # : 1047 still open?",
        "snippet": "",
    }
    lunch = {
        "id": "m-lunch",
        "thread_id": "t-lunch",
        "from": "ap@client.com",
        "to": "me@studio.com",
        "subject": "Lunch?",
        "body": "Lunch tomorrow?",
        "snippet": "",
    }
    _by, units, stats = asyncio.run(_map_window_threads(
        db, [inv], [quote, lunch], my_email="me@studio.com", now_iso="2026-09-16T12:00:00Z",
    ))
    assert inv["source_thread_id"] == "t-qbo"
    assert "t-new" in inv["conversation_thread_ids"]
    assert "t-lunch" not in inv["conversation_thread_ids"]
    assert stats["threads_appended"] == 1
    assert "t-new" in _by
    assert units[inv["_id"]]["oot"][0]["id"] == "m-new"


def test_map_lunch_does_not_steal_single_open_invoice():
    inv = {
        **INV_1047,
        "source_thread_id": "t-qbo",
        "conversation_thread_ids": ["t-qbo"],
        "pay_url": "",
    }
    db = _FakeDB([inv])
    lunch = {
        "id": "m-lunch",
        "thread_id": "t-lunch",
        "from": "ap@client.com",
        "to": "me@studio.com",
        "subject": "Lunch?",
        "body": "Lunch tomorrow?",
        "snippet": "",
    }
    _by, units, stats = asyncio.run(_map_window_threads(
        db, [inv], [lunch], my_email="me@studio.com", now_iso="2026-09-16T12:00:00Z",
    ))
    assert inv["conversation_thread_ids"] == ["t-qbo"]
    assert stats["threads_appended"] == 0
    assert stats["unmapped"] == 1
    assert units == {}


def test_unmatched_intuit_from_attaches_quoted_inbound():
    inv = {
        **INV_1047,
        "source_thread_id": None,
        "conversation_thread_ids": [],
        "source_message_id": "qbo:99",
    }
    db = _FakeDB([inv])
    inbound = {
        "id": "m-in",
        "thread_id": "t-inbound",
        "from": "ap@client.com",
        "to": "me@studio.com",
        "subject": "Re: Invoice 1047",
        "body": (
            "Paying Friday.\n\n"
            "On Wed, 16 Sep 2026 QuickBooks wrote:\n"
            "> Invoice # : 1047\n"
            "> Amount Due: $1,263.60\n"
            "> https://connect.intuit.com/t/AbCdEfGh1234\n"
        ),
        "snippet": "",
        "date": "Wed, 16 Sep 2026 15:00:00 +0000",
    }
    _by, units, stats = asyncio.run(_map_window_threads(
        db, [inv], [inbound], my_email="me@studio.com", now_iso="2026-09-16T16:00:00Z",
    ))
    assert stats["first_matched"] == 1
    assert inv["source_thread_id"] == "t-inbound"
    assert "t-inbound" in inv["conversation_thread_ids"]
    assert db.invoice_events.inserted
    assert db.invoice_events.inserted[0]["action"] == "conversation_matched"
    assert units[inv["_id"]]["oot"][0]["id"] == "m-in"


def test_in_thread_reply_on_extra_conversation_thread():
    inv = {
        **INV_1047,
        "source_thread_id": "t-qbo",
        "conversation_thread_ids": ["t-qbo", "t-later"],
    }
    db = _FakeDB([inv])
    reply = {
        "id": "m-reply",
        "thread_id": "t-later",
        "from": "ap@client.com",
        "body": "ok will pay Friday",
        "subject": "Re: 1047",
        "snippet": "",
    }
    _by, units, stats = asyncio.run(_map_window_threads(
        db, [inv], [reply], my_email="me@studio.com", now_iso="2026-09-16T16:00:00Z",
    ))
    assert stats["threads_appended"] == 0
    assert inv["_id"] in units
    assert units[inv["_id"]]["oot"][0]["id"] == "m-reply"


THREAD_MSGS_1051 = [
    {
        "id": "m-qbo",
        "from": "me@studio.com",
        "body": "Invoice 1051 for $1,242",
        "subject": "Invoice 1051",
        "thread_id": "t-qbo",
        "date": "Wed, 16 Sep 2026 10:00:00 +0000",
    },
    {
        "id": "m-dispute",
        "from": "ap@client.com",
        "body": "I think we agreed on 1200 right?",
        "subject": "Re: Invoice 1051",
        "thread_id": "t-qbo",
        "date": "Wed, 16 Sep 2026 11:59:00 +0000",
    },
    {
        "id": "m-yes",
        "from": "me@studio.com",
        "body": "Yes, that is correct.",
        "subject": "Re: Invoice 1051",
        "thread_id": "t-qbo",
        "date": "Wed, 16 Sep 2026 13:02:00 +0000",
    },
]


def _disputed_inv(**extra):
    return {
        **INV_1047,
        "source_thread_id": "t-qbo",
        "conversation_thread_ids": ["t-qbo"],
        "source_message_id": "qbo:1051",
        "status": "disputed",
        "disputed_claim_amount": 1200,
        "reeval_seen_message_ids": ["m-qbo", "m-dispute"],
        **extra,
    }


def test_owner_gmail_reply_without_money_reevals(monkeypatch):
    inv = _disputed_inv()
    db = _FakeDB([inv])
    called = {}

    async def fake_list_thread_full(access, tid, **kw):
        return list(THREAD_MSGS_1051)

    async def fake_list_messages(*a, **k):
        return []

    async def fake_extract(client, prepared):
        called["n"] = called.get("n", 0) + 1
        return {"status": "invoiced", "amount": 1200, "new_events": []}

    monkeypatch.setattr("incremental_sync.list_thread_full", fake_list_thread_full)
    monkeypatch.setattr("incremental_sync.list_messages", fake_list_messages)
    monkeypatch.setattr("incremental_sync.extract_reeval_with_rulebook", fake_extract)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    stats = asyncio.run(_reevaluate_tracked(
        db, "u1", "token", "me@studio.com",
        datetime(2026, 9, 16, 13, 26, tzinfo=timezone.utc),
        "2026-09-16T13:30:00Z",
    ))
    assert called.get("n") == 1
    assert stats["reevaluated"] == 1
    assert stats["skipped_no_activity"] == 0
    assert "m-yes" in inv["reeval_seen_message_ids"]


def test_no_unseen_messages_skips_without_burying(monkeypatch):
    inv = _disputed_inv(reeval_seen_message_ids=["m-qbo", "m-dispute", "m-yes"])
    db = _FakeDB([inv])
    called = {}

    async def fake_list_thread_full(access, tid, **kw):
        return list(THREAD_MSGS_1051)

    async def fake_list_messages(*a, **k):
        return []

    async def fake_extract(client, prepared):
        called["n"] = called.get("n", 0) + 1
        return {"status": "disputed", "new_events": []}

    monkeypatch.setattr("incremental_sync.list_thread_full", fake_list_thread_full)
    monkeypatch.setattr("incremental_sync.list_messages", fake_list_messages)
    monkeypatch.setattr("incremental_sync.extract_reeval_with_rulebook", fake_extract)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    stats = asyncio.run(_reevaluate_tracked(
        db, "u1", "token", "me@studio.com",
        datetime(2026, 9, 16, 13, 26, tzinfo=timezone.utc),
        "2026-09-16T13:30:00Z",
    ))
    assert called.get("n") is None
    assert stats["reevaluated"] == 0
    assert stats["skipped_no_activity"] == 1
    assert inv["reeval_seen_message_ids"] == ["m-qbo", "m-dispute", "m-yes"]


def test_post_send_without_money_language_still_reevals(monkeypatch):
    inv = _disputed_inv()
    db = _FakeDB([inv])
    called = {}

    async def fake_list_thread_full(access, tid, **kw):
        return list(THREAD_MSGS_1051)

    async def fake_extract(client, prepared):
        called["n"] = called.get("n", 0) + 1
        return {"status": "invoiced", "amount": 1200, "new_events": []}

    monkeypatch.setattr("incremental_sync.list_thread_full", fake_list_thread_full)
    monkeypatch.setattr("incremental_sync.extract_reeval_with_rulebook", fake_extract)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    out = asyncio.run(reeval_after_user_outbound_send(
        db, "u1", inv,
        access="token",
        my_email="me@studio.com",
        subject="Re: Invoice 1051",
        body="Yes, that is correct.",
        gmail_message_id="m-yes",
        thread_id="t-qbo",
    ))
    assert out.get("skipped") != "not_correction"
    assert out["triggered"] is True
    assert called.get("n") == 1
