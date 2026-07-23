# QBO Module 1 — OAuth connect / disconnect

**Spec parent:** [`QBO_INTEGRATION.md`](./QBO_INTEGRATION.md)  
**Status:** Implemented  
**App:** Scotive (Intuit sandbox)  
**Goal:** Users can connect and disconnect QuickBooks Online. Tokens stored encrypted. No invoice import yet.

---

## Sandbox / env (local)

| Variable | Purpose |
|---|---|
| `QBO_CLIENT_ID` | Intuit app Client ID |
| `QBO_CLIENT_SECRET` | Intuit app Client Secret |
| `QBO_REDIRECT_URI` | Must match Intuit app redirect exactly |
| `QBO_ENV` | `sandbox` (stored on connection; API host in Module 2+) |
| `ENCRYPTION_KEY` | Reuse existing Fernet key (same as Gmail) |
| `FRONTEND_URL` | Post-OAuth browser redirect (`http://localhost:3000`) |

**Redirect URI:**  
`https://reemerge-obstinate-latter.ngrok-free.dev/api/qbo/oauth/callback`

**Local requirement:** ngrok must tunnel to the FastAPI backend (port 8000). If the ngrok subdomain changes, update Intuit app + `.env` together.

**Scope:** `com.intuit.quickbooks.accounting`

---

## Shipped

| Area | Location |
|---|---|
| OAuth + status + disconnect + `get_qbo_access_token` | `backend/qbo_oauth.py` |
| Router mount + indexes | `backend/server.py` |
| Account wipe | `backend/settings_router.py` (`qbo_connections`) |
| Hook | `frontend/src/hooks/useQboConnection.js` |
| Callback toast | `frontend/src/hooks/useQboCallbackToast.js` (Dashboard) |
| Settings UI | `QboConnectionPanel` + Settings section |
| Connect button | `ConnectQboButton.jsx` |

**Collection `qbo_connections`:** `user_id` (unique), `realm_id`, encrypted tokens, `token_expires_at`, `scopes`, `status`, `env`, `company_name` (null until Module 2), timestamps.

**Routes:** `GET /api/qbo/status` · `GET /api/qbo/oauth/start` · `GET /api/qbo/oauth/callback` · `POST /api/qbo/disconnect`

---

## How to test

1. Backend running; ngrok → `:8000` with the redirect URI above registered on Intuit.
2. Log in → **Settings** → **Connect QuickBooks** → Intuit sandbox consent.
3. Land on dashboard with toast; Settings shows connected (realm + sandbox).
4. Disconnect → tokens gone; ledger/Gmail unchanged.

---

## Explicitly out of Module 1 (next modules)

- Invoice / Customer API · ledger · conversation match · webhooks · Sync now QBO · onboarding Path B
