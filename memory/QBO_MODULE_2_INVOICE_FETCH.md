# QBO Module 2 — Invoice + Customer fetch → ledger

**Spec parent:** [`QBO_INTEGRATION.md`](./QBO_INTEGRATION.md)  
**Depends on:** [`QBO_MODULE_1_OAUTH.md`](./QBO_MODULE_1_OAUTH.md)  
**Status:** Implemented  
**Goal:** Pull **open/unpaid** QuickBooks invoices (with customer email), map into the Scotive ledger.

---

## Shipped

| Piece | Location |
|---|---|
| API client | `backend/qbo_client.py` — unpaid Invoice query, Customer batch, CompanyInfo |
| Import / upsert | `backend/qbo_import.py` — map fields, upsert by `qbo_id`, merge by ref onto Gmail rows |
| Route | `POST /api/qbo/import` in `qbo_oauth.py` |
| Index | partial unique `(user_id, qbo_id)` where `qbo_id` is a string (not sparse — sparse still indexes null) |
| UI | Settings → connected QBO panel → **Import open invoices** |

### Ledger fields set on import

`qbo_id`, `qbo_customer_id`, `qbo_realm_id`, `source` (`quickbooks` | `both`), amounts/balance, DocNumber, dates, customer email/name when present, synthetic `source_message_id=qbo:{realm}:{id}`.

Missing customer email → still import; `client_identity_key = qbo:customer:{id}` (no invented email).

After import: `apply_past_due_transitions`. Company name backfilled onto `qbo_connections` when available.

---

## How to test

1. Connect QBO (Module 1) with sandbox company that has open invoices + customer emails.
2. Settings → **Import open invoices**.
3. Dashboard ledger shows new rows; re-import does not duplicate.
4. Disconnect QBO — ledger rows remain.

---

## Still later

- Module 3: onboarding Path B + Gmail leftover curation  
- Module 4: Gmail conversation match by client email / after invoice date — done (`QBO_MODULE_4_CONVERSATION.md`)
- Module 5: paid=true override  
- Module 6: Sync now / incremental + webhooks  
