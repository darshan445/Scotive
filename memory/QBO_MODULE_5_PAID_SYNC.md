# QBO Module 5 — Paid sync

**Spec parent:** [`QBO_INTEGRATION.md`](./QBO_INTEGRATION.md)  
**Depends on:** Module 1–2 (OAuth + ledger `qbo_id`)  
**Status:** Implemented  
**Goal:** When QuickBooks reports an invoice fully paid (`Balance <= 0`), mark the Scotive row **Paid** immediately — no “has it arrived?” / Received confirm gate for this QBO-driven flip. Clear pending claim UI.

**Out of this module:** Webhooks (Module 6). QBO partial Balance poll into Scotive (v1 ignores).

---

## Bidirectional paid

| Direction | Behavior |
|---|---|
| **QBO → Scotive** | Poll open ledger rows with `qbo_id`; if QBO `Balance <= 0` → mark Paid, **no** Received confirm |
| **Scotive → QBO** | Unpaid QBO invoices still use Gmail claim → **Received / Not yet** as today. On **Received** / mark paid, push to QBO so that invoice’s Balance drops |

QBO has no writable `Invoice.Status=Paid`. The Accounting API zeros Balance only by creating a **Payment linked to that Invoice** (bookkeeping under the hood — not a Scotive “record a payment” product surface). Deposits to Undeposited Funds by default.

---

## Behavior

1. Load open ledger invoices that have a `qbo_id`.
2. Batch-fetch those Invoice entities from QBO (`fetch_invoices_by_ids`).
3. If `Balance <= 0.005` → `mark_invoice_paid_from_qbo`:
   - `status=paid`, zero balance, full `paid_amount`
   - `clear_payment_claim_fields` + chase/stale clears (same as manual full mark-paid)
   - `ack_followup_prompts`
   - Event `qbo_paid` + attribution `paid_via=quickbooks`, `evidence_sentence=Paid in QuickBooks · [date]`

Does **not** call the HTTP `/invoices/{id}/action` endpoint. Reuses shared `build_full_mark_paid_patch`.

---

## Shipped

| Piece | Location |
|---|---|
| Paid sync (QBO→Scotive) | `backend/qbo_paid_sync.py` → `sync_qbo_paid_status` |
| Push paid (Scotive→QBO) | `push_scotive_paid_to_qbo` on `mark_paid` when `qbo_id` present |
| QBO Payment create | `qbo_client.create_payment_against_invoice` |
| QBO fetch by Id | `qbo_client.fetch_invoices_by_ids` |
| Shared mark-paid patch | `build_full_mark_paid_patch` (also used by manual mark_paid) |
| Incremental / Sync now | `run_incremental_pipeline` → `sync_qbo_paid_status` |
| After import | `import_unpaid_invoices` also runs paid sync |
| Route | `POST /api/qbo/sync-paid` |
| Detail UI | Attribution + empty conversation copy for QBO-paid |

---

## How to test

1. Import an unpaid QBO invoice; leave it open in Scotive.
2. Mark it paid in QuickBooks sandbox.
3. Sync now (or wait for hourly) / `POST /api/qbo/sync-paid`.
4. Ledger shows Paid; no Today confirm card; detail says `Paid in QuickBooks · [date]`.
