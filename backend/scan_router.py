"""Scan + ledger endpoints."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from scan_pipeline import reconcile_receipts
from gmail_sync import INCREMENTAL_LOOKBACK, ack_detections, ack_due_date_prompts, run_onboarding_sync
from post_chase import ack_followup_prompts, mark_chase_sent
from incremental_sync import run_incremental_sync
from seed_scan import (
    SEED_DAYS,
    confirm_seed_curation,
    continue_onboarding,
    discard_seed_review,
    get_onboarding_state,
    list_seed_candidates,
    run_seed_scan,
)
from invoice_lifecycle import (
    apply_stale_transitions,
    clear_payment_claim_fields,
    clear_stale_fields,
    has_pending_payment_claim,
    migrate_unconfirmed_client_partial_claims,
    outstanding_balance,
    payment_claim_amount_value,
)
from ledger_reconcile import (
    INVOICE_MONGO_SORT,
    OPEN_INVOICE_STATUSES,
    REVIEW_MONGO_SORT,
    client_identity_key,
    compute_open_totals,
    enrich_invoice_doc,
    normalize_source_date,
    sort_by_email_date,
    sort_by_due_promise_date,
)
from escalation_scheduler import run_escalation_tick, generate_draft as _gen_escalation_draft
from draft_tone import resolve_draft_tone, tone_instruction
from gmail_oauth import ensure_gmail_account_name
from digest_sender import send_digest_for_user, build_digest_email, collect_today_sections, _totals as _digest_totals
from client_merge import (
    apply_client_merge,
    detect_cross_domain_merge_prompts,
    dismiss_merge_prompt,
    list_pending_merge_prompts,
    resolve_canonical_key_for_lookup,
)

logger = logging.getLogger("scotive.scan_router")


class SeedConfirmInput(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    track_none: bool = False
    due_dates: dict[str, str | None] = Field(default_factory=dict)


class OnboardingQboStepInput(BaseModel):
    """Path B: resolve optional QuickBooks step before/around seed."""
    action: str  # pending | skip | connected


class DetectionAckInput(BaseModel):
    invoice_ids: list[str] | None = None


class ReviewConfirmInput(BaseModel):
    counterparty_email: str | None = None
    counterparty_name: str | None = None
    amount: float | None = None
    currency: str | None = None
    invoice_ref: str | None = None
    due_date: str | None = None
    promise_date: str | None = None
    status: str | None = None
    kind: str | None = None


_OPEN_STATUSES = OPEN_INVOICE_STATUSES


class InvoiceActionInput(BaseModel):
    # mark_paid | write_off | dispute | resolve_dispute | pause | resume | undo |
    # dismiss_stale | set_due_date | skip_due_date | deny_payment_claim
    # pause = user "Pause tracking" (sets tracking_paused + chasing_paused)
    action: str
    due_date: str | None = Field(default=None, max_length=32)


class ChaseDraftInput(BaseModel):
    tone: str | None = None
    note: str | None = None


class ChaseSendInput(BaseModel):
    subject: str
    body: str


class QuickComposeInput(BaseModel):
    invoice_id: str
    intent: str


class ReceiptMatchInput(BaseModel):
    invoice_id: str


class ChaseDraftPatch(BaseModel):
    subject: str | None = None
    body: str | None = None


class ManualInvoiceInput(BaseModel):
    counterparty_email: str = Field(min_length=3, max_length=254)
    counterparty_name: str | None = Field(default=None, max_length=200)
    amount: float = Field(gt=0)
    currency: str = Field(default="USD", max_length=8)
    invoice_ref: str | None = Field(default=None, max_length=100)
    due_date: str | None = Field(default=None, max_length=32)   # YYYY-MM-DD
    promise_date: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=500)


def _serialize(doc: dict) -> dict:
    """Convert a MongoDB doc into a JSON-safe dict. Turns _id/ObjectId into strings."""
    if not doc:
        return doc
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = _json_safe(v)
        elif isinstance(v, list):
            out[k] = [_json_safe(item) if isinstance(item, dict) else (str(item) if isinstance(item, ObjectId) else item) for item in v]
        else:
            out[k] = v
    if "_id" in out and not isinstance(out["_id"], str):
        out["_id"] = str(out["_id"])
    return out


def _json_safe(value):
    """Recursively convert ObjectId / datetime instances anywhere in a nested
    dict or list so FastAPI's default JSON encoder never chokes.

    Used for embedded `meta` fields on invoice_events (e.g. `receipt_id` is an
    ObjectId), which previously bubbled up as a 500 when the timeline endpoint
    tried to return a `receipt_matched` event.
    """
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _parse_date(v):
    """Return a datetime.date or None."""
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).date()
        except Exception:
            try:
                return datetime.strptime(v[:10], "%Y-%m-%d").date()
            except Exception:
                return None
    return None


def _compute_client_stats(invoices: list[dict]) -> dict | None:
    """Compute payment behavior for a client from their serialized invoice list.

    Returns a stats dict when the client has ≥2 completed payment cycles
    (paid invoices), otherwise None so the frontend can skip the whole card.

    Metrics:
      - payment_cycles: count of paid invoices
      - avg_days_late: mean of max(0, paid_date - due_date) across paid invoices
        that had a due_date. Nil when none had a due date.
      - promise_keep_rate: kept / (kept + broken)
          kept   = paid invoice whose paid_date ≤ promise_date + 1d
          broken = status == "promise_broken" OR (paid invoice with paid_date > promise_date + 1d)
        Nil when no promises were ever recorded on this client's invoices.
      - risk_hint: "on_time" | "slow" | "risky"
    """
    paid = [i for i in invoices if i.get("status") == "paid"]
    cycles = len(paid)
    if cycles < 2:
        return None

    # Avg days late (only among paid invoices with a due_date)
    day_lates: list[int] = []
    for inv in paid:
        due = _parse_date(inv.get("due_date"))
        paid_at = _parse_date(inv.get("paid_at")) or _parse_date(inv.get("status_updated_at"))
        if due and paid_at:
            day_lates.append(max(0, (paid_at - due).days))
    avg_days_late = round(sum(day_lates) / len(day_lates), 1) if day_lates else None

    # Promise keep rate — considers every invoice ever seen for this client
    kept = 0
    broken = 0
    for inv in invoices:
        promise = _parse_date(inv.get("promise_date"))
        status = inv.get("status")
        if status == "promise_broken":
            broken += 1
            continue
        if not promise:
            continue
        if status == "paid":
            paid_at = _parse_date(inv.get("paid_at"))
            if paid_at:
                if (paid_at - promise).days <= 1:
                    kept += 1
                else:
                    broken += 1
    denom = kept + broken
    promise_keep_rate = round(kept / denom, 2) if denom else None

    # Risk hint
    late = avg_days_late if avg_days_late is not None else 0
    keep = promise_keep_rate if promise_keep_rate is not None else 1.0
    if late <= 2 and keep >= 0.8:
        risk = "on_time"
    elif late >= 14 or keep < 0.5:
        risk = "risky"
    else:
        risk = "slow"

    return {
        "payment_cycles": cycles,
        "avg_days_late": avg_days_late,
        "promise_keep_rate": promise_keep_rate,
        "promise_kept": kept,
        "promise_total": denom,
        "risk_hint": risk,
    }


def build_router(db, get_current_user):
    router = APIRouter(tags=["scan"])

    @router.get("/onboarding/state")
    async def onboarding_state(user: dict = Depends(get_current_user)):
        return await get_onboarding_state(db, user["_id"])

    @router.post("/onboarding/qbo-step")
    async def onboarding_qbo_step(payload: OnboardingQboStepInput, user: dict = Depends(get_current_user)):
        action = (payload.action or "").strip().lower()
        if action not in ("pending", "skip", "connected"):
            raise HTTPException(status_code=400, detail="action must be pending, skip, or connected")
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.gmail_sync_state.update_one(
            {"user_id": user["_id"]},
            {"$set": {
                "onboarding_qbo_step": action,
                "awaiting_curation": True,
                "updated_at": now_iso,
            }},
            upsert=True,
        )
        return {"ok": True, "onboarding_qbo_step": action}

    @router.post("/onboarding/continue")
    async def onboarding_continue(user: dict = Depends(get_current_user)):
        """Next on connections screen → curation (Gmail-only) or dashboard (with QBO)."""
        try:
            result = await continue_onboarding(db, user["_id"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return result

    @router.post("/seed/start")
    async def seed_start(user: dict = Depends(get_current_user)):
        conn = await db.gmail_connections.find_one({"user_id": user["_id"]})
        if not conn or conn.get("status") == "revoked":
            raise HTTPException(status_code=400, detail="Connect Gmail before seed scan.")
        existing = await db.seed_jobs.find_one(
            {"user_id": user["_id"], "status": {"$in": ["queued", "running"]}}
        )
        if existing:
            return {"job_id": str(existing["_id"]), "status": existing.get("status")}
        now_iso = datetime.now(timezone.utc).isoformat()
        res = await db.seed_jobs.insert_one({
            "user_id": user["_id"],
            "status": "queued",
            "phase": "queued",
            "days": SEED_DAYS,
            "counts": {"candidates": 0},
            "started_at": now_iso,
            "updated_at": now_iso,
        })
        job_id = res.inserted_id
        await db.gmail_sync_state.update_one(
            {"user_id": user["_id"]},
            {"$set": {"awaiting_curation": True, "updated_at": now_iso}},
            upsert=True,
        )
        asyncio.create_task(run_seed_scan(db, user["_id"], job_id))
        return {"job_id": str(job_id), "status": "queued"}

    @router.get("/seed/status")
    async def seed_status(user: dict = Depends(get_current_user)):
        job = await db.seed_jobs.find_one(
            {"user_id": user["_id"]}, sort=[("started_at", -1)]
        )
        if not job:
            return {"has_job": False}
        return {
            "has_job": True,
            "job_id": str(job["_id"]),
            "status": job.get("status"),
            "phase": job.get("phase"),
            "counts": job.get("counts", {}),
            "days": job.get("days", SEED_DAYS),
            "error": job.get("error"),
        }

    @router.get("/seed/candidates")
    async def seed_candidates(user: dict = Depends(get_current_user)):
        rows = await list_seed_candidates(db, user["_id"])
        return {"candidates": [_serialize(r) for r in rows], "count": len(rows)}

    @router.post("/seed/confirm")
    async def seed_confirm(payload: SeedConfirmInput, user: dict = Depends(get_current_user)):
        try:
            result = await confirm_seed_curation(
                db,
                user["_id"],
                payload.candidate_ids,
                track_none=payload.track_none,
                due_dates=payload.due_dates,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, **result}

    @router.post("/seed/review/discard")
    async def seed_review_discard(user: dict = Depends(get_current_user)):
        """Dismiss deferred Gmail seed review on the dashboard (track none)."""
        try:
            result = await discard_seed_review(db, user["_id"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return result

    @router.post("/scan/sync")
    async def scan_sync(user: dict = Depends(get_current_user)):
        """Manual sync — same job as the hourly background sync (last hour of sent mail)."""
        try:
            counts = await run_incremental_sync(db, user["_id"])
        except Exception as e:
            logger.exception("Manual sync failed: %s", e)
            raise HTTPException(status_code=500, detail="Sync failed. Check backend logs.")
        state = await db.gmail_sync_state.find_one({"user_id": user["_id"]}) or {}
        return {
            "ok": True,
            "counts": counts,
            "last_synced_at": state.get("last_synced_at"),
            "new_invoices": counts.get("new_invoices") or [],
        }

    @router.post("/sync/detections/ack")
    async def sync_detections_ack(
        payload: DetectionAckInput | None = None,
        user: dict = Depends(get_current_user),
    ):
        ids = payload.invoice_ids if payload else None
        return await ack_detections(db, user["_id"], ids)

    @router.post("/sync/due-date-prompts/ack")
    async def due_date_prompts_ack(
        payload: DetectionAckInput | None = None,
        user: dict = Depends(get_current_user),
    ):
        ids = payload.invoice_ids if payload else None
        return await ack_due_date_prompts(db, user["_id"], ids)

    @router.post("/sync/followup-prompts/ack")
    async def followup_prompts_ack(
        payload: DetectionAckInput | None = None,
        user: dict = Depends(get_current_user),
    ):
        ids = payload.invoice_ids if payload else None
        return await ack_followup_prompts(db, user["_id"], ids)

    @router.get("/scan/sync-state")
    async def scan_sync_state(user: dict = Depends(get_current_user)):
        state = await db.gmail_sync_state.find_one({"user_id": user["_id"]}) or {}
        out = {
            "last_synced_at": state.get("last_synced_at"),
            "last_detected_at": state.get("last_detected_at"),
            "last_sync_status": state.get("last_sync_status"),
            "watching_sent_mail": state.get("watching_sent_mail", False),
            "unread_detections": state.get("unread_detections") or [],
            "pending_due_date_prompts": state.get("pending_due_date_prompts") or [],
            "pending_followup_prompts": state.get("pending_followup_prompts") or [],
            "sync_lookback": INCREMENTAL_LOOKBACK,
            "seed_lookback_days": SEED_DAYS,
            "sync_running": bool(state.get("sync_running")),
        }
        return out

    @router.get("/ledger")
    async def get_ledger(user: dict = Depends(get_current_user)):
        cursor = db.invoices.find({"user_id": user["_id"]}).sort(INVOICE_MONGO_SORT)
        rows = []
        raw_docs = []
        async for doc in cursor:
            if doc.get("balance_remaining") is None:
                doc["balance_remaining"] = float(doc.get("amount") or 0)
            doc = enrich_invoice_doc(doc, doc.get("counterparty_email") or "")
            raw_docs.append(doc)
        raw_docs = sort_by_due_promise_date(raw_docs)
        rows = [_serialize(doc) for doc in raw_docs]
        agg = compute_open_totals(raw_docs, _OPEN_STATUSES)
        return {
            "invoices": rows,
            "totals_by_currency": agg["totals_by_currency"],
            "total_open": agg["totals_by_currency"],  # legacy key → per-currency map
            "client_count": agg["client_count"],
        }

    # ---- Receipts --------------------------------------------------------
    @router.get("/receipts")
    async def list_receipts(status: str | None = None, user: dict = Depends(get_current_user)):
        query: dict = {"user_id": user["_id"]}
        if status:
            query["match_status"] = status
        else:
            query["match_status"] = {"$nin": ["rejected"]}
        cursor = db.receipts.find(query).sort("source_date", -1)
        rows = []
        async for doc in cursor:
            rows.append(_serialize(doc))
        return {"receipts": rows, "count": len(rows)}

    @router.post("/receipts/reconcile")
    async def receipts_reconcile(user: dict = Depends(get_current_user)):
        result = await reconcile_receipts(db, user["_id"])
        return {"ok": True, **result}

    @router.post("/receipts/{receipt_id}/match")
    async def receipt_match(receipt_id: str, payload: ReceiptMatchInput, user: dict = Depends(get_current_user)):
        try:
            rc = await db.receipts.find_one({"_id": ObjectId(receipt_id), "user_id": user["_id"]})
            inv = await db.invoices.find_one({"_id": ObjectId(payload.invoice_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Not found")
        if not rc or not inv:
            raise HTTPException(status_code=404, detail="Not found")
        if rc.get("match_status") == "matched":
            raise HTTPException(status_code=400, detail="Receipt already matched")
        now_iso = datetime.now(timezone.utc).isoformat()
        bal = float(inv.get("balance_remaining") if inv.get("balance_remaining") is not None else inv.get("amount") or 0)
        applied = min(float(rc.get("amount") or 0), bal)
        new_balance = round(bal - applied, 2)
        new_paid = round(float(inv.get("paid_amount") or 0) + applied, 2)
        new_status = "paid_unconfirmed" if new_balance <= 0.005 else "partially_paid"
        payer = rc.get("payer_name") or ""
        amt_label = f"{rc.get('currency') or ''} {applied}".strip()
        prev_status = inv.get("status") or "invoiced"
        patch: dict = {
            "status": new_status,
            "balance_remaining": max(new_balance, 0.0),
            "paid_amount": new_paid,
            "paid_at": inv.get("paid_at") if new_status != "paid_unconfirmed" else None,
            "status_updated_at": now_iso,
            "chasing_paused": True,
        }
        if new_status == "paid_unconfirmed":
            patch["payment_claim_quote"] = (
                f"Payment of {amt_label} from {payer}" if payer else f"Processor payment of {amt_label}"
            )
            patch["status_before_claim"] = prev_status
            patch["claim_balance_before"] = bal
            patch["claim_paid_before"] = float(inv.get("paid_amount") or 0)
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": patch},
        )
        await db.receipts.update_one(
            {"_id": rc["_id"]},
            {"$set": {
                "match_status": "user_confirmed",
                "matched_invoice_id": inv["_id"],
                "applied_amount": applied,
                "updated_at": now_iso,
            }},
        )
        await db.invoice_events.insert_one({
            "user_id": user["_id"],
            "invoice_id": inv["_id"],
            "action": "receipt_matched_manual",
            "at": now_iso,
            "meta": {"receipt_id": rc["_id"], "amount": applied, "balance_after": max(new_balance, 0.0)},
        })
        return {"ok": True, "status": new_status, "balance_remaining": max(new_balance, 0.0)}

    @router.post("/receipts/{receipt_id}/reject")
    async def receipt_reject(receipt_id: str, user: dict = Depends(get_current_user)):
        try:
            rc = await db.receipts.find_one({"_id": ObjectId(receipt_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Not found")
        if not rc:
            raise HTTPException(status_code=404, detail="Not found")
        await db.receipts.update_one({"_id": rc["_id"]}, {"$set": {"match_status": "rejected"}})
        return {"ok": True}

    @router.post("/receipts/dismiss-unmatched")
    async def dismiss_unmatched_receipts(user: dict = Depends(get_current_user)):
        """Bulk-dismiss noisy processor emails that aren't client payments."""
        res = await db.receipts.update_many(
            {"user_id": user["_id"], "match_status": "unmatched"},
            {"$set": {"match_status": "rejected", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True, "dismissed": res.modified_count}

    @router.get("/invoices/{invoice_id}/timeline")
    async def invoice_timeline(invoice_id: str, user: dict = Depends(get_current_user)):
        from invoice_timeline import build_invoice_timeline, invoice_next_line
        from invoice_event_idempotency import dedupe_stored_invoice_events

        try:
            inv = await db.invoices.find_one({"_id": ObjectId(invoice_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        inv = enrich_invoice_doc(dict(inv), inv.get("counterparty_email") or "")

        receipts = []
        async for rc in db.receipts.find({"user_id": user["_id"], "matched_invoice_id": inv["_id"]}):
            receipts.append(rc)

        await dedupe_stored_invoice_events(db, user["_id"], inv["_id"])
        event_rows = []
        async for ev in db.invoice_events.find({"user_id": user["_id"], "invoice_id": inv["_id"]}):
            event_rows.append(ev)

        events = build_invoice_timeline(inv, receipts, event_rows)
        serialized_inv = _serialize(inv)
        return {
            "invoice": serialized_inv,
            "events": [_json_safe(e) for e in events],
            "next": invoice_next_line(serialized_inv),
        }

    @router.get("/invoices/{invoice_id}/conversation")
    async def invoice_conversation(invoice_id: str, user: dict = Depends(get_current_user)):
        """Full Gmail thread for invoice detail — read path only, fetch-on-open."""
        import re
        from gmail_client import (
            GmailAuthError,
            _html_to_visible_text,
            get_access_token,
            get_message,
            get_thread_messages,
            parse_email_addresses,
        )
        from ledger_reconcile import parse_email_date, strip_quoted_history

        try:
            inv = await db.invoices.find_one({"_id": ObjectId(invoice_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        inv = enrich_invoice_doc(dict(inv), inv.get("counterparty_email") or "")

        conn = await db.gmail_connections.find_one({"user_id": user["_id"]}) or {}
        my_email = (conn.get("email") or "").lower()

        event_rows = []
        async for ev in db.invoice_events.find({"user_id": user["_id"], "invoice_id": inv["_id"]}):
            event_rows.append(ev)

        _MARKER_LABELS = {
            "dispute": "Disputed",
            "payment_promise": "Promised",
            "payment_claim": "Says paid",
            "partial_payment": "Partial payment",
            "invoice_corrected": "Amount corrected",
            "client_question": "Needs reply",
            "mark_paid": "Marked paid",
            "payment_approved": "Approved",
        }
        markers_by_mid: dict[str, list[str]] = {}
        linked_mids: set[str] = set()
        for ev in event_rows:
            meta = ev.get("meta") or {}
            mid = meta.get("message_id")
            action = ev.get("action") or ""
            if mid:
                linked_mids.add(mid)
            label = _MARKER_LABELS.get(action)
            if mid and label:
                markers_by_mid.setdefault(mid, [])
                if label not in markers_by_mid[mid]:
                    markers_by_mid[mid].append(label)

        messages: list[dict] = []
        gmail_error = None
        thread_id = inv.get("source_thread_id")
        try:
            access = await get_access_token(db, user["_id"])
            if thread_id:
                messages = await get_thread_messages(access, thread_id, body_limit=50000)
            seen = {m.get("id") for m in messages if m.get("id")}
            for mid in linked_mids:
                if mid in seen:
                    continue
                extra = await get_message(access, mid)
                if extra:
                    messages.append(extra)
                    seen.add(mid)
            origin = inv.get("source_message_id")
            if origin and origin not in seen:
                extra = await get_message(access, origin)
                if extra:
                    messages.append(extra)
        except GmailAuthError as e:
            gmail_error = str(e) or "Gmail not connected"
            logger.warning("invoice.conversation gmail auth fail inv=%s err=%s", invoice_id, e)
        except Exception as e:
            gmail_error = "Could not load conversation from Gmail"
            logger.warning("invoice.conversation fail inv=%s err=%s", invoice_id, e)

        def _ts(msg: dict) -> float:
            dt = parse_email_date(msg.get("date"))
            return dt.timestamp() if dt else 0.0

        messages.sort(key=_ts)

        out_msgs = []
        for m in messages:
            sender = (parse_email_addresses(m.get("from") or "") or [""])[0].lower()
            direction = "you" if my_email and sender == my_email else "client"
            mid = m.get("id")
            body = m.get("body") or m.get("snippet") or ""
            # Safety net if an older parser left HTML tags in the body
            if re.search(r"</?[a-z][\s\S]*>", body, re.I):
                body = _html_to_visible_text(body)
            # Thread view already shows prior messages — drop quoted history
            body = strip_quoted_history(body)
            out_msgs.append({
                "id": mid,
                "thread_id": m.get("thread_id") or thread_id,
                "subject": m.get("subject") or "",
                "from": m.get("from") or "",
                "to": m.get("to") or "",
                "date": m.get("date") or "",
                "body": body,
                "direction": direction,
                "state_markers": markers_by_mid.get(mid or "", []),
                "attachment_names": m.get("attachment_names") or [],
            })

        client_replied = any(m["direction"] == "client" for m in out_msgs)
        return {
            "invoice": _serialize(inv),
            "messages": out_msgs,
            "thread_id": thread_id,
            "client_ever_replied": client_replied,
            "gmail_error": gmail_error,
            "my_email": my_email or None,
        }

    # ---- Clients ---------------------------------------------------------
    @router.get("/clients")
    async def list_clients(user: dict = Depends(get_current_user)):
        pipeline = [
            {"$match": {"user_id": user["_id"]}},
            {"$addFields": {
                "client_key": {
                    "$ifNull": [
                        "$client_identity_key",
                        {"$concat": ["email:", {"$toLower": "$counterparty_email"}]},
                    ]
                }
            }},
            {"$group": {
                "_id": "$client_key",
                "emails": {"$addToSet": {"$toLower": "$counterparty_email"}},
                "names": {"$push": "$counterparty_name"},
                "invoice_count": {"$sum": 1},
                "open_invoices": {"$push": {
                    "$cond": [
                        {"$and": [
                            {"$in": ["$status", list(_OPEN_STATUSES)]},
                            {"$ne": [{"$ifNull": ["$tracking_paused", False]}, True]},
                        ]},
                        {
                            "currency": {"$ifNull": ["$currency", "USD"]},
                            "amount": "$amount",
                            "balance_remaining": "$balance_remaining",
                            "status": "$status",
                            "payment_claim_pending": "$payment_claim_pending",
                            "payment_claim_amount": "$payment_claim_amount",
                            "claim_balance_before": "$claim_balance_before",
                            "claim_paid_before": "$claim_paid_before",
                            "paid_amount": "$paid_amount",
                        },
                        None,
                    ]
                }},
                "last_activity": {"$max": {"$ifNull": ["$source_date", "$created_at"]}},
            }},
            {"$sort": {"last_activity": -1}},
        ]
        rows = []
        async for c in db.invoices.aggregate(pipeline):
            totals: dict[str, float] = {}
            for item in c.get("open_invoices") or []:
                if not item:
                    continue
                cur = (item.get("currency") or "USD").upper()
                totals[cur] = round(totals.get(cur, 0) + outstanding_balance(item), 2)
            names = [n for n in (c.get("names") or []) if n]
            display_name = names[0] if names else None
            emails = sorted(c.get("emails") or [])
            primary_email = emails[0] if emails else c["_id"]
            rows.append({
                "email": primary_email,
                "name": display_name,
                "identities": emails,
                "client_key": c["_id"],
                "invoice_count": c.get("invoice_count", 0),
                "open_by_currency": totals,
                "open_amount": sum(totals.values()),  # legacy — prefer open_by_currency in UI
                "last_activity": c.get("last_activity"),
            })
        return {"clients": rows}

    @router.get("/clients/merge-prompts")
    async def get_merge_prompts(user: dict = Depends(get_current_user)):
        prompts = await list_pending_merge_prompts(db, user["_id"])
        return {"prompts": prompts, "count": len(prompts)}

    @router.post("/clients/merge-prompts/{prompt_id}/confirm")
    async def confirm_merge_prompt(prompt_id: str, user: dict = Depends(get_current_user)):
        try:
            result = await apply_client_merge(db, user["_id"], prompt_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"ok": True, **result}

    @router.post("/clients/merge-prompts/{prompt_id}/dismiss")
    async def dismiss_merge_prompt_route(prompt_id: str, user: dict = Depends(get_current_user)):
        try:
            await dismiss_merge_prompt(db, user["_id"], prompt_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"ok": True}

    @router.get("/clients/{email}")
    async def client_detail(email: str, user: dict = Depends(get_current_user)):
        email = email.lower()
        canonical_key = await resolve_canonical_key_for_lookup(db, user["_id"], email)
        query = {"user_id": user["_id"], "client_identity_key": canonical_key}
        cursor = db.invoices.find(query).sort(INVOICE_MONGO_SORT)
        raw_docs = []
        identities: dict[str, int] = {}
        primary_name = None
        async for doc in cursor:
            if doc.get("balance_remaining") is None:
                doc["balance_remaining"] = float(doc.get("amount") or 0)
            doc = enrich_invoice_doc(doc, doc.get("counterparty_email") or "")
            raw_docs.append(doc)
            ident = doc.get("counterparty_email")
            if ident:
                identities[ident] = identities.get(ident, 0) + 1
            if not primary_name and doc.get("counterparty_name"):
                primary_name = doc["counterparty_name"]
        if not raw_docs:
            raise HTTPException(status_code=404, detail="Client not found")

        raw_docs = sort_by_due_promise_date(raw_docs)
        invoices = [_serialize(doc) for doc in raw_docs]

        agg = compute_open_totals(raw_docs, _OPEN_STATUSES)
        stats = _compute_client_stats(invoices)

        return {
            "email": email,
            "name": primary_name,
            "identities": [{"email": e, "message_count": n} for e, n in sorted(identities.items(), key=lambda x: -x[1])],
            "invoices": invoices,
            "totals_by_currency": agg["totals_by_currency"],
            "total_open": agg["totals_by_currency"],
            "stats": stats,
            "client_key": canonical_key,
        }

    # ---- Review queue -----------------------------------------------------
    @router.get("/review-queue")
    async def list_review(user: dict = Depends(get_current_user)):
        cursor = db.review_items.find({"user_id": user["_id"], "review_status": "pending"}).sort(REVIEW_MONGO_SORT)
        items_raw = []
        async for doc in cursor:
            if doc.get("source_date"):
                normalized = normalize_source_date(doc["source_date"])
                if normalized:
                    doc["source_date"] = normalized
            items_raw.append(doc)
        items = [_serialize(doc) for doc in sort_by_email_date(items_raw)]
        return {"items": items, "count": len(items)}

    @router.post("/review-queue/{item_id}/confirm")
    async def confirm_review(item_id: str, patch: ReviewConfirmInput, user: dict = Depends(get_current_user)):
        try:
            item = await db.review_items.find_one({"_id": ObjectId(item_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Item not found")
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        merged = {**item}
        for k, v in patch.model_dump(exclude_none=True).items():
            merged[k] = v
        merged.pop("_id", None)
        merged.pop("review_status", None)
        merged["confidence"] = 1.0  # user-confirmed
        merged = enrich_invoice_doc(merged, merged.get("counterparty_email") or "")
        existing = await db.invoices.find_one({"user_id": user["_id"], "source_message_id": item["source_message_id"]})
        if not existing:
            await db.invoices.insert_one(merged)
        await db.review_items.update_one({"_id": item["_id"]}, {"$set": {"review_status": "confirmed"}})
        return {"ok": True}

    @router.post("/review-queue/{item_id}/reject")
    async def reject_review(item_id: str, user: dict = Depends(get_current_user)):
        try:
            item = await db.review_items.find_one({"_id": ObjectId(item_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Item not found")
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        await db.review_items.update_one({"_id": item["_id"]}, {"$set": {"review_status": "rejected"}})
        return {"ok": True}

    @router.post("/review-queue/{item_id}/suppress")
    async def suppress_sender(item_id: str, user: dict = Depends(get_current_user)):
        try:
            item = await db.review_items.find_one({"_id": ObjectId(item_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Item not found")
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        sender = (item.get("counterparty_email") or "").lower()
        if sender:
            try:
                await db.suppressed_senders.insert_one({
                    "user_id": user["_id"],
                    "email": sender,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                pass
        await db.review_items.update_one({"_id": item["_id"]}, {"$set": {"review_status": "suppressed"}})
        return {"ok": True}

    # ---- Lifecycle transitions -------------------------------------------
    @router.post("/invoices/{invoice_id}/action")
    async def invoice_action(invoice_id: str, payload: InvoiceActionInput, user: dict = Depends(get_current_user)):
        try:
            inv = await db.invoices.find_one({"_id": ObjectId(invoice_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        now = datetime.now(timezone.utc).isoformat()
        action = payload.action

        # UNDO: revert to the pre-action snapshot stored on the last invoice_event
        if action == "undo":
            last = await db.invoice_events.find_one(
                {"user_id": user["_id"], "invoice_id": inv["_id"], "undo_snapshot": {"$exists": True}},
                sort=[("at", -1)],
            )
            if not last:
                raise HTTPException(status_code=400, detail="Nothing to undo")
            snap = last.get("undo_snapshot") or {}
            await db.invoices.update_one({"_id": inv["_id"]}, {"$set": snap})
            await db.invoice_events.update_one({"_id": last["_id"]}, {"$set": {"undone_at": now}})
            await db.invoice_events.insert_one({
                "user_id": user["_id"], "invoice_id": inv["_id"], "action": "undo", "at": now,
                "meta": {"reverted_action": last.get("action")},
            })
            return {"ok": True, "restored_status": snap.get("status")}

        # Capture pre-state snapshot so we can undo destructive actions
        undo_snapshot = {
            "status": inv.get("status"),
            "balance_remaining": inv.get("balance_remaining"),
            "paid_amount": inv.get("paid_amount"),
            "paid_at": inv.get("paid_at"),
            "chasing_paused": inv.get("chasing_paused", False),
            "tracking_paused": inv.get("tracking_paused", False),
            "payment_claim_amount": inv.get("payment_claim_amount"),
            "payment_claim_pending": inv.get("payment_claim_pending"),
            "payment_claim_quote": inv.get("payment_claim_quote"),
            "status_before_claim": inv.get("status_before_claim"),
            "claim_balance_before": inv.get("claim_balance_before"),
            "claim_paid_before": inv.get("claim_paid_before"),
            "disputed_claim_amount": inv.get("disputed_claim_amount"),
        }

        patch: dict = {"status_updated_at": now}
        if action == "mark_paid":
            pending = has_pending_payment_claim(inv)
            claim_amt = payment_claim_amount_value(inv) if pending else None
            if pending and claim_amt is not None:
                # Confirm a (full or partial) client payment claim — only this
                # amount moves into paid_amount (unless a receipt already booked it).
                bal = float(
                    inv.get("balance_remaining")
                    if inv.get("balance_remaining") is not None
                    else inv.get("amount") or 0
                )
                cur_paid = float(inv.get("paid_amount") or 0)
                snapshot_paid = float(inv.get("claim_paid_before") or 0)
                money_already_in = cur_paid > snapshot_paid + 0.005
                if money_already_in:
                    new_paid = cur_paid
                    new_bal = bal
                else:
                    applied = min(claim_amt, bal if bal > 0.005 else claim_amt)
                    new_paid = round(cur_paid + applied, 2)
                    new_bal = round(max(bal - applied, 0), 2)
                has_dispute = inv.get("disputed_claim_amount") is not None
                if new_bal <= 0.005:
                    patch["status"] = "paid"
                    patch["paid_at"] = now
                    patch["balance_remaining"] = 0.0
                    patch["paid_amount"] = float(inv.get("amount") or new_paid)
                    patch["chasing_paused"] = False
                    patch["disputed_claim_amount"] = None
                else:
                    patch["status"] = "partially_paid"
                    patch["balance_remaining"] = new_bal
                    patch["paid_amount"] = new_paid
                    patch["paid_at"] = inv.get("paid_at")
                    patch["chasing_paused"] = bool(has_dispute)
                    if has_dispute:
                        patch["disputed_claim_amount"] = inv["disputed_claim_amount"]
                clear_payment_claim_fields(patch)
                patch["tracking_paused"] = False
                patch["watching_for_reply"] = False
                patch["ladder_exhausted"] = False
                clear_stale_fields(patch)
                patch["last_activity_at"] = now
                await ack_followup_prompts(db, user["_id"], [invoice_id])
            else:
                # Full mark-paid (manual or legacy full claim without amount).
                from qbo_paid_sync import build_full_mark_paid_patch
                patch.update(build_full_mark_paid_patch(inv, now))
                await ack_followup_prompts(db, user["_id"], [invoice_id])
        elif action == "deny_payment_claim":
            has_dispute = (
                inv.get("disputed_claim_amount") is not None
                or inv.get("status") == "disputed"
            )
            if has_dispute:
                # Keep dispute + claim amount as context; stop asking to confirm.
                patch["status"] = "disputed"
                patch["chasing_paused"] = True
                clear_payment_claim_fields(patch, keep_amount=True)
                patch["payment_claim_pending"] = False
            else:
                prev = inv.get("status_before_claim") or ""
                if prev == "stale":
                    prev = inv.get("status_before_stale") or ""
                # Seed-stamped claims have no pre-claim snapshot, and a stored
                # invoiced/overdue may predate a due-date change — resolve by date.
                if prev in ("", "paid_unconfirmed", "invoiced", "overdue"):
                    due = _parse_date(inv.get("due_date"))
                    today = datetime.now(timezone.utc).date()
                    prev = "overdue" if (due and due < today) else "invoiced"
                patch["status"] = prev
                patch["chasing_paused"] = False
                clear_payment_claim_fields(patch, keep_amount=True)
                patch["payment_claim_pending"] = False
            # Restore money only when a prior path had already applied it
            # (e.g. receipt → paid_unconfirmed). Client claims never touch money.
            if inv.get("claim_balance_before") is not None and float(inv.get("paid_amount") or 0) > float(inv.get("claim_paid_before") or 0) + 0.005:
                patch["balance_remaining"] = float(inv["claim_balance_before"])
                patch["paid_amount"] = float(inv.get("claim_paid_before") or 0)
        elif action == "write_off":
            patch["status"] = "written_off"
            patch["watching_for_reply"] = False
            patch["tracking_paused"] = False
            clear_stale_fields(patch)
            patch["last_activity_at"] = now
            await ack_followup_prompts(db, user["_id"], [invoice_id])
        elif action == "dispute":
            patch["status"] = "disputed"
            patch["last_activity_at"] = now
        elif action == "resolve_dispute":
            patch["status"] = "invoiced"
            patch["last_activity_at"] = now
        elif action == "dismiss_stale":
            patch["status"] = inv.get("status_before_stale") or "overdue"
            patch["chasing_paused"] = False
            clear_stale_fields(patch)
            patch["last_activity_at"] = now
        elif action == "pause":
            # User "Pause tracking" — hide from active surfaces; stop chases.
            patch["tracking_paused"] = True
            patch["chasing_paused"] = True
            await ack_followup_prompts(db, user["_id"], [invoice_id])
        elif action == "resume":
            patch["tracking_paused"] = False
            # Restore chase gate: auto-pause statuses keep chasing paused.
            auto_pause = inv.get("status") in (
                "promised", "disputed", "paid_unconfirmed", "stale",
            )
            patch["chasing_paused"] = bool(auto_pause)
        elif action == "set_due_date":
            if not payload.due_date:
                raise HTTPException(status_code=400, detail="due_date required")
            try:
                d = datetime.strptime(payload.due_date[:10], "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid due_date")
            patch["due_date"] = d.isoformat()
            patch["due_date_assumed"] = False
            patch["last_activity_at"] = now
            today = datetime.now(timezone.utc).date()
            if d < today and inv.get("status") == "invoiced":
                patch["status"] = "overdue"
            elif d >= today and inv.get("status") == "overdue":
                patch["status"] = "invoiced"
            await ack_due_date_prompts(db, user["_id"], [invoice_id])
        elif action == "skip_due_date":
            patch["last_activity_at"] = now
            await ack_due_date_prompts(db, user["_id"], [invoice_id])
        else:
            raise HTTPException(status_code=400, detail="Unknown action")
        await db.invoices.update_one({"_id": inv["_id"]}, {"$set": patch})
        await db.invoice_events.insert_one({
            "user_id": user["_id"], "invoice_id": inv["_id"], "action": action, "at": now,
            "undo_snapshot": undo_snapshot,
        })

        # QBO-sourced: when user confirms Received / mark paid, push paid to QuickBooks
        # (Payment linked to Invoice — QBO's only way to drop Balance / mark paid).
        qbo_push = None
        if action == "mark_paid" and inv.get("qbo_id"):
            new_status = patch.get("status")
            if new_status in ("paid", "partially_paid"):
                if new_status == "paid":
                    push_amt = float(
                        inv.get("balance_remaining")
                        if inv.get("balance_remaining") is not None
                        else inv.get("amount") or 0
                    )
                    if push_amt <= 0.005:
                        push_amt = float(inv.get("amount") or 0)
                else:
                    # Partial confirm — push the newly applied amount
                    push_amt = round(
                        float(patch.get("paid_amount") or 0) - float(inv.get("paid_amount") or 0),
                        2,
                    )
                    if push_amt <= 0.005:
                        push_amt = float(patch.get("paid_amount") or 0) - float(inv.get("claim_paid_before") or 0)
                if push_amt > 0.005:
                    try:
                        from qbo_paid_sync import push_scotive_paid_to_qbo
                        merged = {**inv, **patch}
                        qbo_push = await push_scotive_paid_to_qbo(
                            db, user["_id"], merged, amount=push_amt, now_iso=now,
                        )
                    except Exception as e:
                        logger.exception("QBO push paid after mark_paid failed: %s", e)
                        qbo_push = {"ok": False, "error": str(e)[:200]}

        out = {"ok": True}
        if qbo_push is not None:
            out["qbo_push"] = qbo_push
        return out

    @router.post("/lifecycle/run")
    async def run_lifecycle(user: dict = Depends(get_current_user)):
        """Recompute stale transitions and merge prompts (past-due runs on hourly sync)."""
        migrated = await migrate_unconfirmed_client_partial_claims(db, user["_id"])
        stale_updates = await apply_stale_transitions(db, user["_id"])
        merge_prompts = await detect_cross_domain_merge_prompts(db, user["_id"])
        return {
            "ok": True,
            "stale": stale_updates,
            "merge_prompts": merge_prompts,
            "migrated_partial_claims": migrated,
        }

    # ---- Today digest ----------------------------------------------------
    @router.get("/digest/today")
    async def digest_today(user: dict = Depends(get_current_user)):
        today = datetime.now(timezone.utc).date()
        due_overdue = []
        broken = []
        needs_reply = []
        resolved = []
        watching = []
        confirm_prompts = []
        stale_prompts = []
        merge_prompts = []
        async for inv in db.invoices.find({"user_id": user["_id"]}):
            if inv.get("tracking_paused"):
                continue
            s = inv.get("status")
            row = _serialize(inv)
            # Pending payment claim (full or partial) — one confirm card, even
            # when a dispute coexists (never two cards for one invoice).
            if has_pending_payment_claim(inv):
                confirm_prompts.append(row)
            elif s == "stale" and inv.get("stale_prompt_pending"):
                stale_prompts.append(row)
            elif inv.get("needs_reply") and s in ("invoiced", "overdue"):
                # Client asked a question — answering beats chasing.
                needs_reply.append(row)
            elif s in ("overdue",):
                if inv.get("watching_for_reply"):
                    watching.append(row)
                elif inv.get("ladder_exhausted"):
                    watching.append(row)
                else:
                    due_overdue.append(row)
            elif s == "invoiced" and inv.get("due_date"):
                try:
                    due = datetime.fromisoformat(inv["due_date"]).date()
                    if due < today and not inv.get("watching_for_reply"):
                        due_overdue.append(row)
                    else:
                        watching.append(row)
                except Exception:
                    pass
            elif s == "invoiced" and not inv.get("due_date"):
                watching.append(row)
            elif s == "promise_broken":
                # After the user sends a follow-up we watch the thread instead
                # of re-surfacing the row as an action item.
                if inv.get("watching_for_reply") or inv.get("ladder_exhausted"):
                    watching.append(row)
                else:
                    broken.append(row)
            elif s == "disputed":
                if inv.get("watching_for_reply"):
                    watching.append(row)
                else:
                    needs_reply.append(row)
            elif s in ("promised", "partially_paid"):
                watching.append(row)
            elif s == "paid":
                paid_at = inv.get("paid_at")
                try:
                    d = datetime.fromisoformat(paid_at).date() if paid_at else None
                    if d and (today - d).days <= 1:
                        resolved.append(row)
                except Exception:
                    pass
        merge_prompts = await list_pending_merge_prompts(db, user["_id"])
        return {
            "due_overdue": sort_by_email_date(due_overdue),
            "broken_promises": sort_by_email_date(broken),
            "needs_reply": sort_by_email_date(needs_reply),
            "resolved": sort_by_email_date(resolved),
            "watching": sort_by_email_date(watching),
            "confirm_prompts": sort_by_email_date(confirm_prompts),
            "stale_prompts": sort_by_email_date(stale_prompts),
            "merge_prompts": merge_prompts,
        }

    # ---- Chase drafts (Feature 7) ----------------------------------------
    @router.post("/invoices/{invoice_id}/draft-chase")
    async def draft_chase(invoice_id: str, payload: ChaseDraftInput, user: dict = Depends(get_current_user)):
        from scan_pipeline import OPENROUTER_URL, OPENROUTER_MODEL
        import httpx, os, json
        try:
            inv = await db.invoices.find_one({"_id": ObjectId(invoice_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")

        settings = await db.user_settings.find_one({"user_id": user["_id"]}) or {}
        offsets = settings.get("escalation_offsets") or [-3, 0, 3, 10]
        dispute_rounds = await db.invoice_events.count_documents({
            "user_id": user["_id"],
            "invoice_id": inv["_id"],
            "action": "dispute",
        })
        # State-derived tone always wins over any client-supplied tone field.
        # Regenerate `note` may nudge register for this generation only.
        tone_info = resolve_draft_tone(
            inv,
            offsets=offsets,
            dispute_rounds=int(dispute_rounds or 0),
            note=payload.note,
        )
        tone = tone_info["tone"]
        tone_label = tone_info["tone_label"]
        signer_name = await ensure_gmail_account_name(db, user["_id"])

        thread_subject = inv.get("source_subject") or ""
        is_dispute = inv.get("status") == "disputed" or inv.get("disputed_claim_amount") is not None
        is_clarifying = tone == "clarifying" or tone_info.get("is_reply")
        dispute_quote = None
        claim_amt = inv.get("disputed_claim_amount")
        payment_claim = payment_claim_amount_value(inv)
        payment_pending = has_pending_payment_claim(inv)
        confirmed_paid = float(inv.get("paid_amount") or 0)
        if is_dispute:
            ev = await db.invoice_events.find_one(
                {"user_id": user["_id"], "invoice_id": inv["_id"], "action": "dispute"},
                sort=[("at", -1)],
            )
            dispute_quote = ((ev or {}).get("meta") or {}).get("quote")
        sign_rule = (
            f"Always end the body with a short professional sign-off (e.g. Best regards,) "
            f"then the sender's name on its own line, exactly: {signer_name}. "
            if signer_name
            else "Always end the body with a short professional sign-off and the sender's name. "
        )
        sys = (
            "You draft short, professional payment follow-up emails for a small business owner. "
            "Under 120 words. No 'hope this finds you well'. "
            "Always include invoice ref (if any), amount, due date. On a broken promise, quote the client's own stated date verbatim. "
            + tone_instruction(tone) + " "
            + sign_rule
            + (
                "The client has DISPUTED this invoice — do not demand payment. Acknowledge their concern, "
                "reference what they said, and if a claimed amount is provided, confirm you'll adjust the invoice "
                "to that amount (e.g. 'you're right — adjusting to $X'). Propose resolving it briefly. "
                if is_dispute
                else ""
            )
            + (
                "The client asked a question that needs an answer — reply to that, do not chase. "
                if is_clarifying and not is_dispute
                else ""
            )
            + (
                "The client said they sent a payment that is NOT yet confirmed received. "
                "Say they mentioned sending that amount — do NOT thank them as if the money already arrived. "
                if payment_pending and payment_claim
                else (
                    "A partial payment has been confirmed received — you may thank them for that amount. "
                    if confirmed_paid > 0.005 and float(inv.get("balance_remaining") or 0) > 0.005
                    else ""
                )
            )
            + "Never sound templated or AI-written. "
            "This is a REPLY in an existing email thread — subject must be 'Re: <original subject>' matching the thread. "
            "Facts (amount, dates, promises) always come from the ledger below — a user note may only adjust delivery/register, never invent different numbers. "
            "Output STRICT JSON: {\"subject\": string, \"body\": string}."
        )
        user_msg = (
            f"Client: {inv.get('counterparty_name') or inv.get('counterparty_email')}\n"
            f"Original thread subject: {thread_subject or 'n/a'}\n"
            f"Invoice ref: {inv.get('invoice_ref') or 'n/a'}\n"
            f"Amount: {inv.get('amount')} {inv.get('currency','USD')}\n"
            f"Client claimed amount (if disputing): {claim_amt if claim_amt is not None else 'n/a'}\n"
            f"Client says sent (unconfirmed): {payment_claim if payment_pending and payment_claim else 'n/a'}\n"
            f"Confirmed paid amount: {confirmed_paid if confirmed_paid > 0.005 else 'n/a'}\n"
            f"Balance remaining: {inv.get('balance_remaining')}\n"
            f"Due date: {inv.get('due_date') or 'n/a'}\n"
            f"Promise date: {inv.get('promise_date') or 'n/a'}\n"
            f"Status: {inv.get('status')}\n"
            f"Ladder step: {tone_info.get('step_label') or 'n/a'}\n"
            f"Dispute rounds so far: {int(dispute_rounds or 0)}\n"
            f"Tone label: {tone_label}\n"
            f"Tone register: {tone}\n"
            f"Sign emails as: {signer_name or 'n/a'}\n"
            f"Client's own words (broken promise or dispute): {dispute_quote or inv.get('evidence_sentence') or ''}\n"
            f"User extra note (one-time delivery steer only): {payload.note or ''}"
        )
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="AI not configured")
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                             json={"model": OPENROUTER_MODEL, "messages":[{"role":"system","content":sys},{"role":"user","content":user_msg}],
                                   "temperature":0.4, "response_format":{"type":"json_object"}, "max_tokens":400})
            if r.status_code != 200:
                raise HTTPException(status_code=502, detail="AI draft failed")
            content = r.json()["choices"][0]["message"]["content"]
            draft = json.loads(content)
        return {
            "subject": draft.get("subject", ""),
            "body": draft.get("body", ""),
            "tone": tone,
            "tone_label": tone_label,
            "is_reply": bool(tone_info.get("is_reply")),
            "to": inv.get("counterparty_email"),
            "thread_id": inv.get("source_thread_id"),
            "invoice_id": str(inv["_id"]),
        }

    @router.post("/invoices/{invoice_id}/send-chase")
    async def send_chase(invoice_id: str, payload: ChaseSendInput, user: dict = Depends(get_current_user)):
        from gmail_client import get_access_token, send_gmail_reply
        try:
            inv = await db.invoices.find_one({"_id": ObjectId(invoice_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        conn = await db.gmail_connections.find_one({"user_id": user["_id"]})
        if not conn or not conn.get("can_send"):
            raise HTTPException(status_code=400, detail="Gmail send scope missing. Reconnect Gmail.")
        access = await get_access_token(db, user["_id"])
        to_addr = inv.get("counterparty_email")
        from_addr = conn.get("email")
        try:
            sent = await send_gmail_reply(
                access,
                from_addr=from_addr,
                to_addr=to_addr,
                subject=payload.subject,
                body=payload.body,
                thread_id=inv.get("source_thread_id"),
                reply_to_message_id=inv.get("source_message_id"),
            )
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.chase_sends.insert_one({
            "user_id": user["_id"], "invoice_id": inv["_id"], "to": to_addr,
            "subject": sent.get("subject") or payload.subject,
            "body": payload.body, "sent_at": now_iso,
            "gmail_thread_id": sent.get("thread_id"),
        })
        await mark_chase_sent(db, user["_id"], inv["_id"], step_index=None, now_iso=now_iso)
        await ack_followup_prompts(db, user["_id"], [invoice_id])
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$inc": {"chase_count": 1}},
        )
        # Same Stage 4 path as agreeing in Gmail (dispute accept / amount correction).
        reeval = {}
        try:
            from incremental_sync import reeval_after_user_outbound_send
            reeval = await reeval_after_user_outbound_send(
                db, user["_id"], inv,
                access=access,
                my_email=from_addr or "",
                subject=sent.get("subject") or payload.subject,
                body=payload.body,
                gmail_message_id=sent.get("gmail_message_id"),
                thread_id=sent.get("thread_id") or inv.get("source_thread_id"),
            )
        except Exception:
            logger.exception("post-send reeval failed inv=%s", inv["_id"])
            reeval = {"skipped": "error"}
        return {"ok": True, "reeval": reeval}

    @router.post("/quick-compose")
    async def quick_compose(payload: QuickComposeInput, user: dict = Depends(get_current_user)):
        from scan_pipeline import OPENROUTER_URL, OPENROUTER_MODEL
        import httpx, os, json
        try:
            inv = await db.invoices.find_one({"_id": ObjectId(payload.invoice_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        signer_name = await ensure_gmail_account_name(db, user["_id"])
        sign_rule = (
            f"Always end the body with a short professional sign-off then the sender's name "
            f"on its own line, exactly: {signer_name}. "
            if signer_name
            else "Always end the body with a short professional sign-off and the sender's name. "
        )
        sys = ("Expand the user's rough intent into a polished professional email under 120 words. "
               "Honor every point the user made. Add nothing substantive they didn't say. No fluff. "
               + sign_rule
               + "Output STRICT JSON: {\"subject\": string, \"body\": string}.")
        user_msg = (f"Client: {inv.get('counterparty_name') or inv.get('counterparty_email')}\n"
                    f"Invoice: {inv.get('invoice_ref') or 'n/a'} · {inv.get('amount')} {inv.get('currency','USD')}\n"
                    f"Sign emails as: {signer_name or 'n/a'}\n"
                    f"User rough intent: {payload.intent}")
        api_key = os.environ.get("OPENROUTER_API_KEY")
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"},
                             json={"model": OPENROUTER_MODEL, "messages":[{"role":"system","content":sys},{"role":"user","content":user_msg}],
                                   "temperature":0.4, "response_format":{"type":"json_object"}, "max_tokens":400})
            content = r.json()["choices"][0]["message"]["content"]
            draft = json.loads(content)
        return {"subject": draft.get("subject",""), "body": draft.get("body",""),
                "to": inv.get("counterparty_email"), "invoice_id": payload.invoice_id}

    # ---- Escalation ladder scheduler (Feature 9b) ------------------------
    @router.post("/invoices/manual")
    async def create_manual_invoice(payload: ManualInvoiceInput, user: dict = Depends(get_current_user)):
        """Add an invoice by hand — for things the scan missed or off-Gmail contracts."""
        cp_email = payload.counterparty_email.strip().lower()
        if "@" not in cp_email:
            raise HTTPException(status_code=400, detail="Client email must include an @.")
        # Guardrail: can't invoice yourself
        conn = await db.gmail_connections.find_one({"user_id": user["_id"]})
        my_email = ((conn or {}).get("email") or "").lower()
        if my_email and cp_email == my_email:
            raise HTTPException(status_code=400, detail="You can't invoice your own connected Gmail address.")

        now_iso = datetime.now(timezone.utc).isoformat()
        today = datetime.now(timezone.utc).date()
        status = "invoiced"
        # If the due date is already past today, start it as overdue so it
        # surfaces in the Today card immediately.
        if payload.due_date:
            try:
                d = datetime.strptime(payload.due_date[:10], "%Y-%m-%d").date()
                if d < today:
                    status = "overdue"
            except Exception:
                pass
        if payload.promise_date:
            status = "promised"

        doc = {
            "user_id": user["_id"],
            "counterparty_email": cp_email,
            "counterparty_name": payload.counterparty_name or None,
            "amount": float(payload.amount),
            "balance_remaining": float(payload.amount),
            "paid_amount": 0.0,
            "currency": (payload.currency or "USD").upper(),
            "invoice_ref": payload.invoice_ref or None,
            "due_date": payload.due_date or None,
            "promise_date": payload.promise_date or None,
            "status": status,
            "kind": "invoice_sent",
            "source": "manual",              # tag so we know this didn't come from Gmail
            "manual_note": payload.note or None,
            "evidence_sentence": payload.note or "Manually added",
            "confidence": 1.0,
            "created_at": now_iso,
            "last_activity_at": now_iso,
        }
        res = await db.invoices.insert_one(doc)
        doc["_id"] = res.inserted_id
        await db.invoice_events.insert_one({
            "user_id": user["_id"], "invoice_id": res.inserted_id,
            "action": "manual_add", "at": now_iso,
            "meta": {"amount": float(payload.amount), "currency": doc["currency"],
                     "counterparty_email": cp_email},
        })
        return {"ok": True, "invoice": _serialize(doc)}

    @router.post("/escalation/run")
    async def escalation_run(user: dict = Depends(get_current_user)):
        from feature_flags import chasing_timing_enabled
        if not chasing_timing_enabled():
            return {"ok": True, "disabled": True, "drafts_generated": 0}
        counts = await run_escalation_tick(db, user["_id"])
        return {"ok": True, **counts}

    @router.get("/chase-drafts")
    async def list_chase_drafts(status: str = "queued", user: dict = Depends(get_current_user)):
        query = {"user_id": user["_id"]}
        if status and status != "all":
            query["status"] = status
        cursor = db.chase_drafts.find(query).sort("generated_at", -1)
        rows = []
        async for doc in cursor:
            rows.append(_serialize(doc))
        return {"drafts": rows, "count": len(rows)}

    @router.patch("/chase-drafts/{draft_id}")
    async def patch_chase_draft(draft_id: str, payload: ChaseDraftPatch, user: dict = Depends(get_current_user)):
        patch = payload.model_dump(exclude_none=True)
        if not patch:
            raise HTTPException(status_code=400, detail="No changes provided.")
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            res = await db.chase_drafts.update_one(
                {"_id": ObjectId(draft_id), "user_id": user["_id"], "status": "queued"},
                {"$set": patch},
            )
        except Exception:
            raise HTTPException(status_code=404, detail="Draft not found")
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Draft not found or not queued")
        return {"ok": True}

    @router.post("/chase-drafts/{draft_id}/dismiss")
    async def dismiss_chase_draft(draft_id: str, user: dict = Depends(get_current_user)):
        try:
            res = await db.chase_drafts.update_one(
                {"_id": ObjectId(draft_id), "user_id": user["_id"], "status": "queued"},
                {"$set": {"status": "dismissed", "dismissed_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            raise HTTPException(status_code=404, detail="Draft not found")
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="Draft not found or already actioned")
        draft = await db.chase_drafts.find_one({"_id": ObjectId(draft_id)})
        if draft and draft.get("invoice_id"):
            await ack_followup_prompts(db, user["_id"], [str(draft["invoice_id"])])
        return {"ok": True}

    @router.post("/chase-drafts/{draft_id}/regenerate")
    async def regenerate_chase_draft(draft_id: str, user: dict = Depends(get_current_user)):
        try:
            draft = await db.chase_drafts.find_one({"_id": ObjectId(draft_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Draft not found")
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        inv = await db.invoices.find_one({"_id": draft.get("invoice_id"), "user_id": user["_id"]})
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice missing")
        settings = await db.user_settings.find_one({"user_id": user["_id"]}) or {}
        late_fee_text = settings.get("late_fee_text") if settings.get("late_fee_enabled") else None
        signer_name = await ensure_gmail_account_name(db, user["_id"])
        new_draft = await _gen_escalation_draft(
            inv,
            draft.get("tone") or "friendly",
            draft.get("step_label") or "step",
            late_fee_text,
            signer_name=signer_name,
        )
        if not new_draft:
            raise HTTPException(status_code=502, detail="AI draft failed")
        await db.chase_drafts.update_one(
            {"_id": draft["_id"]},
            {"$set": {"subject": new_draft.get("subject", ""),
                      "body": new_draft.get("body", ""),
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True, "subject": new_draft.get("subject", ""), "body": new_draft.get("body", "")}

    @router.post("/chase-drafts/{draft_id}/send")
    async def send_chase_draft(draft_id: str, user: dict = Depends(get_current_user)):
        """Send a queued draft via the user's Gmail. Marks the draft as sent."""
        from gmail_client import get_access_token, send_gmail_reply
        try:
            draft = await db.chase_drafts.find_one({"_id": ObjectId(draft_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Draft not found")
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        if draft.get("status") != "queued":
            raise HTTPException(status_code=400, detail="Draft is not queued for send.")
        conn = await db.gmail_connections.find_one({"user_id": user["_id"]})
        if not conn or not conn.get("can_send"):
            raise HTTPException(status_code=400, detail="Gmail send scope missing. Reconnect Gmail.")
        access = await get_access_token(db, user["_id"])
        to_addr = draft.get("to")
        from_addr = conn.get("email")
        inv = None
        if draft.get("invoice_id"):
            inv = await db.invoices.find_one({"_id": draft["invoice_id"], "user_id": user["_id"]})
        try:
            sent = await send_gmail_reply(
                access,
                from_addr=from_addr,
                to_addr=to_addr,
                subject=draft.get("subject", ""),
                body=draft.get("body", ""),
                thread_id=draft.get("thread_id") or (inv or {}).get("source_thread_id"),
                reply_to_message_id=(inv or {}).get("source_message_id"),
            )
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.chase_drafts.update_one(
            {"_id": draft["_id"]}, {"$set": {"status": "sent", "sent_at": now_iso}}
        )
        await db.chase_sends.insert_one({
            "user_id": user["_id"], "invoice_id": draft.get("invoice_id"),
            "to": to_addr,
            "subject": sent.get("subject") or draft.get("subject", ""),
            "body": draft.get("body", ""),
            "sent_at": now_iso, "chase_draft_id": draft["_id"],
            "gmail_thread_id": sent.get("thread_id"),
        })
        step_index = draft.get("step_index")
        if step_index is not None:
            try:
                step_index = int(step_index)
            except (TypeError, ValueError):
                step_index = None
        await mark_chase_sent(
            db, user["_id"], draft.get("invoice_id"),
            step_index=step_index, now_iso=now_iso,
        )
        await db.invoices.update_one(
            {"_id": draft.get("invoice_id"), "user_id": user["_id"]},
            {"$inc": {"chase_count": 1}},
        )
        await ack_followup_prompts(db, user["_id"], [str(draft.get("invoice_id"))])
        reeval = {}
        if inv:
            try:
                from incremental_sync import reeval_after_user_outbound_send
                reeval = await reeval_after_user_outbound_send(
                    db, user["_id"], inv,
                    access=access,
                    my_email=from_addr or "",
                    subject=sent.get("subject") or draft.get("subject", ""),
                    body=draft.get("body", ""),
                    gmail_message_id=sent.get("gmail_message_id"),
                    thread_id=sent.get("thread_id")
                        or draft.get("thread_id")
                        or inv.get("source_thread_id"),
                )
            except Exception:
                logger.exception("post-send reeval failed draft=%s", draft_id)
                reeval = {"skipped": "error"}
        return {"ok": True, "sent_at": now_iso, "reeval": reeval}

    # ---- Daily digest (Feature 9c) ---------------------------------------
    @router.post("/digest/send-now")
    async def digest_send_now(user: dict = Depends(get_current_user)):
        res = await send_digest_for_user(db, user["_id"], force=True)
        return res

    @router.get("/digest/preview")
    async def digest_preview(user: dict = Depends(get_current_user)):
        sections = await collect_today_sections(db, user["_id"])
        totals = _digest_totals(sections)
        # Serialize enough for the frontend to show a preview
        def _row(inv):
            return {
                "counterparty_name": inv.get("counterparty_name"),
                "counterparty_email": inv.get("counterparty_email"),
                "amount": inv.get("balance_remaining") or inv.get("amount"),
                "currency": inv.get("currency", "USD"),
                "invoice_ref": inv.get("invoice_ref"),
                "due_date": inv.get("due_date"),
                "promise_date": inv.get("promise_date"),
                "status": inv.get("status"),
            }
        return {
            "subject": build_digest_email(user, sections, totals)["subject"],
            "totals": totals,
            "sections": {k: [_row(i) for i in v] for k, v in sections.items()},
        }

    @router.get("/digest/last")
    async def digest_last(user: dict = Depends(get_current_user)):
        settings = await db.user_settings.find_one({"user_id": user["_id"]}) or {}
        return {
            "last_digest_sent_at": settings.get("last_digest_sent_at"),
            "last_digest_status": settings.get("last_digest_status"),
            "last_digest_counts": settings.get("last_digest_counts"),
        }

    return router
