# Scotive × QuickBooks Online — Integration Spec (v1)

**Status**: Planned — first accounting-tool expansion. Does not replace the Gmail pipeline.

**Implementation:** module-by-module (plan → build).  
- Module 1 (done): [`QBO_MODULE_1_OAUTH.md`](./QBO_MODULE_1_OAUTH.md)  
- Module 2 (done): [`QBO_MODULE_2_INVOICE_FETCH.md`](./QBO_MODULE_2_INVOICE_FETCH.md)  
- Module 3 (done): [`QBO_MODULE_3_ONBOARDING.md`](./QBO_MODULE_3_ONBOARDING.md)  
- Module 4 (done): [`QBO_MODULE_4_CONVERSATION.md`](./QBO_MODULE_4_CONVERSATION.md)  
- Module 5 (done): [`QBO_MODULE_5_PAID_SYNC.md`](./QBO_MODULE_5_PAID_SYNC.md)  
- Module 6 (done): [`QBO_MODULE_6_SYNC.md`](./QBO_MODULE_6_SYNC.md)

**Sandbox app:** Scotive · redirect `https://reemerge-obstinate-latter.ngrok-free.dev/api/qbo/oauth/callback` (ngrok → backend). Creds live in `backend/.env` only (`QBO_*`).

**One line**: QuickBooks is an extra invoice feed + a single paid/not-paid signal. Until QBO says paid, Scotive tracking and UX are identical to today (including “has it arrived?” / Received / Not yet). Gmail stays the conversation layer and still discovers email-sent invoices.

---

## Principles

1. **Additive, not exclusive** — Connecting QBO adds a feed. It never disables Gmail invoice detection or conversation tracking.
2. **Narrow QBO role** — Discover unpaid invoices + report **paid or not**. Do **not** sync QBO’s Open/Overdue/etc. into Scotive. Statuses and tracking always live in Scotive.
3. **Unpaid = full Scotive UX** — For any QBO-sourced invoice that is **not** paid in QuickBooks, show **exactly what we show today**: overdue, promised, disputed, drafts, remittance/claim flow, **“has it arrived?” / Received / Not yet**, manual mark-paid, etc. Source does not change the unpaid experience.
4. **Paid in QBO = Paid in Scotive** — When QBO flips to paid, mark the ledger row **Paid** (trusted fact). No confirm-payment prompt for that flip. Attribution e.g. `Paid in QuickBooks · [date]`.
5. **Gmail owns conversation** — For every ledger invoice (Gmail-sourced or QBO-sourced), replies, promises, disputes, and chase drafts come from Gmail.
6. **One ledger** — Both feeds write into the same `invoices` collection. Dedup by invoice ref (and conservative fallbacks). Source-tag rows (`gmail` / `quickbooks` / `both`).
7. **No new “fetch mode” settings** — No checkboxes for “conversations only” vs “also detect Gmail invoices.” Existing Settings stay (Gmail connect/disconnect, escalation, digest, etc.) and gain QBO connect/disconnect only.

---

## Status ownership (locked)

| Who | Owns |
|---|---|
| **Scotive** | All tracking statuses while unpaid: `invoiced`, `overdue`, `promised`, `partially_paid`, `promise_broken`, `disputed`, `paid_unconfirmed`, chase drafts, Today confirm prompts, user actions |
| **QuickBooks** | Only the boolean **paid / not paid** (plus discovery of which open invoices exist) |

```text
QBO unpaid  →  identical Scotive pipeline & UI (incl. “has it arrived?”)
QBO paid    →  status becomes Paid (no confirm gate for that transition)
```

**Email-side payment claims** (“sent via bank transfer”), remittance matches, and Today **Received / Not yet** apply to **QBO-sourced invoices the same as Gmail-sourced ones** for as long as QBO has not marked them paid. When the user confirms **Received** / mark paid in Scotive on a QBO-linked row, Scotive also updates that invoice in QuickBooks (Payment linked to Invoice — QBO’s only way to drop Balance). QBO’s own `paid` / Balance=0 signal is the only shortcut that bypasses the confirm gate — and only when QBO itself reports paid.

---

## What QBO does / does not do

| QBO does | QBO does not |
|---|---|
| Pull open (unpaid) invoices into the ledger | Replace Gmail seed/live detection |
| Webhook (or poll) for new invoices | Drive Scotive statuses like `promised` / `disputed` / `overdue` |
| Signal `paid=true` → mark **Paid** (skip confirm for that flip only) | Change unpaid UX (no hiding Received/Not yet, no alternate status UI) |
| Optionally expose payment attribution when reliable | Require a Gmail-role chooser at onboarding |

