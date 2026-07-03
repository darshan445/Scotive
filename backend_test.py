#!/usr/bin/env python3
"""
Backend test for GET /api/invoices/:id/timeline ObjectId serialization fix.

Tests three scenarios:
1. Paid invoice with receipt_matched event (meta.receipt_id as BSON ObjectId) - the crash case
2. Overdue invoice with no receipt_matched - regression check
3. Edge case with ObjectId in other meta keys
"""
import os
import sys
import requests
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient

# Configuration
BASE_URL = "https://partial-pay-1.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@scotive.com"
ADMIN_PASSWORD = "Admin@Scotive1"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

# Test data markers
TEST_SOURCE_PREFIX = "test-tl-"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def log(msg, color=None):
    if color:
        print(f"{color}{msg}{Colors.END}")
    else:
        print(msg)

def cleanup_test_data(db, admin_user_id):
    """Remove all test data created during this test run."""
    log("\n🧹 Cleaning up test data...", Colors.BLUE)
    
    # Find test invoices
    test_invoices = list(db.invoices.find({
        "user_id": admin_user_id,
        "source_message_id": {"$regex": f"^{TEST_SOURCE_PREFIX}"}
    }))
    test_invoice_ids = [inv["_id"] for inv in test_invoices]
    
    # Delete test receipts
    receipts_deleted = db.receipts.delete_many({
        "user_id": admin_user_id,
        "source_message_id": {"$regex": f"^{TEST_SOURCE_PREFIX}"}
    }).deleted_count
    
    # Delete test invoice_events
    events_deleted = db.invoice_events.delete_many({
        "user_id": admin_user_id,
        "invoice_id": {"$in": test_invoice_ids}
    }).deleted_count
    
    # Delete test invoices
    invoices_deleted = db.invoices.delete_many({
        "_id": {"$in": test_invoice_ids}
    }).deleted_count
    
    log(f"   Deleted: {invoices_deleted} invoices, {receipts_deleted} receipts, {events_deleted} events", Colors.BLUE)

