"""Smoke test for _extract_and_write helper — validates dedup & routing."""
import asyncio, os, sys
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from scan_pipeline import _extract_and_write, _already_processed, reconcile_receipts

async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    user = await db.users.find_one({"email":"admin@scotive.com"})
    uid = user["_id"]
    my_email = "admin@scotive.com"
    now = "2026-07-03T00:00:00Z"

    # Cleanup previous test rows
    for coll in ("invoices","receipts","review_items","invoice_events"):
        await db[coll].delete_many({"user_id": uid, "source_message_id": {"$regex":"^sync-"}})

    # Case 1: invoice_sent → invoices
    inv_msg = {"id":"sync-1","thread_id":"t1","from":"admin@scotive.com","to":"client@acme.com","subject":"Invoice 42","date":"2026-06-01","body":""}
    inv_ext = {"is_money_related": True, "kind": "invoice_sent", "amount": 1200, "currency":"USD",
               "counterparty_email":"ap@acme.com","counterparty_name":"Acme Widgets",
               "invoice_ref":"INV-42","due_date":"2026-06-15","confidence": 0.9,
               "evidence_sentence":"Invoice 42 attached, due June 15."}
    r = await _extract_and_write(db, uid, inv_msg, inv_ext, my_email, now)
    assert r == (1,0,0), r

    # Case 2: same message again → no-op (dedup)
    r = await _extract_and_write(db, uid, inv_msg, inv_ext, my_email, now)
    assert r == (0,0,0), r

    # Case 3: receipt → receipts
    rc_msg = {"id":"sync-2","thread_id":"t2","from":"receipts@stripe.com","to":"admin@scotive.com","subject":"Payment received","date":"2026-06-16","body":""}
    rc_ext = {"is_money_related": True, "kind": "receipt", "amount": 1200,
              "counterparty_name":"Acme Widgets", "confidence": 0.95}
    r = await _extract_and_write(db, uid, rc_msg, rc_ext, my_email, now)
    assert r == (0,1,0), r

    # Case 4: low-confidence invoice → review_items
    low_msg = {"id":"sync-3","thread_id":"t3","from":"foo@bar.com","to":"admin@scotive.com","subject":"maybe an invoice","date":"2026-06-20","body":""}
    low_ext = {"is_money_related": True, "kind": "invoice_sent", "amount": 300,
               "counterparty_email":"foo@bar.com","confidence": 0.5}
    r = await _extract_and_write(db, uid, low_msg, low_ext, my_email, now)
    assert r == (0,0,1), r

    # Case 5: non-money → nothing
    r = await _extract_and_write(db, uid, {"id":"sync-4"}, {"is_money_related": False, "kind":"none"}, my_email, now)
    assert r == (0,0,0), r

    print("Basic writes: OK")

    # Reconcile: the $1200 receipt should match the $1200 Acme invoice
    result = await reconcile_receipts(db, uid)
    print("Reconcile:", result)

    inv = await db.invoices.find_one({"user_id": uid, "source_message_id":"sync-1"})
    print("Invoice after reconcile:", inv["status"], "balance:", inv["balance_remaining"])

    # _already_processed sanity check
    assert await _already_processed(db, uid, "sync-1") is True
    assert await _already_processed(db, uid, "sync-99") is False
    print("_already_processed: OK")

    # cleanup
    for coll in ("invoices","receipts","review_items","invoice_events"):
        await db[coll].delete_many({"user_id": uid, "source_message_id": {"$regex":"^sync-"}})
    await db.invoice_events.delete_many({"user_id": uid, "meta.receipt_id":{"$exists":True}})

asyncio.run(main())
