# Scotive – Product Memory

## Problem statement (verbatim from user)
Scotive MVP — Payment ops inside Gmail. User connects Gmail → sees everything clients owe them → chases with AI drafts sent from their own address, always with approval.
Target user: 1–20 employee US service firms (agencies, consultants, studios) that invoice clients over email.

Full spec is stored in the initial user message (14 sections + build order + beta gates). We are building strictly feature-by-feature with user approval between each.

## User's build directives
- Build one feature at a time, wait for approval, iterate backend-first, then move on.
- Custom JWT email/password auth, no email verification for now.
- No email provider integration yet (forgot-password logs the link to backend logs).
- AI parsing to use OpenRouter (`sk-or-v1-...`) with `openai/gpt-4o-mini` as default plus best models for specific use-cases later.
- Google OAuth client id/secret provided by user for future Gmail feature. User will register the redirect URI themselves.

## Personas
- **Founder/owner** of a 1–20 employee US service firm (agency, consultant, studio) who invoices clients over email and needs to be paid faster without becoming the "bad cop."
- Secondary: **Ops/finance lead** in the same size firm.

## Architecture
- Backend: FastAPI @ 0.0.0.0:8001 via supervisor. All routes under `/api`.
- Frontend: React (react-router-dom v7) via craco. Tailwind + Shadcn UI. Custom Cabinet Grotesk / Manrope / JetBrains Mono type system.
- Data: MongoDB via `MONGO_URL` + `DB_NAME` env vars.
- Auth: JWT (access 24h, refresh 30d) issued as httpOnly cookies AND accepted via `Authorization: Bearer` header. Passwords hashed with bcrypt. Login brute-force protection: 5 fails / 15min lockout per (ip, email).

## Feature status
### ✅ Feature 1 — Auth (Feb 2026)
Backend endpoints (`/api/auth/*`): register, login, logout, me, refresh, forgot-password (stub logs link), reset-password. MongoDB indexes on `users.email` unique, `login_attempts.identifier`, `password_reset_tokens.expires_at` TTL. Admin user auto-seeded from `.env`.
Frontend routes: `/login`, `/register`, `/forgot-password`, `/reset-password`, `/dashboard` (protected placeholder). AuthContext + ProtectedRoute/GuestRoute wrappers. Shadcn Button/Input/Label + Sonner toaster wired.

## Backlog (prioritised)
- **P0 Feature 2** — Empty-state marketing dashboard with "Connect Gmail" CTA, trust line, and 3-step "How it works". (Next up.)
- **P0 Feature 3** — Google OAuth Gmail connect flow (`/api/gmail/oauth/*`).
- **P0 Feature 4** — Historical scan pipeline (12-month window, noise filter, structured-source parsing, AI classification, ledger seeding, progress card).
- **P1 Feature 5** — Client entity + evidence timelines + review queue.
- **P1 Feature 6** — Lifecycle state machine (overdue / promised / promise-broken / disputed / partial / paid).
- **P1 Feature 7** — Chase drafts with escalation ladder, approval flow, quick-compose, send from user Gmail.
- **P2 Feature 8** — Receipt matching, partial payments, mark-paid/write-off, client stats, settings.
- **P2 Feature 9** — Continuous sync + daily digest email.

## Deferred / explicitly NOT in MVP
Generic inbox digest, notes, Outlook support, auto-send, analytics dashboards, team/multi-user, accounting-software write-back, payment links, native mobile app.
