# QBO Module 4 — Gmail conversation match

**Spec parent:** [`QBO_INTEGRATION.md`](./QBO_INTEGRATION.md)  
**Depends on:** Module 1–3  
**Status:** Implemented  
**Goal:** Attach Gmail conversations to QBO-imported invoices, then run the **existing** in-thread + out-of-thread → rulebook re-eval pipeline. Do not invent a second status/amount path.

---

## Locked query shape (from parent spec)

```text
(from:client@… OR to:client@…) after:YYYY/MM/DD
```

- **Client email** from QBO / ledger `counterparty_email` only — no unbounded mailbox search.
- **After** = invoice `source_date` / TxnDate.
- Optional tighteners: DocNumber / amount when choosing among several threads.
- Missing email → skip match; keep empty-conversation copy.

---

## Approach (extend only)

1. **Bulk list + batch get** — same `list_message_ids` / `get_messages_batch` pattern as seed/incremental.
2. **Pick best `thread_id`** — score by invoice ref, then amount language; prefer threads with both directions.
3. **Attach** — set `source_thread_id` on the ledger row (keep synthetic `source_message_id=qbo:…`).
4. **Hand off** — call existing `_reevaluate_tracked` with window = invoice date so it:
   - loads **in-thread** via `get_thread_messages`
   - attaches **out-of-thread** client mail via existing OOT relevance
   - runs `rulebook_reeval` → events / amount / status (**unchanged**)

No changes to seed discovery, rulebook prompts, or Gmail-native invoice paths.

---

## Shipped

| Piece | Location |
|---|---|
| Matcher | `backend/qbo_conversation.py` |
| Background job | `enqueue_qbo_conversation_match` → `qbo_pipeline_jobs` (progress for dashboard) |
| After QBO import | Fast ledger import, then enqueue match (does not block Next) |
| Incremental | Enqueues match if unmatched QBO rows remain |
| Route | `POST /api/qbo/match-conversations` · `GET /api/qbo/pipeline-status` |
| UI | `QboPipelineProgress` on dashboard while job is queued/running |

Skips rows that already have `source_thread_id` (e.g. merged Gmail+QBO).

---

## Empty conversation

Unchanged product copy (UI): unpaid / no thread → “No client emails on this invoice yet”.
