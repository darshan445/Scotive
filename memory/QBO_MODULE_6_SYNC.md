# QBO Module 6 — Ongoing sync (webhooks + CDC poll)

**Spec parent:** [`QBO_INTEGRATION.md`](./QBO_INTEGRATION.md)  
**Status:** Implemented  
**Goal:** Keep ledger current after onboarding — new QBO invoices + paid updates — without a second status/amount pipeline.

---

## Webhook URL (ngrok)

```text
https://reemerge-obstinate-latter.ngrok-free.dev/api/qbo/webhooks
```

Env: `QBO_WEBHOOK_URL`, `QBO_WEBHOOK_VERIFIER_TOKEN`  
Subscribe: **Invoice** + **Payment** (Create, Update, **Delete**).

Invoice **Delete** removes the matching Scotive ledger row (`qbo_id`) plus events /
chase drafts/sends / review items; receipts are unmatched. CDC poll does the same when
`status=Deleted`.

---

## Shipped

| Piece | Location |
|---|---|
| Webhooks | `POST /api/qbo/webhooks` — HMAC verify; Create/Update → import/paid/match; **Delete** → remove ledger by `qbo_id` |
| CDC poll backup | `qbo_sync.sync_qbo_cdc` on Sync now / hourly; deleted entities remove ledger rows |
| Skip QB notify emails | `accounting_notify` drops intuit.com / quickbooks.com when QBO connected |
| Paid + conversation | Same Module 4/5 helpers — no new status/amount logic |

---

## Principle

QBO = invoice feed + paid signal. Status, amount, drafts, conversation = existing Gmail pipeline for every unpaid row.
