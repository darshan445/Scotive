"""Mailbox connect via Unipile Hosted Auth (Google Gmail + Microsoft Outlook).

Unipile owns the provider OAuth verification surface. Scotive stores
`unipile_account_id`, mailbox email, and `provider` (google | outlook).

Also exports encrypt/decrypt helpers used by QBO token storage.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Literal, Optional

from bson import ObjectId
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import unipile_client as unipile

logger = logging.getLogger("scotive.gmail")

ProviderKey = Literal["google", "outlook"]

UNIPILE_PROVIDERS: dict[str, str] = {
    "google": "GOOGLE",
    "outlook": "OUTLOOK",
}


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


# Kept for any legacy imports; Unipile does not use Google token endpoint.
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class MailboxConnectionStatus(BaseModel):
    provider: str
    connected: bool
    email: Optional[str] = None
    account_name: Optional[str] = None
    can_send: bool = False
    connected_at: Optional[datetime] = None
    status: str = "disconnected"


class GmailStatus(BaseModel):
    connected: bool
    email: Optional[str] = None
    account_name: Optional[str] = None
    can_send: bool = False
    connected_at: Optional[datetime] = None
    status: str = "disconnected"  # disconnected | connected | revoked | send_missing
    provider: Optional[str] = None  # primary mailbox provider
    connections: list[MailboxConnectionStatus] = []


class OAuthStartResponse(BaseModel):
    authorization_url: str
    provider: str


def signer_fallback_from_email(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return None
    local = email.split("@", 1)[0].strip()
    if not local:
        return None
    return local.replace(".", " ").replace("_", " ").title()


def _parse_user_id(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return ObjectId(raw)
    except Exception:
        return raw


def _normalize_provider(raw: str | None) -> str:
    key = (raw or "google").strip().lower()
    if key in ("outlook", "microsoft", "office365", "o365"):
        return "outlook"
    return "google"


async def upsert_unipile_connection(
    db,
    user_id,
    *,
    account_id: str,
    provider: str = "google",
    email: Optional[str] = None,
    account_name: Optional[str] = None,
):
    """Upsert one mailbox row keyed by (user_id, provider). Other providers stay."""
    now = datetime.now(timezone.utc)
    provider = _normalize_provider(provider)
    doc = {
        "user_id": user_id,
        "unipile_account_id": account_id,
        "provider": provider,
        "via": "unipile",
        "can_send": True,
        "can_read": True,
        "status": "connected",
        "scopes": f"unipile:{provider}",
        "updated_at": now.isoformat(),
        "access_token_enc": None,
        "refresh_token_enc": None,
        "expires_at": None,
    }
    if email:
        doc["email"] = email.lower().strip()
    if account_name:
        doc["account_name"] = account_name.strip()

    existing = await db.gmail_connections.find_one({"user_id": user_id, "provider": provider})
    # Legacy rows may lack provider — treat as google when upserting google
    if existing is None and provider == "google":
        existing = await db.gmail_connections.find_one({
            "user_id": user_id,
            "$or": [{"provider": {"$exists": False}}, {"provider": None}, {"provider": ""}],
        })

    old_account = (existing or {}).get("unipile_account_id")
    if existing is None:
        doc["connected_at"] = now.isoformat()
        await db.gmail_connections.insert_one(doc)
    else:
        if "email" not in doc and existing.get("email"):
            doc["email"] = existing["email"]
        if "account_name" not in doc and existing.get("account_name"):
            doc["account_name"] = existing["account_name"]
        if not existing.get("connected_at"):
            doc["connected_at"] = now.isoformat()
        await db.gmail_connections.update_one({"_id": existing["_id"]}, {"$set": doc})

    # Re-link same provider only — never delete the other mailbox (Gmail vs Outlook)
    if old_account and old_account != account_id:
        try:
            await unipile.delete_account(old_account)
        except Exception as e:
            logger.warning("unipile delete previous account best-effort: %s", e)
    return doc


async def ensure_gmail_account_name(db, user_id) -> Optional[str]:
    from gmail_client import list_connected_mailboxes
    mailboxes = await list_connected_mailboxes(db, user_id)
    if not mailboxes:
        conn = await db.gmail_connections.find_one({"user_id": user_id})
        if not conn:
            return None
        existing = (conn.get("account_name") or "").strip()
        return existing or signer_fallback_from_email(conn.get("email"))
    for conn in mailboxes:
        existing = (conn.get("account_name") or "").strip()
        if existing:
            return existing
    return signer_fallback_from_email(mailboxes[0].get("email"))


def _conn_to_mailbox_status(conn: dict) -> MailboxConnectionStatus:
    connected_at = conn.get("connected_at")
    if isinstance(connected_at, str):
        connected_at = datetime.fromisoformat(connected_at)
    provider = _normalize_provider(conn.get("provider") or "google")
    status_val = conn.get("status", "connected")
    has_account = bool((conn.get("unipile_account_id") or "").strip())
    account_name = (conn.get("account_name") or "").strip() or None
    if status_val == "revoked" or not has_account:
        return MailboxConnectionStatus(
            provider=provider,
            connected=False,
            email=conn.get("email"),
            account_name=account_name,
            can_send=False,
            connected_at=connected_at,
            status="revoked" if status_val == "revoked" else "disconnected",
        )
    can_send = bool(conn.get("can_send", True))
    return MailboxConnectionStatus(
        provider=provider,
        connected=True,
        email=conn.get("email"),
        account_name=account_name,
        can_send=can_send,
        connected_at=connected_at,
        status="connected" if can_send else "send_missing",
    )


async def _make_status(db, user_id) -> GmailStatus:
    rows = []
    async for conn in db.gmail_connections.find({"user_id": user_id}):
        rows.append(conn)
    if not rows:
        return GmailStatus(connected=False, status="disconnected", connections=[])

    connections = [_conn_to_mailbox_status(c) for c in rows]
    # Sort: connected first, google before outlook
    connections.sort(key=lambda c: (0 if c.connected else 1, 0 if c.provider == "google" else 1))

    primary = next((c for c in connections if c.connected), None)
    if primary is None:
        # All revoked / disconnected — surface first row for reconnect UX
        any_revoked = any(c.status == "revoked" for c in connections)
        first = connections[0]
        return GmailStatus(
            connected=False,
            email=first.email,
            account_name=first.account_name,
            can_send=False,
            connected_at=first.connected_at,
            status="revoked" if any_revoked else "disconnected",
            provider=first.provider,
            connections=connections,
        )

    return GmailStatus(
        connected=True,
        email=primary.email,
        account_name=primary.account_name,
        can_send=primary.can_send,
        connected_at=primary.connected_at,
        status=primary.status,
        provider=primary.provider,
        connections=connections,
    )


def _verify_unipile_webhook(request: Request) -> None:
    secret = unipile.webhook_secret()
    if not secret:
        return
    got = request.headers.get("Unipile-Auth") or request.headers.get("unipile-auth") or ""
    if got != secret:
        raise HTTPException(status_code=401, detail="Invalid Unipile webhook auth")


async def _enrich_from_unipile_account(
    db,
    user_id,
    account_id: str,
    *,
    fallback_provider: str | None = None,
) -> None:
    provider = _normalize_provider(fallback_provider)
    email = None
    try:
        account = await unipile.get_account(account_id)
        provider = unipile.provider_from_account(account) or provider
        email = unipile.account_email(account)
    except Exception as e:
        logger.warning("unipile get_account failed id=%s err=%s", account_id, e)
        await upsert_unipile_connection(
            db, user_id, account_id=account_id, provider=provider,
        )
        return
    await upsert_unipile_connection(
        db,
        user_id,
        account_id=account_id,
        provider=provider,
        email=email,
        account_name=signer_fallback_from_email(email),
    )


def build_router(db, get_current_user):
    router = APIRouter(prefix="/gmail", tags=["gmail"])

    @router.get("/status", response_model=GmailStatus)
    async def status(user: dict = Depends(get_current_user)):
        return await _make_status(db, user["_id"])

    @router.get("/oauth/start", response_model=OAuthStartResponse)
    async def start(
        user: dict = Depends(get_current_user),
        provider: str = Query("google", description="google | outlook"),
    ):
        provider_key = _normalize_provider(provider)
        unipile_provider = UNIPILE_PROVIDERS[provider_key]
        frontend = _frontend_url()
        conn = await db.gmail_connections.find_one({
            "user_id": user["_id"],
            "provider": provider_key,
        })
        if conn is None and provider_key == "google":
            conn = await db.gmail_connections.find_one({
                "user_id": user["_id"],
                "$or": [{"provider": {"$exists": False}}, {"provider": None}, {"provider": ""}],
            })
        reconnect_id = None
        if conn and conn.get("status") == "revoked" and conn.get("unipile_account_id"):
            reconnect_id = conn["unipile_account_id"]
        label = "outlook" if provider_key == "outlook" else "gmail"
        try:
            url = await unipile.create_hosted_auth_link(
                user_key=str(user["_id"]),
                providers=[unipile_provider],
                success_redirect_url=f"{frontend}/dashboard?mail=connected&provider={provider_key}",
                failure_redirect_url=f"{frontend}/dashboard?mail=error&provider={provider_key}",
                reconnect_account_id=reconnect_id,
            )
        except unipile.UnipileError as e:
            logger.warning("Hosted auth link failed provider=%s: %s", provider_key, e)
            raise HTTPException(
                status_code=502,
                detail=f"Could not start {label} connect",
            ) from e
        return OAuthStartResponse(authorization_url=url, provider=provider_key)

    @router.post("/unipile/notify")
    async def unipile_notify(request: Request):
        """Hosted-auth notify_url — stores account_id ↔ user after mailbox connect."""
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        status_val = (payload.get("status") or "").upper()
        account_id = (payload.get("account_id") or "").strip()
        name = payload.get("name") or ""
        user_id = _parse_user_id(str(name))
        logger.info(
            "unipile.notify status=%s account=%s name=%s",
            status_val, account_id[:12] if account_id else None, name,
        )
        if status_val not in ("CREATION_SUCCESS", "RECONNECTED") or not account_id or user_id is None:
            return JSONResponse({"ok": True, "ignored": True})
        await _enrich_from_unipile_account(db, user_id, account_id)
        return {"ok": True}

    @router.post("/unipile/account-status")
    async def unipile_account_status(request: Request):
        """Dashboard/API webhook: CREDENTIALS → mark connection revoked."""
        _verify_unipile_webhook(request)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        account_id = (payload.get("account_id") or "").strip()
        status_raw = (
            payload.get("AccountStatus")
            or payload.get("account_status")
            or payload.get("status")
            or payload.get("message")
            or ""
        )
        status_s = str(status_raw).upper()
        logger.info("unipile.account_status account=%s status=%s", account_id[:12] if account_id else None, status_s)
        if not account_id:
            return {"ok": True}
        conn = await db.gmail_connections.find_one({"unipile_account_id": account_id})
        if not conn:
            return {"ok": True, "unknown_account": True}
        if status_s in ("CREDENTIALS", "ERROR", "DELETED", "STOPPED"):
            await db.gmail_connections.update_one(
                {"_id": conn["_id"]},
                {"$set": {"status": "revoked", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
        elif status_s in ("OK", "RECONNECTED", "SYNC_SUCCESS"):
            await db.gmail_connections.update_one(
                {"_id": conn["_id"]},
                {"$set": {"status": "connected", "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
        return {"ok": True}

    @router.post("/unipile/email")
    async def unipile_email_webhook(request: Request):
        """Optional mail_received/mail_sent webhook — ack only (polling still primary)."""
        _verify_unipile_webhook(request)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        logger.info(
            "unipile.email event=%s account=%s email_id=%s",
            payload.get("event"),
            (payload.get("account_id") or "")[:12],
            (payload.get("email_id") or "")[:12],
        )
        return {"ok": True}

    @router.post("/disconnect")
    async def disconnect(
        user: dict = Depends(get_current_user),
        provider: Optional[str] = Query(None, description="google | outlook; omit = all"),
    ):
        query: dict = {"user_id": user["_id"]}
        if provider:
            query["provider"] = _normalize_provider(provider)
        deleted = 0
        async for conn in db.gmail_connections.find(query):
            account_id = conn.get("unipile_account_id")
            if account_id:
                try:
                    await unipile.delete_account(account_id)
                except Exception as e:
                    logger.warning("unipile delete_account best-effort: %s", e)
            await db.gmail_connections.delete_one({"_id": conn["_id"]})
            deleted += 1
        return {"ok": True, "deleted": deleted}

    @router.post("/mark-revoked")
    async def mark_revoked(
        user: dict = Depends(get_current_user),
        provider: Optional[str] = Query(None),
    ):
        query: dict = {"user_id": user["_id"]}
        if provider:
            query["provider"] = _normalize_provider(provider)
        await db.gmail_connections.update_many(query, {"$set": {"status": "revoked"}})
        return {"ok": True}

    return router
