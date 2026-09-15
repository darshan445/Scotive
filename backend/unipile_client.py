"""Unipile HTTP client — Gmail (Google) connect + mail via Unipile DSN."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger("scotive.unipile")

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class UnipileError(Exception):
    def __init__(self, message: str, *, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class UnipileAuthError(UnipileError):
    """Account missing, credentials invalid, or disconnected."""


def dsn() -> str:
    raw = (os.environ.get("UNIPILE_DSN") or "").strip().rstrip("/")
    if not raw:
        raise UnipileError("UNIPILE_DSN is not set")
    return raw


def api_key() -> str:
    key = (os.environ.get("UNIPILE_API_KEY") or "").strip()
    if not key:
        raise UnipileError("UNIPILE_API_KEY is not set")
    return key


def webhook_secret() -> str:
    return (os.environ.get("UNIPILE_WEBHOOK_SECRET") or "").strip()


def public_api_url() -> str:
    """Public base for notify/webhooks (no trailing slash), e.g. https://api.scotive.com."""
    return (os.environ.get("PUBLIC_API_URL") or "").strip().rstrip("/")


def notify_url() -> str:
    explicit = (os.environ.get("UNIPILE_NOTIFY_URL") or "").strip()
    if explicit:
        return explicit
    base = public_api_url()
    if not base:
        raise UnipileError(
            "Set UNIPILE_NOTIFY_URL or PUBLIC_API_URL so Unipile can POST account connect events"
        )
    return f"{base}/api/gmail/unipile/notify"


def _headers(*, json_body: bool = False) -> dict[str, str]:
    h = {
        "X-API-KEY": api_key(),
        "accept": "application/json",
    }
    if json_body:
        h["content-type"] = "application/json"
    return h


def _url(path: str) -> str:
    base = dsn()
    if not path.startswith("/"):
        path = "/" + path
    return urljoin(base + "/", path.lstrip("/"))


async def request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
    data: dict | None = None,
    files: Any = None,
    timeout: float = 45.0,
) -> Any:
    url = _url(path if path.startswith("/api/") else f"/api/v1/{path.lstrip('/')}")
    headers = _headers(json_body=json is not None and files is None and data is None)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json,
            data=data,
            files=files,
        )
    if r.status_code in (401, 403):
        raise UnipileAuthError(f"Unipile auth failed: {r.status_code}", status=r.status_code, body=r.text[:400])
    if r.status_code == 404:
        raise UnipileError(f"Not found: {path}", status=404, body=r.text[:400])
    if r.status_code >= 400:
        logger.warning("unipile %s %s → %s %s", method, path, r.status_code, r.text[:300])
        raise UnipileError(
            f"Unipile {method} {path} failed: {r.status_code}",
            status=r.status_code,
            body=r.text[:800],
        )
    if r.status_code == 204 or not r.content:
        return None
    ct = r.headers.get("content-type", "")
    if "application/json" in ct:
        return r.json()
    return r.content


async def create_hosted_auth_link(
    *,
    user_key: str,
    success_redirect_url: str,
    failure_redirect_url: str,
    providers: list[str] | None = None,
    reconnect_account_id: str | None = None,
    expires_minutes: int = 30,
) -> str:
    """Return Unipile Hosted Auth Wizard URL (GOOGLE and/or OUTLOOK)."""
    expires = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    expires_on = expires.strftime("%Y-%m-%dT%H:%M:%S.") + f"{expires.microsecond // 1000:03d}Z"
    provider_list = providers or ["GOOGLE"]
    payload: dict[str, Any] = {
        "type": "reconnect" if reconnect_account_id else "create",
        "providers": provider_list,
        "api_url": dsn(),
        "expiresOn": expires_on,
        "name": user_key,
        "notify_url": notify_url(),
        "success_redirect_url": success_redirect_url,
        "failure_redirect_url": failure_redirect_url,
        "bypass_success_screen": True,
        "single_use": True,
    }
    if reconnect_account_id:
        payload["reconnect_account"] = reconnect_account_id
    data = await request("POST", "/api/v1/hosted/accounts/link", json=payload)
    url = (data or {}).get("url")
    if not url:
        raise UnipileError("Hosted auth link missing url", body=str(data)[:300])
    return url


def provider_from_account(account: dict | None) -> str:
    """Map Unipile account.type → scotive provider key."""
    raw = ((account or {}).get("type") or "").upper()
    if raw in ("OUTLOOK", "MICROSOFT", "OFFICE365"):
        return "outlook"
    if raw in ("GOOGLE", "GOOGLE_OAUTH", "GMAIL"):
        return "google"
    if raw == "MAIL":
        return "imap"
    return "google"


