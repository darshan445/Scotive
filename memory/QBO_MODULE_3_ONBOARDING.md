# QBO Module 3 — Onboarding Path B

**Spec parent:** [`QBO_INTEGRATION.md`](./QBO_INTEGRATION.md)  
**Depends on:** Module 1 (OAuth) · Module 2 (import)  
**Status:** Implemented  
**Goal:** Dual-connect onboarding (Gmail + optional QBO). Silent Gmail seed. Next → curation (Gmail-only) or dashboard (if QBO) with deferred seed review banner.

**Out of this module:** Gmail conversation match for QBO invoices (Module 4).

---

## Flow

```text
After signup → connections screen (two buttons)
  Gmail (required)  → connect → start 90d seed in background (no progress UI)
  QBO (optional)    → connect → import unpaid invoices
  → user clicks Next
       if Gmail only    → preparing → curation → dashboard
       if QBO connected → dashboard immediately
            → seed continues in background
            → when seed finds Gmail-only leftovers → sticky banner:
                 Discard | Review & confirm → curation → track selected
```

## Backend

- Phases: `connections` | `preparing` | `curating` | `complete`/`watching`
- QBO Next → `unlock_qbo_dashboard` (watching on; does **not** auto-ignore Gmail leftovers)
- `seed_review` on `/onboarding/state`: `{ status, pending_count, seed_running }`
- `POST /seed/review/discard` — dismiss leftovers (track none)
- `POST /seed/confirm` — same curation confirm for Review path
- Pending seed message IDs held out of live/incremental auto-track until reviewed

## Frontend

- `OnboardingConnections` — Gmail + QBO + Next
- `SeedReviewBanner` — sticky on dashboard until Discard / Review (not a timed toast)
- Review opens `CurationScreen` inline on the dashboard
