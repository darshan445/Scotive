"""Incremental re-eval Extract LLM — rulebook_reeval.txt + prepared JSON I/O.

Used by Sync now / hourly incremental Stage 4 for already-tracked invoices.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from client_sweep import _extract_email_addr, preprocess_body
from promise_dates import resolve_relative_date
from seed_rulebook import (
    _msg_date_iso,
    _msg_direction,
    _msg_to_addrs,
    normalize_null_strings,
)

logger = logging.getLogger("scotive.reeval_rulebook")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("SEED_AI_MODEL", "openai/gpt-4o-mini")
RULEBOOK_PATH = Path(__file__).resolve().parent / "prompts" / "rulebook_reeval.txt"

_RULEBOOK_CACHE: str | None = None

# Rulebook event type → client_sweep / _write_event type
_EVENT_TYPE_MAP = {
    "dispute": "dispute",
    "amount_correction": "correction",
    "promise": "promise",
    "partial_payment": "partial_payment",
    "paid_claim": "payment_claimed",
    "needs_reply": "question",
    "approved": "approved",
}

# Matches rulebook_reeval.txt status enum (uses overdue, not past_due).
_STATUS_MAP = {
    "invoiced": "invoiced",
    "overdue": "overdue",
    "promised": "promised",
    "disputed": "disputed",
    "partially_paid": "partially_paid",
    "paid_unconfirmed": "paid_unconfirmed",
}

LLM_IO_LOG_PATH = Path(
    os.environ.get(
        "REEVAL_RULEBOOK_LLM_IO_LOG",
        str(Path(__file__).resolve().parent / "logs" / "reeval_rulebook_llm_io.log"),
    )
)


def load_reeval_rulebook() -> str:
    global _RULEBOOK_CACHE
    if _RULEBOOK_CACHE is None:
        _RULEBOOK_CACHE = RULEBOOK_PATH.read_text(encoding="utf-8")
    return _RULEBOOK_CACHE


def _write_llm_io(label: str, client_email: str, payload: Any) -> None:
    if isinstance(payload, (dict, list)):
        text = json.dumps(payload, indent=2, default=str)
    else:
        text = str(payload)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = (
        f"\n{'=' * 72}\n"
        f"{ts}  REEVAL RULEBOOK LLM {label}  client={client_email}\n"
        f"{'=' * 72}\n"
        f"{text}\n"
        f"{'=' * 72}\n"
    )
    try:
        LLM_IO_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LLM_IO_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(block)
    except OSError as e:
        logger.warning("reeval.rulebook IO-LOG write fail path=%s err=%s", LLM_IO_LOG_PATH, e)


def build_tracked_state(
    inv: dict,
    processed_message_ids: list[str],
) -> dict[str, Any]:
    """Build tracked_state block for rulebook_reeval input."""
    amount = float(inv.get("amount") or 0)
    paid = float(inv.get("paid_amount") or 0)
    bal = inv.get("balance_remaining")
    try:
        bal_f = float(bal) if bal is not None else max(0.0, amount - paid)
    except (TypeError, ValueError):
        bal_f = max(0.0, amount - paid)

    due_status = inv.get("due_date_status")
    if not due_status:
        if inv.get("due_date_assumed"):
            due_status = "missing"
        elif inv.get("due_date"):
            due_status = "explicit"
        else:
            due_status = "missing"

    claimed = inv.get("disputed_claim_amount")
    try:
        claimed_f = float(claimed) if claimed is not None else None
    except (TypeError, ValueError):
        claimed_f = None

    return {
        "invoice_ref": inv.get("invoice_ref_normalized") or inv.get("invoice_ref"),
        "amount": amount,
        "currency": (inv.get("currency") or "USD").upper(),
        "due_date": inv.get("due_date"),
        "due_date_status": due_status,
        "status": inv.get("status") or "invoiced",
        "promise_date": inv.get("promise_date"),
        "paid_amount": paid,
        "balance_remaining": bal_f,
        "disputed_claim_amount": claimed_f,
        "processed_message_ids": list(processed_message_ids),
    }


def build_reeval_input(
    *,
    my_email: str,
    client_email: str,
    messages: list[dict],
    tracked_state: dict[str, Any],
    anchor_ids: list[str] | None = None,
    anchor_invoice_ref: str | None = None,
) -> dict[str, Any]:
    """Prepared JSON payload for rulebook_reeval (one invoice per call)."""
    anchor_set = {a for a in (anchor_ids or []) if a}
    payload: dict[str, Any] = {
        "user_email": my_email.lower(),
        "client_email": client_email.lower(),
        "tracked_state": tracked_state,
        "messages": [],
    }
    if anchor_invoice_ref:
        payload["anchor_invoice_ref"] = anchor_invoice_ref

    for m in messages:
        mid = m.get("id")
        if not mid:
            continue
        body = preprocess_body(m.get("body") or m.get("snippet") or "", 4000)
        pdf = (m.get("pdf_text") or "").strip() or None
        payload["messages"].append({
            "id": mid,
            "thread_id": m.get("thread_id") or "",
            "date": _msg_date_iso(m),
            "direction": _msg_direction(m, my_email),
            "from": _extract_email_addr(m.get("from", "")) or (m.get("from") or ""),
            "to": _msg_to_addrs(m),
            "subject": m.get("subject") or "",
            "body": body,
            "attachment_names": list(m.get("attachment_names") or []),
            "pdf_text": pdf,
            "is_anchor": mid in anchor_set,
        })
    return payload


def filter_new_events_to_unprocessed(parsed: dict, tracked_state: dict) -> dict:
    """Strip new_events whose message_id was already processed."""
    already = set(tracked_state.get("processed_message_ids") or [])
    events = parsed.get("new_events") or []
    filtered = [e for e in events if e.get("message_id") not in already]
    dropped = len(events) - len(filtered)
    if dropped:
        logger.warning(
            "reeval.rulebook filtered %d already-processed event(s)",
            dropped,
        )
    parsed["new_events"] = filtered
    return parsed


def apply_promise_date_resolution(parsed: dict) -> dict:
    """Overwrite model-guessed promise dates with code-computed ones."""
    from promise_dates import extract_explicit_due_from_text

    latest_resolved: str | None = None
    for event in parsed.get("new_events") or []:
        if event.get("type") != "promise":
            continue
        data = event.setdefault("data", {}) or {}
        event["data"] = data
        phrase = data.get("relative_phrase")
        anchor_str = data.get("anchor_date")
        anchor: date | None = None
        if anchor_str:
            try:
                anchor = datetime.strptime(str(anchor_str)[:10], "%Y-%m-%d").date()
            except ValueError:
                anchor = None
        resolved = None
        # Prefer explicit calendar dates ("July 20", "2026-07-20") over relative math.
        for candidate in (phrase, data.get("date"), event.get("quote")):
            if not candidate:
                continue
            try:
                resolved = datetime.strptime(str(candidate).strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
                break
            except ValueError:
                resolved = extract_explicit_due_from_text(str(candidate), anchor)
                if resolved:
                    break
                resolved = resolve_relative_date(str(candidate), anchor)
                if resolved:
                    break
        data["date"] = resolved
        if resolved:
            latest_resolved = resolved
    if latest_resolved:
        parsed["promise_date"] = latest_resolved
    return parsed


def enforce_dispute_resolution(parsed: dict, tracked_state: dict) -> dict:
    """Clear disputed_claim_amount when a correction resolves the dispute."""
    events = parsed.get("new_events") or []
    last_dispute_idx = None
    last_correction_idx = None
    for i, e in enumerate(events):
        if e.get("type") == "dispute":
            last_dispute_idx = i
        if e.get("type") == "amount_correction":
            last_correction_idx = i

    if last_dispute_idx is not None:
        if last_correction_idx is not None and last_correction_idx > last_dispute_idx:
            parsed["disputed_claim_amount"] = None
    elif last_correction_idx is not None:
        parsed["disputed_claim_amount"] = None
    elif tracked_state.get("disputed_claim_amount") is None:
        parsed["disputed_claim_amount"] = None
    return parsed


def _event_confidence(ev: dict) -> float:
    """Model often emits confidence 0.0 / null — treat as default, not reject."""
    raw = ev.get("confidence")
    if raw is None:
        return 0.85
    try:
        conf = float(raw)
    except (TypeError, ValueError):
        return 0.85
    # Explicit zero / nonsense → default. Real low scores stay low.
    if conf <= 0:
        return 0.85
    return min(conf, 1.0)


def rulebook_events_to_write_events(
    result: dict,
    *,
    invoice_ref: str | None = None,
) -> list[dict]:
    """Map rulebook new_events → _write_event payloads."""
    out: list[dict] = []
    for ev in result.get("new_events") or []:
        raw_type = ev.get("type") or ""
        mapped = _EVENT_TYPE_MAP.get(raw_type)
        if not mapped:
            logger.info("reeval.rulebook SKIP unknown event type=%s", raw_type)
            continue
        data = ev.get("data") or {}
        row: dict[str, Any] = {
            "type": mapped,
            "message_id": ev.get("message_id"),
            "quote": (ev.get("quote") or "").strip(),
            "confidence": _event_confidence(ev),
            "invoice_ref": invoice_ref or result.get("invoice_ref"),
        }
        if mapped == "correction" and data.get("amount") is not None:
            row["amount"] = float(data["amount"])
            if data.get("date"):
                row["date"] = data["date"]
        elif mapped == "dispute":
            if data.get("amount") is not None:
                row["claimed_amount"] = float(data["amount"])
            row["dispute_kind"] = "wrong_amount"
        elif mapped == "partial_payment" and data.get("amount") is not None:
            row["amount"] = float(data["amount"])
        elif mapped == "promise":
            # Prefer post-processed data.date; fall back to top-level promise_date
            row["date"] = data.get("date") or result.get("promise_date")
        elif mapped == "payment_claimed" and data.get("amount") is not None:
            row["amount"] = float(data["amount"])
            if data.get("reference"):
                row["reference"] = data["reference"]
        out.append(row)
    return out


def normalize_reeval_status(status: str | None) -> str | None:
    if not status:
        return None
    return _STATUS_MAP.get(str(status).strip().lower())


async def extract_reeval_with_rulebook(
    client_email: str,
    prepared_input: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Call OpenRouter with rulebook_reeval.txt as the sole system prompt."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("reeval.rulebook SKIP client=%s reason=no_openrouter_key", client_email)
        return None

    tracked_state = prepared_input.get("tracked_state") or {}
    prompt = load_reeval_rulebook()
    user_content = json.dumps(prepared_input, default=str)[:14000]

    _write_llm_io("INPUT (prepared JSON → user message)", client_email, prepared_input)
    logger.info(
        "reeval.rulebook CALL client=%s model=%s system=rulebook_reeval.txt "
        "user_chars=%s msgs=%s processed=%s ref=%s io_log=%s",
        client_email,
        OPENROUTER_MODEL,
        len(user_content),
        len(prepared_input.get("messages") or []),
        len(tracked_state.get("processed_message_ids") or []),
        tracked_state.get("invoice_ref"),
        LLM_IO_LOG_PATH,
    )

    try:
        async with httpx.AsyncClient(timeout=90.0) as c:
            r = await c.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": os.environ.get("FRONTEND_URL", "https://scotive.app"),
                    "X-Title": "Scotive",
                },
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 1200,
                },
            )
            if r.status_code != 200:
                logger.warning(
                    "reeval.rulebook FAIL client=%s status=%s body=%s",
                    client_email, r.status_code, r.text[:500],
                )
                _write_llm_io(f"OUTPUT FAIL status={r.status_code}", client_email, r.text[:2000])
                return None
            raw_content = r.json()["choices"][0]["message"]["content"]
            try:
                raw_parsed = json.loads(raw_content)
            except json.JSONDecodeError:
                _write_llm_io("OUTPUT (raw, non-JSON)", client_email, raw_content)
                raise
            _write_llm_io("OUTPUT (raw from LLM)", client_email, raw_parsed)

            # Post-process order matches the reference reeval harness:
            # null-string scrub → drop already-processed events → promise dates
            # → dispute claim safety net.
            parsed = normalize_null_strings(dict(raw_parsed))
            parsed = filter_new_events_to_unprocessed(parsed, tracked_state)
            parsed = apply_promise_date_resolution(parsed)
            parsed = enforce_dispute_resolution(parsed, tracked_state)
            _write_llm_io(
                "OUTPUT (after null/filter/promise/dispute post-process)",
                client_email,
                parsed,
            )
            logger.info(
                "reeval.rulebook OK client=%s status=%s amount=%s promise=%s "
                "claim=%s new_events=%s",
                client_email,
                parsed.get("status"),
                parsed.get("amount"),
                parsed.get("promise_date"),
                parsed.get("disputed_claim_amount"),
                len(parsed.get("new_events") or []),
            )
            return parsed
    except Exception as e:
        logger.warning("reeval.rulebook ERROR client=%s err=%s", client_email, e)
        return None
