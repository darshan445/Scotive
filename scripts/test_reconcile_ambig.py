"""Ambiguity smoke test for receipt reconciliation."""
import asyncio, os, sys
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from scan_pipeline import reconcile_receipts

async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    user = await db.users.find_one({"email": "admin@scotive.com"})
    uid = user["_id"]

    await db.invoices.delete_many({"user_id": uid, "source_message_id": {"$regex": "^test-"}})
    await db.receipts.delete_many({"user_id": uid, "source_message_id": {"$regex": "^test-"}})

    await db.invoices.insert_one({
        "user_id": uid, "counterparty_email": "a@x.com", "counterparty_name": "Acme Widgets",
        "amount": 800.0, "balance_remaining": 800.0, "paid_amount": 0.0, "currency": "USD",
        "invoice_ref": "INV-A", "status": "invoiced", "kind": "invoice_sent",
        "source_message_id": "test-inv-a", "created_at": "2026-01-01T00:00:00Z",
    })
    await db.invoices.insert_one({
        "user_id": uid, "counterparty_email": "b@y.com", "counterparty_name": "Acme Widgets",
        "amount": 800.0, "balance_remaining": 800.0, "paid_amount": 0.0, "currency": "USD",
        "invoice_ref": "INV-B", "status": "invoiced", "kind": "invoice_sent",
        "source_message_id": "test-inv-b", "created_at": "2026-01-02T00:00:00Z",
    })
    await db.receipts.insert_one({
        "user_id": uid, "amount": 800.0, "payer_name": "Acme Widgets", "match_status": "unmatched",
        "processor_from": "receipts@stripe.com", "source_message_id": "test-rc-1",
        "matched_invoice_id": None, "candidate_invoice_ids": [],
        "source_date": "2026-02-01T00:00:00Z",
    })

    result = await reconcile_receipts(db, uid)
    print("Result:", result)
    async for rc in db.receipts.find({"user_id": uid, "source_message_id": "test-rc-1"}):
        print(f"  Receipt -> status={rc['match_status']} candidates={rc.get('candidate_invoice_ids')}")

    await db.invoices.delete_many({"user_id": uid, "source_message_id": {"$regex": "^test-"}})
    await db.receipts.delete_many({"user_id": uid, "source_message_id": {"$regex": "^test-"}})

asyncio.run(main())