---

## Onboarding (no decisions, no new fetch toggles)

```text
Signup
  → One connections screen: Connect Gmail (required) + Connect QuickBooks (optional)
       Gmail connect → start 90d seed in background (no Gmail progress UI)
       QBO connect   → import unpaid invoices (conversation match = Module 4)
  → Next
       ├─ Gmail only  → preparing (wait for silent seed) → curation → dashboard
       └─ QBO connected → dashboard (seed may still run)
            → When seed finds Gmail-only leftovers → sticky Review banner
                 Discard | Review & confirm → curation → track unpaid
```

### Path A — Gmail only (skip QBO)

Silent seed after Gmail connect; on Next → curation (select still-unpaid) → dashboard / Today. No Gmail scan progress bar on the connections screen.

### Path B — Gmail + QuickBooks

1. **QBO import** — Fetch open/unpaid invoices only (never import already-paid for seed). Write straight to the ledger. No per-item “is this unpaid?” judgment — QBO already knows.
2. **Conversation match** — Module 4: for each QBO invoice, query Gmail using the **client email from QBO**, scoped **from that invoice’s date forward**.
3. **Gmail seed still runs** — Last ~90 days of sent-mail invoice candidates in the background (no progress UI on connections).
4. **Dedup** — If a Gmail candidate matches a QBO invoice (prefer invoice ref / DocNumber), **ignore** it. Do not create a second row.
5. **Deferred curation when QBO is connected** — Next goes to the dashboard. If the Gmail seed finds leftovers (not already in QBO), a **sticky** top banner stays until Discard or Review & confirm (opens curation). Not a timed toast.

Background work starts as soon as each connection succeeds; the connections screen stays until the user clicks Next.

---

## Dashboard & detail

- Gmail-confirmed and QBO-imported invoices share one ledger / list UI.
- Normal list is **not** split by source.
- Invoice detail shows light attribution, e.g.:
  - `Tracked from Gmail`
  - `Imported from QuickBooks`
  - `Paid in QuickBooks · [date]` (prefer this wording unless payment-link vs manual mark can be distinguished reliably)

### Empty conversation (QBO or any source)

Not a bug — common when the client never replied or paid without email.

- Unpaid, no thread: **“No client emails on this invoice yet”**
- Paid via QBO, no thread: **“No client emails — paid in QuickBooks, [date]”**

Do not render a blank Conversation panel that looks broken.

---

## Ongoing sync (post-onboarding)

Every incremental cycle (and via webhooks where available):

| Concern | Behavior |
|---|---|
| **New QBO invoices** | Prefer **webhook** to create/update ledger row; attempt conversation match. Incremental poll as backup for missed events. While unpaid → full Scotive tracking/UI. |
| **QBO still unpaid** | No special path. Same state machine, drafts, claim/remittance confirm prompts (“has it arrived?” / Received / Not yet) as Gmail-native invoices. |
| **QBO invoice deleted** | Webhook Delete (and CDC `status=Deleted`) remove the matching Scotive ledger row by `qbo_id` (events/drafts cascaded). |
| **QBO paid** | Poll / webhook `paid=true` every cycle, independent of Gmail activity → status **Paid** immediately; no confirm-payment prompt **for this QBO-driven transition**. Clear any pending claim UI. |
| **QBO invoice conversations** | Query Gmail by **QBO client email**, messages **on/after the invoice date**; then Stage 4 re-eval → promised / disputed / partially_paid / `paid_unconfirmed` / etc., same as Gmail-native rows. |

### QBO → Gmail conversation queries

Locked query shape for attaching / refreshing conversation on a QBO-sourced invoice:

1. **Client identity from QBO** — Use the customer email stored on the QBO invoice / Customer record (same address written onto the ledger as `counterparty_email` / `client_identity_key`). Do **not** invent broad mailbox searches without that email.
2. **Time window from the invoice** — Only consider Gmail messages **on or after the invoice date** (TxnDate / equivalent). Nothing before that invoice’s date.
3. **Optional tighteners** (when available, to pick the right thread among several with the same client): invoice ref / DocNumber, amount language — still within the client-email + after-invoice-date constraint.
4. **Missing client email on QBO** — Skip conversation match for that row until an email exists; keep empty-conversation copy. Do not fall back to unbounded inbox search.
5. **Ongoing** — Same query rules on Sync now / hourly incremental and after webhooks that create or update a QBO invoice: re-query by client email from invoice date forward for new replies.

