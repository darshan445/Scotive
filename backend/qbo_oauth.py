"""QuickBooks Online OAuth 2.0 connect / disconnect (Module 1).

Stores encrypted tokens + realm_id. No Invoice API calls here.
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from gmail_oauth import decrypt_token, encrypt_token

logger = logging.getLogger("scotive.qbo")

QBO_SCOPE = "com.intuit.quickbooks.accounting"
QBO_AUTH_ENDPOINT = "https://appcenter.intuit.com/connect/oauth2"
QBO_TOKEN_ENDPOINT = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_REVOKE_ENDPOINT = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"

STATE_TTL_MINUTES = 15
PROVIDER = "qbo"


class QboAuthError(Exception):
    """Raised when refresh token is invalid (user revoked) or connection missing."""


# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------
def _client_id() -> str:
    return os.environ["QBO_CLIENT_ID"]


def _client_secret() -> str:
    return os.environ["QBO_CLIENT_SECRET"]


def _redirect_uri() -> str:
    return os.environ["QBO_REDIRECT_URI"]


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _qbo_env() -> str:
    env = (os.environ.get("QBO_ENV") or "sandbox").strip().lower()
    return "production" if env == "production" else "sandbox"


def _basic_auth_header() -> str:
    raw = f"{_client_id()}:{_client_secret()}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class QboStatus(BaseModel):
    connected: bool
    status: str = "disconnected"  # disconnected | connected | revoked
    realm_id: Optional[str] = None
    company_name: Optional[str] = None
    env: Optional[str] = None
    connected_at: Optional[datetime] = None


class OAuthStartResponse(BaseModel):
    authorization_url: str


# ---------------------------------------------------------------------------
# State (oauth_states with provider=qbo)
# ---------------------------------------------------------------------------
async def issue_state(db, user_id) -> str:
    token = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "state": token,
        "user_id": user_id,
        "provider": PROVIDER,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES)).isoformat(),
    })
    return token


async def consume_state(db, state: str) -> Optional[str]:
    doc = await db.oauth_states.find_one({"state": state, "provider": PROVIDER})
    if not doc:
        # Fallback: unique state token may predate provider field — still consume once.
        doc = await db.oauth_states.find_one({"state": state})
        if not doc:
            return None
    await db.oauth_states.delete_one({"_id": doc["_id"]})
    expires_at = doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    return doc["user_id"]


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------
async def upsert_qbo_connection(db, user_id, realm_id: str, tokens: dict, granted_scopes: str):
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "realm_id": str(realm_id),
        "access_token_enc": encrypt_token(tokens["access_token"]),
        "token_expires_at": (
            now + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        ).isoformat(),
        "scopes": granted_scopes.split() if isinstance(granted_scopes, str) else list(granted_scopes or []),
        "status": "connected",
        "env": _qbo_env(),
        "updated_at": now.isoformat(),
        "last_error": None,
    }
    if tokens.get("refresh_token"):
        doc["refresh_token_enc"] = encrypt_token(tokens["refresh_token"])

    existing = await db.qbo_connections.find_one({"user_id": user_id})
    if existing is None:
        doc["connected_at"] = now.isoformat()
        doc["company_name"] = None
        await db.qbo_connections.insert_one(doc)
    else:
        if "refresh_token_enc" not in doc and existing.get("refresh_token_enc"):
            doc["refresh_token_enc"] = existing["refresh_token_enc"]
        if existing.get("company_name"):
            doc["company_name"] = existing["company_name"]
        await db.qbo_connections.update_one({"user_id": user_id}, {"$set": doc})
    return doc


def _make_status(conn: Optional[dict]) -> QboStatus:
    if not conn:
        return QboStatus(connected=False, status="disconnected")
    status_val = conn.get("status", "connected")
    connected_at = conn.get("connected_at")
    if isinstance(connected_at, str):
        connected_at = datetime.fromisoformat(connected_at)
    company_name = (conn.get("company_name") or "").strip() or None
    if status_val == "revoked":
        return QboStatus(
            connected=False,
            status="revoked",
            realm_id=conn.get("realm_id"),
            company_name=company_name,
            env=conn.get("env"),
            connected_at=connected_at,
        )
    return QboStatus(
        connected=True,
        status="connected",
        realm_id=conn.get("realm_id"),
        company_name=company_name,
        env=conn.get("env"),
        connected_at=connected_at,
    )


# ---------------------------------------------------------------------------
# Intuit HTTP
# ---------------------------------------------------------------------------
async def exchange_code_for_tokens(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(),
    }
    headers = {
        "Authorization": _basic_auth_header(),
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(QBO_TOKEN_ENDPOINT, data=data, headers=headers)
        if r.status_code != 200:
            logger.warning("QBO token exchange failed: %s %s", r.status_code, r.text)
            raise HTTPException(status_code=400, detail="Failed to exchange QuickBooks authorization code.")
        return r.json()


async def refresh_access_token(refresh_token: str) -> dict:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    headers = {
        "Authorization": _basic_auth_header(),
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(QBO_TOKEN_ENDPOINT, data=data, headers=headers)
        if r.status_code != 200:
            logger.warning("QBO refresh failed: %s %s", r.status_code, r.text)
            raise QboAuthError(r.text)
        return r.json()


async def revoke_token(token: str) -> None:
    headers = {
        "Authorization": _basic_auth_header(),
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            await client.post(QBO_REVOKE_ENDPOINT, data={"token": token}, headers=headers)
        except Exception as e:  # pragma: no cover
            logger.warning("QBO revoke best-effort failed: %s", e)


async def get_qbo_access_token(db, user_id) -> str:
    """Return a valid access token; refresh and mark revoked on failure."""
    conn = await db.qbo_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") == "revoked":
        raise QboAuthError("No QuickBooks connection")
    expires_at = conn.get("token_expires_at") or conn.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if expires_at and expires_at > now + timedelta(seconds=60):
        return decrypt_token(conn["access_token_enc"])
    if not conn.get("refresh_token_enc"):
        await db.qbo_connections.update_one(
            {"user_id": user_id},
            {"$set": {"status": "revoked", "last_error": "missing_refresh_token", "updated_at": now.isoformat()}},
        )
        raise QboAuthError("Missing refresh token")
    refresh = decrypt_token(conn["refresh_token_enc"])
    try:
        tok = await refresh_access_token(refresh)
    except QboAuthError as e:
        await db.qbo_connections.update_one(
            {"user_id": user_id},
            {"$set": {
                "status": "revoked",
                "last_error": str(e)[:500],
                "updated_at": now.isoformat(),
            }},
        )
        raise
    patch = {
        "access_token_enc": encrypt_token(tok["access_token"]),
        "token_expires_at": (now + timedelta(seconds=int(tok.get("expires_in", 3600)))).isoformat(),
        "status": "connected",
        "last_error": None,
        "updated_at": now.isoformat(),
    }
    # Intuit may rotate refresh tokens
    if tok.get("refresh_token"):
        patch["refresh_token_enc"] = encrypt_token(tok["refresh_token"])
    await db.qbo_connections.update_one({"user_id": user_id}, {"$set": patch})
    return tok["access_token"]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def build_router(db, get_current_user):
    router = APIRouter(prefix="/qbo", tags=["qbo"])

    @router.get("/status", response_model=QboStatus)
    async def status(user: dict = Depends(get_current_user)):
        conn = await db.qbo_connections.find_one({"user_id": user["_id"]})
        return _make_status(conn)

    @router.get("/oauth/start", response_model=OAuthStartResponse)
    async def start(user: dict = Depends(get_current_user)):
        try:
            _client_id()
            _client_secret()
            _redirect_uri()
        except KeyError as e:
            raise HTTPException(
                status_code=503,
                detail=f"QuickBooks OAuth is not configured ({e.args[0]} missing).",
            ) from e
        state = await issue_state(db, user["_id"])
        params = {
            "client_id": _client_id(),
            "redirect_uri": _redirect_uri(),
            "response_type": "code",
            "scope": QBO_SCOPE,
            "state": state,
        }
        url = f"{QBO_AUTH_ENDPOINT}?{urlencode(params)}"
        return OAuthStartResponse(authorization_url=url)

    @router.get("/oauth/callback")
    async def callback(request: Request):
        params = request.query_params
        code = params.get("code")
        state = params.get("state")
        realm_id = params.get("realmId")
        err = params.get("error")
        frontend = _frontend_url()

        if err or not code or not state:
            if state:
                await consume_state(db, state)
            reason = err or "cancelled"
            return RedirectResponse(f"{frontend}/dashboard?qbo={reason}")

        user_id = await consume_state(db, state)
        if user_id is None:
            return RedirectResponse(f"{frontend}/dashboard?qbo=state_invalid")

        if not realm_id:
            return RedirectResponse(f"{frontend}/dashboard?qbo=error")

        try:
            tokens = await exchange_code_for_tokens(code)
            granted = tokens.get("scope") or QBO_SCOPE
            await upsert_qbo_connection(db, user_id, realm_id, tokens, granted)
        except HTTPException as e:
            logger.warning("QBO OAuth callback error: %s", e.detail)
            return RedirectResponse(f"{frontend}/dashboard?qbo=error")
        except Exception as e:
            logger.exception("QBO OAuth callback unexpected error: %s", e)
            return RedirectResponse(f"{frontend}/dashboard?qbo=error")

        return RedirectResponse(f"{frontend}/dashboard?qbo=connected")

    @router.post("/disconnect")
    async def disconnect(user: dict = Depends(get_current_user)):
        conn = await db.qbo_connections.find_one({"user_id": user["_id"]})
        if conn:
            enc = conn.get("refresh_token_enc") or conn.get("access_token_enc")
            if enc:
                try:
                    await revoke_token(decrypt_token(enc))
                except Exception:  # pragma: no cover
                    pass
            await db.qbo_connections.delete_one({"_id": conn["_id"]})
        return {"ok": True}

    @router.post("/import")
    async def import_invoices(user: dict = Depends(get_current_user)):
        """Pull unpaid QuickBooks invoices into the ledger (Module 2)."""
        from qbo_import import import_unpaid_invoices

        conn = await db.qbo_connections.find_one({"user_id": user["_id"]})
        if not conn or conn.get("status") != "connected":
            raise HTTPException(status_code=400, detail="Connect QuickBooks first.")
        try:
            counts = await import_unpaid_invoices(db, user["_id"])
        except QboAuthError as e:
            raise HTTPException(status_code=401, detail=str(e) or "QuickBooks auth failed.") from e
        except httpx.HTTPStatusError as e:
            logger.warning("QBO import HTTP error: %s %s", e.response.status_code, e.response.text[:300])
            raise HTTPException(
                status_code=502,
                detail="QuickBooks API error while importing invoices.",
            ) from e
        return {"ok": True, "counts": counts}

    @router.post("/match-conversations")
    async def match_conversations(user: dict = Depends(get_current_user)):
        """Module 4: enqueue Gmail conversation match for QBO invoices (background)."""
        from qbo_conversation import enqueue_qbo_conversation_match

        conn = await db.qbo_connections.find_one({"user_id": user["_id"]})
        if not conn or conn.get("status") != "connected":
            raise HTTPException(status_code=400, detail="Connect QuickBooks first.")
        try:
            result = await enqueue_qbo_conversation_match(db, user["_id"])
        except Exception as e:
            logger.exception("QBO match-conversations failed: %s", e)
            raise HTTPException(status_code=500, detail="Conversation match failed.") from e
        return {"ok": True, **result}

    @router.get("/pipeline-status")
    async def pipeline_status(user: dict = Depends(get_current_user)):
        """Progress for background QBO conversation / status pipeline."""
        from qbo_conversation import get_qbo_pipeline_status

        status = await get_qbo_pipeline_status(db, user["_id"])
        return {"ok": True, "pipeline": status}

    @router.post("/sync-paid")
    async def sync_paid(user: dict = Depends(get_current_user)):
        """Module 5: poll QBO Balance for open ledger rows; mark Paid when zero."""
        from qbo_paid_sync import sync_qbo_paid_status

        conn = await db.qbo_connections.find_one({"user_id": user["_id"]})
        if not conn or conn.get("status") != "connected":
            raise HTTPException(status_code=400, detail="Connect QuickBooks first.")
        try:
            counts = await sync_qbo_paid_status(db, user["_id"])
        except QboAuthError as e:
            raise HTTPException(status_code=401, detail=str(e) or "QuickBooks auth failed.") from e
        except Exception as e:
            logger.exception("QBO sync-paid failed: %s", e)
            raise HTTPException(status_code=500, detail="Paid sync failed.") from e
        return {"ok": True, "counts": counts}

    # Module 6 webhooks (public; signature-verified)
    from qbo_webhooks import build_webhook_routes
    router.include_router(build_webhook_routes(db))

    return router
