"""One-shot backfill: move vendor-billed and self-invoiced rows out of the
ledger for the affected user. Run once after F9d bug fix.

Semantics:
  - Any invoice whose source_from is a vendor domain (Cloudflare, Vultr, etc.)
    → move to review_items with review_reason="vendor_domain_backfill"
    → delete from invoices.
  - Any invoice whose counterparty_email is the user's own gmail
    → delete from invoices (self-invoice).
  - Any receipt whose payer_name looks like the user themselves (contains their
    email or their name from the gmail account) → set match_status="rejected".
"""
import asyncio, os, sys
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from scan_pipeline import _is_vendor, _sender_domain, _extract_email_addr


async def cleanup_user(db, user_id) -> dict:
    conn = await db.gmail_connections.find_one({"user_id": user_id})
    my_email = ((conn or {}).get("email") or "").lower()
    my_domain = _sender_domain(my_email)
    stats = {"invoices_moved_to_review": 0, "invoices_deleted_self": 0,
             "receipts_rejected_self": 0, "user_email": my_email}
    async for inv in db.invoices.find({"user_id": user_id}):
        src_from = inv.get("source_from") or inv.get("counterparty_email") or ""
        src_email = _extract_email_addr(src_from).lower()
        src_domain = _sender_domain(src_email)
        cp_email = (inv.get("counterparty_email") or "").lower()
        cp_domain = _sender_domain(cp_email)

        # Vendor-billed inbound
        if _is_vendor(src_domain) or _is_vendor(cp_domain):
            await db.review_items.update_one(
                {"user_id": user_id, "source_message_id": inv.get("source_message_id")},
                {"$set": {
                    **{k: v for k, v in inv.items() if k not in ("_id",)},
                    "review_status": "pending",
                    "review_reason": "vendor_domain_backfill",
                }},
                upsert=True,
            )
            await db.invoices.delete_one({"_id": inv["_id"]})
            stats["invoices_moved_to_review"] += 1
            continue

        # Self-invoice
        if my_email and (cp_email == my_email or (my_domain and cp_domain == my_domain)):
            await db.invoices.delete_one({"_id": inv["_id"]})
            stats["invoices_deleted_self"] += 1
            continue

    async for rc in db.receipts.find({"user_id": user_id}):
        payer = (rc.get("payer_name") or "").lower()
        if my_email and (my_email in payer or (my_domain and my_domain in payer)):
            await db.receipts.update_one({"_id": rc["_id"]}, {"$set": {"match_status": "rejected"}})
            stats["receipts_rejected_self"] += 1
    return stats


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    async for u in db.users.find({}):
        stats = await cleanup_user(db, u["_id"])
        if any(v for k, v in stats.items() if k not in ("user_email",)):
            print(u.get("email"), "→", stats)


if __name__ == "__main__":
    asyncio.run(main())
