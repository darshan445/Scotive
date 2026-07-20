"""Gmail OAuth 2.0 web-server flow.

Requests exactly two Gmail scopes plus openid/email so we can identify the
connected mailbox address: gmail.readonly and gmail.send.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

logger = logging.getLogger("scotive.gmail")

# ---------------------------------------------------------------------------
# OAuth constants
# ---------------------------------------------------------------------------
GMAIL_SCOPE_READ = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPE_SEND = "https://www.googleapis.com/auth/gmail.send"
IDENTITY_SCOPES = ["openid", "email", "profile"]
REQUESTED_SCOPES = IDENTITY_SCOPES + [GMAIL_SCOPE_READ, GMAIL_SCOPE_SEND]

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"

STATE_TTL_MINUTES = 15


# ---------------------------------------------------------------------------
# Env-derived config
# ---------------------------------------------------------------------------
def _client_id() -> str:
    return os.environ["GOOGLE_CLIENT_ID"]


def _client_secret() -> str:
    return os.environ["GOOGLE_CLIENT_SECRET"]


def _redirect_uri() -> str:
    return os.environ["GMAIL_REDIRECT_URI"]


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _fernet() -> Fernet:
    key = os.environ["ENCRYPTION_KEY"]
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Encrypted token corrupted") from e


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class GmailStatus(BaseModel):
    connected: bool
    email: Optional[str] = None
    account_name: Optional[str] = None
    can_send: bool = False
    connected_at: Optional[datetime] = None
    status: str = "disconnected"  # disconnected | connected | revoked | send_missing


def name_from_userinfo(userinfo: dict) -> Optional[str]:
    """Prefer Google profile display name, then given name."""
    if not userinfo:
        return None
    for key in ("name", "given_name"):
        val = (userinfo.get(key) or "").strip()
        if val:
            return val
    return None


def signer_fallback_from_email(email: Optional[str]) -> Optional[str]:
    """Last-resort sign-off when Google profile name is unavailable."""
    if not email or "@" not in email:
        return None
    local = email.split("@", 1)[0].strip()
    if not local:
        return None
    return local.replace(".", " ").replace("_", " ").title()


class OAuthStartResponse(BaseModel):
    authorization_url: str


# ---------------------------------------------------------------------------
# DB helpers (db handle is injected by server.py through get_db)
# ---------------------------------------------------------------------------
def scopes_include_send(scope_str: str) -> bool:
    granted = set((scope_str or "").split())
    return GMAIL_SCOPE_SEND in granted


def scopes_include_read(scope_str: str) -> bool:
    granted = set((scope_str or "").split())
    return GMAIL_SCOPE_READ in granted


async def upsert_gmail_connection(
    db,
    user_id,
    email,
    tokens,
    granted_scopes: str,
    account_name: Optional[str] = None,
):
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        "email": email,
        "access_token_enc": encrypt_token(tokens["access_token"]),
        "expires_at": (now + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat(),
        "scopes": granted_scopes,
        "can_send": scopes_include_send(granted_scopes),
        "can_read": scopes_include_read(granted_scopes),
        "status": "connected",
        "updated_at": now.isoformat(),
    }
    if account_name:
        doc["account_name"] = account_name.strip()
    # Preserve stored refresh_token if Google didn't send a new one on re-consent
    if tokens.get("refresh_token"):
        doc["refresh_token_enc"] = encrypt_token(tokens["refresh_token"])
    existing = await db.gmail_connections.find_one({"user_id": user_id})
    if existing is None:
        doc["connected_at"] = now.isoformat()
        await db.gmail_connections.insert_one(doc)
    else:
        if "refresh_token_enc" not in doc and existing.get("refresh_token_enc"):
            doc["refresh_token_enc"] = existing["refresh_token_enc"]
        # Keep prior account_name if this reconnect didn't return a profile name
        if "account_name" not in doc and existing.get("account_name"):
            doc["account_name"] = existing["account_name"]
        await db.gmail_connections.update_one({"user_id": user_id}, {"$set": doc})
    return doc


async def ensure_gmail_account_name(db, user_id) -> Optional[str]:
    """Return stored Gmail profile name, backfilling from Google userinfo if missing."""
    conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not conn:
        return None
    existing = (conn.get("account_name") or "").strip()
    if existing:
        return existing

    # Lazy import — gmail_client imports decrypt helpers from this module.
    try:
        from gmail_client import get_access_token
        access = await get_access_token(db, user_id)
        info = await fetch_userinfo(access)
        name = name_from_userinfo(info)
    except Exception as e:
        logger.warning("Could not backfill Gmail account_name for %s: %s", user_id, e)
        name = None

    if name:
        await db.gmail_connections.update_one(
            {"user_id": user_id},
            {"$set": {"account_name": name}},
        )
        return name

    return signer_fallback_from_email(conn.get("email"))


def _make_status(conn: Optional[dict]) -> GmailStatus:
    if not conn:
        return GmailStatus(connected=False, status="disconnected")
    status_val = conn.get("status", "connected")
    connected_at = conn.get("connected_at")
    if isinstance(connected_at, str):
        connected_at = datetime.fromisoformat(connected_at)
    account_name = (conn.get("account_name") or "").strip() or None
    if status_val == "revoked":
        return GmailStatus(
            connected=False,
            email=conn.get("email"),
            account_name=account_name,
            can_send=False,
            connected_at=connected_at,
            status="revoked",
        )
    can_send = bool(conn.get("can_send"))
    return GmailStatus(
        connected=True,
        email=conn.get("email"),
        account_name=account_name,
        can_send=can_send,
        connected_at=connected_at,
        status="connected" if can_send else "send_missing",
    )


# ---------------------------------------------------------------------------
# HTTP calls to Google
# ---------------------------------------------------------------------------
async def exchange_code_for_tokens(code: str) -> dict:
    data = {
        "code": code,
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "redirect_uri": _redirect_uri(),
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(GOOGLE_TOKEN_ENDPOINT, data=data)
        if r.status_code != 200:
            logger.warning("Token exchange failed: %s %s", r.status_code, r.text)
            raise HTTPException(status_code=400, detail="Failed to exchange authorization code.")
        return r.json()


async def fetch_userinfo(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if r.status_code != 200:
            logger.warning("Userinfo failed: %s %s", r.status_code, r.text)
            raise HTTPException(status_code=400, detail="Failed to fetch Google account info.")
        return r.json()


async def revoke_token(token: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(GOOGLE_REVOKE_ENDPOINT, data={"token": token})
        except Exception as e:  # pragma: no cover
            logger.warning("Revoke best-effort failed: %s", e)


# ---------------------------------------------------------------------------
# State token (opaque, TTL-checked in DB)
# ---------------------------------------------------------------------------
async def issue_state(db, user_id) -> str:
    token = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "state": token,
        "user_id": user_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES)).isoformat(),
    })
    return token


async def consume_state(db, state: str) -> Optional[str]:
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
# Router factory (server.py wires in db + get_current_user)
# ---------------------------------------------------------------------------
def build_router(db, get_current_user):
    router = APIRouter(prefix="/gmail", tags=["gmail"])

    @router.get("/status", response_model=GmailStatus)
    async def status(user: dict = Depends(get_current_user)):
        conn = await db.gmail_connections.find_one({"user_id": user["_id"]})
        return _make_status(conn)

    @router.get("/oauth/start", response_model=OAuthStartResponse)
    async def start(user: dict = Depends(get_current_user)):
        state = await issue_state(db, user["_id"])
        params = {
            "response_type": "code",
            "client_id": _client_id(),
            "redirect_uri": _redirect_uri(),
            "scope": " ".join(REQUESTED_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"
        return OAuthStartResponse(authorization_url=url)

    @router.get("/oauth/callback")
    async def callback(request: Request):
        params = request.query_params
        code = params.get("code")
        state = params.get("state")
        err = params.get("error")
        frontend = _frontend_url()

        # User cancelled the consent
        if err or not code or not state:
            if state:
                await consume_state(db, state)
            reason = err or "cancelled"
            return RedirectResponse(f"{frontend}/dashboard?gmail={reason}")

        user_id = await consume_state(db, state)
        if user_id is None:
            return RedirectResponse(f"{frontend}/dashboard?gmail=state_invalid")

        try:
            tokens = await exchange_code_for_tokens(code)
            granted = tokens.get("scope", "")
            if not scopes_include_read(granted):
                return RedirectResponse(f"{frontend}/dashboard?gmail=read_missing")
            userinfo = await fetch_userinfo(tokens["access_token"])
            email = (userinfo.get("email") or "").lower()
            account_name = name_from_userinfo(userinfo)
            await upsert_gmail_connection(
                db, user_id, email, tokens, granted, account_name=account_name,
            )
        except HTTPException as e:
            logger.warning("OAuth callback error: %s", e.detail)
            return RedirectResponse(f"{frontend}/dashboard?gmail=error")

        result = "connected" if scopes_include_send(granted) else "send_missing"
        return RedirectResponse(f"{frontend}/dashboard?gmail={result}")

    @router.post("/disconnect")
    async def disconnect(user: dict = Depends(get_current_user)):
        conn = await db.gmail_connections.find_one({"user_id": user["_id"]})
        if conn:
            # Best-effort revoke of the refresh token so Google forgets us
            enc = conn.get("refresh_token_enc")
            if enc:
                try:
                    await revoke_token(decrypt_token(enc))
                except Exception:  # pragma: no cover
                    pass
            await db.gmail_connections.delete_one({"_id": conn["_id"]})
        return {"ok": True}

    @router.post("/mark-revoked")
    async def mark_revoked(user: dict = Depends(get_current_user)):
        """Dev helper: force the connection into 'revoked' state so we can preview
        the reconnect banner. Removed once continuous sync detects revocation live."""
        await db.gmail_connections.update_one(
            {"user_id": user["_id"]}, {"$set": {"status": "revoked"}}
        )
        return {"ok": True}

    return router
