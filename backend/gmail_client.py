"""Gmail API client. Handles OAuth token refresh + message list/get."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from email import message_from_bytes
from email import policy
from typing import Awaitable, Callable, Optional, TypeVar

import httpx

from gmail_oauth import decrypt_token, encrypt_token, GOOGLE_TOKEN_ENDPOINT

logger = logging.getLogger("scotive.gmail_client")

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
GMAIL_BATCH_URL = "https://gmail.googleapis.com/batch/gmail/v1"
GMAIL_FETCH_CONCURRENCY = int(os.environ.get("GMAIL_FETCH_CONCURRENCY", "18"))
GMAIL_FETCH_RETRIES = int(os.environ.get("GMAIL_FETCH_RETRIES", "4"))
GMAIL_BATCH_SIZE = min(100, max(1, int(os.environ.get("GMAIL_BATCH_SIZE", "50"))))
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

T = TypeVar("T")


class GmailAuthError(Exception):
    """Raised when refresh token is invalid (user revoked)."""


async def _retry_gmail(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = GMAIL_FETCH_RETRIES,
    label: str = "gmail",
) -> T:
    """Retry transient transport errors and rate limits."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await coro_factory()
        except httpx.TransportError as e:
            last_exc = e
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in RETRYABLE_STATUS:
                raise
            last_exc = e
        if attempt >= attempts - 1:
            break
        delay = 0.5 * (2 ** attempt)
        logger.warning(
            "%s retry attempt=%s/%s err=%s",
            label, attempt + 1, attempts, last_exc,
        )
        await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


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
    expires_at = conn.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if expires_at and expires_at > now + timedelta(seconds=60):
        return decrypt_token(conn["access_token_enc"])
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
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30.0) as c:
        for _ in range(max_pages):
            pages += 1
            params = {"q": query, "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token

            async def _list_page(p=params):
                r = await c.get(
                    f"{GMAIL_API}/users/me/messages",
                    headers=headers,
                    params=p,
                )
                if r.status_code in RETRYABLE_STATUS:
                    r.raise_for_status()
                return r

            r = await _retry_gmail(_list_page, label="gmail.list_messages")
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


def _html_to_visible_text(html: str) -> str:
    """Turn an HTML email body into readable plain text for UI / LLM."""
    import html as html_lib

    text = html or ""
    # Drop quoted-reply chrome early when possible
    text = re.sub(
        r'(?is)<div[^>]*class=["\'][^"\']*gmail_quote[^"\']*["\'][^>]*>.*$',
        "",
        text,
    )
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", "", text)
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", "", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"(?i)</h[1-6]\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_text_from_payload(payload: dict) -> str:
    """Prefer text/plain; fall back to HTML→text. Never concatenate both."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def walk(node):
        if not node:
            return
        mime = (node.get("mimeType") or "").lower()
        body = node.get("body", {})
        data = body.get("data")
        if data and mime.startswith("text/"):
            try:
                decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
            except Exception:
                decoded = ""
            if not decoded:
                pass
            elif mime == "text/html":
                html_parts.append(decoded)
            else:
                # text/plain and other text/*
                plain_parts.append(decoded)
        for child in node.get("parts", []) or []:
            walk(child)

    walk(payload)
    if plain_parts:
        return "\n".join(plain_parts).strip()
    if html_parts:
        return _html_to_visible_text("\n".join(html_parts))
    return ""


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


def _parse_full_message(raw: dict, *, body_limit: int = 8000) -> Optional[dict]:
    if not raw.get("id"):
        return None
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    body = _extract_text_from_payload(payload)
    if body_limit and body_limit > 0:
        body = body[:body_limit]
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


async def get_message(
    access_token: str,
    message_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> Optional[dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"format": "full"}
    label = f"gmail.get_message({message_id[:8]})"

    async def _fetch(c: httpx.AsyncClient) -> Optional[dict]:
        async def _once():
            r = await c.get(
                f"{GMAIL_API}/users/me/messages/{message_id}",
                headers=headers,
                params=params,
            )
            if r.status_code in RETRYABLE_STATUS:
                r.raise_for_status()
            return r

        r = await _retry_gmail(_once, label=label)
        if r.status_code != 200:
            return None
        return _parse_full_message(r.json())

    if client is not None:
        return await _fetch(client)
    async with httpx.AsyncClient(timeout=20.0) as c:
        return await _fetch(c)


def _build_batch_request_body(message_ids: list[str], boundary: str) -> bytes:
    """Google batch: multipart/mixed with nested GET requests."""
    chunks: list[str] = []
    for mid in message_ids:
        chunks.append(f"--{boundary}\r\n")
        chunks.append("Content-Type: application/http\r\n")
        chunks.append(f"Content-ID: <msg-{mid}>\r\n")
        chunks.append("\r\n")
        chunks.append(f"GET /gmail/v1/users/me/messages/{mid}?format=full HTTP/1.1\r\n")
        chunks.append("\r\n")
    chunks.append(f"--{boundary}--\r\n")
    return "".join(chunks).encode("utf-8")


def _parse_batch_http_part(part_bytes: bytes) -> tuple[int, Optional[dict]]:
    if b"\r\n\r\n" not in part_bytes:
        return 0, None
    header_block, body = part_bytes.split(b"\r\n\r\n", 1)
    status_line = header_block.split(b"\r\n")[0].decode("utf-8", errors="ignore")
    parts = status_line.split()
    status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    if status != 200:
        return status, None
    body = body.strip()
    if not body:
        return status, None
    try:
        return status, json.loads(body.decode("utf-8"))
    except Exception:
        return status, None


def _parse_batch_response(body: bytes, content_type: str) -> list[Optional[dict]]:
    """Parse multipart batch response; part order matches request order."""
    if not body:
        return []
    envelope = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8") + body
    try:
        msg = message_from_bytes(envelope, policy=policy.default)
    except Exception as e:
        logger.warning("gmail.batch parse envelope err=%s", e)
        return []
    out: list[Optional[dict]] = []
    for part in msg.iter_parts():
        payload = part.get_payload(decode=True)
        if not payload:
            out.append(None)
            continue
        status, raw = _parse_batch_http_part(payload)
        if status != 200 or not raw:
            out.append(None)
            continue
        out.append(_parse_full_message(raw))
    return out


async def _batch_get_messages_chunk(
    access_token: str,
    message_ids: list[str],
    client: httpx.AsyncClient,
) -> dict[str, dict]:
    if not message_ids:
        return {}
    boundary = f"batch_{uuid.uuid4().hex}"
    body = _build_batch_request_body(message_ids, boundary)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": f'multipart/mixed; boundary="{boundary}"',
    }

    async def _once():
        r = await client.post(GMAIL_BATCH_URL, headers=headers, content=body)
        if r.status_code in RETRYABLE_STATUS:
            r.raise_for_status()
        return r

    r = await _retry_gmail(_once, label=f"gmail.batch({len(message_ids)})")
    if r.status_code != 200:
        logger.warning(
            "gmail.batch FAIL status=%s body=%s",
            r.status_code, (r.text or "")[:300],
        )
        return {}

    ct = r.headers.get("content-type", "")
    parsed = _parse_batch_response(r.content, ct)
    result: dict[str, dict] = {}
    for mid, msg in zip(message_ids, parsed):
        if msg:
            result[mid] = msg
    if len(result) < len(message_ids):
        logger.info(
            "gmail.batch partial ok=%s/%s",
            len(result), len(message_ids),
        )
    return result


async def _fetch_messages_concurrent(
    access_token: str,
    message_ids: list[str],
    *,
    concurrency: int,
) -> dict[str, dict]:
    if not message_ids:
        return {}
    sem = asyncio.Semaphore(max(1, concurrency))
    async with httpx.AsyncClient(timeout=20.0) as client:
        async def one(mid: str) -> tuple[str, Optional[dict]]:
            async with sem:
                msg = await get_message(access_token, mid, client=client)
            return mid, msg

        results = await asyncio.gather(
            *[one(mid) for mid in message_ids],
            return_exceptions=True,
        )
    out: dict[str, dict] = {}
    for mid, res in zip(message_ids, results):
        if isinstance(res, Exception):
            logger.warning("gmail fetch skip id=%s err=%s", mid, res)
            continue
        key, msg = res
        if msg:
            out[key] = msg
    return out


async def get_messages_batch(
    access_token: str,
    message_ids: list[str],
    *,
    concurrency: int = GMAIL_FETCH_CONCURRENCY,
) -> list[dict]:
    """Fetch messages via Google batch API (chunks of N) with concurrent fallback."""
    if not message_ids:
        return []

    by_id: dict[str, dict] = {}
    missing = list(message_ids)

    # Always try Google batch first when fetching more than one message.
    # Failed / missing IDs fall through to concurrent per-message fetch below.
    if len(message_ids) > 1:
        chunks = [
            message_ids[i:i + GMAIL_BATCH_SIZE]
            for i in range(0, len(message_ids), GMAIL_BATCH_SIZE)
        ]
        batch_parallel = max(1, min(4, concurrency // 6 or 1))
        sem = asyncio.Semaphore(batch_parallel)
        async with httpx.AsyncClient(timeout=90.0) as client:
            async def run_chunk(chunk: list[str]) -> dict[str, dict]:
                async with sem:
                    try:
                        return await _batch_get_messages_chunk(access_token, chunk, client)
                    except Exception as e:
                        logger.warning("gmail.batch chunk failed n=%s err=%s", len(chunk), e)
                        return {}

            chunk_maps = await asyncio.gather(*[run_chunk(c) for c in chunks])

        missing = []
        for chunk, cmap in zip(chunks, chunk_maps):
            for mid in chunk:
                if mid in cmap:
                    by_id[mid] = cmap[mid]
                else:
                    missing.append(mid)

    if missing:
        fallback = await _fetch_messages_concurrent(
            access_token, missing, concurrency=concurrency,
        )
        by_id.update(fallback)

    return [by_id[mid] for mid in message_ids if mid in by_id]


async def fetch_attachment_bytes(access_token: str, message_id: str, attachment_id: str) -> bytes:
    headers = {"Authorization": f"Bearer {access_token}"}

    async def _once():
        async with httpx.AsyncClient(timeout=45.0) as c:
            r = await c.get(
                f"{GMAIL_API}/users/me/messages/{message_id}/attachments/{attachment_id}",
                headers=headers,
            )
            if r.status_code in RETRYABLE_STATUS:
                r.raise_for_status()
            return r

    r = await _retry_gmail(_once, label="gmail.attachment")
    if r.status_code != 200:
        raise RuntimeError(f"attachment fetch failed: {r.status_code}")
    data = r.json().get("data")
    if not data:
        return b""
    return base64.urlsafe_b64decode(data + "==")


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
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "format": "metadata",
        "metadataHeaders": ["Message-ID", "Subject", "References", "In-Reply-To"],
    }

    async def _once():
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(
                f"{GMAIL_API}/users/me/messages/{message_id}",
                headers=headers,
                params=params,
            )
            if r.status_code in RETRYABLE_STATUS:
                r.raise_for_status()
            return r

    r = await _retry_gmail(_once, label="gmail.get_metadata")
    if r.status_code != 200:
        return None
    return _parse_metadata_message(r.json())


async def get_thread_message_ids(access_token: str, thread_id: str) -> list[str]:
    """List message ids in a Gmail thread (chronological order)."""
    headers = {"Authorization": f"Bearer {access_token}"}

    async def _once():
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(
                f"{GMAIL_API}/users/me/threads/{thread_id}",
                headers=headers,
                params={"format": "minimal"},
            )
            if r.status_code in RETRYABLE_STATUS:
                r.raise_for_status()
            return r

    r = await _retry_gmail(_once, label="gmail.thread_ids")
    if r.status_code != 200:
        return []
    return [m["id"] for m in (r.json().get("messages") or []) if m.get("id")]


async def get_thread_messages(
    access_token: str,
    thread_id: str,
    *,
    body_limit: int = 8000,
) -> list[dict]:
    """Fetch every message in a thread (one threads.get?format=full call)."""
    headers = {"Authorization": f"Bearer {access_token}"}

    async def _once():
        async with httpx.AsyncClient(timeout=45.0) as c:
            r = await c.get(
                f"{GMAIL_API}/users/me/threads/{thread_id}",
                headers=headers,
                params={"format": "full"},
            )
            if r.status_code in RETRYABLE_STATUS:
                r.raise_for_status()
            return r

    r = await _retry_gmail(_once, label=f"gmail.thread_full({thread_id[:8]})")
    if r.status_code != 200:
        return []
    out: list[dict] = []
    for raw in r.json().get("messages") or []:
        msg = _parse_full_message(raw, body_limit=body_limit)
        if msg:
            out.append(msg)
    return out


async def get_thread_latest_metadata(access_token: str, thread_id: str) -> Optional[dict]:
    """Latest message in a thread — reply target for in-thread chases."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "format": "metadata",
        "metadataHeaders": ["Message-ID", "Subject", "References", "In-Reply-To"],
    }

    async def _once():
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(
                f"{GMAIL_API}/users/me/threads/{thread_id}",
                headers=headers,
                params=params,
            )
            if r.status_code in RETRYABLE_STATUS:
                r.raise_for_status()
            return r

    r = await _retry_gmail(_once, label="gmail.thread_metadata")
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
