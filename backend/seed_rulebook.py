"""90-day seed + incremental new-invoice Extract LLM — rulebook_seed_scan.txt.

Used for onboarding seed and incremental Stage 3 (new invoices).
Incremental Stage 4 re-eval uses reeval_rulebook / rulebook_reeval.txt.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from client_sweep import (
    _extract_email_addr,
    parse_email_date,
    preprocess_body,
)
from ledger_reconcile import (
    client_identity_key,
    is_plausible_invoice_ref,
    normalize_invoice_ref,
    normalize_source_date,
    normalize_subject,
)
from promise_dates import resolve_relative_date

logger = logging.getLogger("scotive.seed_rulebook")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("SEED_AI_MODEL", "openai/gpt-4o-mini")
RULEBOOK_PATH = Path(__file__).resolve().parent / "prompts" / "rulebook_seed_scan.txt"

_RULEBOOK_CACHE: str | None = None

# Rulebook status → ledger enriched_status (rulebook uses overdue, not past_due)
_STATUS_MAP = {
    "invoiced": "invoiced",
    "overdue": "overdue",
    "promised": "promised",
    "disputed": "disputed",
    "partially_paid": "partially_paid",
    "paid_unconfirmed": "paid_unconfirmed",
    # legacy alias if an older model reply still emits past_due
    "past_due": "overdue",
}


def load_seed_scan_rulebook() -> str:
    global _RULEBOOK_CACHE
    if _RULEBOOK_CACHE is None:
        _RULEBOOK_CACHE = RULEBOOK_PATH.read_text(encoding="utf-8")
    return _RULEBOOK_CACHE


def _msg_date_iso(msg: dict) -> str:
    dt = parse_email_date(msg.get("date"))
    if dt:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(msg.get("date") or "")


def _msg_direction(msg: dict, my_email: str) -> str:
    sender = _extract_email_addr(msg.get("from", ""))
    return "user_to_client" if sender == my_email.lower() else "client_to_user"


def _msg_to_addrs(msg: dict) -> list[str]:
    addrs = list(msg.get("to_addrs") or [])
    if not addrs and msg.get("to"):
        from gmail_client import parse_email_addresses
        addrs = parse_email_addresses(msg.get("to") or "")
    return [a.lower() for a in addrs if a]


def build_seed_scan_input(
    *,
    my_email: str,
    client_email: str,
    messages: list[dict],
    anchor_ids: list[str],
    anchor_invoice_ref: str | None = None,
) -> dict[str, Any]:
    """Prepared JSON payload for rulebook_seed_scan (one invoice per call)."""
    anchor_set = {a for a in anchor_ids if a}
    payload: dict[str, Any] = {
        "user_email": my_email.lower(),
        "client_email": client_email.lower(),
        "anchor_message_ids": list(anchor_ids),
        "tracked_state": None,
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


def apply_promise_date_resolution(parsed: dict) -> dict:
    """Overwrite model-guessed promise dates with code-computed ones."""
    latest_resolved: str | None = None
    for event in parsed.get("events") or []:
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
        # Prefer absolute date already in relative_phrase / data.date
        resolved = None
        if phrase:
            try:
                resolved = datetime.strptime(str(phrase).strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                resolved = resolve_relative_date(str(phrase), anchor)
        if not resolved and data.get("date"):
            try:
                resolved = datetime.strptime(str(data["date"])[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                resolved = None
        data["date"] = resolved
        if resolved:
            latest_resolved = resolved
    if latest_resolved:
        parsed["promise_date"] = latest_resolved
    else:
        # Rulebook: top-level promise_date is always null from the model
        if parsed.get("status") == "promised" and not parsed.get("promise_date"):
            parsed["promise_date"] = None
    return parsed


def normalize_null_strings(obj: Any) -> Any:
    """Recursively convert literal string \"null\" into Python None.

    The model often emits the string \"null\" despite prompt instructions
    (same class of failure as disputed_claim_amount). Enforce in code.
    """
    if isinstance(obj, dict):
        return {k: normalize_null_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_null_strings(v) for v in obj]
    if isinstance(obj, str) and obj.strip().lower() == "null":
        return None
    return obj


def enforce_dispute_resolution(parsed: dict) -> dict:
    """If amount_correction follows the latest dispute, clear disputed_claim_amount."""
    events = parsed.get("events") or []
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
    else:
        parsed["disputed_claim_amount"] = None
    return parsed


LLM_IO_LOG_PATH = Path(
    os.environ.get(
        "SEED_RULEBOOK_LLM_IO_LOG",
        str(Path(__file__).resolve().parent / "logs" / "seed_rulebook_llm_io.log"),
    )
)


def reset_llm_io_log() -> None:
    """Overwrite the LLM I/O log at the start of each 90d seed run."""
    try:
        LLM_IO_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with LLM_IO_LOG_PATH.open("w", encoding="utf-8") as f:
            f.write(
                f"# Seed rulebook LLM I/O log — started {ts}\n"
                f"# Overwritten on every 90d seed run.\n"
            )
        logger.info("seed.rulebook IO-LOG reset path=%s", LLM_IO_LOG_PATH)
    except OSError as e:
        logger.warning("seed.rulebook IO-LOG reset fail path=%s err=%s", LLM_IO_LOG_PATH, e)


def _write_llm_io(label: str, client_email: str, payload: Any) -> None:
    """Append Seed Scan LLM I/O to a text log file (no stdout spam)."""
    if isinstance(payload, (dict, list)):
        text = json.dumps(payload, indent=2, default=str)
    else:
        text = str(payload)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = (
        f"\n{'=' * 72}\n"
        f"{ts}  SEED RULEBOOK LLM {label}  client={client_email}\n"
        f"{'=' * 72}\n"
        f"{text}\n"
        f"{'=' * 72}\n"
    )
    try:
        LLM_IO_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LLM_IO_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(block)
    except OSError as e:
        logger.warning("seed.rulebook IO-LOG write fail path=%s err=%s", LLM_IO_LOG_PATH, e)
    logger.debug("seed.rulebook %s client=%s (wrote %s)", label, client_email, LLM_IO_LOG_PATH)


async def extract_seed_scan_with_rulebook(
    client_email: str,
    prepared_input: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Call OpenRouter with rulebook_seed_scan.txt as the sole system prompt."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning("seed.rulebook SKIP client=%s reason=no_openrouter_key", client_email)
        return None

    prompt = load_seed_scan_rulebook()
    user_content = json.dumps(prepared_input, default=str)[:14000]

    _write_llm_io(
        "INPUT (prepared JSON → user message)",
        client_email,
        prepared_input,
    )
    logger.info(
        "seed.rulebook CALL client=%s model=%s system=rulebook_seed_scan.txt "
        "user_chars=%s msgs=%s anchor_ids=%s anchor_ref=%s io_log=%s",
        client_email,
        OPENROUTER_MODEL,
        len(user_content),
        len(prepared_input.get("messages") or []),
        prepared_input.get("anchor_message_ids"),
        prepared_input.get("anchor_invoice_ref"),
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
                    "seed.rulebook FAIL client=%s status=%s body=%s",
                    client_email, r.status_code, r.text[:500],
                )
                _write_llm_io(
                    f"OUTPUT FAIL status={r.status_code}",
                    client_email,
                    r.text[:2000],
                )
                return None
            raw_content = r.json()["choices"][0]["message"]["content"]
            try:
                raw_parsed = json.loads(raw_content)
            except json.JSONDecodeError:
                _write_llm_io("OUTPUT (raw, non-JSON)", client_email, raw_content)
                raise
            _write_llm_io("OUTPUT (raw from LLM)", client_email, raw_parsed)

            # Post-process order matches the reference seed harness:
            # null-string scrub → promise dates → dispute claim safety net.
            parsed = normalize_null_strings(dict(raw_parsed))
            parsed = apply_promise_date_resolution(parsed)
            parsed = enforce_dispute_resolution(parsed)
            _write_llm_io(
                "OUTPUT (after null/promise/dispute post-process)",
                client_email,
                parsed,
            )
            logger.info(
                "seed.rulebook OK client=%s receivable=%s status=%s amount=%s "
                "promise=%s claim=%s events=%s",
                client_email,
                parsed.get("is_receivable"),
                parsed.get("status"),
                parsed.get("amount"),
                parsed.get("promise_date"),
                parsed.get("disputed_claim_amount"),
                len(parsed.get("events") or []),
            )
            return parsed
    except Exception as e:
        logger.warning("seed.rulebook ERROR client=%s err=%s", client_email, e)
        return None


def _event_confidence(events: list[dict]) -> float:
    confs = []
    for e in events or []:
        try:
            confs.append(float(e.get("confidence") or 0))
        except (TypeError, ValueError):
            pass
    if not confs:
        return 0.85
    return max(confs)


def _latest_event(events: list[dict], *types: str) -> Optional[dict]:
    for e in reversed(events or []):
        if e.get("type") in types:
            return e
    return None


def rulebook_result_to_candidate(
    client_email: str,
    result: dict,
    messages_by_id: dict[str, dict],
    *,
    user_id,
    job_id,
    now_iso: str,
    my_email: str,
    anchor_ids: list[str],
    confidence_min: float | None = None,
) -> Optional[dict]:
    """Map rulebook seed-scan output → seed_candidates document."""
    from seed_scan import _client_display_name, _parse_msg_date

    if not result or result.get("is_receivable") is False:
        return None

    amount = result.get("amount")
    if amount in (None, 0):
        return None

    events = list(result.get("events") or [])
    conf = _event_confidence(events)
    min_conf = confidence_min if confidence_min is not None else 0.5
    if conf < min_conf:
        logger.info(
            "seed.rulebook DROP client=%s reason=low_confidence conf=%.2f",
            client_email, conf,
        )
        return None

    # Prefer invoice_sent event's message as the anchor source
    sent_ev = _latest_event(events, "invoice_sent")
    mid = (sent_ev or {}).get("message_id") or (anchor_ids[0] if anchor_ids else None)
    src = messages_by_id.get(mid or "") if mid else None
    if not src and anchor_ids:
        for aid in anchor_ids:
            if aid in messages_by_id:
                mid = aid
                src = messages_by_id[aid]
                break
    if not src:
        logger.info("seed.rulebook DROP client=%s reason=missing_anchor", client_email)
        return None

    inv_num = result.get("invoice_ref")
    norm_ref = normalize_invoice_ref(inv_num, src.get("subject"))
    if not norm_ref:
        norm_ref = normalize_invoice_ref(None, src.get("subject"))

    status_raw = (result.get("status") or "invoiced").strip().lower()
    enriched = _STATUS_MAP.get(status_raw)

    paid = result.get("paid_amount")
    balance = result.get("balance_remaining")
    try:
        paid_f = float(paid) if paid is not None else 0.0
    except (TypeError, ValueError):
        paid_f = 0.0
    try:
        bal_f = float(balance) if balance is not None else max(0.0, float(amount) - paid_f)
    except (TypeError, ValueError):
        bal_f = max(0.0, float(amount) - paid_f)

    partial_ev = _latest_event(events, "partial_payment")
    correction_ev = _latest_event(events, "amount_correction")
    # Client-claimed partials stay in the claim bucket until user confirms.
    # User-stated corrections (haul-video) keep booking to paid_amount.
    client_partial_claim = None
    if partial_ev and not correction_ev:
        try:
            client_partial_claim = float((partial_ev.get("data") or {}).get("amount") or 0)
        except (TypeError, ValueError):
            client_partial_claim = None
        if client_partial_claim is not None and client_partial_claim > 0.005:
            paid_f = 0.0
            bal_f = float(amount)

    # Auto partially_paid when prior CONFIRMED partial is clear
    if (
        enriched in (None, "invoiced", "overdue")
        and paid_f > 0.005
        and bal_f > 0.005
        and bal_f < float(amount) - 0.005
        and not client_partial_claim
    ):
        enriched = "partially_paid"

    # Client partial claim → paid_unconfirmed (or keep disputed if also disputed)
    if client_partial_claim and client_partial_claim > 0.005:
        if enriched == "partially_paid":
            enriched = "paid_unconfirmed"
        elif enriched in (None, "invoiced", "overdue"):
            enriched = "paid_unconfirmed"

    promise_date = result.get("promise_date")
    if enriched == "promised" and not promise_date:
        pev = _latest_event(events, "promise")
        if pev:
            data = pev.get("data") or {}
            promise_date = data.get("date")

    dispute_ev = _latest_event(events, "dispute")
    needs_ev = _latest_event(events, "needs_reply")
    approved_ev = _latest_event(events, "approved")
    evidence = None
    for key in ("dispute", "promise", "paid_claim", "partial_payment", "amount_correction", "invoice_sent"):
        ev = _latest_event(events, key)
        if ev and ev.get("quote"):
            evidence = ev["quote"]
            break

    sent_dt = _parse_msg_date(src)
    age_days = 0
    if sent_dt:
        age_days = (datetime.now(timezone.utc) - sent_dt).days

    cp_name = _client_display_name(src, client_email)
    src_date = normalize_source_date(src.get("date")) or now_iso

    claimed = result.get("disputed_claim_amount")
    try:
        claimed_f = float(claimed) if claimed is not None else None
    except (TypeError, ValueError):
        claimed_f = None

    row: dict[str, Any] = {
        "user_id": user_id,
        "job_id": job_id,
        "message_id": mid,
        "counterparty_email": client_email.lower(),
        "counterparty_name": cp_name,
        "client_identity_key": client_identity_key(client_email),
        "amount": float(amount),
        "currency": (result.get("currency") or "USD").upper(),
        "invoice_ref": (inv_num if is_plausible_invoice_ref(inv_num) else None) or norm_ref,
        "invoice_ref_normalized": norm_ref,
        "source_subject": normalize_subject(src.get("subject")),
        "source_from": src.get("from"),
        "source_date": src_date,
        "source_thread_id": src.get("thread_id"),
        "due_date": result.get("due_date"),
        "due_date_assumed": (result.get("due_date_status") or "") == "missing",
        "due_date_status": result.get("due_date_status"),
        "issue_date": result.get("issue_date"),
        "age_days": age_days,
        "confidence": conf,
        "ai_extracted": True,
        "conversation_enriched": True,
        "seed_rulebook": True,
        "status": "pending",
        "created_at": now_iso,
        "paid_amount": paid_f,
        "balance_remaining": bal_f,
        "seed_events": events,
        "unmatched_signals": list(result.get("unmatched_signals") or []),
    }
    if paid_f > 0.005 and bal_f < float(amount) - 0.005:
        row["amount_original"] = float(amount)
    if enriched:
        row["enriched_status"] = enriched
    if promise_date:
        row["promise_date"] = promise_date
    if evidence:
        row["status_evidence"] = str(evidence)[:500]
    if client_partial_claim and client_partial_claim > 0.005:
        row["payment_claim_amount"] = client_partial_claim
        row["payment_claim_pending"] = True
        if partial_ev and partial_ev.get("quote"):
            row["payment_claim_quote"] = str(partial_ev["quote"])[:500]
    if claimed_f is not None and enriched in ("disputed", "paid_unconfirmed", "partially_paid"):
        row["disputed_claim_amount"] = claimed_f
        if dispute_ev:
            row["dispute_kind"] = "wrong_amount"
        # Dispute + unconfirmed partial claim → disputed chip with says-paid.
        if client_partial_claim and client_partial_claim > 0.005:
            row["enriched_status"] = "disputed"
    if needs_ev and enriched in (None, "invoiced", "overdue"):
        row["needs_reply"] = True
        if needs_ev.get("quote"):
            row["needs_reply_quote"] = str(needs_ev["quote"])[:500]
    if approved_ev:
        row["client_approved"] = True
        if approved_ev.get("quote"):
            row["approval_quote"] = str(approved_ev["quote"])[:500]
    return row


# Event types written to invoice_events on confirm
_EVENT_TO_ACTION = {
    "invoice_sent": "invoice_sent",
    "dispute": "dispute",
    "amount_correction": "invoice_corrected",
    "promise": "payment_promise",
    "partial_payment": "partial_payment",
    "paid_claim": "payment_claim",
    "needs_reply": "client_question",
    "approved": "payment_approved",
}


async def write_seed_events_for_invoice(
    db,
    user_id,
    invoice_id,
    events: list[dict],
    *,
    now_iso: str,
) -> int:
    """Persist rulebook seed events as invoice_events (skip duplicates)."""
    written = 0
    for ev in events or []:
        ev_type = ev.get("type")
        action = _EVENT_TO_ACTION.get(ev_type or "")
        if not action:
            continue
        mid = ev.get("message_id")
        query: dict[str, Any] = {
            "user_id": user_id,
            "invoice_id": invoice_id,
            "action": action,
        }
        if mid:
            query["meta.message_id"] = mid
        if await db.invoice_events.find_one(query):
            continue

        data = ev.get("data") or {}
        meta: dict[str, Any] = {
            "quote": ev.get("quote"),
            "message_id": mid,
            "confidence": ev.get("confidence"),
            "date": data.get("date"),
            "amount": data.get("amount"),
            "reference": data.get("reference"),
            "relative_phrase": data.get("relative_phrase"),
            "anchor_date": data.get("anchor_date"),
            "sender": ev.get("sender"),
            "seed_rulebook": True,
        }
        if ev_type == "dispute" and data.get("amount") is not None:
            meta["claimed_amount"] = data["amount"]
        if ev_type == "amount_correction" and data.get("amount") is not None:
            meta["new_amount"] = data["amount"]
            meta["amount"] = data["amount"]

        await db.invoice_events.insert_one({
            "user_id": user_id,
            "invoice_id": invoice_id,
            "action": action,
            "at": now_iso,
            "meta": meta,
        })
        written += 1
    return written
