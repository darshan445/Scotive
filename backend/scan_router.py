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
    get_onboarding_state,
    list_seed_candidates,
    run_seed_scan,
)
from ledger_reconcile import (
    INVOICE_MONGO_SORT,
    REVIEW_MONGO_SORT,
    client_identity_key,
    compute_open_totals,
    enrich_invoice_doc,
    normalize_source_date,
    sort_by_email_date,
    sort_by_due_promise_date,
)
from escalation_scheduler import run_escalation_tick, generate_draft as _gen_escalation_draft
from digest_sender import send_digest_for_user, build_digest_email, collect_today_sections, _totals as _digest_totals
from invoice_lifecycle import apply_stale_transitions, clear_stale_fields
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


_OPEN_STATUSES = ("invoiced", "overdue", "promised", "partially_paid", "promise_broken")


class InvoiceActionInput(BaseModel):
    action: str  # mark_paid | write_off | dispute | resolve_dispute | pause | resume | undo | dismiss_stale | set_due_date | skip_due_date
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
                "open_by_currency": {"$push": {
                    "$cond": [
                        {"$in": ["$status", list(_OPEN_STATUSES)]},
                        {
                            "currency": {"$ifNull": ["$currency", "USD"]},
                            "amount": {"$ifNull": ["$balance_remaining", "$amount"]},
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
            for item in c.get("open_by_currency") or []:
                if not item:
                    continue
                cur = (item.get("currency") or "USD").upper()
                totals[cur] = round(totals.get(cur, 0) + float(item.get("amount") or 0), 2)
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
        }

        patch: dict = {"status_updated_at": now}
        if action == "mark_paid":
            patch["status"] = "paid"
            patch["paid_at"] = now
            patch["balance_remaining"] = 0.0
            patch["paid_amount"] = float(inv.get("amount") or 0)
            patch["payment_claim_quote"] = None
            patch["status_before_claim"] = None
            patch["claim_balance_before"] = None
            patch["claim_paid_before"] = None
            patch["chasing_paused"] = False
            patch["watching_for_reply"] = False
            patch["ladder_exhausted"] = False
            clear_stale_fields(patch)
            patch["last_activity_at"] = now
            await ack_followup_prompts(db, user["_id"], [invoice_id])
        elif action == "deny_payment_claim":
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
            patch["payment_claim_quote"] = None
            patch["status_before_claim"] = None
            if inv.get("claim_balance_before") is not None:
                patch["balance_remaining"] = float(inv["claim_balance_before"])
                patch["paid_amount"] = float(inv.get("claim_paid_before") or 0)
                patch["claim_balance_before"] = None
                patch["claim_paid_before"] = None
        elif action == "write_off":
            patch["status"] = "written_off"
            patch["watching_for_reply"] = False
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
            patch["chasing_paused"] = True
            await ack_followup_prompts(db, user["_id"], [invoice_id])
        elif action == "resume":
            patch["chasing_paused"] = False
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
        return {"ok": True}

    @router.post("/lifecycle/run")
    async def run_lifecycle(user: dict = Depends(get_current_user)):
        """Recompute stale transitions and merge prompts (past-due runs on hourly sync)."""
        stale_updates = await apply_stale_transitions(db, user["_id"])
        merge_prompts = await detect_cross_domain_merge_prompts(db, user["_id"])
        return {
            "ok": True,
            "stale": stale_updates,
            "merge_prompts": merge_prompts,
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
            s = inv.get("status")
            row = _serialize(inv)
            if s == "paid_unconfirmed":
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
    def _tone_for(inv: dict) -> str:
        s = inv.get("status")
        if s == "promise_broken": return "firm"
        if s == "overdue": return "firm"
        return "friendly"

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
        tone = payload.tone or _tone_for(inv)
        thread_subject = inv.get("source_subject") or ""
        is_dispute = inv.get("status") == "disputed"
        dispute_quote = None
        if is_dispute:
            ev = await db.invoice_events.find_one(
                {"user_id": user["_id"], "invoice_id": inv["_id"], "action": "dispute"},
                sort=[("at", -1)],
            )
            dispute_quote = ((ev or {}).get("meta") or {}).get("quote")
        sys = (
            "You draft short, professional payment follow-up emails for a small business owner. "
            "Under 120 words. Plain professional tone. No 'hope this finds you well'. "
            "Always include invoice ref (if any), amount, due date. On a broken promise, quote the client's own stated date verbatim. "
            + (
                "The client has DISPUTED this invoice — do not demand payment. Acknowledge their concern, "
                "reference what they said, and propose resolving it (a quick call or clarification). "
                if is_dispute
                else ""
            )
            + "Never sound templated or AI-written. "
            "This is a REPLY in an existing email thread — subject must be 'Re: <original subject>' matching the thread. "
            "Output STRICT JSON: {\"subject\": string, \"body\": string}."
        )
        user_msg = (
            f"Client: {inv.get('counterparty_name') or inv.get('counterparty_email')}\n"
            f"Original thread subject: {thread_subject or 'n/a'}\n"
            f"Invoice ref: {inv.get('invoice_ref') or 'n/a'}\n"
            f"Amount: {inv.get('amount')} {inv.get('currency','USD')}\n"
            f"Due date: {inv.get('due_date') or 'n/a'}\n"
            f"Promise date: {inv.get('promise_date') or 'n/a'}\n"
            f"Status: {inv.get('status')}\n"
            f"Tone: {tone}\n"
            f"Client's own words (broken promise or dispute): {dispute_quote or inv.get('evidence_sentence') or ''}\n"
            f"User extra note: {payload.note or ''}"
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
        return {"subject": draft.get("subject",""), "body": draft.get("body",""), "tone": tone,
                "to": inv.get("counterparty_email"), "thread_id": inv.get("source_thread_id"),
                "invoice_id": str(inv["_id"])}

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
        return {"ok": True}

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
        sys = ("Expand the user's rough intent into a polished professional email under 120 words. "
               "Honor every point the user made. Add nothing substantive they didn't say. No fluff. "
               "Output STRICT JSON: {\"subject\": string, \"body\": string}.")
        user_msg = (f"Client: {inv.get('counterparty_name') or inv.get('counterparty_email')}\n"
                    f"Invoice: {inv.get('invoice_ref') or 'n/a'} · {inv.get('amount')} {inv.get('currency','USD')}\n"
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
        new_draft = await _gen_escalation_draft(inv, draft.get("tone") or "friendly",
                                                draft.get("step_label") or "step",
                                                late_fee_text)
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
        return {"ok": True, "sent_at": now_iso}

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
