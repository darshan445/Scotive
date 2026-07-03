"""Smoke test: mark_paid → undo restores prior state."""
import asyncio, os, sys
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    user = await db.users.find_one({"email": "admin@scotive.com"})
    uid = user["_id"]

    await db.invoices.delete_many({"user_id": uid, "source_message_id": "test-undo"})
    await db.invoice_events.delete_many({"user_id": uid})

    inv_id = ObjectId()
    await db.invoices.insert_one({
        "_id": inv_id, "user_id": uid,
        "counterparty_email": "c@z.com", "counterparty_name": "Zed Co",
        "amount": 500.0, "balance_remaining": 500.0, "paid_amount": 0.0, "currency": "USD",
        "status": "invoiced", "kind": "invoice_sent",
        "source_message_id": "test-undo", "created_at": "2026-01-01T00:00:00Z",
    })

    # Simulate the /api/invoices/:id/action mark_paid + undo directly by importing the router
    # Instead we'll drive via HTTP:
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:8001") as c:
        r = await c.post("/api/auth/login", json={"email":"admin@scotive.com","password":"Admin@Scotive1"})
        cookies = r.cookies
        r = await c.post(f"/api/invoices/{inv_id}/action", json={"action":"mark_paid"}, cookies=cookies)
        print("mark_paid:", r.status_code, r.text)
        inv = await db.invoices.find_one({"_id": inv_id})
        print("  status after mark_paid:", inv["status"], "balance:", inv["balance_remaining"])
        r = await c.post(f"/api/invoices/{inv_id}/action", json={"action":"undo"}, cookies=cookies)
        print("undo:", r.status_code, r.text)
        inv = await db.invoices.find_one({"_id": inv_id})
        print("  status after undo:", inv["status"], "balance:", inv["balance_remaining"])

    await db.invoices.delete_many({"user_id": uid, "source_message_id": "test-undo"})
    await db.invoice_events.delete_many({"user_id": uid})

asyncio.run(main())
