# Scotive — PRD

## Shipped (Feb 2026)
- **F1 Auth**: JWT email/password, register/login/logout/me/refresh/forgot/reset. Bcrypt, brute-force lockout, admin seeded.
- **F2 Empty-state dashboard**: hero "$18,450 across 7 clients" preview, Connect Gmail CTA, trust line, 3-step how-it-works.
- **F3 Gmail OAuth**: scopes `gmail.readonly` + `gmail.send` + `openid email profile`. Fernet-encrypted refresh tokens. States: disconnected/connected/send_missing/revoked with reconnect banners. Endpoints: `/api/gmail/{status,oauth/start,oauth/callback,disconnect,mark-revoked}`.
- **F4 Historical scan**: 5 phases (fetching/filtering/extracting/building/complete). Cheap noise filter + payment-processor whitelist + money-keyword regex. gpt-4o-mini via OpenRouter, 150-call cap, concurrency 4. Progress polling. Ledger populated. Endpoints: `/api/scan/{start,status}`, `/api/ledger`.
- **F5 Clients + timelines + review queue**: same-domain identity linking, expandable evidence timelines with quoted sentences. Review queue for confidence < 0.75 with confirm/reject/suppress actions. Pages: `/clients`, `/clients/:email`, `/review`. Endpoints: `/api/invoices/:id/timeline`, `/api/clients`, `/api/clients/:email`, `/api/review-queue/*`.
- **F6 Lifecycle + Today digest**: state machine (invoiced/overdue/promised/promise_broken/disputed/partially_paid/paid/written_off). Date-driven transitions via `/api/lifecycle/run`. Row actions dropdown. Today card with 4 sections. Endpoints: `/api/invoices/:id/action`, `/api/lifecycle/run`, `/api/digest/today`.
- **F7 Chase drafts + send**: AI drafts (tone auto by status), regenerate w/ note, quick-compose from rough intent, real Gmail send threaded into original conversation, `chase_sends` log. Endpoints: `/api/invoices/:id/{draft-chase,send-chase}`, `/api/quick-compose`.

## Remaining
- **F8 Receipt matching, partial payments, mark-paid/write-off polish, client stats, settings** — split into:
  - **8a** Receipt matching + partial payments (cross-thread amount + payer-name similarity, balance reduction, remainder promise)
  - **8b** Mark-paid / write-off confirm dialogs + undo toast
  - **8c** Client payment stats (avg days late, promise-keep rate) after 2+ payment cycles
  - **8d** Settings page: grace periods, escalation timing, late-fee toggle, scan window, suppressed senders list, delete account
- **F9 Continuous sync + daily digest email + escalation ladder scheduler** (pre-due 3d / due-date / firm 3d after / final 10d after) + Gmail push/poll for new mail.

## Instructions to next agent
User builds feature-by-feature and approves each. NO auto-testing (user tests themselves). Backend URL: `https://partial-pay-1.preview.emergentagent.com`. Env keys already set: JWT_SECRET, GOOGLE_CLIENT_ID/SECRET, GMAIL_REDIRECT_URI, ENCRYPTION_KEY, OPENROUTER_API_KEY. Admin: admin@scotive.com / Admin@Scotive1.