def authenticate():
    """Authenticate as admin and return session with cookies."""
    log("\n🔐 Authenticating as admin...", Colors.BLUE)
    session = requests.Session()
    
    response = session.post(
        f"{API_BASE}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    
    if response.status_code != 200:
        log(f"❌ Authentication failed: {response.status_code} - {response.text}", Colors.RED)
        sys.exit(1)
    
    data = response.json()
    user_id = data.get("id")
    if not user_id:
        log(f"❌ No user ID in response: {data}", Colors.RED)
        sys.exit(1)
    log(f"   ✓ Authenticated as {ADMIN_EMAIL} (user_id: {user_id})", Colors.GREEN)
    return session, user_id

def test_scenario_1(session, db, admin_user_id):
    """
    Scenario 1: Paid invoice with receipt_matched event containing BSON ObjectId.
    This is the exact case that was crashing before the fix.
    """
    log("\n" + "="*80, Colors.BLUE)
    log("TEST 1: Paid invoice with receipt_matched event (ObjectId in meta)", Colors.BLUE)
    log("="*80, Colors.BLUE)
    
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Create invoice
    invoice_doc = {
        "user_id": ObjectId(admin_user_id),
        "status": "paid",
        "amount": 24.0,
        "balance_remaining": 0.4,
        "paid_amount": 23.6,
        "currency": "USD",
        "counterparty_email": "billing@vultr.com",
        "counterparty_name": "Vultr",
        "source_message_id": f"{TEST_SOURCE_PREFIX}1",
        "created_at": now_iso,
        "paid_at": now_iso,
    }
    invoice_result = db.invoices.insert_one(invoice_doc)
    invoice_id = invoice_result.inserted_id
    log(f"   Created invoice: {invoice_id}", Colors.BLUE)
    
    # Create receipt
    receipt_doc = {
        "user_id": ObjectId(admin_user_id),
        "amount": 23.6,
        "payer_name": "Anthropic, PBC",
        "match_status": "matched",
        "matched_invoice_id": invoice_id,
        "applied_amount": 23.6,
        "source_message_id": f"{TEST_SOURCE_PREFIX}rc-1",
        "processor_from": "receipts@stripe.com",
        "source_date": "2026-06-22T05:48:27Z",
        "created_at": now_iso,
    }
    receipt_result = db.receipts.insert_one(receipt_doc)
    receipt_id = receipt_result.inserted_id
    log(f"   Created receipt: {receipt_id}", Colors.BLUE)
    
    # Create invoice_event with BSON ObjectId in meta - THIS IS THE CRASH CASE
    event_doc = {
        "user_id": ObjectId(admin_user_id),
        "invoice_id": invoice_id,  # BSON ObjectId
        "action": "receipt_matched",
        "at": now_iso,
        "meta": {
            "receipt_id": receipt_id,  # BSON ObjectId - this was causing the crash!
            "amount": 23.6,
            "balance_after": 0.4,
            "payer_name": "Anthropic, PBC",
            "score": 0.7
        }
    }
    db.invoice_events.insert_one(event_doc)
    log(f"   Created invoice_event with ObjectId in meta.receipt_id", Colors.BLUE)
    
    # Test the timeline endpoint
    log(f"\n   Testing GET /api/invoices/{invoice_id}/timeline...", Colors.YELLOW)
    response = session.get(f"{API_BASE}/invoices/{invoice_id}/timeline")
    
    # Validate response
    if response.status_code != 200:
        log(f"   ❌ FAILED: Expected HTTP 200, got {response.status_code}", Colors.RED)
        log(f"   Response: {response.text[:500]}", Colors.RED)
        return False
    
    log(f"   ✓ HTTP 200 OK", Colors.GREEN)
    
    try:
        data = response.json()
    except Exception as e:
        log(f"   ❌ FAILED: Response is not valid JSON: {e}", Colors.RED)
        log(f"   Response: {response.text[:500]}", Colors.RED)
        return False
    
    # Verify events array exists
    if "events" not in data:
        log(f"   ❌ FAILED: Response missing 'events' array", Colors.RED)
        return False
    
    events = data["events"]
    log(f"   ✓ Found {len(events)} events", Colors.GREEN)
    
    # Find receipt_matched event
    receipt_matched_event = None
    receipt_event = None
    for event in events:
        if event.get("kind") == "receipt_matched":
            receipt_matched_event = event
        if event.get("kind") == "receipt":
            receipt_event = event
    
    if not receipt_matched_event:
        log(f"   ❌ FAILED: No receipt_matched event found in timeline", Colors.RED)
        return False
    
    log(f"   ✓ Found receipt_matched event", Colors.GREEN)
    
    # Verify meta.receipt_id is a string (not a dict/BSON representation)
    meta = receipt_matched_event.get("meta", {})
    receipt_id_value = meta.get("receipt_id")
    
    if not isinstance(receipt_id_value, str):
        log(f"   ❌ FAILED: meta.receipt_id is not a string, got {type(receipt_id_value)}: {receipt_id_value}", Colors.RED)
        return False
    
    log(f"   ✓ meta.receipt_id is a string: {receipt_id_value}", Colors.GREEN)
    
    # Verify receipt event also has receipt_id as string
    if receipt_event:
        receipt_id_in_receipt = receipt_event.get("receipt_id")
        if not isinstance(receipt_id_in_receipt, str):
            log(f"   ❌ FAILED: receipt event's receipt_id is not a string, got {type(receipt_id_in_receipt)}", Colors.RED)
            return False
        log(f"   ✓ receipt event's receipt_id is also a string: {receipt_id_in_receipt}", Colors.GREEN)
    
    log(f"\n   ✅ TEST 1 PASSED", Colors.GREEN)
    return True

def test_scenario_2(session, db, admin_user_id):
    """
    Scenario 2: Overdue invoice with no receipt_matched events.
    Regression check - this should have always worked.
    """
    log("\n" + "="*80, Colors.BLUE)
    log("TEST 2: Overdue invoice with no receipt_matched events (regression check)", Colors.BLUE)
    log("="*80, Colors.BLUE)
    
    now_iso = datetime.now(timezone.utc).isoformat()
    past_date = "2026-01-01T00:00:00Z"
    
    # Create overdue invoice
    invoice_doc = {
        "user_id": ObjectId(admin_user_id),
        "status": "overdue",
        "amount": 12.34,
        "balance_remaining": 12.34,
        "currency": "USD",
        "counterparty_email": "noreply@notify.cloudflare.com",
        "counterparty_name": "Cloudflare",
        "invoice_ref": "IN-TEST",
        "due_date": past_date,
        "source_message_id": f"{TEST_SOURCE_PREFIX}2",
        "created_at": now_iso,
    }
    invoice_result = db.invoices.insert_one(invoice_doc)
    invoice_id = invoice_result.inserted_id
    log(f"   Created overdue invoice: {invoice_id}", Colors.BLUE)
    
    # Test the timeline endpoint
    log(f"\n   Testing GET /api/invoices/{invoice_id}/timeline...", Colors.YELLOW)
    response = session.get(f"{API_BASE}/invoices/{invoice_id}/timeline")
    
    # Validate response
    if response.status_code != 200:
        log(f"   ❌ FAILED: Expected HTTP 200, got {response.status_code}", Colors.RED)
        log(f"   Response: {response.text[:500]}", Colors.RED)
        return False
    
    log(f"   ✓ HTTP 200 OK", Colors.GREEN)
    
    try:
        data = response.json()
    except Exception as e:
        log(f"   ❌ FAILED: Response is not valid JSON: {e}", Colors.RED)
        return False
    
    # Verify events array exists and has at least origin event
    if "events" not in data:
        log(f"   ❌ FAILED: Response missing 'events' array", Colors.RED)
        return False
    
    events = data["events"]
    if len(events) < 1:
        log(f"   ❌ FAILED: Expected at least 1 event (origin), got {len(events)}", Colors.RED)
        return False
    
    log(f"   ✓ Found {len(events)} events (including origin)", Colors.GREEN)
    
    log(f"\n   ✅ TEST 2 PASSED", Colors.GREEN)
    return True

def test_scenario_3(session, db, admin_user_id):
    """
    Scenario 3: Paid invoice with ObjectId in other meta keys.
    Edge case to ensure _json_safe handles all ObjectIds in meta.
    """
    log("\n" + "="*80, Colors.BLUE)
    log("TEST 3: Paid invoice with ObjectId in other meta keys (edge case)", Colors.BLUE)
    log("="*80, Colors.BLUE)
    
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Create invoice
    invoice_doc = {
        "user_id": ObjectId(admin_user_id),
        "status": "paid",
        "amount": 50.0,
        "balance_remaining": 0.0,
        "paid_amount": 50.0,
        "currency": "USD",
        "counterparty_email": "billing@example.com",
        "counterparty_name": "Example Corp",
        "source_message_id": f"{TEST_SOURCE_PREFIX}3",
        "created_at": now_iso,
        "paid_at": now_iso,
    }
    invoice_result = db.invoices.insert_one(invoice_doc)
    invoice_id = invoice_result.inserted_id
    log(f"   Created invoice: {invoice_id}", Colors.BLUE)
    
    # Create a dummy ObjectId for chase_draft_id
    dummy_draft_id = ObjectId()
    
    # Create invoice_event with ObjectId in a different meta key
    event_doc = {
        "user_id": ObjectId(admin_user_id),
        "invoice_id": invoice_id,
        "action": "mark_paid",
        "at": now_iso,
        "meta": {
            "chase_draft_id": dummy_draft_id,  # Another ObjectId in meta
            "note": "Paid via bank transfer"
        }
    }
    db.invoice_events.insert_one(event_doc)
    log(f"   Created invoice_event with ObjectId in meta.chase_draft_id", Colors.BLUE)
    
    # Test the timeline endpoint
    log(f"\n   Testing GET /api/invoices/{invoice_id}/timeline...", Colors.YELLOW)
    response = session.get(f"{API_BASE}/invoices/{invoice_id}/timeline")
    
    # Validate response
    if response.status_code != 200:
        log(f"   ❌ FAILED: Expected HTTP 200, got {response.status_code}", Colors.RED)
        log(f"   Response: {response.text[:500]}", Colors.RED)
        return False
    
    log(f"   ✓ HTTP 200 OK", Colors.GREEN)
    
    try:
        data = response.json()
    except Exception as e:
        log(f"   ❌ FAILED: Response is not valid JSON: {e}", Colors.RED)
        return False
    
    # Verify events array exists
    if "events" not in data:
        log(f"   ❌ FAILED: Response missing 'events' array", Colors.RED)
        return False
    
    events = data["events"]
    log(f"   ✓ Found {len(events)} events", Colors.GREEN)
    
    # Find mark_paid event
    mark_paid_event = None
    for event in events:
        if event.get("kind") == "mark_paid":
            mark_paid_event = event
            break
    
    if not mark_paid_event:
        log(f"   ❌ FAILED: No mark_paid event found in timeline", Colors.RED)
        return False
    
    log(f"   ✓ Found mark_paid event", Colors.GREEN)
    
    # Verify meta.chase_draft_id is a string
    meta = mark_paid_event.get("meta", {})
    chase_draft_id_value = meta.get("chase_draft_id")
    
    if chase_draft_id_value is not None and not isinstance(chase_draft_id_value, str):
        log(f"   ❌ FAILED: meta.chase_draft_id is not a string, got {type(chase_draft_id_value)}", Colors.RED)
        return False
    
    log(f"   ✓ meta.chase_draft_id is properly serialized: {chase_draft_id_value}", Colors.GREEN)
    
    log(f"\n   ✅ TEST 3 PASSED", Colors.GREEN)
    return True

def main():
    log("\n" + "="*80, Colors.BLUE)
    log("BACKEND TEST: GET /api/invoices/:id/timeline ObjectId Serialization", Colors.BLUE)
    log("="*80, Colors.BLUE)
    
    # Connect to MongoDB
    log("\n📦 Connecting to MongoDB...", Colors.BLUE)
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    log(f"   ✓ Connected to {MONGO_URL}/{DB_NAME}", Colors.GREEN)
    
    # Authenticate
    session, admin_user_id = authenticate()
    
    # Run tests
    results = []
    
    try:
        results.append(("Test 1: Paid invoice with receipt_matched (ObjectId crash case)", 
                       test_scenario_1(session, db, admin_user_id)))
        
        results.append(("Test 2: Overdue invoice (regression check)", 
                       test_scenario_2(session, db, admin_user_id)))
        
        results.append(("Test 3: ObjectId in other meta keys (edge case)", 
                       test_scenario_3(session, db, admin_user_id)))
    
    finally:
        # Cleanup
        cleanup_test_data(db, ObjectId(admin_user_id))
    
    # Summary
    log("\n" + "="*80, Colors.BLUE)
    log("TEST SUMMARY", Colors.BLUE)
    log("="*80, Colors.BLUE)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        color = Colors.GREEN if passed else Colors.RED
        log(f"{status}: {test_name}", color)
        if not passed:
            all_passed = False
    
    log("\n" + "="*80, Colors.BLUE)
    if all_passed:
        log("🎉 ALL TESTS PASSED", Colors.GREEN)
        log("="*80, Colors.BLUE)
        sys.exit(0)
    else:
        log("💥 SOME TESTS FAILED", Colors.RED)
        log("="*80, Colors.BLUE)
        sys.exit(1)

if __name__ == "__main__":
    main()
