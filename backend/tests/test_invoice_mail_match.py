"""Regional QBO email chrome → invoice thread match."""
from invoice_mail_match import (
    amount_in_message,
    date_in_hay,
    extra_thread_ids,
    pay_url_token,
    ref_in_message,
    waterfall_threads,
)


INV = {
    "invoice_ref": "1047",
    "invoice_ref_normalized": "1047",
    "amount": 1263.60,
    "due_date": "2026-10-16",
    "source_date": "2026-09-16",
    "counterparty_email": "vt444713@gmail.com",
    "pay_url": "",
}


def test_us_summary_block():
    msg = {
        "thread_id": "t1",
        "body": (
            "Invoice # : 1047\n"
            "Invoice Date: 09/16/2026\n"
            "Due Date: 10/16/2026\n"
            "Terms: Net 30\n"
            "Amount Due: $1,263.60\n"
        ),
        "subject": "Invoice 1047",
        "snippet": "",
    }
    assert ref_in_message(msg, INV)
    assert amount_in_message(msg, INV)
    assert date_in_hay(msg["body"], "2026-09-16")
    assert date_in_hay(msg["body"], "2026-10-16")


def test_uk_invoice_no_and_dd_mm():
    msg = {
        "thread_id": "t1",
        "body": "Invoice no : 1047\nInvoice Date: 16/09/2026\nDue Date: 16/10/2026\nAmount Due: £1,263.60",
        "subject": "",
        "snippet": "",
    }
    assert ref_in_message(msg, INV)
    assert amount_in_message(msg, INV)
    assert date_in_hay(msg["body"], "2026-09-16")
    assert date_in_hay(msg["body"], "2026-10-16")


def test_au_tax_invoice():
    msg = {
        "thread_id": "t1",
        "body": "Tax Invoice # : 1047\nAmount Due: A$1,263.60",
        "subject": "",
        "snippet": "",
    }
    assert ref_in_message(msg, INV)
    assert amount_in_message(msg, INV)


def test_html_table_not_dashed_block():
    msg = {
        "thread_id": "t1",
        "subject": "",
        "snippet": "",
        "body": (
            "Invoice no 1047 Quantity Rate Amount\n"
            "Design 1 1263.60 1,263.60\n"
            "Amount Due 1,263.60"
        ),
    }
    assert ref_in_message(msg, INV)
    assert amount_in_message(msg, INV)


def test_short_ref_needs_invoice_label():
    inv = {**INV, "invoice_ref": "7", "invoice_ref_normalized": "7"}
    labeled = {"thread_id": "a", "body": "Invoice # : 7", "subject": "", "snippet": ""}
    noise = {"thread_id": "b", "body": "see you at 7", "subject": "", "snippet": ""}
    assert ref_in_message(labeled, inv)
    assert not ref_in_message(noise, inv)


def test_104_does_not_steal_1047():
    other = {**INV, "invoice_ref": "104", "invoice_ref_normalized": "104"}
    msg = {"thread_id": "t1", "body": "Invoice # : 1047\nAmount Due: $1,263.60", "subject": "", "snippet": ""}
    assert ref_in_message(msg, INV)
    assert not ref_in_message(msg, other)


def test_waterfall_keeps_two_threads_same_invoice():
    send = {
        "id": "s",
        "thread_id": "t-send",
        "from": "me@studio.com",
        "to": "vt444713@gmail.com",
        "body": "Invoice # : 1047\nAmount Due: $1,263.60",
        "subject": "Invoice 1047",
        "snippet": "",
        "date": "Wed, 16 Sep 2026 10:00:00 +0000",
    }
    new_mail = {
        "id": "n",
        "thread_id": "t-new",
        "from": "vt444713@gmail.com",
        "to": "me@studio.com",
        "body": "Re invoice 1047 I think we agreed on $1200",
        "subject": "1047",
        "snippet": "",
        "date": "Wed, 16 Sep 2026 15:00:00 +0000",
    }
    lunch = {
        "id": "l",
        "thread_id": "t-lunch",
        "from": "vt444713@gmail.com",
        "to": "me@studio.com",
        "body": "Lunch tomorrow?",
        "subject": "Lunch",
        "snippet": "",
        "date": "Wed, 16 Sep 2026 16:00:00 +0000",
    }
    tids = set(waterfall_threads([send, new_mail, lunch], INV))
    assert tids == {"t-send", "t-new"}


def test_invoicelink_unique_wins():
    inv = {
        **INV,
        "pay_url": "https://connect.intuit.com/t/AbCdEfGh1234",
    }
    hit = {
        "id": "1",
        "thread_id": "t-pay",
        "body": "Pay here https://connect.intuit.com/t/AbCdEfGh1234",
        "subject": "hi",
        "snippet": "",
    }
    other = {
        "id": "2",
        "thread_id": "t-other",
        "body": "Invoice # : 1047 Amount Due: $1,263.60",
        "subject": "",
        "snippet": "",
    }
    assert waterfall_threads([hit, other], inv) == ["t-pay"]
    assert pay_url_token(inv["pay_url"]) == "AbCdEfGh1234"


def test_phase2_skips_known_thread():
    later = {
        "id": "n",
        "thread_id": "t-new",
        "body": "Invoice no : 1047",
        "subject": "",
        "snippet": "",
    }
    extras = extra_thread_ids([later], INV, known={"t-send"})
    assert extras == ["t-new"]
    assert extra_thread_ids([later], INV, known={"t-new"}) == []


def test_quoted_summary_in_reply_matches():
    msg = {
        "thread_id": "t-reply",
        "subject": "Re: Invoice 1047",
        "snippet": "",
        "body": (
            "We'll pay Friday.\n\n"
            "On Wed, 16 Sep 2026 at 10:00 QuickBooks wrote:\n"
            "> Invoice # : 1047\n"
            "> Amount Due: $1,263.60\n"
            "> Pay here https://connect.intuit.com/t/AbCdEfGh1234\n"
        ),
    }
    assert ref_in_message(msg, INV)
    assert amount_in_message(msg, INV)


def test_phase2_lunch_does_not_steal():
    lunch = {
        "id": "l",
        "thread_id": "t-lunch",
        "body": "Lunch tomorrow?",
        "subject": "Lunch",
        "snippet": "",
    }
    quote = {
        "id": "n",
        "thread_id": "t-new",
        "body": "Invoice no : 1047 — can we settle this?",
        "subject": "",
        "snippet": "",
    }
    assert extra_thread_ids([lunch], INV, known={"t-send"}) == []
    assert extra_thread_ids([lunch, quote], INV, known={"t-send"}) == ["t-new"]


def test_terms_omitted_still_matches():
    msg = {
        "thread_id": "t1",
        "body": "Invoice # : 1047\nDue Date: 10/16/2026\nAmount Due: $1,263.60",
        "subject": "",
        "snippet": "",
    }
    assert waterfall_threads([msg], INV) == ["t1"]
