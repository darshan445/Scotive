"""Gmail API client. Handles OAuth token refresh + message list/get."""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from gmail_oauth import decrypt_token, encrypt_token, GOOGLE_TOKEN_ENDPOINT

logger = logging.getLogger("scotive.gmail_client")

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


class GmailAuthError(Exception):
    """Raised when refresh token is invalid (user revoked)."""


async def _refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if r.status_code != 200:
            logger.warning("Refresh failed: %s %s", r.status_code, r.text)
            raise GmailAuthError(r.text)
        return r.json()


async def get_access_token(db, user_id) -> str:
    conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not conn:
        raise GmailAuthError("No Gmail connection")
    # Check expiry
    expires_at = conn.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if expires_at and expires_at > now + timedelta(seconds=60):
        return decrypt_token(conn["access_token_enc"])
    # Refresh
    if not conn.get("refresh_token_enc"):
        raise GmailAuthError("Missing refresh token")
    refresh = decrypt_token(conn["refresh_token_enc"])
    try:
        tok = await _refresh_access_token(refresh)
    except GmailAuthError:
        await db.gmail_connections.update_one({"user_id": user_id}, {"$set": {"status": "revoked"}})
        raise
    new_access = tok["access_token"]
    new_expires = (now + timedelta(seconds=int(tok.get("expires_in", 3600)))).isoformat()
    await db.gmail_connections.update_one(
        {"user_id": user_id},
        {"$set": {"access_token_enc": encrypt_token(new_access), "expires_at": new_expires}},
    )
    return new_access


async def list_message_ids(access_token: str, query: str, max_pages: int = 20) -> list[str]:
    """List up to max_pages * 500 message IDs matching query."""
    ids: list[str] = []
    page_token: Optional[str] = None
    async with httpx.AsyncClient(timeout=30.0) as c:
        for _ in range(max_pages):
            params = {"q": query, "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            r = await c.get(
                f"{GMAIL_API}/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            if r.status_code != 200:
                logger.warning("list_messages failed: %s %s", r.status_code, r.text[:200])
                break
            data = r.json()
            for m in data.get("messages", []):
                ids.append(m["id"])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return ids


def _extract_text_from_payload(payload: dict) -> str:
    parts = []

    def walk(node):
        if not node:
            return
        mime = node.get("mimeType", "")
        body = node.get("body", {})
        data = body.get("data")
        if data and mime.startswith("text/"):
            try:
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                parts.append(decoded)
            except Exception:
                pass
        for child in node.get("parts", []) or []:
            walk(child)

    walk(payload)
    return "\n".join(parts)


async def get_message(access_token: str, message_id: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(
            f"{GMAIL_API}/users/me/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"},
        )
        if r.status_code != 200:
            return None
        raw = r.json()

    headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
    body = _extract_text_from_payload(raw.get("payload", {}))
    # Truncate body aggressively — AI doesn't need footers/signatures
    body = body[:4000]
    return {
        "id": raw["id"],
        "thread_id": raw.get("threadId"),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "snippet": raw.get("snippet", ""),
        "body": body,
        "has_attachment": any(
            (p.get("filename") or "").lower().endswith(".pdf")
            for p in (raw.get("payload", {}).get("parts") or [])
        ),
    }
