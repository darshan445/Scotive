# Scotive MVP — Final Locked Spec (Payment-First, Forward-Tracking)

**One line**: Scotive watches your Gmail, tracks every invoice you send from sent-to-paid, reads client replies for promises and disputes, and drafts the follow-ups — you approve with one tap, it sends from your own address.

**Users**: creators, freelancers, and small agencies (1–20 people) with multiple clients, invoicing over email.

**Core principle**: **forward-tracking, not archaeology.** Scotive is the authority on everything that happens in email (sent, overdue, promised, disputed); the user is the authority on money received (mark paid). No historical paid/unpaid inference, no bank statements, no reconciliation screens.

---

## Product sections (locked)

### 1. Sign Up / Sign In

Email + password with verification, login, forgot password. App account is separate from the Gmail connection.

**Status**: Shipped. **Do not change** unless user explicitly asks.

### 2. Empty Dashboard (pre-connect)

- Headline: **"Chase every invoice — automatically."**
- Subhead: **"Scotive watches your Gmail, tracks invoices you send, reads client replies, and drafts the follow-ups. Nothing sends without your approval."**
- CTA: Connect Gmail.
- Trust line: read + send-with-approval only · emails never train AI · disconnect anytime.

**Status**: Partially aligned. Landing + empty state exist but copy/hero differ from locked spec. **UI copy update only** — no auth/Gmail changes.

### 3. Connect Gmail

Two permissions only: read email, send on user's behalf. Handle: consent cancelled (friendly return, no dead end) · send permission unchecked (tracking works, sending disabled, reconnect banner) · access revoked later (reconnect banner, never silent failure).

**Status**: Shipped. **Do not change** unless user explicitly asks.

### 4. Seed Scan + Curation (the first 60 seconds)

Scan the last **60 days of sent mail only** for invoice signals (invoice-like subjects, amounts + due language, invoice attachments). **No inbox-wide scan, no paid/unpaid guessing.**

Show a **curation list**:

> "We found 6 invoices you sent in the last 60 days. Which are still unpaid? (tap to track)"

Each row: client · amount · sent date · due date if found. Older rows dimmed. Grouped by client with select-all when volume is high.

Buttons: **[Track selected]** · **[None — start fresh]**

The user curates in ~20 seconds — they know their last 60 days cold. Selected invoices enter the ledger; everything else is **ignored forever**.

**Immediately after curation**: state machine evaluates real due dates on the spot — anything past due flips to **Overdue** instantly — so the very next screen is the digest already working:

> ⚠️ Acme — $2,400 — 4 days overdue → [View follow-up draft]
> 💰 Meraki — $1,850 — due today → [View reminder draft]
> 👀 Watching: Nuts Over Tech (due Jul 3 — reading replies)

**Goal**: user approves their first real chase draft within **3 minutes** of connecting.

**Empty/edge paths**: nothing found or nothing selected → "Scotive is watching — send your next invoice like you always do and it appears here" + [Track manually] (client, amount, due date — 20 seconds) + tip: forward any invoice email to see it tracked. All-paid users → same watching state; digest stays quiet until something is real.

**Status**: **Major gap.** Current build runs a deep client-sweep (months of mail, AI per client, no curation). Must be replaced with 60d sent-only seed + curation screen + instant state eval. See **Alignment backlog** below.

### 5. Live Auto-Detection (the first magic)

From connection onward, Scotive watches **sent mail**. When the user sends an invoice the way they always do (attachment or amount + due language in the body), it appears tracked within **minutes** — no action required. This moment is the product's signature; it must be fast and reliable.

Detection also parses **invoice notification emails** from accounting tools (QuickBooks, FreshBooks, Wave, Zoho) so users who invoice from software are covered — replies still land in Gmail where only Scotive can read them.

**Status**: Partial. Incremental sync exists (polling) but is not sent-first / minutes-fast UX. Accounting-tool notification parsing not shipped. **Behavior + UI surfacing** needed.

### 6. Clients, Not Threads

The tracked entity is the **client** (counterparty), never the thread. Each client has known email identities; same-business-domain senders auto-link (accounts person counts), cross-domain matches prompt a one-tap merge. Every message from any known identity is evaluated against that client's open invoices — new thread, old thread, mixed-topic email, different sender at same company: all caught.

Message-to-invoice mapping: explicit invoice number → exact amount → single-open-invoice shortcut → ask the user. Evidence is sentence-level.

**Status**: Partial. Domain dedup + client view exist. **Cross-domain merge prompt** shipped Jul 2026 (same-name / same-invoice detection + one-tap merge).

### 7. Reply Intelligence (the moat — highest accuracy bar)

From client replies, detect: promises · disputes · partial payments · payment claims without proof · payment confirmations with references · approvals · adjustments. Deliverable-anchored terms resolve against deliverable date. Every extraction stores exact quoted sentence + link to source message. Below confidence bar → **review queue** — never silently into ledger.

