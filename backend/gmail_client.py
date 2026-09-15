"""Mailbox client via Unipile (Google/Gmail).

Public function names/signatures match the former Gmail API client so seed,
incremental sync, chase send, and digest keep working unchanged.

`access_token` parameters are Unipile `account_id` values (returned by
`get_access_token`).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Awaitable, Callable, Optional, TypeVar

import httpx

import unipile_client as unipile

logger = logging.getLogger("scotive.gmail_client")

GMAIL_FETCH_CONCURRENCY = int(os.environ.get("GMAIL_FETCH_CONCURRENCY", "18"))
GMAIL_FETCH_RETRIES = int(os.environ.get("GMAIL_FETCH_RETRIES", "4"))
GMAIL_BATCH_SIZE = min(100, max(1, int(os.environ.get("GMAIL_BATCH_SIZE", "50"))))
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
LIST_PAGE_SIZE = 100

T = TypeVar("T")

# Cache sent-folder provider_id per Unipile account
_sent_folder_cache: dict[str, str | None] = {}


class GmailAuthError(Exception):
    """Raised when the mailbox connection is missing or Unipile credentials failed."""


async def _retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = GMAIL_FETCH_RETRIES,
    label: str = "unipile",
) -> T:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await coro_factory()
        except httpx.TransportError as e:
            last_exc = e
        except unipile.UnipileError as e:
            if e.status not in RETRYABLE_STATUS:
                raise
            last_exc = e
        if attempt >= attempts - 1:
            break
        delay = 0.5 * (2 ** attempt)
        logger.warning("%s retry attempt=%s/%s err=%s", label, attempt + 1, attempts, last_exc)
        await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


async def get_access_token(
    db,
    user_id,
    *,
    provider: str | None = None,
    email: str | None = None,
) -> str:
    """Return Unipile account_id for a connected mailbox.

    Resolution order: explicit provider → email match → first connected (google preferred).
    """
    conn = await resolve_mailbox_connection(db, user_id, provider=provider, email=email)
    if not conn:
        raise GmailAuthError("No mailbox connection")
    if conn.get("status") == "revoked":
        raise GmailAuthError("Mailbox connection revoked")
    account_id = (conn.get("unipile_account_id") or "").strip()
    if not account_id:
        raise GmailAuthError("Missing Unipile account id — reconnect mailbox")
    return account_id


async def list_connected_mailboxes(db, user_id) -> list[dict]:
    """All active mailbox connections for a user (Gmail and/or Outlook)."""
    out: list[dict] = []
    async for conn in db.gmail_connections.find({
        "user_id": user_id,
        "status": "connected",
        "unipile_account_id": {"$exists": True, "$nin": [None, ""]},
    }):
        out.append(conn)
    # Prefer google first for stable "primary" behavior
    out.sort(key=lambda c: 0 if (c.get("provider") or "google") == "google" else 1)
    return out


async def resolve_mailbox_connection(
    db,
    user_id,
    *,
    provider: str | None = None,
    email: str | None = None,
) -> Optional[dict]:
    if provider:
        conn = await db.gmail_connections.find_one({
            "user_id": user_id,
            "provider": provider,
            "status": "connected",
        })
        if conn and (conn.get("unipile_account_id") or "").strip():
            return conn
    if email:
        want = email.strip().lower()
        conn = await db.gmail_connections.find_one({
            "user_id": user_id,
            "email": want,
            "status": "connected",
        })
        if conn and (conn.get("unipile_account_id") or "").strip():
            return conn
    mailboxes = await list_connected_mailboxes(db, user_id)
    return mailboxes[0] if mailboxes else None


async def mailbox_tokens_for_user(db, user_id) -> list[tuple[dict, str]]:
    """[(connection_doc, unipile_account_id), ...] for every connected mailbox."""
    pairs: list[tuple[dict, str]] = []
    for conn in await list_connected_mailboxes(db, user_id):
        aid = (conn.get("unipile_account_id") or "").strip()
        if aid:
            pairs.append((conn, aid))
    return pairs


# ---------------------------------------------------------------------------
# Gmail search query → Unipile list params
# ---------------------------------------------------------------------------
_RE_AFTER_EPOCH = re.compile(r"\bafter:(\d+)\b", re.I)
_RE_NEWER_THAN_D = re.compile(r"\bnewer_than:(\d+)d\b", re.I)
_RE_IN_SENT = re.compile(r"\bin:sent\b", re.I)
_RE_HAS_ATTACH = re.compile(r"\bhas:attachment\b", re.I)
_RE_FROM_GROUP = re.compile(r"\bfrom:\(([^)]+)\)", re.I)
_RE_FROM_SINGLE = re.compile(r"\bfrom:([^\s()]+)", re.I)
_RE_TO_GROUP = re.compile(r"\bto:\(([^)]+)\)", re.I)
_RE_TO_SINGLE = re.compile(r"\bto:([^\s()]+)", re.I)
_RE_ANY_OR = re.compile(
    r"\(\s*from:([^\s)]+)\s+OR\s+to:\1\s*\)",
    re.I,
)
_RE_SUBJECT_GROUP = re.compile(r"\bsubject:\(([^)]+)\)", re.I)
_RE_STRIP_OPS = re.compile(
    r"\b(?:after|before|newer_than|older_than|in|has|from|to|subject|label|category):\S*",
    re.I,
)
_RE_STRIP_GROUP_OPS = re.compile(
    r"\b(?:from|to|subject):\([^)]*\)",
    re.I,
)


def _epoch_to_unipile_after(epoch: int) -> str:
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    # exclusive "after" — nudge 1ms earlier so boundary messages are kept
    dt = dt - timedelta(milliseconds=1)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _days_ago_unipile_after(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days) - timedelta(milliseconds=1)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _split_or_addrs(raw: str) -> list[str]:
    parts = re.split(r"\s+OR\s+", raw.strip(), flags=re.I)
    out: list[str] = []
    for p in parts:
        a = p.strip().strip('"').lower()
        if a and "@" in a:
            out.append(a)
        elif a and not a.startswith("-"):
            # domain-only from:example.com
            out.append(a)
    return out


def parse_gmail_query(query: str) -> dict:
    """Translate a subset of Gmail `q` into Unipile list filters + client flags."""
    q = (query or "").strip()
    flags = {"require_attachment": False, "sent_only": False}
    after: str | None = None
    from_addrs: list[str] = []
    to_addrs: list[str] = []
    any_emails: list[str] = []
    search_bits: list[str] = []

    m = _RE_AFTER_EPOCH.search(q)
    if m:
        after = _epoch_to_unipile_after(int(m.group(1)))
    else:
        m = _RE_NEWER_THAN_D.search(q)
        if m:
            after = _days_ago_unipile_after(int(m.group(1)))

    if _RE_IN_SENT.search(q):
        flags["sent_only"] = True
    if _RE_HAS_ATTACH.search(q):
        flags["require_attachment"] = True

    for m in _RE_ANY_OR.finditer(q):
        any_emails.append(m.group(1).strip().lower())

    for m in _RE_FROM_GROUP.finditer(q):
        from_addrs.extend(_split_or_addrs(m.group(1)))
    # singles not already inside a group — rough: remove groups first
    q_wo_groups = _RE_FROM_GROUP.sub(" ", q)
    for m in _RE_FROM_SINGLE.finditer(q_wo_groups):
        from_addrs.extend(_split_or_addrs(m.group(1)))

    for m in _RE_TO_GROUP.finditer(q):
        to_addrs.extend(_split_or_addrs(m.group(1)))
    q_wo_to = _RE_TO_GROUP.sub(" ", q)
    for m in _RE_TO_SINGLE.finditer(q_wo_to):
        to_addrs.extend(_split_or_addrs(m.group(1)))

    for m in _RE_SUBJECT_GROUP.finditer(q):
        # subject:(a OR b) → free-text search tokens
        inner = m.group(1)
        for part in re.split(r"\s+OR\s+", inner, flags=re.I):
            tok = part.strip().strip('"')
            if tok:
                search_bits.append(tok)

    rest = _RE_STRIP_GROUP_OPS.sub(" ", q)
    rest = _RE_STRIP_OPS.sub(" ", rest)
    rest = re.sub(r"[()]", " ", rest)
    rest = re.sub(r"\bOR\b", " ", rest, flags=re.I)
    rest = re.sub(r"\s+", " ", rest).strip()
    if rest:
        search_bits.append(rest)

    # Dedupe preserving order
    def uniq(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    from_addrs = uniq(from_addrs)
    to_addrs = uniq(to_addrs)
    any_emails = uniq(any_emails)
    search = " ".join(uniq(search_bits)).strip() or None

    return {
        "after": after,
        "from_addrs": from_addrs,
        "to_addrs": to_addrs,
        "any_emails": any_emails,
        "search": search,
        "flags": flags,
    }


async def _sent_folder_id(account_id: str) -> str | None:
    if account_id in _sent_folder_cache:
        return _sent_folder_cache[account_id]
    try:
        folders = await unipile.list_folders(account_id)
    except Exception as e:
        logger.warning("unipile folders fail account=%s err=%s", account_id[:8], e)
        _sent_folder_cache[account_id] = None
        return None
    folder_id = None
    for f in folders:
        role = (f.get("role") or "").lower()
        name = (f.get("name") or f.get("display_name") or "").lower()
        if role == "sent" or name in ("sent", "sent mail", "[gmail]/sent mail"):
            folder_id = f.get("provider_id") or f.get("id")
            break
    _sent_folder_cache[account_id] = folder_id
    return folder_id


def _header_map(raw: dict) -> dict[str, str]:
    headers = raw.get("headers") or []
    out: dict[str, str] = {}
    if isinstance(headers, list):
        for h in headers:
            if not isinstance(h, dict):
                continue
            name = (h.get("name") or "").lower()
            val = h.get("value") or ""
            if name:
                out[name] = val
    elif isinstance(headers, dict):
        out = {str(k).lower(): str(v) for k, v in headers.items()}
    return out


def _attendee_header(attendees) -> str:
    if not attendees:
        return ""
    if isinstance(attendees, dict):
        attendees = [attendees]
    parts: list[str] = []
    for a in attendees:
        if not isinstance(a, dict):
            continue
        ident = (a.get("identifier") or "").strip()
        name = (a.get("display_name") or "").strip()
        if name and ident:
            parts.append(f"{name} <{ident}>")
        elif ident:
            parts.append(ident)
        elif name:
            parts.append(name)
    return ", ".join(parts)


def _html_to_visible_text(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _format_date(raw_date) -> str:
    if raw_date is None:
        return ""
    if isinstance(raw_date, (int, float)):
        try:
            return datetime.fromtimestamp(raw_date, tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            return str(raw_date)
    s = str(raw_date).strip()
    if not s:
        return ""
    # Already RFC2822-ish
    if re.match(r"^[A-Za-z]{3},", s) or " +" in s or " -" in s[-6:]:
        return s
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        try:
            return parsedate_to_datetime(s).strftime("%a, %d %b %Y %H:%M:%S +0000")
        except Exception:
            return s


def parse_email_addresses(header_value: str) -> list[str]:
    if not header_value:
        return []
    found = re.findall(r"[\w.+-]+@[\w.-]+\.\w+", header_value, flags=re.I)
    return [a.lower() for a in found]


def _parse_unipile_email(raw: dict, *, body_limit: int = 8000) -> Optional[dict]:
    if not raw:
        return None
    eid = raw.get("id") or raw.get("email_id")
    if not eid:
        return None
    headers = _header_map(raw)
    from_h = _attendee_header(raw.get("from_attendee")) or headers.get("from", "")
    to_h = _attendee_header(raw.get("to_attendees")) or headers.get("to", "")
    cc_h = _attendee_header(raw.get("cc_attendees")) or headers.get("cc", "")
    subject = raw.get("subject") or headers.get("subject", "") or ""
    body = (raw.get("body_plain") or "").strip()
    if not body and raw.get("body"):
        body = _html_to_visible_text(str(raw.get("body")))
    if body_limit and body_limit > 0:
        body = body[:body_limit]
    atts = raw.get("attachments") or []
    attachment_names: list[str] = []
    attachment_parts: list[dict] = []
    for a in atts:
        if not isinstance(a, dict):
            continue
        name = (a.get("name") or a.get("filename") or "").strip()
        if name:
            attachment_names.append(name)
        aid = a.get("id") or a.get("attachment_id")
        if name and aid:
            attachment_parts.append({
                "filename": name,
                "mime_type": a.get("mime") or a.get("mime_type") or "",
                "attachment_id": aid,
                "size": int(a.get("size") or 0),
            })
    rfc_mid = (raw.get("message_id") or headers.get("message-id") or "").strip()
    role = (raw.get("role") or "").lower()
    folders = raw.get("folders") or []
    label_ids: list[str] = []
    if role:
        label_ids.append(role.upper() if role != "inbox" else "INBOX")
    if isinstance(folders, list):
        for f in folders:
            if isinstance(f, str):
                label_ids.append(f)
            elif isinstance(f, dict) and f.get("name"):
                label_ids.append(str(f["name"]))
    date_s = _format_date(raw.get("date") or headers.get("date"))
    snippet = (body or subject)[:160]
    return {
        "id": eid,
        "thread_id": raw.get("thread_id") or "",
        "provider_id": raw.get("provider_id") or "",
        "rfc_message_id": rfc_mid,
        "subject": subject,
        "from": from_h,
        "to": to_h,
        "cc": cc_h,
        "to_addrs": parse_email_addresses(to_h),
        "cc_addrs": parse_email_addresses(cc_h),
        "date": date_s,
        "snippet": snippet,
        "body": body,
        "list_unsubscribe": headers.get("list-unsubscribe", ""),
        "has_attachment": bool(raw.get("has_attachments")) or any(
            n.lower().endswith(".pdf") for n in attachment_names
        ),
        "attachment_names": attachment_names,
        "attachment_parts": attachment_parts,
        "label_ids": label_ids,
        "in_reply_to": headers.get("in-reply-to", "").strip(),
        "references": headers.get("references", "").strip(),
    }


async def list_message_ids(access_token: str, query: str, max_pages: int = 20) -> list[str]:
    """List Unipile email IDs matching a Gmail-style query (best-effort translation)."""
    account_id = access_token
    parsed = parse_gmail_query(query)
    folder = None
    if parsed["flags"]["sent_only"]:
        folder = await _sent_folder_id(account_id)

    # Build one or more Unipile list calls (OR of many from: → any_email / multiple)
    call_specs: list[dict] = []
    base = {
        "after": parsed["after"],
        "search": parsed["search"],
        "folder": folder,
    }
    from_addrs = parsed["from_addrs"]
    to_addrs = parsed["to_addrs"]
    any_emails = parsed["any_emails"]

    if any_emails and not from_addrs and not to_addrs:
        call_specs.append({**base, "any_email": ",".join(any_emails)})
    elif from_addrs and to_addrs and set(from_addrs) == set(to_addrs):
        call_specs.append({**base, "any_email": ",".join(from_addrs)})
    elif len(from_addrs) > 1 and not to_addrs:
        # Unipile `from` is singular — use any_email for multi-from client mail
        call_specs.append({**base, "any_email": ",".join(from_addrs)})
    elif len(from_addrs) == 1 and not to_addrs:
        call_specs.append({**base, "from_addr": from_addrs[0]})
    elif len(to_addrs) == 1 and not from_addrs:
        call_specs.append({**base, "to": to_addrs[0]})
    elif from_addrs or to_addrs:
        if from_addrs:
            call_specs.append({**base, "any_email": ",".join(from_addrs + to_addrs)})
        else:
            call_specs.append({**base, "to": to_addrs[0] if len(to_addrs) == 1 else None, "any_email": ",".join(to_addrs) if len(to_addrs) > 1 else None})
    else:
        call_specs.append(base)

    ids: list[str] = []
    seen: set[str] = set()
    require_att = parsed["flags"]["require_attachment"]

    for spec in call_specs:
        cursor = None
        for _ in range(max_pages):
            async def _once(spec=spec, cursor=cursor):
                return await unipile.list_emails(
                    account_id,
                    limit=LIST_PAGE_SIZE,
                    cursor=cursor,
                    meta_only=True,
                    after=spec.get("after"),
                    search=spec.get("search"),
                    from_addr=spec.get("from_addr"),
                    to=spec.get("to"),
                    any_email=spec.get("any_email"),
                    folder=spec.get("folder"),
                )

            try:
                data = await _retry(_once, label="unipile.list")
            except unipile.UnipileAuthError as e:
                raise GmailAuthError(str(e)) from e
            except unipile.UnipileError as e:
                logger.warning("unipile.list fail q=%r err=%s", query[:80], e)
                break

            items = (data or {}).get("items") or []
            for item in items:
                eid = item.get("id")
                if not eid or eid in seen:
                    continue
                if require_att and not (
                    item.get("has_attachments")
                    or any(
                        str(a.get("name", "")).lower().endswith(".pdf")
                        for a in (item.get("attachments") or [])
                        if isinstance(a, dict)
                    )
                ):
                    # meta_only may omit attachments — keep and let full fetch filter later
                    # Prefer keeping if has_attachments unknown
                    if item.get("has_attachments") is False:
                        continue
                seen.add(eid)
                ids.append(eid)
            cursor = (data or {}).get("cursor")
            if not cursor or not items:
                break
    return ids


async def get_message(
    access_token: str,
    message_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> Optional[dict]:
    _ = client  # unused; kept for call-site compatibility
    account_id = access_token
    _ = account_id

    async def _once():
        return await unipile.get_email(message_id, include_headers=True)

    try:
        raw = await _retry(_once, label=f"unipile.get({message_id[:8]})")
    except unipile.UnipileAuthError as e:
        raise GmailAuthError(str(e)) from e
    except unipile.UnipileError as e:
        if e.status == 404:
            return None
        logger.warning("unipile.get fail id=%s err=%s", message_id[:12], e)
        return None
    return _parse_unipile_email(raw)


async def get_messages_batch(
    access_token: str,
    message_ids: list[str],
    *,
    concurrency: int = GMAIL_FETCH_CONCURRENCY,
) -> list[dict]:
    if not message_ids:
        return []
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(mid: str) -> tuple[str, Optional[dict]]:
        async with sem:
            msg = await get_message(access_token, mid)
            return mid, msg

    results = await asyncio.gather(
        *[one(mid) for mid in message_ids],
        return_exceptions=True,
    )
    out: list[dict] = []
    by_id: dict[str, dict] = {}
    for mid, res in zip(message_ids, results):
        if isinstance(res, Exception):
            logger.warning("unipile batch skip id=%s err=%s", mid, res)
            continue
        key, msg = res
        if msg:
            by_id[key] = msg
    for mid in message_ids:
        if mid in by_id:
            out.append(by_id[mid])
    return out


async def fetch_attachment_bytes(access_token: str, message_id: str, attachment_id: str) -> bytes:
    _ = access_token

    async def _once():
        return await unipile.get_attachment(message_id, attachment_id)

    return await _retry(_once, label="unipile.attachment")


async def get_message_metadata(access_token: str, message_id: str) -> Optional[dict]:
    msg = await get_message(access_token, message_id)
    if not msg:
        return None
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("thread_id"),
        "rfc_message_id": msg.get("rfc_message_id") or "",
        "subject": msg.get("subject") or "",
        "references": msg.get("references") or "",
        "in_reply_to": msg.get("in_reply_to") or "",
        "provider_id": msg.get("provider_id") or "",
    }


async def get_thread_message_ids(access_token: str, thread_id: str) -> list[str]:
    account_id = access_token
    ids: list[str] = []
    cursor = None
    for _ in range(20):
        data = await unipile.list_emails(
            account_id,
            limit=LIST_PAGE_SIZE,
            cursor=cursor,
            meta_only=True,
            thread_id=thread_id,
        )
        for item in (data or {}).get("items") or []:
            if item.get("id"):
                ids.append(item["id"])
        cursor = (data or {}).get("cursor")
        if not cursor:
            break
    return list(reversed(ids))  # Unipile returns newest first; chronological preferred


async def get_thread_messages(
    access_token: str,
    thread_id: str,
    *,
    body_limit: int = 8000,
) -> list[dict]:
    ids = await get_thread_message_ids(access_token, thread_id)
    if not ids:
        return []
    batch = await get_messages_batch(access_token, ids)
    # Re-apply body_limit
    for m in batch:
        if body_limit and m.get("body"):
            m["body"] = m["body"][:body_limit]
    # Sort chronological by date
    def sort_key(m):
        try:
            return parsedate_to_datetime(m.get("date") or "").timestamp()
        except Exception:
            return 0.0
    batch.sort(key=sort_key)
    return batch


async def get_thread_latest_metadata(access_token: str, thread_id: str) -> Optional[dict]:
    ids = await get_thread_message_ids(access_token, thread_id)
    if not ids:
        return None
    # get_thread_message_ids returns chronological; latest is last
    return await get_message_metadata(access_token, ids[-1])


async def resolve_thread_reply_context(
    access_token: str,
    *,
    thread_id: str | None = None,
    message_id: str | None = None,
) -> Optional[dict]:
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
                "unipile_email_id": latest.get("id"),
                "provider_id": latest.get("provider_id") or "",
            }

    if message_id:
        meta = await get_message_metadata(access_token, message_id)
        if meta:
            parent_mid = meta.get("rfc_message_id") or ""
            prior_refs = meta.get("references") or meta.get("in_reply_to") or ""
            references = f"{prior_refs} {parent_mid}".strip() if parent_mid else prior_refs
            return {
                "thread_id": meta.get("thread_id") or resolved_thread,
                "rfc_message_id": parent_mid,
                "subject": meta.get("subject") or "",
                "references": references,
                "unipile_email_id": meta.get("id") or message_id,
                "provider_id": meta.get("provider_id") or "",
            }
    return None


_RE_PREFIX = re.compile(r"^(?:(?:re|fwd|fw)\s*:\s*)+", re.I)


def reply_subject(thread_subject: str, draft_subject: str) -> str:
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
    """Kept for callers that still build MIME; Unipile send uses structured fields."""
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
    """Send a plain-text chase reply via Unipile (threaded when possible)."""
    account_id = access_token
    ctx = await resolve_thread_reply_context(
        account_id,
        thread_id=thread_id,
        message_id=reply_to_message_id,
    )
    send_thread = thread_id
    send_subject = subject
    reply_to = reply_to_message_id

    if ctx:
        send_thread = ctx.get("thread_id") or send_thread
        send_subject = reply_subject(ctx.get("subject", ""), subject)
        reply_to = ctx.get("unipile_email_id") or ctx.get("provider_id") or reply_to

    to_payload = [{"display_name": "", "identifier": to_addr}]
    from_payload = {"display_name": "", "identifier": from_addr} if from_addr else None
    try:
        data = await unipile.send_email(
            account_id,
            to=to_payload,
            subject=send_subject,
            body=body,
            reply_to=reply_to,
            from_attendee=from_payload,
            custom_headers=[{"name": "Content-Type", "value": "text/plain; charset=utf-8"}],
        )
    except unipile.UnipileAuthError as e:
        raise GmailAuthError(str(e)) from e
    except unipile.UnipileError as e:
        raise RuntimeError(f"Gmail send failed: {e.status} {e.body[:200]}") from e

    return {
        "gmail_message_id": (data or {}).get("id") or (data or {}).get("email_id"),
        "thread_id": (data or {}).get("thread_id") or send_thread,
        "subject": send_subject,
    }


async def send_mailbox_email(
    access_token: str,
    *,
    from_addr: str,
    to_addr: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
) -> dict:
    """Send a standalone email (daily digest) via Unipile."""
    account_id = access_token
    body = body_html or body_text or ""
    try:
        data = await unipile.send_email(
            account_id,
            to=[{"display_name": "", "identifier": to_addr}],
            subject=subject,
            body=body,
            from_attendee={"display_name": "", "identifier": from_addr} if from_addr else None,
        )
    except unipile.UnipileAuthError as e:
        raise GmailAuthError(str(e)) from e
    except unipile.UnipileError as e:
        raise RuntimeError(f"Gmail send failed: {e.status} {e.body[:200]}") from e
    return {
        "gmail_message_id": (data or {}).get("id") or (data or {}).get("email_id"),
        "thread_id": (data or {}).get("thread_id"),
        "subject": subject,
    }
