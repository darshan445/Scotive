"""
Backend test for payment direction guardrails.
Tests _is_vendor, _extract_and_write, and _sender_domain functions directly.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, '/app/backend')

from motor.motor_asyncio import AsyncIOMotorClient
from scan_pipeline import _is_vendor, _extract_and_write, _sender_domain

# MongoDB connection
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Admin credentials
ADMIN_EMAIL = "admin@scotive.com"
ADMIN_PASSWORD = "Admin@Scotive1"

# Test results tracking
test_results = {
    "vendor_function_tests": [],
    "scenario_a": None,
    "scenario_b": None,
    "scenario_c": None,
    "scenario_d": None,
}


async def setup_admin_connection(db, admin_uid):
    """Seed gmail_connection for admin user."""
    existing = await db.gmail_connections.find_one({"user_id": admin_uid})
    if not existing:
        await db.gmail_connections.insert_one({
            "user_id": admin_uid,
            "email": ADMIN_EMAIL,
            "status": "connected",
            "can_send": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"✓ Seeded gmail_connection for {ADMIN_EMAIL}")
    else:
        print(f"✓ gmail_connection already exists for {ADMIN_EMAIL}")


async def get_admin_user_id(db):
    """Get admin user ID from database."""
    user = await db.users.find_one({"email": ADMIN_EMAIL})
    if not user:
        raise Exception(f"Admin user {ADMIN_EMAIL} not found in database")
    return user["_id"]


async def cleanup_test_data(db, admin_uid):
    """Remove all test data with source_message_id starting with 'guard-'."""
    collections = ["invoices", "receipts", "review_items"]
    total_deleted = 0
    for coll_name in collections:
        result = await db[coll_name].delete_many({
            "user_id": admin_uid,
            "source_message_id": {"$regex": "^guard-"}
        })
        if result.deleted_count > 0:
            print(f"  Cleaned {result.deleted_count} docs from {coll_name}")
            total_deleted += result.deleted_count
    return total_deleted


def test_is_vendor():
    """Test the _is_vendor function with various domains."""
    print("\n=== Testing _is_vendor() function ===")
    
    test_cases = [
        ("cloudflare.com", True, "cloudflare.com is in VENDOR_DOMAINS"),
        ("notify.cloudflare.com", True, "subdomain of cloudflare.com"),
        ("anthropic.com", True, "anthropic.com is in VENDOR_DOMAINS"),
        ("vultr.com", True, "vultr.com is in VENDOR_DOMAINS"),
        ("stripe.com", False, "stripe.com is a processor, not in VENDOR_DOMAINS"),
        ("acme.com", False, "acme.com is not a vendor"),
        ("", False, "empty string should return False"),
    ]
    
    all_passed = True
    for domain, expected, description in test_cases:
        result = _is_vendor(domain)
        passed = result == expected
        status = "✓" if passed else "✗"
        print(f"  {status} _is_vendor('{domain}') = {result} (expected {expected}) - {description}")
        test_results["vendor_function_tests"].append({
            "domain": domain,
            "expected": expected,
            "actual": result,
            "passed": passed,
            "description": description
        })
        if not passed:
            all_passed = False
    
    return all_passed


async def test_scenario_a(db, admin_uid, now_iso):
    """Scenario A: Vendor invoice should go to review_items, NOT invoices."""
    print("\n=== Scenario A: Vendor invoice (Cloudflare) ===")
    
    msg = {
        "id": "guard-1",
        "from": "noreply@notify.cloudflare.com",
        "to": ADMIN_EMAIL,
        "subject": "Payment failed",
        "thread_id": "t1",
        "date": "2026-06-28"
    }
    
    ext = {
        "is_money_related": True,
        "kind": "invoice_sent",
        "amount": 12.34,
        "currency": "USD",
        "counterparty_email": "noreply@notify.cloudflare.com",
        "counterparty_name": "Cloudflare",
        "invoice_ref": "IN-69681681",
        "due_date": "2026-06-28",
        "confidence": 0.9,
        "evidence_sentence": "Outstanding balance: $12.34"
    }
    
    # Call _extract_and_write
    result = await _extract_and_write(db, admin_uid, msg, ext, ADMIN_EMAIL, now_iso)
    print(f"  Return value: {result}")
    
    # Check database state
    invoice_count = await db.invoices.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-1"
    })
    
    review_count = await db.review_items.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-1"
    })
    
    review_doc = await db.review_items.find_one({
        "user_id": admin_uid,
        "source_message_id": "guard-1"
    })
    
    review_reason = review_doc.get("review_reason") if review_doc else None
    
    print(f"  Invoices collection: {invoice_count} docs")
    print(f"  Review_items collection: {review_count} docs")
    print(f"  Review reason: {review_reason}")
    
    # Verify expectations
    expected_return = (0, 0, 1)
    passed = (
        result == expected_return and
        invoice_count == 0 and
        review_count == 1 and
        review_reason == "vendor_domain"
    )
    
    status = "✓ PASSED" if passed else "✗ FAILED"
    print(f"  {status}")
    
    test_results["scenario_a"] = {
        "passed": passed,
        "return_value": result,
        "expected_return": expected_return,
        "invoice_count": invoice_count,
        "review_count": review_count,
        "review_reason": review_reason
    }
    
    return passed


async def test_scenario_b(db, admin_uid, now_iso):
    """Scenario B: Stripe receipt (not a vendor) should be inserted as receipt."""
    print("\n=== Scenario B: Stripe receipt (processor, not vendor) ===")
    
    msg = {
        "id": "guard-2",
        "from": "receipts@stripe.com",
        "to": ADMIN_EMAIL,
        "subject": "Anthropic charge",
        "thread_id": "t2",
        "date": "2026-06-22"
    }
    
    ext = {
        "is_money_related": True,
        "kind": "receipt",
        "amount": 23.60,
        "counterparty_name": "Anthropic, PBC",
        "confidence": 0.9
    }
    
    # Call _extract_and_write
    result = await _extract_and_write(db, admin_uid, msg, ext, ADMIN_EMAIL, now_iso)
    print(f"  Return value: {result}")
    
    # Check database state
    receipt_count = await db.receipts.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-2"
    })
    
    invoice_count = await db.invoices.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-2"
    })
    
    review_count = await db.review_items.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-2"
    })
    
    print(f"  Receipts collection: {receipt_count} docs")
    print(f"  Invoices collection: {invoice_count} docs")
    print(f"  Review_items collection: {review_count} docs")
    
    # Verify expectations
    expected_return = (0, 1, 0)
    passed = (
        result == expected_return and
        receipt_count == 1 and
        invoice_count == 0 and
        review_count == 0
    )
    
    status = "✓ PASSED" if passed else "✗ FAILED"
    print(f"  {status}")
    
    test_results["scenario_b"] = {
        "passed": passed,
        "return_value": result,
        "expected_return": expected_return,
        "receipt_count": receipt_count,
        "invoice_count": invoice_count,
        "review_count": review_count
    }
    
    return passed


async def test_scenario_c(db, admin_uid, now_iso):
    """Scenario C: Self-invoice should be dropped entirely."""
    print("\n=== Scenario C: Self-invoice (should be dropped) ===")
    
    msg = {
        "id": "guard-3",
        "from": ADMIN_EMAIL,
        "to": ADMIN_EMAIL,
        "subject": "note to self",
        "thread_id": "t3",
        "date": "2026-07-01"
    }
    
    ext = {
        "is_money_related": True,
        "kind": "invoice_sent",
        "amount": 189.0,
        "currency": "USD",
        "counterparty_email": ADMIN_EMAIL,
        "counterparty_name": "Me",
        "invoice_ref": "self",
        "confidence": 0.9
    }
    
    # Call _extract_and_write
    result = await _extract_and_write(db, admin_uid, msg, ext, ADMIN_EMAIL, now_iso)
    print(f"  Return value: {result}")
    
    # Check database state
    invoice_count = await db.invoices.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-3"
    })
    
    receipt_count = await db.receipts.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-3"
    })
    
    review_count = await db.review_items.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-3"
    })
    
    print(f"  Invoices collection: {invoice_count} docs")
    print(f"  Receipts collection: {receipt_count} docs")
    print(f"  Review_items collection: {review_count} docs")
    
    # Verify expectations
    expected_return = (0, 0, 0)
    passed = (
        result == expected_return and
        invoice_count == 0 and
        receipt_count == 0 and
        review_count == 0
    )
    
    status = "✓ PASSED" if passed else "✗ FAILED"
    print(f"  {status}")
    
    test_results["scenario_c"] = {
        "passed": passed,
        "return_value": result,
        "expected_return": expected_return,
        "invoice_count": invoice_count,
        "receipt_count": receipt_count,
        "review_count": review_count
    }
    
    return passed


async def test_scenario_d(db, admin_uid, now_iso):
    """Scenario D: Real client invoice should go to invoices normally."""
    print("\n=== Scenario D: Real client invoice (Northbeam) ===")
    
    msg = {
        "id": "guard-4",
        "from": ADMIN_EMAIL,
        "to": "ap@northbeam.com",
        "subject": "Invoice NB-102",
        "thread_id": "t4",
        "date": "2026-06-15"
    }
    
    ext = {
        "is_money_related": True,
        "kind": "invoice_sent",
        "amount": 6200.0,
        "currency": "USD",
        "counterparty_email": "ap@northbeam.com",
        "counterparty_name": "Northbeam Studio",
        "invoice_ref": "NB-102",
        "due_date": "2026-06-30",
        "confidence": 0.9,
        "evidence_sentence": "Please remit $6,200 by June 30."
    }
    
    # Call _extract_and_write
    result = await _extract_and_write(db, admin_uid, msg, ext, ADMIN_EMAIL, now_iso)
    print(f"  Return value: {result}")
    
    # Check database state
    invoice_count = await db.invoices.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-4"
    })
    
    invoice_doc = await db.invoices.find_one({
        "user_id": admin_uid,
        "source_message_id": "guard-4"
    })
    
    status_val = invoice_doc.get("status") if invoice_doc else None
    balance_val = invoice_doc.get("balance_remaining") if invoice_doc else None
    
    receipt_count = await db.receipts.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-4"
    })
    
    review_count = await db.review_items.count_documents({
        "user_id": admin_uid,
        "source_message_id": "guard-4"
    })
    
    print(f"  Invoices collection: {invoice_count} docs")
    print(f"  Invoice status: {status_val}")
    print(f"  Invoice balance_remaining: {balance_val}")
    print(f"  Receipts collection: {receipt_count} docs")
    print(f"  Review_items collection: {review_count} docs")
    
    # Verify expectations
    expected_return = (1, 0, 0)
    passed = (
        result == expected_return and
        invoice_count == 1 and
        status_val == "invoiced" and
        balance_val == 6200.0 and
        receipt_count == 0 and
        review_count == 0
    )
    
    status = "✓ PASSED" if passed else "✗ FAILED"
    print(f"  {status}")
    
    test_results["scenario_d"] = {
        "passed": passed,
        "return_value": result,
        "expected_return": expected_return,
        "invoice_count": invoice_count,
        "invoice_status": status_val,
        "invoice_balance": balance_val,
        "receipt_count": receipt_count,
        "review_count": review_count
    }
    
    return passed


async def main():
    """Main test runner."""
    print("=" * 70)
    print("PAYMENT DIRECTION GUARDRAILS TEST")
    print("=" * 70)
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    try:
        # Get admin user ID
        print(f"\nConnecting to MongoDB: {MONGO_URL}/{DB_NAME}")
        admin_uid = await get_admin_user_id(db)
        print(f"✓ Found admin user: {ADMIN_EMAIL} (ID: {admin_uid})")
        
        # Setup gmail connection
        await setup_admin_connection(db, admin_uid)
        
        # Clean up any existing test data
        print("\nCleaning up any existing test data...")
        deleted = await cleanup_test_data(db, admin_uid)
        if deleted > 0:
            print(f"✓ Cleaned up {deleted} existing test docs")
        else:
            print("✓ No existing test data found")
        
        # Test _is_vendor function
        vendor_tests_passed = test_is_vendor()
        
        # Run scenarios
        now_iso = datetime.now(timezone.utc).isoformat()
        
        scenario_a_passed = await test_scenario_a(db, admin_uid, now_iso)
        scenario_b_passed = await test_scenario_b(db, admin_uid, now_iso)
        scenario_c_passed = await test_scenario_c(db, admin_uid, now_iso)
        scenario_d_passed = await test_scenario_d(db, admin_uid, now_iso)
        
        # Cleanup test data
        print("\n=== Cleanup ===")
        deleted = await cleanup_test_data(db, admin_uid)
        print(f"✓ Cleaned up {deleted} test docs")
        
        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        all_vendor_tests_passed = all(t["passed"] for t in test_results["vendor_function_tests"])
        print(f"_is_vendor() tests: {'✓ ALL PASSED' if all_vendor_tests_passed else '✗ SOME FAILED'}")
        
        scenarios = [
            ("Scenario A (Vendor invoice → review_items)", scenario_a_passed),
            ("Scenario B (Stripe receipt → receipts)", scenario_b_passed),
            ("Scenario C (Self-invoice → dropped)", scenario_c_passed),
            ("Scenario D (Real client → invoices)", scenario_d_passed),
        ]
        
        for name, passed in scenarios:
            status = "✓ PASSED" if passed else "✗ FAILED"
            print(f"{name}: {status}")
        
        all_passed = all_vendor_tests_passed and all([p for _, p in scenarios])
        
        print("\n" + "=" * 70)
        if all_passed:
            print("✓✓✓ ALL TESTS PASSED ✓✓✓")
        else:
            print("✗✗✗ SOME TESTS FAILED ✗✗✗")
        print("=" * 70)
        
        return 0 if all_passed else 1
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