def account_email(account: dict) -> Optional[str]:
    params = account.get("connection_params") or {}
    mail = params.get("mail") or {}
    username = (mail.get("username") or "").strip().lower()
    if username:
        return username
    # Some Outlook payloads nest under microsoft / identity
    for key in ("microsoft", "outlook", "identity"):
        block = params.get(key) or {}
        u = (block.get("username") or block.get("email") or "").strip().lower()
        if u:
            return u
    return None


async def get_account(account_id: str) -> dict:
    return await request("GET", f"/api/v1/accounts/{account_id}")


async def delete_account(account_id: str) -> None:
    try:
        await request("DELETE", f"/api/v1/accounts/{account_id}")
    except UnipileError as e:
        if e.status == 404:
            return
        raise


async def list_emails(
    account_id: str,
    *,
    limit: int = 100,
    cursor: str | None = None,
    meta_only: bool = False,
    include_headers: bool = False,
    after: str | None = None,
    before: str | None = None,
    search: str | None = None,
    from_addr: str | None = None,
    to: str | None = None,
    any_email: str | None = None,
    folder: str | None = None,
    thread_id: str | None = None,
    message_id: str | None = None,
) -> dict:
    params: dict[str, Any] = {
        "account_id": account_id,
        "limit": max(1, min(250, limit)),
    }
    if cursor:
        params["cursor"] = cursor
    if meta_only:
        params["meta_only"] = "true"
    if include_headers and not meta_only:
        params["include_headers"] = "true"
    if after:
        params["after"] = after
    if before:
        params["before"] = before
    if search:
        params["search"] = search
    if from_addr:
        params["from"] = from_addr
    if to:
        params["to"] = to
    if any_email:
        params["any_email"] = any_email
    if folder:
        params["folder"] = folder
    if thread_id:
        params["thread_id"] = thread_id
    if message_id:
        params["message_id"] = message_id
    return await request("GET", "/api/v1/emails", params=params, timeout=60.0)


async def get_email(email_id: str, *, include_headers: bool = True) -> dict:
    params = {}
    if include_headers:
        params["include_headers"] = "true"
    return await request("GET", f"/api/v1/emails/{email_id}", params=params or None)


async def get_attachment(email_id: str, attachment_id: str) -> bytes:
    data = await request(
        "GET",
        f"/api/v1/emails/{email_id}/attachments/{attachment_id}",
        timeout=60.0,
    )
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, dict) and data.get("data"):
        import base64
        raw = data["data"]
        return base64.b64decode(raw + "==")
    raise UnipileError("Unexpected attachment response")


async def list_folders(account_id: str) -> list[dict]:
    data = await request("GET", "/api/v1/folders", params={"account_id": account_id})
    return list((data or {}).get("items") or [])


async def send_email(
    account_id: str,
    *,
    to: list[dict],
    subject: str,
    body: str,
    cc: list[dict] | None = None,
    reply_to: str | None = None,
    from_attendee: dict | None = None,
    custom_headers: list[dict] | None = None,
) -> dict:
    """Send via multipart form (Unipile recommended for replies)."""
    form: dict[str, Any] = {
        "account_id": account_id,
        "subject": subject,
        "body": body,
        "to": _json_form(to),
    }
    if cc:
        form["cc"] = _json_form(cc)
    if reply_to:
        form["reply_to"] = reply_to
    if from_attendee:
        form["from"] = _json_form(from_attendee)
    if custom_headers:
        form["custom_headers"] = _json_form(custom_headers)
    return await request("POST", "/api/v1/emails", data=form, timeout=30.0)


def _json_form(value: Any) -> str:
    import json
    return json.dumps(value)


async def list_webhooks() -> list[dict]:
    data = await request("GET", "/api/v1/webhooks")
    return list((data or {}).get("items") or [])


async def create_webhook(payload: dict) -> dict:
    return await request("POST", "/api/v1/webhooks", json=payload)


async def ensure_account_status_webhook() -> Optional[str]:
    """Idempotently register account_status → CREDENTIALS/etc. Returns webhook_id or None."""
    base = public_api_url()
    if not base:
        logger.info("unipile: skip account_status webhook (PUBLIC_API_URL unset)")
        return None
    request_url = f"{base}/api/gmail/unipile/account-status"
    secret = webhook_secret()
    existing = await list_webhooks()
    for wh in existing:
        if (wh.get("request_url") or "").rstrip("/") == request_url.rstrip("/") and wh.get("source") == "account_status":
            return wh.get("id") or wh.get("webhook_id")
    headers = [{"key": "Content-Type", "value": "application/json"}]
    if secret:
        headers.append({"key": "Unipile-Auth", "value": secret})
    created = await create_webhook({
        "request_url": request_url,
        "name": "scotive-account-status",
        "source": "account_status",
        "format": "json",
        "events": ["credentials", "error", "deleted", "reconnected", "ok"],
        "headers": headers,
    })
    wid = (created or {}).get("webhook_id") or (created or {}).get("id")
    logger.info("unipile: created account_status webhook id=%s", wid)
    return wid
