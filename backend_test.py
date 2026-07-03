"""
Backend test for POST /api/invoices/manual endpoint.
Tests all 8 scenarios specified in the test plan.
"""
import asyncio
import os
import sys
import json
from datetime import datetime, timezone, timedelta

# Add backend to path
sys.path.insert(0, '/app/backend')

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# Base URL - using localhost as specified in review request
BASE_URL = "http://localhost:8001"

# MongoDB connection
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Admin credentials
ADMIN_EMAIL = "admin@scotive.com"
ADMIN_PASSWORD = "Admin@Scotive1"

# Test results tracking
test_results = {
    "test_1_happy_path": None,
    "test_2_past_due": None,
    "test_3_promise_date": None,
    "test_4_self_invoice": None,
    "test_5_bad_email": None,
    "test_6_amount_zero": None,
    "test_7_ledger_reflects": None,
    "test_8_timeline": None,
}


async def login_admin(client: httpx.AsyncClient):
    """Login as admin and return access token."""
    print(f"\n=== Logging in as {ADMIN_EMAIL} ===")
    
    response = await client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if response.status_code != 200:
        raise Exception(f"Login failed: {response.status_code} - {response.text}")
    
    data = response.json()
    access_token = data.get("access_token")
    
    if not access_token:
        raise Exception(f"No access_token in login response: {data}")
    
    print(f"✓ Login successful")
    return access_token


async def seed_gmail_connection(db, admin_uid):
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
    """Remove all test data created during testing."""
    print("\n=== Cleanup ===")
    
    # Delete manual invoices with testclient email
    invoice_result = await db.invoices.delete_many({
        "user_id": admin_uid,
        "source": "manual",
        "counterparty_email": {"$regex": "testclient"}
    })
    print(f"  Deleted {invoice_result.deleted_count} manual invoices")
    
    # Delete invoice_events for manual_add action
    events_result = await db.invoice_events.delete_many({
        "user_id": admin_uid,
        "action": "manual_add"
    })
    print(f"  Deleted {events_result.deleted_count} manual_add events")
    
    # Remove seeded gmail_connection (optional - keep it for future tests)
    # await db.gmail_connections.delete_one({"user_id": admin_uid, "email": ADMIN_EMAIL})
    
    return invoice_result.deleted_count + events_result.deleted_count


async def test_1_happy_path(client: httpx.AsyncClient, db, admin_uid, token):
    """Test 1: Happy path - valid invoice with future due date."""
    print("\n=== Test 1: Happy path - valid invoice with future due date ===")
    
    payload = {
        "counterparty_email": "billing@testclient.com",
        "counterparty_name": "Test Client",
        "amount": 1250.50,
        "currency": "USD",
        "invoice_ref": "TST-1",
        "due_date": "2027-01-15",
        "note": "test"
    }
    
    response = await client.post(
        f"{BASE_URL}/api/invoices/manual",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"  Status code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"  ✗ FAILED: Expected 200, got {response.status_code}")
        print(f"  Response: {response.text}")
        test_results["test_1_happy_path"] = {
            "passed": False,
            "status_code": response.status_code,
            "error": response.text
        }
        return False
    
    data = response.json()
    print(f"  Response: {json.dumps(data, indent=2)}")
    
    # Verify response structure
    invoice = data.get("invoice", {})
    invoice_id = invoice.get("_id")
    
    checks = {
        "has_invoice_id": invoice_id is not None,
        "status_is_invoiced": invoice.get("status") == "invoiced",
        "source_is_manual": invoice.get("source") == "manual",
        "balance_remaining_correct": invoice.get("balance_remaining") == 1250.50,
        "paid_amount_zero": invoice.get("paid_amount") == 0.0,
    }
    
    all_passed = all(checks.values())
    
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}")
    
    # Store invoice_id for test 8
    if invoice_id:
        test_results["test_1_invoice_id"] = invoice_id
    
    status = "✓ PASSED" if all_passed else "✗ FAILED"
    print(f"  {status}")
    
    test_results["test_1_happy_path"] = {
        "passed": all_passed,
        "status_code": response.status_code,
        "invoice_id": invoice_id,
        "checks": checks
    }
    
    return all_passed