**Status**: Partial. Client-sweep AI + review queue exist. Full reply taxonomy (approvals, deliverable-anchored terms, etc.) not complete. Review queue UI now shows reasons (not just "low confidence").

### 8. Invoice Lifecycle

States: Invoiced · Overdue · Promised · Promise broken · Disputed · Partially paid · Paid (unconfirmed) · Paid · Written off · **Stale**.

Rules: due + grace → Overdue · promise pauses chasing · dispute pauses chasing · client says paid without reference → Paid (unconfirmed) · missing due date → assumed terms (editable) · **120 days no activity → Stale** · nightly job for date transitions + next-day drafts.

**Data integrity** (from live bugs): one row per client + invoice number · Re: attaches as events not rows · quoted history stripped · same-domain dedup · never sum across currencies.

**Status**: Partial. Most states shipped. **Stale** state + 120d one-time prompt shipped Jul 2026. Nightly job exists via escalation/digest loops.

### 9. Confirming Paid (user is the authority)

Three channels, in order:
1. **Receipt/remittance parsing (no AI)**: Stripe, PayPal, Zelle, Wise, Payoneer, Square, Bill.com, Melio, QuickBooks payments, bank credit alerts — template-parsed, matched by reference or amount + payer. Remittance → Paid (unconfirmed).
2. **Client confirmation with reference** → confirmable.
3. **One-tap mark-paid everywhere**: ledger, drawer, digest card. Digest asks: "paid, or chase?" — both one tap.

**Status**: Partial. Receipt parsing + mark-paid + undo exist. **No reconciliation screen** (correct per spec). Digest confirm prompts + PaymentsCard confirm-paid framing shipped Jul 2026.

### 10. Chasing (grounded drafts, one-tap send)

Escalation ladder (configurable): pre-due nudge (−3d) → due-date reminder → firm (+3d) → final (+10d). Draft rules: ≤120 words · user's tone per client · invoice #, amount, due date · broken-promise quotes client · approval-aware · never templated.

**Approval is absolute**: draft → edit / regenerate / skip / pause → explicit Send only. **Nothing auto-sends.** Sends from user's Gmail, threaded, lands in Sent, recorded as evidence.

**Quick-compose**: rough intent → AI expands with thread + ledger context → review → send.

**Status**: Shipped (drafts, queue, send, quick-compose, escalation scheduler). Tone-learning from sent mail per client not verified.

### 11. Digest & Alerts (the daily habit)

Dashboard **Today** card + morning digest email: due/overdue with drafts · broken promises · confirm prompts · needs reply (disputes) · resolved since yesterday.

**Hard rule: no ledger link, no digest slot.**

Alerts: due today, became overdue, promise broken, dispute detected, payment confirmed, connection lost.

**Status**: Partial. Today card + digest email exist. Buckets need alignment (confirm prompts, "watching" state). **Hard rule** (nothing in digest unless ledger-linked) must be enforced in UI copy + filtering.

### 12. Client View

Per client: open + past invoices (newest Gmail date first), evidence timeline, identities, follow-ups sent, behavior stats after 2+ closed cycles.

**Status**: Partial. Client detail + stats exist. Invoice sort by `source_date` shipped. Follow-ups-sent section may be thin.

### 13. Review Queue

Low-confidence extractions and ambiguous mappings → cards with fields + quote + source → confirm / edit / not-payment-related (suppress). Users must never find a wrong number silently in ledger.

**Status**: Shipped. Queue surfaces reason labels, source + quote, field grid, and edit-before-confirm (Jul 2026).

### 14. Settings

Connection + disconnect (purge cache, ledger stays) · grace · escalation timing · late-fee · default payment terms · suppressed senders · delete account.

**Status**: Shipped. **Seed fixed at 60d**; `scan_window_months` applies to **ongoing background sync** only (Jul 2026 alignment).

### 15. Privacy Commitments

Two Gmail permissions. Store extracted facts + evidence + message refs — not the mailbox. Emails never train AI. Disconnect/deletion honored.

**Status**: Shipped in policy/copy; verify consent screen matches.

### 16. Explicitly OUT of MVP

Do **not** build or surface:

- Historical reconciliation / paid-unpaid inference / client confirmation cards at seed
- Bank statements & bank connections
- Generic inbox digest or triage
- General open-loop chasing (architect generically; ship payments only)
- Invoice creation (beyond manual track)
- Accounting-software sync (read notification emails only — no API sync)
- Auto-send
- Outlook
- Money-out / subscription tracking
- Analytics dashboards
- Teams
- Native mobile apps
- Deep archaeology scans (12-month inbox sweeps as default onboarding)
- Reconciliation screens / ambiguous receipt matcher as primary UX

### 17. Build Order (locked)

