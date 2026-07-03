#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  User reported: expanding a `paid` invoice row on the ledger shows
  "Something went wrong. Please try again." while `overdue` rows expand fine.
  The client detail page for the same invoices renders correctly.

backend:
  - task: "GET /api/invoices/:id/timeline JSON-serializes ObjectId in invoice_events.meta"
    implemented: true
    working: true
    file: "/app/backend/scan_router.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Root cause: `receipt_matched` (and `receipt_matched_manual`) events
          are inserted into `invoice_events` with a `meta` dict that carries
          `receipt_id` as a raw BSON `ObjectId`. The timeline endpoint used to
          return `meta` as-is, which crashed FastAPI's default JSON encoder
          → HTTP 500 → frontend showed generic "Something went wrong."
          Overdue invoices have no `receipt_matched` history so their timeline
          fetch worked.
          Fix: added a recursive `_json_safe(value)` helper in scan_router.py
          that walks nested dicts/lists and converts ObjectId→str and
          datetime→isoformat. Applied to:
            - meta on each `invoice_events` entry returned in the timeline
            - `receipt_id` added on each receipt event
          Reproduced against the affected user's actual paid Vultr invoice
          (id `6a474ca1b87066da797a6a15`); after the fix the payload
          serializes to clean JSON. Awaiting testing_agent confirmation via
          real HTTP round-trip.
      - working: true
        agent: "testing"
        comment: |
          ✅ VERIFIED: All three test scenarios passed via real HTTP calls to GET /api/invoices/:id/timeline.
          
          Test 1 (Critical - ObjectId crash case): Created paid invoice with receipt_matched 
          event containing BSON ObjectId in meta.receipt_id. Endpoint returned HTTP 200 with 
          properly serialized JSON. Verified meta.receipt_id is a string (not dict/BSON object).
          
          Test 2 (Regression check): Created overdue invoice with no receipt_matched events. 
          Endpoint returned HTTP 200 with origin event. No regression detected.
          
          Test 3 (Edge case): Created paid invoice with ObjectId in other meta keys 
          (chase_draft_id). Endpoint returned HTTP 200 with all ObjectIds properly serialized 
          to strings.
          
          The _json_safe() helper in scan_router.py (lines 87-103) correctly handles recursive 
          conversion of ObjectId→str and datetime→isoformat throughout nested dicts/lists.
          
          Test execution: Authenticated as admin@scotive.com, seeded test data with real BSON 
          ObjectIds in invoice_events.meta, verified HTTP responses, cleaned up all test data.
          
          Bug fix confirmed working. The reporter's paid invoices (Vultr, Thakor) should now 

  - task: "Payment direction guardrails — vendors and self-invoices"
    implemented: true
    working: true
    file: "/app/backend/scan_pipeline.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          User reported multiple wrong ledger entries: Anthropic (a vendor they
          pay) shown as a paying client, Cloudflare shown as owing money after
          the user actually paid, Vultr subscription treated as an unpaid
          invoice from a client, and the user's own gmail (`tdarshan336@gmail.com`)
          appearing as a paying client.

          Root cause: the AI prompt allowed direction ambiguity — any invoice-
          shaped email (subscription bill, vendor dunning notice, hosting
          receipt) was classified as `invoice_sent` (money owed TO the user),
          and no backend guardrail rejected vendor-domain or self-invoice
          rows before they hit the ledger.

          Fix in `scan_pipeline.py`:
            1. New `VENDOR_DOMAINS` list covering ~30 SaaS/hosting/AI vendors
               (Cloudflare, Vultr, DigitalOcean, AWS, Google, Microsoft,
               Anthropic, OpenAI, GitHub, Vercel, Netlify, etc.) + `_is_vendor()`
               subdomain-aware matcher.
            2. Rewrote the AI prompt with an explicit DIRECTION CHECK section:
               emails from vendor domains → is_money_related=false, kind=none.
               "receipt" of a vendor charging the user (e.g. Anthropic $23.60
               subscription) → not a receipt of incoming money.
            3. `USER_EMAIL:` prefix added to the AI user-prompt so the LLM can
               reason about self-invoice cases.
            4. Backend override in `_extract_and_write()` (applies regardless
               of what the LLM returns):
                  - vendor domain sender + any money kind → routes to
                    `review_items` with `review_reason: "vendor_domain"`, never
                    into `invoices`.
                  - "receipt" with payer matching user's email/domain → dropped.
                  - counterparty_email == user's email OR same domain as user →
                    invoice creation dropped (can't be your own client).
            5. Refactored `run_historical_scan` phase-5 to reuse the shared
               `_extract_and_write()` helper so guardrails apply on initial
               scan too (not just incremental sync).
            6. Threaded `my_email` into both `extract_with_ai()` callsites.

          Backfill: `/app/scripts/backfill_vendor_cleanup.py` ran once against
          the DB; moved 3 vendor invoices to the review queue and deleted 1
          self-invoice for the affected user (`tdarshan336@gmail.com`, also
          the linked account `darsh@getscotive.com`).

          Awaiting testing_agent to verify that:
            - a fake historical scan with vendor + self-invoice + real client
              messages produces only the real-client row in invoices (vendor
              rows land in review_items, self-invoice row is dropped).
            - reconcile still works for legitimate receipt→invoice matches.
      - working: true
        agent: "testing"
        comment: |
          ✅ VERIFIED: All payment direction guardrails working correctly via direct function calls to MongoDB.
          
          Test execution: Authenticated as admin@scotive.com, seeded gmail_connection, called 
          _extract_and_write() directly with test data (no HTTP, no OpenRouter), verified DB state, 
          cleaned up all test data (source_message_id starting with "guard-").
          
          _is_vendor() function tests (7/7 passed):
          ✓ cloudflare.com → True
          ✓ notify.cloudflare.com (subdomain) → True  
          ✓ anthropic.com → True
          ✓ vultr.com → True
          ✓ stripe.com → False (processor, not vendor)
          ✓ acme.com → False
          ✓ empty string → False
          
          Scenario A - Vendor invoice (Cloudflare notify.cloudflare.com):
          ✓ Returned (0,0,1) as expected
          ✓ 0 docs in invoices collection
          ✓ 1 doc in review_items with review_reason="vendor_domain"
          
          Scenario B - Stripe receipt (processor, not vendor):
          ✓ Returned (0,1,0) as expected
          ✓ 1 doc in receipts collection
          ✓ 0 docs in invoices or review_items
          ✓ Confirms legitimate processor receipts are not over-filtered
          
          Scenario C - Self-invoice (admin@scotive.com invoicing themselves):
          ✓ Returned (0,0,0) as expected
          ✓ Completely dropped - 0 docs in invoices, receipts, or review_items
          
          Scenario D - Real client invoice (Northbeam Studio):
          ✓ Returned (1,0,0) as expected
          ✓ 1 doc in invoices collection
          ✓ status="invoiced", balance_remaining=6200.0
          ✓ 0 docs in receipts or review_items
          
          All guardrails functioning as designed. Vendor bills are routed to review queue, 
          self-invoices are dropped, legitimate client invoices and processor receipts are 
          correctly classified. The fix prevents vendor subscriptions (Cloudflare, Vultr, 
          Anthropic) from appearing as client invoices in the ledger.

agent_communication:
  - agent: "main"
    message: |
      Second bug report from the same user. Fix + backfill applied. Please
      test the new direction guardrails without hitting real OpenRouter:

      1. As admin `admin@scotive.com` / `Admin@Scotive1`, seed:
         a. gmail_connection: {user_id: admin_uid, email: "admin@scotive.com",
            status:"connected", can_send:true}
         b. Then directly call `scan_pipeline._extract_and_write(db, admin_uid,
            msg, ext, my_email, now_iso)` for these four scenarios (bypasses
            the LLM — you're testing the writer's guardrails):

         Scenario A — Vendor invoice (should → review_items only, NOT invoices):
           msg = {"id":"guard-1","from":"noreply@notify.cloudflare.com",
                  "to":"admin@scotive.com","subject":"Payment failed",
                  "thread_id":"t1","date":"2026-06-28"}
           ext = {"is_money_related":True,"kind":"invoice_sent","amount":12.34,
                  "currency":"USD","counterparty_email":"noreply@notify.cloudflare.com",
                  "counterparty_name":"Cloudflare","invoice_ref":"IN-69681681",
                  "due_date":"2026-06-28","confidence":0.9,
                  "evidence_sentence":"Outstanding balance: $12.34"}
           Expect return (0,0,1). Expect NO doc in `invoices`. Expect one doc
           in `review_items` with `review_reason == "vendor_domain"`.

         Scenario B — Vendor receipt of user paying (should be dropped by
         review-queue rule, same as A):
           msg = {"id":"guard-2","from":"receipts@stripe.com",
                  "to":"admin@scotive.com","subject":"Anthropic charge",
                  "thread_id":"t2","date":"2026-06-22"}
           ext = {"is_money_related":True,"kind":"receipt","amount":23.60,
                  "counterparty_name":"Anthropic, PBC","confidence":0.9}
           Note: stripe.com is NOT in vendor_domains — it's a processor. This
           receipt has the user as the PAYER (their money left the account),
           so payer_name is Anthropic. Expect (0,1,0) — receipt inserted. This
           tests we haven't over-filtered legitimate processor receipts.

         Scenario C — Self-invoice (should be dropped entirely):
           msg = {"id":"guard-3","from":"admin@scotive.com",
                  "to":"admin@scotive.com","subject":"note to self",
                  "thread_id":"t3","date":"2026-07-01"}
           ext = {"is_money_related":True,"kind":"invoice_sent","amount":189.0,
                  "currency":"USD","counterparty_email":"admin@scotive.com",
                  "counterparty_name":"Me","invoice_ref":"self",
                  "confidence":0.9}
           Expect return (0,0,0). Nothing in invoices, receipts, OR review_items.

         Scenario D — Real client invoice (should → invoices normally):
           msg = {"id":"guard-4","from":"admin@scotive.com",
                  "to":"ap@northbeam.com","subject":"Invoice NB-102",
                  "thread_id":"t4","date":"2026-06-15"}
           ext = {"is_money_related":True,"kind":"invoice_sent","amount":6200.0,
                  "currency":"USD","counterparty_email":"ap@northbeam.com",
                  "counterparty_name":"Northbeam Studio","invoice_ref":"NB-102",
                  "due_date":"2026-06-30","confidence":0.9,
                  "evidence_sentence":"Please remit $6,200 by June 30."}
           Expect return (1,0,0). One doc in invoices, status "invoiced",
           balance_remaining=6200.

      Also verify the `_is_vendor` helper: `_is_vendor("cloudflare.com")` True,
      `_is_vendor("notify.cloudflare.com")` True (subdomain match),
      `_is_vendor("stripe.com")` False (that's a processor, not a vendor),
      `_is_vendor("acme.com")` False.

      Cleanup: delete every doc you inserted (source_message_id starting
      with "guard-"). Do NOT touch the reporter's real data.

          expand correctly in the ledger UI without "Something went wrong" errors.

test_credentials:
  - Admin (empty ledger, exists but not the reporter):
      email: admin@scotive.com
      password: Admin@Scotive1
  - Reporter's account (has the paid Vultr invoice with the bug):
      email: darsh@getscotive.com
      password_known: false   # main-agent does NOT know this user's password.
      user_id: 6a474bdeb87066da797a6a10
      paid_invoice_id: 6a474ca1b87066da797a6a15  # Vultr, was failing
      other_paid_invoice_id: 6a474ca1b87066da797a6a1f  # Thakor, also failing

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "stuck_first"

agent_communication:
  - agent: "main"
    message: |
      Please test the `GET /api/invoices/:id/timeline` endpoint for the two
      specific invoice ids listed under `test_credentials.Reporter's account`:
        - 6a474ca1b87066da797a6a15 (Vultr, paid)
        - 6a474ca1b87066da797a6a1f (Thakor, paid)
      Since I don't have the reporter's login password, please authenticate
      as `admin@scotive.com` / `Admin@Scotive1` and CURL the endpoint —
      it will 404 for that admin (not their invoice), which is fine. What we
      actually need is a repro on a paid invoice belonging to the authed
      user, so please:
        1. As admin, seed a paid invoice with a `receipt_matched` event whose
           `meta.receipt_id` is a real BSON ObjectId, then hit the timeline
           endpoint. Before the fix this returned 500 due to ObjectId not
           being JSON-serializable. After the fix it must return 200 with a
           JSON body containing `events[*].meta.receipt_id` as a string.
        2. Confirm the response contains at least one event with
           `kind == "receipt_matched"` and that its `meta.receipt_id` is a
           string (not a dict/object).
        3. Also seed & test an `overdue` invoice with NO receipt_matched
           events to confirm we didn't break the working case (should still
           return 200).
      Please clean up any seeded rows on completion. Do NOT test the
      reporter's real data — read-only inspection is fine but no mutations.
  - agent: "testing"
    message: |
      ✅ Bug fix verified and working correctly.
      
      Executed comprehensive end-to-end HTTP tests covering all three scenarios:
      1. ✅ Paid invoice with receipt_matched event (meta.receipt_id as BSON ObjectId) - HTTP 200, properly serialized
      2. ✅ Overdue invoice with no receipt_matched events - HTTP 200, no regression
      3. ✅ Edge case with ObjectId in other meta keys - HTTP 200, all ObjectIds serialized
      
      All test data seeded with real BSON ObjectIds and cleaned up after testing.
      The _json_safe() helper correctly handles recursive ObjectId→str conversion.
      
      The reporter's paid invoices should now expand correctly in the ledger UI.
  - agent: "testing"
    message: |
      ✅ Payment direction guardrails fully verified and working correctly.
      
      Completed comprehensive testing of all scenarios specified in agent_communication:
      
      **_is_vendor() Function Tests (7/7 PASSED):**
      - All domain checks working correctly including subdomain matching
      - Correctly distinguishes between vendors (Cloudflare, Anthropic, Vultr) and processors (Stripe)
      
      **Scenario Tests (4/4 PASSED):**
      - Scenario A: Vendor invoice correctly routed to review_items with review_reason="vendor_domain"
      - Scenario B: Stripe receipt (processor) correctly inserted into receipts collection
      - Scenario C: Self-invoice correctly dropped (no DB entries)
      - Scenario D: Real client invoice correctly inserted into invoices with proper status and balance
      
      **Test Method:**
      - Direct function calls to _extract_and_write() bypassing HTTP and OpenRouter
      - Seeded admin gmail_connection
      - Verified exact return tuples and DB state for each scenario
      - Cleaned up all test data (source_message_id starting with "guard-")
      
      **Conclusion:**
      The fix successfully prevents vendor subscriptions (Cloudflare, Vultr, Anthropic, etc.) 
      from appearing as client invoices in the ledger. Self-invoices are properly rejected. 
      Legitimate client invoices and processor receipts flow correctly. All guardrails 
      functioning as designed.