async def test_2_past_due(client: httpx.AsyncClient, db, admin_uid, token):
    """Test 2: Past-due date - status should be 'overdue'."""
    print("\n=== Test 2: Past-due date - status should be 'overdue' ===")
    
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    
    payload = {
        "counterparty_email": "billing@testclient.com",
        "counterparty_name": "Test Client",
        "amount": 1250.50,
        "currency": "USD",
        "invoice_ref": "TST-2",
        "due_date": yesterday,
        "note": "test overdue"
    }
    
    response = await client.post(
        f"{BASE_URL}/api/invoices/manual",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"  Status code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"  ✗ FAILED: Expected 200, got {response.status_code}")
        print(f"  Response: {response.text}")
        test_results["test_2_past_due"] = {
            "passed": False,
            "status_code": response.status_code,
            "error": response.text
        }
        return False
    
    data = response.json()
    invoice = data.get("invoice", {})
    status = invoice.get("status")
    
    print(f"  Invoice status: {status}")
    
    passed = status == "overdue"
    result_status = "✓ PASSED" if passed else "✗ FAILED"
    print(f"  {result_status}")
    
    test_results["test_2_past_due"] = {
        "passed": passed,
        "status_code": response.status_code,
        "invoice_status": status
    }
    
    return passed


async def test_3_promise_date(client: httpx.AsyncClient, db, admin_uid, token):
    """Test 3: Promise date set - status should be 'promised'."""
    print("\n=== Test 3: Promise date set - status should be 'promised' ===")
    
    future_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
    
    payload = {
        "counterparty_email": "billing@testclient.com",
        "counterparty_name": "Test Client",
        "amount": 1250.50,
        "currency": "USD",
        "invoice_ref": "TST-3",
        "promise_date": future_date,
        "note": "test promise"
    }
    
    response = await client.post(
        f"{BASE_URL}/api/invoices/manual",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"  Status code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"  ✗ FAILED: Expected 200, got {response.status_code}")
        print(f"  Response: {response.text}")
        test_results["test_3_promise_date"] = {
            "passed": False,
            "status_code": response.status_code,
            "error": response.text
        }
        return False
    
    data = response.json()
    invoice = data.get("invoice", {})
    status = invoice.get("status")
    
    print(f"  Invoice status: {status}")
    
    passed = status == "promised"
    result_status = "✓ PASSED" if passed else "✗ FAILED"
    print(f"  {result_status}")
    
    test_results["test_3_promise_date"] = {
        "passed": passed,
        "status_code": response.status_code,
        "invoice_status": status
    }
    
    return passed


async def test_4_self_invoice(client: httpx.AsyncClient, db, admin_uid, token):
    """Test 4: Self-invoice rejection - should return 400."""
    print("\n=== Test 4: Self-invoice rejection - should return 400 ===")
    
    payload = {
        "counterparty_email": ADMIN_EMAIL,
        "counterparty_name": "Self",
        "amount": 1250.50,
        "currency": "USD",
        "invoice_ref": "TST-4",
        "note": "self invoice"
    }
    
    response = await client.post(
        f"{BASE_URL}/api/invoices/manual",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"  Status code: {response.status_code}")
    
    if response.status_code == 400:
        data = response.json()
        detail = data.get("detail", "")
        print(f"  Error detail: {detail}")
        
        passed = "invoice your own connected" in detail.lower()
        result_status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {result_status}")
        
        test_results["test_4_self_invoice"] = {
            "passed": passed,
            "status_code": response.status_code,
            "detail": detail
        }
        
        return passed
    else:
        print(f"  ✗ FAILED: Expected 400, got {response.status_code}")
        test_results["test_4_self_invoice"] = {
            "passed": False,
            "status_code": response.status_code,
            "error": "Expected 400 status code"
        }
        return False


async def test_5_bad_email(client: httpx.AsyncClient, db, admin_uid, token):
    """Test 5: Bad email (no @) - should return 400."""
    print("\n=== Test 5: Bad email (no @) - should return 400 ===")
    
    payload = {
        "counterparty_email": "notanemail",
        "counterparty_name": "Test Client",
        "amount": 1250.50,
        "currency": "USD",
        "invoice_ref": "TST-5",
        "note": "bad email"
    }
    
    response = await client.post(
        f"{BASE_URL}/api/invoices/manual",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"  Status code: {response.status_code}")
    
    if response.status_code == 400:
        data = response.json()
        detail = data.get("detail", "")
        print(f"  Error detail: {detail}")
        
        passed = "must include an @" in detail.lower()
        result_status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {result_status}")
        
        test_results["test_5_bad_email"] = {
            "passed": passed,
            "status_code": response.status_code,
            "detail": detail
        }
        
        return passed
    else:
        print(f"  ✗ FAILED: Expected 400, got {response.status_code}")
        test_results["test_5_bad_email"] = {
            "passed": False,
            "status_code": response.status_code,
            "error": "Expected 400 status code"
        }
        return False


async def test_6_amount_zero(client: httpx.AsyncClient, db, admin_uid, token):
    """Test 6: Amount <= 0 - should return 422 (Pydantic validation)."""
    print("\n=== Test 6: Amount <= 0 - should return 422 ===")
    
    payload = {
        "counterparty_email": "billing@testclient.com",
        "counterparty_name": "Test Client",
        "amount": 0,
        "currency": "USD",
        "invoice_ref": "TST-6",
        "note": "zero amount"
    }
    
    response = await client.post(
        f"{BASE_URL}/api/invoices/manual",
        json=payload,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    print(f"  Status code: {response.status_code}")
    
    if response.status_code == 422:
        data = response.json()
        print(f"  Validation error: {json.dumps(data, indent=2)}")
        
        passed = True
        result_status = "✓ PASSED"
        print(f"  {result_status}")
        
        test_results["test_6_amount_zero"] = {
            "passed": passed,
            "status_code": response.status_code,
            "detail": data
        }
        
        return passed
    else:
        print(f"  ✗ FAILED: Expected 422, got {response.status_code}")
        test_results["test_6_amount_zero"] = {
            "passed": False,
            "status_code": response.status_code,
            "error": "Expected 422 status code"
        }
        return False


async def test_7_ledger_reflects(client: httpx.AsyncClient, db, admin_uid):
    """Test 7: Ledger reflects manual invoices."""
    print("\n=== Test 7: Ledger reflects manual invoices ===")
    
    response = await client.get(f"{BASE_URL}/api/ledger")
    
    print(f"  Status code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"  ✗ FAILED: Expected 200, got {response.status_code}")
        test_results["test_7_ledger_reflects"] = {
            "passed": False,
            "status_code": response.status_code,
            "error": response.text
        }
        return False
    
    data = response.json()
    invoices = data.get("invoices", [])
    total_open = data.get("total_open", 0)
    
    # Count manual invoices with testclient email
    manual_invoices = [inv for inv in invoices if inv.get("source") == "manual" and "testclient" in inv.get("counterparty_email", "")]
    
    print(f"  Total invoices: {len(invoices)}")
    print(f"  Manual test invoices: {len(manual_invoices)}")
    print(f"  Total open: ${total_open}")
    
    # We should have at least 3 manual invoices from tests 1, 2, 3
    passed = len(manual_invoices) >= 3
    
    result_status = "✓ PASSED" if passed else "✗ FAILED"
    print(f"  {result_status}")
    
    test_results["test_7_ledger_reflects"] = {
        "passed": passed,
        "status_code": response.status_code,
        "manual_invoice_count": len(manual_invoices),
        "total_open": total_open
    }
    
    return passed


async def test_8_timeline(client: httpx.AsyncClient, db, admin_uid):
    """Test 8: Timeline lookup on manual invoice shows manual_add event."""
    print("\n=== Test 8: Timeline lookup on manual invoice ===")
    
    # Use invoice_id from test 1
    invoice_id = test_results.get("test_1_invoice_id")
    
    if not invoice_id:
        print("  ✗ FAILED: No invoice_id from test 1")
        test_results["test_8_timeline"] = {
            "passed": False,
            "error": "No invoice_id from test 1"
        }
        return False
    
    response = await client.get(f"{BASE_URL}/api/invoices/{invoice_id}/timeline")
    
    print(f"  Status code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"  ✗ FAILED: Expected 200, got {response.status_code}")
        print(f"  Response: {response.text}")
        test_results["test_8_timeline"] = {
            "passed": False,
            "status_code": response.status_code,
            "error": response.text
        }
        return False
    
    data = response.json()
    events = data.get("events", [])
    
    print(f"  Total events: {len(events)}")
    
    # Find manual_add event
    manual_add_events = [e for e in events if e.get("kind") == "manual_add"]
    
    if not manual_add_events:
        print("  ✗ FAILED: No manual_add event found")
        test_results["test_8_timeline"] = {
            "passed": False,
            "status_code": response.status_code,
            "error": "No manual_add event found",
            "events": events
        }
        return False
    
    manual_event = manual_add_events[0]
    meta = manual_event.get("meta", {})
    amount = meta.get("amount")
    
    print(f"  Manual add event found:")
    print(f"    Amount: {amount}")
    print(f"    Meta: {json.dumps(meta, indent=4)}")
    
    # Verify amount matches
    passed = amount == 1250.50
    
    result_status = "✓ PASSED" if passed else "✗ FAILED"
    print(f"  {result_status}")
    
    test_results["test_8_timeline"] = {
        "passed": passed,
        "status_code": response.status_code,
        "manual_event": manual_event
    }
    
    return passed


async def main():
    """Main test runner."""
    print("=" * 70)
    print("POST /api/invoices/manual ENDPOINT TEST")
    print("=" * 70)
    
    # Connect to MongoDB
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    db = mongo_client[DB_NAME]
    
    try:
        # Get admin user ID
        print(f"\nConnecting to MongoDB: {MONGO_URL}/{DB_NAME}")
        admin_uid = await get_admin_user_id(db)
        print(f"✓ Found admin user: {ADMIN_EMAIL} (ID: {admin_uid})")
        
        # Seed gmail connection
        await seed_gmail_connection(db, admin_uid)
        
        # Create HTTP client
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Login
            cookies = await login_admin(client)
            
            # Run all tests
            test_1_passed = await test_1_happy_path(client, db, admin_uid)
            test_2_passed = await test_2_past_due(client, db, admin_uid)
            test_3_passed = await test_3_promise_date(client, db, admin_uid)
            test_4_passed = await test_4_self_invoice(client, db, admin_uid)
            test_5_passed = await test_5_bad_email(client, db, admin_uid)
            test_6_passed = await test_6_amount_zero(client, db, admin_uid)
            test_7_passed = await test_7_ledger_reflects(client, db, admin_uid)
            test_8_passed = await test_8_timeline(client, db, admin_uid)
        
        # Cleanup
        await cleanup_test_data(db, admin_uid)
        
        # Summary
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        
        tests = [
            ("Test 1: Happy path (future due date)", test_1_passed),
            ("Test 2: Past-due date (status=overdue)", test_2_passed),
            ("Test 3: Promise date (status=promised)", test_3_passed),
            ("Test 4: Self-invoice rejection (400)", test_4_passed),
            ("Test 5: Bad email (400)", test_5_passed),
            ("Test 6: Amount <= 0 (422)", test_6_passed),
            ("Test 7: Ledger reflects manual invoices", test_7_passed),
            ("Test 8: Timeline shows manual_add event", test_8_passed),
        ]
        
        for name, passed in tests:
            status = "✓ PASSED" if passed else "✗ FAILED"
            print(f"{name}: {status}")
        
        all_passed = all([p for _, p in tests])
        
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
        mongo_client.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
