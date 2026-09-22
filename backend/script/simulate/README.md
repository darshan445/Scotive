# AR simulation runner

Seeds **real** QuickBooks invoices and **real** Gmail threads (via Unipile), then calls the same interactors the UI uses. Product code under `app/` is not modified.

## Identities

| Role | Email | Where |
|---|---|---|
| Logged-in user | `testuser@gmail.com` | Scotive account |
| Org mailbox | `tdarshan336@gmail.com` | Unipile + Scotive mailbox integration |
| Client | `vt444713@gmail.com` | Unipile only (not a Scotive login) |

Both Gmail accounts must already be connected in Unipile. The org must already have QBO + Gmail connected in Scotive.

## Run

From the repo root, with the API container up:

```bash
docker compose exec api bin/rails runner script/simulate/run.rb -- --mode=all
```

Or:

```bash
docker compose exec api bin/rails simulate:ar -- --mode=onboarding
```

## Modes

| `--mode=` | What it triggers (same as UI) |
|---|---|
| `onboarding` | QBO create+email invoices, then Unipile replies → `Quickbooks::ImportOpenInvoices` → `Quickbooks::EnqueueConversationMatch` → `Onboarding::Continue` |
| `sync` | Seed, then `Sync::Start` (inline `Sync::RunNow`: accounting + mailbox + clock) |
| `webhook` | Seed, then `Webhooks::Ingest` for QBO invoice create and each inbound client mail (received id on the **user** mailbox) |
| `all` | webhook ingest while sending, then onboarding, then sync |

Jobs run **inline** in this process so Sidekiq is not required.

## Scenario file

Default: `backend/script/simulate/scenario.yml`

Clustering extras live in two more files. **Do not run them while SIM-21xx invoices are still open** on this client — Pass 2 joint-links every open invoice, which hides clock / fallback / single-invoice leftover.

```bash
# Main Pass 1/2 suite (digits, QBO-style subject, OOO, other_payment, quoted-only)
docker compose exec api bin/rails simulate:ar -- --mode=onboarding

# Token-only HOME + outbound clock + FindInvoiceThread miss (pay/void SIM-21xx first)
docker compose exec api bin/rails simulate:ar -- --mode=onboarding --file=/app/script/simulate/scenario_clock.yml

# Pass 2 with exactly one open invoice (same: no other open invoices for this client)
docker compose exec api bin/rails simulate:ar -- --mode=onboarding --file=/app/script/simulate/scenario_single.yml
```

```yaml
invoices:
  - number: SIM-1001
    send:
      via: qbo                         # QBO /send (native email)
      message: "Due {{due_date}}."     # optional QBO customer note
  - number: SIM-1002
    send:
      via: mailbox                     # same look as QBO email, from Gmail
      from: tdarshan336@gmail.com
  - number: SIM-1003
    send:
      via: plain                       # custom subject/body, no PDF (token-only HOME)
      subject: "Your invoice is ready"
      message: "Pay here: {{pay_link}}"
  - number: SIM-1004
    send:
      via: none                        # create in QBO, never email (fallback miss)
```

| `send.via` | What happens |
|---|---|
| `qbo` (default) | Create invoice. Native QBO `/send` only if `unique_subjects` is false **and** `send.subject` is blank (QBO always uses `Invoice from {company}` and Gmail stacks them). |
| `mailbox` | Create invoice, fetch PDF + `InvoiceLink`, send the QBO-lookalike HTML from `send.from`. Sets `EmailStatus=EmailSent`. Does **not** mark paid. |
| `plain` | Create invoice, send `send.subject` + `send.message` from Gmail with **no PDF**. For token-only HOME (no invoice # in the mail). |
| `none` | Create the QBO invoice and skip email. Batch match misses it; `FindInvoiceThread` runs. |

Default invoice subject is unique so Gmail does not group every invoice:

`Invoice {{invoice_number}} from Craig's Design and Landscaping Services`

Set `send.subject` to override (SIM-2006 uses the generic QBO subject on purpose). `unique_subjects: false` or `--unique-subjects=false` restores native QBO `/send` grouping.

`send.message` is only written onto the QBO invoice (CustomerMemo / PDF note). The mailbox email body is the recreated QBO template.

Replies use Unipile `reply_to` plus the **parent email’s real subject** (`Re: …`). Inventing a different subject returns Unipile `invalid_reply_subject`.

**Which thread is “existing”?**

| `thread:` | Meaning |
|---|---|
| `existing` (default) | The QBO invoice email. Client replies on **their** copy. User replies after that mail exists in **their** inbox. |
| `new` | New email, not a reply. Give it `as: name` so later turns can join it. After it is delivered, it is the existing thread for the recipient (`thread: last` or `thread: name`). |
| `last` | Last thread this sender received mail on (invoice, or a new email from the other party). |
| `<name>` | The thread created with `as: <name>`. |

Client mail is sent from `vt444713` Unipile; user mail from `tdarshan336` Unipile. QBO mail is sent by QuickBooks.

Placeholders: `{{invoice_number}}` `{{amount}}` `{{due_date}}` `{{pay_link}}` `{{client_email}}` `{{user_email}}`. Put the invoice number in new-thread subjects if you want Scotive matching to attach that mail to the invoice.

## Flags

```
--mode=onboarding|sync|webhook|all
--file=/app/script/simulate/scenario.yml
--user=testuser@gmail.com
--wait=10
--send-from-qbo=false    # skip QBO email; only Unipile conversation turns
--skip-emails=true
```

Env overrides: `SIMULATE_MODE`, `SIMULATE_FILE`, `SIMULATE_USER`, `SIMULATE_WAIT`.

## Webhooks

Mailbox webhooks use the message **as it appears on `tdarshan336`**, not the send id from the client Unipile account. That matches a real Unipile `mail_received` on the org mailbox.

Requires `UNIPILE_WEBHOOK_SECRET` and, for QBO invoice webhooks, `QBO_WEBHOOK_VERIFIER_TOKEN`.