1. Auth + empty state + Gmail connect — **done**
2. Seed scan (60d sent-only) + curation screen + ledger + instant state eval → **demo-able** — **next**
3. Live sent-invoice auto-detection (signature moment)
4. Reply intelligence + client entities + evidence + review queue
5. State machine + nightly job + alerts + digest (in-app, then email)
6. Chase drafts + escalation + one-tap send + quick-compose → **sellable** — largely done; polish after seed
7. Receipt/remittance parsers + mark-paid polish + client behavior stats + settings — largely done

### 18. Beta Success Gates

| Metric | Gate |
|---|---|
| Time to first approved chase draft | < 3 minutes from OAuth for most users |
| Auto-detection of newly sent invoices | Appears within minutes, ≥95% precision |
| Reply-intelligence accuracy | ≥95% on regression fixture (S1–S20) before scaling |
| Daily/weekly digest engagement | >50% of connected users weekly |
| Core loop completions | send invoice → watch tracked → approve chase → mark paid |

---

## Alignment backlog (UI & behavior — implement when user says go)

Ordered by impact on the new vision. **No code changes until user requests each item.**

| # | Area | Current | Target (locked spec) |
|---|---|---|---|
| A1 | Onboarding scan | ~~12-month client-sweep~~ | **Done (Jul 2026)** — 60d sent-only seed + curation API + UI |
| A2 | Post-curation UX | ~~Lands on full ledger table~~ | **Done (Jul 2026)** — Today card first, ledger secondary |
| A3 | Empty / zero selection | ~~Generic empty ledger~~ | **Done (Jul 2026)** — WatchingEmptyState + forward tip |
| A4 | Empty dashboard copy | ~~Old hero~~ | **Done (Jul 2026)** — locked headline on landing + empty state |
| A5 | Today card | ~~4 buckets only~~ | **Done (Jul 2026)** — confirm prompts bucket + Received/Not yet actions |
| A6 | Live detection UX | ~~Background sync bar only~~ | **Done (Jul 2026)** — sent-only auto-track, 75s poll, banner + toast |
| A7 | Accounting tools | ~~Not parsed~~ | **Done (Jul 2026)** — QB/FreshBooks/Wave/Zoho notification parse in live detect |
| A8 | Payments UI | PaymentsCard + reconcile CTA | **Done (Jul 2026)** — confirm-paid framing; ambiguous matcher collapsed |
| A9 | Stale invoices | Not implemented | **Done (Jul 2026)** — 120d inactivity → Stale + one-time Today/digest prompt |
| A10 | Cross-domain merge | Auto domain only | **Done (Jul 2026)** — one-tap merge prompt for cross-domain same client |
| A11 | Settings scan window | Default 12 months | **Done (Jul 2026)** — seed fixed 60d; setting drives ongoing sync lookback |
| A12 | Review queue | Mixed reasons | **Done (Jul 2026)** — PRD §13 copy, fields + source, edit-before-confirm |

---

## Implementation reference (what exists today — Jul 2026)

Condensed technical inventory for agents. **Do not treat as product spec** — the locked sections above are authoritative for UX.

| Area | Shipped |
|---|---|
| Auth | JWT email/password, register/login/forgot/reset, lockout |
| Gmail | OAuth readonly+send, encrypted tokens, reconnect banners |
| Scan (legacy) | Client-sweep pipeline (`client_sweep.py`), 5-phase progress UI, OpenRouter AI per client |
| Ledger | Invoice rows, per-currency totals, domain client dedup, upsert by invoice ref |
| Clients | List + detail, payment behavior stats, identities |
| Lifecycle | States, grace, row actions, mark-paid/write-off + undo |
| Chase | AI drafts, escalation scheduler, chase queue card, Gmail send threaded |
| Receipts | Template parse (processors), match/reconcile API, PaymentsCard |
| Digest | Today card, daily email, timezone-aware schedule |
| Sync | Polling incremental sync (`run_client_sweep_sync`), manual sync button |
| Review | Queue with confirm/reject/suppress, reason codes |
| Settings | Grace, escalation, late fee, payment terms, suppress list, delete account |

**Key files**: `client_sweep.py`, `scan_router.py`, `ledger_reconcile.py`, `digest_sender.py`, `escalation_scheduler.py`, `Dashboard.jsx`, `TodayCard.jsx`, `ScanProgressCard.jsx`, `ReviewQueue.jsx`, `LedgerCard.jsx`.

---

## Instructions to next agent

- User approves changes **one feature at a time**. Do not batch-align the whole backlog unless asked.
- **Do not change** sign-up, sign-in, or Gmail connect flows unless explicitly requested.
- When implementing alignment items, update the **Alignment backlog** table (mark done / note deltas).
- NO auto-testing unless user asks. User tests themselves.
- Backend: `uvicorn server:app --reload --host 0.0.0.0 --port 8000`. Env: JWT_SECRET, GOOGLE_*, GMAIL_REDIRECT_URI, ENCRYPTION_KEY, OPENROUTER_API_KEY.
