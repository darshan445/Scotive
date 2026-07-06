"""Gmail API client. Handles OAuth token refresh + message list/get."""
from __future__ import annotations

import base64
import logging
import os
import re
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
    pages = 0
    async with httpx.AsyncClient(timeout=30.0) as c:
        for _ in range(max_pages):
            pages += 1
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
    logger.info("pipeline.gmail LIST query=%r pages=%s ids=%s", query, pages, len(ids))
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


def _collect_attachment_filenames(payload: dict) -> list[str]:
    names: list[str] = []

    def walk(node):
        if not node:
            return
        fn = (node.get("filename") or "").strip()
        if fn:
            names.append(fn)
        for child in node.get("parts", []) or []:
            walk(child)

    walk(payload)
    return names


def _collect_attachment_parts(payload: dict) -> list[dict]:
    """Attachment metadata for download via Gmail attachments API."""
    parts: list[dict] = []

    def walk(node):
        if not node:
            return
        fn = (node.get("filename") or "").strip()
        body = node.get("body") or {}
        att_id = body.get("attachmentId")
        if fn and att_id:
            parts.append({
                "filename": fn,
                "mime_type": node.get("mimeType") or "",
                "attachment_id": att_id,
                "size": int(body.get("size") or 0),
            })
        for child in node.get("parts", []) or []:
            walk(child)

    walk(payload)
    return parts


def parse_email_addresses(header_value: str) -> list[str]:
    """Extract bare email addresses from a To/Cc/From header."""
    if not header_value:
        return []
    found = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", header_value, flags=re.I)
    return [a.lower() for a in found]


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

    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    body = _extract_text_from_payload(payload)
    body = body[:8000]
    attachment_names = _collect_attachment_filenames(payload)
    attachment_parts = _collect_attachment_parts(payload)
    to_addrs = parse_email_addresses(headers.get("to", ""))
    cc_addrs = parse_email_addresses(headers.get("cc", ""))
    return {
        "id": raw["id"],
        "thread_id": raw.get("threadId"),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "to_addrs": to_addrs,
        "cc_addrs": cc_addrs,
        "date": headers.get("date", ""),
        "snippet": raw.get("snippet", ""),
        "body": body,
        "list_unsubscribe": headers.get("list-unsubscribe", ""),
        "has_attachment": any(n.lower().endswith(".pdf") for n in attachment_names),
        "attachment_names": attachment_names,
        "attachment_parts": attachment_parts,
        "label_ids": raw.get("labelIds") or [],
    }


async def fetch_attachment_bytes(access_token: str, message_id: str, attachment_id: str) -> bytes:
    async with httpx.AsyncClient(timeout=45.0) as c:
        r = await c.get(
            f"{GMAIL_API}/users/me/messages/{message_id}/attachments/{attachment_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if r.status_code != 200:
            raise RuntimeError(f"attachment fetch failed: {r.status_code}")
        data = r.json().get("data")
        if not data:
            return b""
        return base64.urlsafe_b64decode(data + "==")


async def get_messages_batch(access_token: str, message_ids: list[str]) -> list[dict]:
    """Fetch full messages sequentially (Gmail has no batch get in REST v1)."""
    out: list[dict] = []
    for mid in message_ids:
        msg = await get_message(access_token, mid)
        if msg:
            out.append(msg)
    return out


def _parse_metadata_message(raw: dict) -> dict:
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    rfc_mid = headers.get("message-id", "").strip()
    refs = headers.get("references", "").strip()
    return {
        "id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "rfc_message_id": rfc_mid,
        "subject": headers.get("subject", ""),
        "references": refs,
        "in_reply_to": headers.get("in-reply-to", "").strip(),
    }


async def get_message_metadata(access_token: str, message_id: str) -> Optional[dict]:
    """Lightweight fetch for threading headers (Message-ID, Subject, References)."""
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(
            f"{GMAIL_API}/users/me/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "format": "metadata",
                "metadataHeaders": ["Message-ID", "Subject", "References", "In-Reply-To"],
            },
        )
        if r.status_code != 200:
            return None
        return _parse_metadata_message(r.json())