Example Gmail search intent (illustrative):

```text
(from:client@acme.com OR to:client@acme.com) after:YYYY/MM/DD
```

where `client@acme.com` comes from QBO and `YYYY/MM/DD` is the invoice date.
| **Gmail-only invoices** | Existing seed/live detection + conversation pipeline — unchanged. |
| **Overlap** | Same invoice from both paths → one row; merge refs / `qbo_id` / `source_thread_id` as available. |
| **QB notification emails** | When QBO API is connected, skip Intuit/QuickBooks notification-email ingest (redundant; increases dup risk). Keep for users without QBO if that path remains shipped. |

### Partial payments in QBO (v1 default)

v1 only treats full **`paid=true`** as a money override. QBO partial `Balance` is **not** synced into Scotive unless explicitly added later. Email-derived partials still work via the existing pipeline.

---

## Settings

Keep **existing** Settings (Gmail connect/disconnect, escalation, digest, scan window for ongoing sync, late fee, account delete, etc.).

**Add only:**

- **Connect QuickBooks** / **Disconnect QuickBooks** (mirror Gmail connection UX: status, reconnect on revoke, disconnect does not wipe the ledger by default — same privacy pattern as Gmail unless product says otherwise).

**Do not add:**

- Toggles for “fetch Gmail invoices vs conversations only”
- Per-source “what to sync” checkboxes
- Separate “QBO status sync” mode settings

---

## Dedup rules (short)

1. Prefer match on normalized invoice ref / QBO DocNumber (+ `user_id`).
2. If no reliable ref, do **not** aggressively drop Gmail candidates (avoid false merges).
3. When merged: keep one ledger row; store `qbo_id` when known; keep Gmail `source_thread_id` / message ids for conversation; set source tag to `both` if both paths contributed.
4. Until QBO `paid=true`, Scotive owns all status (including confirm prompts). When QBO reports paid, money status becomes **Paid**; conversational history remains.

---

## Architecture sketch

```text
                    ┌─────────────────┐
                    │  Ledger +       │
         ┌─────────▶│  state machine  │◀─────────┐
         │          │  + drafts       │          │
         │          └────────┬────────┘          │
         │                   │                   │
   QBO API / webhook    Gmail conversation   Gmail seed/live
   (unpaid + paid)      (all invoices)       (email-only invoices;
         │                                       dedupe vs QBO)
         └───────────────────────────────────────┘
```

Reuse existing patterns:

- OAuth connector pattern from `gmail_oauth` → `qbo_connections` (encrypted tokens, connect/disconnect/status).
- Ledger write path → `upsert_sweep_invoice` / lifecycle hooks.
- Reply intelligence → same re-eval / events pipeline for QBO-linked rows once a thread is attached.

---

## Out of scope for this integration

- Creating / editing invoices inside QuickBooks from Scotive
- Full QBO status mirror (Open / Overdue / etc.) — Scotive statuses only; QBO contributes paid/not-paid
- Bank / payment-processor reconciliation screens
- Outlook (future conversation channel)
- FreshBooks / Stripe / other tools (same shape later; QBO is first)
- New onboarding chooser for “how you use Gmail”

---

## Acceptance checklist

- [ ] Dual-connect screen: Gmail + optional QBO; Next requires Gmail.
- [ ] Gmail connect starts silent 90d seed (no progress UI on connections).
- [ ] QBO connect imports unpaid invoices; Next → dashboard.
- [ ] After seed, Gmail leftovers show sticky Discard / Review & confirm banner on dashboard.
- [ ] Gmail-only Next → curation (or auto-skip if zero candidates).
- [ ] Gmail seed still runs with QBO; QBO-overlapping candidates excluded.
- [ ] Detail shows source / Paid-in-QBO attribution; empty conversation copy is factual.
- [ ] While QBO invoice is unpaid: identical UX to today (Today confirm prompts, Received / Not yet, drafts, status chips).
- [ ] Webhook or poll creates new QBO invoices; when QBO reports paid → Paid without confirm prompt for that flip.
- [ ] Email payment claims / remittance on unpaid QBO-sourced invoices still use Received / Not yet.
- [ ] QBO conversation match queries by **QBO client email** and only messages **on/after the invoice date**.
- [ ] Missing QBO client email → no unbounded Gmail search; empty conversation copy instead.
- [ ] Settings: QBO connect/disconnect only — no fetch-role toggles.
- [ ] Disconnect QBO does not delete ledger history by default (align with Gmail disconnect policy).
```
