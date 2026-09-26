# AR simulation runner

Seeds **real** QuickBooks invoices and **real** Gmail threads (via Unipile), then calls the same interactors the UI uses. Product code under `app/` is not modified.

One scenario file: `script/simulate/scenario.yml`.

## Identities

| Role | Email | Where |
|---|---|---|
| Logged-in user | `testuser@gmail.com` | Scotive account |
| Org mailbox | `wherewasthis.contact@gmail.com` | Unipile + Scotive mailbox integration |
| Client | `r24827708@gmail.com` | Unipile only (not a Scotive login) |

Those are the only two Gmail accounts. Both are public Gmail (`gmail.com`), so the matcher uses the exact `from:` / `to:` address. It must not search `from:gmail.com`. `clients.domain` stays blank.

Both Unipile accounts must already be connected. The org must already have QBO + Gmail connected in Scotive.

## Run

From the repo root, with the API container up:

```bash
docker compose exec -T api bin/rails simulate:ar -- --mode=all
```

Jobs run **inline**. After the snapshot the runner **raises** if any `expect:` line is wrong (tab, thread count, inbound).

## Modes

| `--mode=` | What it triggers (same as UI) |
|---|---|
| `onboarding` | QBO create+email invoices, then Unipile replies → `Quickbooks::ImportOpenInvoices` → `Quickbooks::EnqueueConversationMatch` → `Onboarding::Continue` |
| `sync` | Seed, then `Sync::Start` (inline `Sync::RunNow`: accounting + mailbox + clock) |
| `webhook` | Seed, then `Webhooks::Ingest` for QBO invoice create and each inbound client mail (received id on the **user** mailbox) |
| `all` | webhook ingest while sending, then onboarding, then sync |

## What the live pack covers (SIM-2301–2315)

| Invoice | Real-world case | Expected tab | Threads |
|---|---|---|---|
| SIM-2301 | Sent, silent, due in 3 days | Auto reminders | HOME only |
| SIM-2302 | Sent, silent, due today | Auto reminders | HOME only |
| SIM-2303 | Sent, silent, 2 days late (still in Friendly) | Auto reminders | HOME only |
| SIM-2304 | Client promised Friday (reply omits the number) | Needs you | HOME + inbound |
| SIM-2305 | Client asked to cut $400 | Needs you | HOME + inbound |
| SIM-2306 | Client asked for a W-9 | Needs you | HOME + inbound |
| SIM-2307 | Silent, 12 days late (past Friendly) | Needs you | HOME, no inbound |
| SIM-2308 | Client says already paid | Needs you | HOME + inbound |
| SIM-2309 | Two-way: client → you → client | Needs you | HOME + inbound |
| SIM-2310 + 2311 | One client mail names two invoices | Needs you on both | 2311 must pick up that thread |
| SIM-2312 | OOO on a new thread (must not pause) | Auto reminders | HOME only, no inbound |
| SIM-2313 | Project chatter, no invoice # (must not attach) | Auto reminders | HOME only, no inbound |
| SIM-2314 | Token-only send (pay link, no # in subject) | Auto reminders | HOME |
| SIM-2315 | Created in QBO, never emailed | Auto reminders | zero threads |

Watching / Stopped / Paid are not seeded. Those tabs are exercised in the UI after this seed (check-back date, Stop, books paid).

**Cannot live-test with these two Gmails** (unit specs only): Outlook, a corporate `@acme.com` coworker, a third AP alias inbox, QBO mark-paid / void.

Payment replies always name the invoice so Pass 2 does not joint-link every open invoice on this client.

## Send options

| `send.via` | What happens |
|---|---|
| `qbo` (default) | Create invoice. Native QBO `/send` only if `unique_subjects` is false **and** `send.subject` is blank (QBO always uses `Invoice from {company}` and Gmail stacks them). |
| `mailbox` | Create invoice, fetch PDF + `InvoiceLink`, send the QBO-lookalike HTML from `send.from`. Sets `EmailStatus=EmailSent`. Does **not** mark paid. |
| `plain` | Create invoice, send `send.subject` + `send.message` from Gmail with **no PDF**. For token-only HOME (no invoice # in the mail). |
| `none` | Create the QBO invoice and skip email. Batch match misses it; `FindInvoiceThread` runs. |

Default invoice subject is unique so Gmail does not group every invoice:

`Invoice {{invoice_number}} from Craig's Design and Landscaping Services`

Replies use Unipile `reply_to` plus the **parent email’s real subject** (`Re: …`). Inventing a different subject returns Unipile `invalid_reply_subject`.

| `thread:` | Meaning |
|---|---|
| `existing` (default) | The QBO invoice email. Client replies on **their** copy. User replies after that mail exists in **their** inbox. |
| `new` | New email, not a reply. Give it `as: name` so later turns can join it. |
| `last` | Last thread this sender received mail on. |
| `<name>` | The thread created with `as: <name>`. |

Placeholders: `{{invoice_number}}` `{{amount}}` `{{due_date}}` `{{pay_link}}` `{{client_email}}` `{{user_email}}`.

## Flags

```
--mode=onboarding|sync|webhook|all
--file=/app/script/simulate/scenario.yml
--user=testuser@gmail.com
--wait=10
--send-from-qbo=false
--skip-emails=true
--resume=true            # skip QBO create + mail; import/match/sync/assert only
```

Env overrides: `SIMULATE_MODE`, `SIMULATE_FILE`, `SIMULATE_USER`, `SIMULATE_WAIT`.

Requires `UNIPILE_WEBHOOK_SECRET` and, for QBO invoice webhooks, `QBO_WEBHOOK_VERIFIER_TOKEN`.