async def get_thread_latest_metadata(access_token: str, thread_id: str) -> Optional[dict]:
    """Latest message in a thread — reply target for in-thread chases."""
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(
            f"{GMAIL_API}/users/me/threads/{thread_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "format": "metadata",
                "metadataHeaders": ["Message-ID", "Subject", "References", "In-Reply-To"],
            },
        )
        if r.status_code != 200:
            return None
        messages = r.json().get("messages") or []
        if not messages:
            return None
        return _parse_metadata_message(messages[-1])


async def resolve_thread_reply_context(
    access_token: str,
    *,
    thread_id: str | None = None,
    message_id: str | None = None,
) -> Optional[dict]:
    """Pick the best anchor for a threaded reply (prefer latest in thread)."""
    resolved_thread = thread_id
    if message_id:
        meta = await get_message_metadata(access_token, message_id)
        if meta:
            resolved_thread = meta.get("thread_id") or resolved_thread

    if resolved_thread:
        latest = await get_thread_latest_metadata(access_token, resolved_thread)
        if latest:
            parent_mid = latest.get("rfc_message_id") or ""
            prior_refs = latest.get("references") or latest.get("in_reply_to") or ""
            references = f"{prior_refs} {parent_mid}".strip() if parent_mid else prior_refs
            return {
                "thread_id": resolved_thread,
                "rfc_message_id": parent_mid,
                "subject": latest.get("subject") or "",
                "references": references,
            }

    if message_id:
        meta = await get_message_metadata(access_token, message_id)
        if meta and meta.get("rfc_message_id"):
            parent_mid = meta["rfc_message_id"]
            prior_refs = meta.get("references") or meta.get("in_reply_to") or ""
            references = f"{prior_refs} {parent_mid}".strip() if parent_mid else prior_refs
            return {
                "thread_id": meta.get("thread_id") or resolved_thread,
                "rfc_message_id": parent_mid,
                "subject": meta.get("subject") or "",
                "references": references,
            }
    return None


_RE_PREFIX = re.compile(r"^(?:(?:re|fwd|fw)\s*:\s*)+", re.I)


def reply_subject(thread_subject: str, draft_subject: str) -> str:
    """Ensure chase subject stays on the original thread."""
    orig = (thread_subject or "").strip()
    subj = (draft_subject or "").strip()
    if not orig:
        return subj or "Payment follow-up"
    if subj and _RE_PREFIX.sub("", subj).strip().lower() == _RE_PREFIX.sub("", orig).strip().lower():
        return subj if _RE_PREFIX.match(subj) else f"Re: {subj}"
    if _RE_PREFIX.match(orig):
        return orig
    return f"Re: {orig}"


def build_mime_message(
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    *,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> str:
    lines = [
        f"From: {from_addr}",
        f"To: {to_addr}",
        f"Subject: {subject}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=UTF-8",
        "Content-Transfer-Encoding: 7bit",
    ]
    if in_reply_to:
        lines.append(f"In-Reply-To: {in_reply_to}")
    if references:
        lines.append(f"References: {references}")
    lines.append("")
    lines.append(body)
    return "\r\n".join(lines)


async def send_gmail_reply(
    access_token: str,
    *,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
    reply_to_message_id: str | None = None,
) -> dict:
    """Send a plain-text email, threaded into an existing conversation when possible."""
    ctx = await resolve_thread_reply_context(
        access_token,
        thread_id=thread_id,
        message_id=reply_to_message_id,
    )
    send_thread = thread_id
    in_reply_to = None
    references = None
    send_subject = subject

    if ctx and ctx.get("rfc_message_id"):
        send_thread = ctx.get("thread_id") or send_thread
        in_reply_to = ctx["rfc_message_id"]
        references = ctx.get("references") or in_reply_to
        send_subject = reply_subject(ctx.get("subject", ""), subject)

    raw = build_mime_message(
        from_addr, to_addr, send_subject, body,
        in_reply_to=in_reply_to, references=references,
    )
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")
    payload: dict = {"raw": encoded}
    if send_thread:
        payload["threadId"] = send_thread

    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.post(
            f"{GMAIL_API}/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Gmail send failed: {r.status_code} {r.text[:200]}")
        data = r.json()
    return {
        "gmail_message_id": data.get("id"),
        "thread_id": data.get("threadId") or send_thread,
        "subject": send_subject,
    }
