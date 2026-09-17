"""QBO conversation match — InvoiceLink / DocNumber waterfall, not dump-and-score."""
from qbo_conversation import _has_real_client_email, _item_snapshot, _pick_best_thread
from invoice_mail_match import (
    amount_in_message,
    date_in_hay,
    extra_thread_ids,
    pay_url_token,
    ref_in_message,
    waterfall_threads,
)


def test_item_snapshot_waiting():
    row = _item_snapshot({
        "_id": "abc",
        "invoice_ref": "1041",
        "counterparty_name": "Acme",
        "counterparty_email": "ap@acme.com",
        "amount": 150,
        "currency": "USD",
    })
    assert row["invoice_id"] == "abc"
    assert row["state"] == "waiting"
    assert row["invoice_ref"] == "1041"
    assert row["client"] == "Acme"


def test_skip_placeholder_invoicing_emails():
    assert _has_real_client_email({"counterparty_email": "qbo:16"}) is False
    assert _has_real_client_email({"counterparty_email": "xero:abc"}) is False
    assert _has_real_client_email({"counterparty_email": "freshbooks:9"}) is False
    assert _has_real_client_email({"counterparty_email": ""}) is False
    assert _has_real_client_email({"counterparty_email": "ap@studio.com"}) is True


def test_pick_invoice_thread_not_lunch():
    inv = {
        "invoice_ref": "1042",
        "invoice_ref_normalized": "1042",
        "amount": 200,
        "counterparty_email": "vt444713@gmail.com",
        "source_date": "2025-09-01",
    }
    msgs = [
        {
            "id": "m1",
            "thread_id": "t-invoice",
            "subject": "Invoice 1042",
            "body": "Invoice # : 1042\nAmount Due: $200.00",
            "snippet": "",
            "from": "me@getscotive.com",
            "to": "vt444713@gmail.com",
            "date": "Tue, 02 Sep 2025 10:00:00 +0000",
        },
        {
            "id": "m2",
            "thread_id": "t-noise",
            "subject": "Lunch?",
            "body": "",
            "snippet": "",
            "from": "vt444713@gmail.com",
            "to": "me@getscotive.com",
            "date": "Wed, 03 Sep 2025 10:00:00 +0000",
        },
    ]
    tid, anchor = _pick_best_thread(msgs, inv, my_email="me@getscotive.com")
    assert tid == "t-invoice"
    assert anchor == "m1"
