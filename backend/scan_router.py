"""Scan + ledger endpoints."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from scan_pipeline import run_historical_scan, reconcile_receipts, run_incremental_sync
from escalation_scheduler import run_escalation_tick, generate_draft as _gen_escalation_draft
from digest_sender import send_digest_for_user, build_digest_email, collect_today_sections, _totals as _digest_totals

logger = logging.getLogger("scotive.scan_router")


class StartScanInput(BaseModel):
    months: int = 12


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
    action: str  # mark_paid | write_off | dispute | resolve_dispute | pause | resume | undo


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
        else:
            out[k] = v
    if "_id" in out and not isinstance(out["_id"], str):
        out["_id"] = str(out["_id"])
    return out


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

    @router.post("/scan/start")
    async def start_scan(payload: StartScanInput | None = None, user: dict = Depends(get_current_user)):
        conn = await db.gmail_connections.find_one({"user_id": user["_id"]})
        if not conn or conn.get("status") == "revoked":
            raise HTTPException(status_code=400, detail="Connect Gmail before starting a scan.")
        # If a scan is already running, return it instead of starting a new one
        existing = await db.scan_jobs.find_one(
            {"user_id": user["_id"], "status": {"$in": ["queued", "running"]}}
        )
        if existing:
            return {"job_id": str(existing["_id"]), "status": existing.get("status")}

        # If caller didn't supply months, fall back to user_settings.scan_window_months, else 12
        default_months = 12
        try:
            s = await db.user_settings.find_one({"user_id": user["_id"]})
            if s and isinstance(s.get("scan_window_months"), int):
                default_months = s["scan_window_months"]
        except Exception:
            pass
        months = (payload.months if payload else default_months) or default_months
        doc = {
            "user_id": user["_id"],
            "status": "queued",
            "phase": "queued",
            "months": months,
            "counts": {"fetched": 0, "filtered_in": 0, "ai_extracted": 0, "invoices_created": 0},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        res = await db.scan_jobs.insert_one(doc)
        job_id = res.inserted_id
        # Fire and forget
        asyncio.create_task(run_historical_scan(db, user["_id"], job_id, months=months))
        return {"job_id": str(job_id), "status": "queued"}

    @router.get("/scan/status")
    async def scan_status(user: dict = Depends(get_current_user)):
        job = await db.scan_jobs.find_one(
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
            "months": job.get("months", 12),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "error": job.get("error"),
        }

    @router.post("/scan/sync")
    async def scan_sync(user: dict = Depends(get_current_user)):
        """Manually trigger one incremental sync tick for the current user."""
        try:
            counts = await run_incremental_sync(db, user["_id"])
        except Exception as e:
            logger.exception("Manual sync failed: %s", e)
            raise HTTPException(status_code=500, detail="Sync failed. Check backend logs.")
        state = await db.gmail_sync_state.find_one({"user_id": user["_id"]})
        last_synced_at = (state or {}).get("last_synced_at")
        return {"ok": True, "counts": counts, "last_synced_at": last_synced_at}

    @router.get("/scan/sync-state")
    async def scan_sync_state(user: dict = Depends(get_current_user)):
        state = await db.gmail_sync_state.find_one({"user_id": user["_id"]}) or {}
        state.pop("_id", None)
        state.pop("user_id", None)
        return state

    @router.get("/ledger")
    async def get_ledger(user: dict = Depends(get_current_user)):
        cursor = db.invoices.find({"user_id": user["_id"]}).sort("created_at", -1)
        rows = []
        total_open = 0.0
        clients: set[str] = set()
        async for doc in cursor:
            # For legacy rows that don't carry balance_remaining, fall back to amount.
            if doc.get("balance_remaining") is None:
                doc["balance_remaining"] = float(doc.get("amount") or 0)
            rows.append(_serialize(doc))
            if doc.get("status") in _OPEN_STATUSES:
                total_open += float(doc.get("balance_remaining") or doc.get("amount") or 0)
                if doc.get("counterparty_email"):
                    clients.add(doc["counterparty_email"])
        return {"invoices": rows, "total_open": round(total_open, 2), "client_count": len(clients)}

    # ---- Receipts --------------------------------------------------------
    @router.get("/receipts")
    async def list_receipts(status: str | None = None, user: dict = Depends(get_current_user)):
        query: dict = {"user_id": user["_id"]}
        if status:
            query["match_status"] = status
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
        new_status = "paid" if new_balance <= 0.005 else "partially_paid"
        await db.invoices.update_one(
            {"_id": inv["_id"]},
            {"$set": {
                "status": new_status,
                "balance_remaining": max(new_balance, 0.0),
                "paid_amount": new_paid,
                "paid_at": now_iso if new_status == "paid" else inv.get("paid_at"),
                "status_updated_at": now_iso,
            }},
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

    @router.get("/invoices/{invoice_id}/timeline")
    async def invoice_timeline(invoice_id: str, user: dict = Depends(get_current_user)):
        try:
            inv = await db.invoices.find_one({"_id": ObjectId(invoice_id), "user_id": user["_id"]})
        except Exception:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found")
        events = []
        # Origin event
        events.append({
            "kind": inv.get("kind") or "invoice_sent",
            "date": inv.get("source_date") or inv.get("created_at"),
            "quote": inv.get("evidence_sentence"),
            "subject": inv.get("source_subject"),
            "from": inv.get("source_from"),
            "message_id": inv.get("source_message_id"),
            "thread_id": inv.get("source_thread_id"),
        })
        # Any other invoices from same counterparty in the same thread as additional evidence
        if inv.get("source_thread_id"):
            related = db.invoices.find({
                "user_id": user["_id"],
                "source_thread_id": inv["source_thread_id"],
                "_id": {"$ne": inv["_id"]},
            })
            async for r in related:
                events.append({
                    "kind": r.get("kind"),
                    "date": r.get("source_date") or r.get("created_at"),
                    "quote": r.get("evidence_sentence"),
                    "subject": r.get("source_subject"),
                    "from": r.get("source_from"),
                    "message_id": r.get("source_message_id"),
                    "thread_id": r.get("source_thread_id"),
                })
        # Receipt matches applied to this invoice
        async for rc in db.receipts.find({"user_id": user["_id"], "matched_invoice_id": inv["_id"]}):
            events.append({
                "kind": "receipt",
                "date": rc.get("source_date") or rc.get("created_at"),
                "quote": rc.get("evidence_sentence"),
                "subject": rc.get("source_subject"),
                "from": rc.get("processor_from"),
                "message_id": rc.get("source_message_id"),
                "thread_id": rc.get("source_thread_id"),
                "amount": rc.get("applied_amount") or rc.get("amount"),
                "payer_name": rc.get("payer_name"),
            })
        # Recorded invoice_events (mark_paid, receipt_matched, etc.)
        async for ev in db.invoice_events.find({"user_id": user["_id"], "invoice_id": inv["_id"]}):
            events.append({
                "kind": ev.get("action"),
                "date": ev.get("at"),
                "meta": ev.get("meta") or {},
            })
        events.sort(key=lambda e: str(e.get("date") or ""))
        return {"invoice": _serialize(inv), "events": events}

    # ---- Clients ---------------------------------------------------------
    @router.get("/clients")
    async def list_clients(user: dict = Depends(get_current_user)):
        pipeline = [
            {"$match": {"user_id": user["_id"]}},
            {"$group": {
                "_id": "$counterparty_email",
                "name": {"$first": "$counterparty_name"},
                "invoice_count": {"$sum": 1},
                "open_amount": {"$sum": {
                    "$cond": [
                        {"$in": ["$status", list(_OPEN_STATUSES)]},
                        {"$ifNull": ["$balance_remaining", "$amount"]},
                        0,
                    ]
                }},
                "last_activity": {"$max": "$created_at"},
            }},
            {"$sort": {"open_amount": -1}},
        ]
        rows = []
        async for c in db.invoices.aggregate(pipeline):
            rows.append({
                "email": c["_id"],
                "name": c.get("name"),
                "invoice_count": c.get("invoice_count", 0),
                "open_amount": round(float(c.get("open_amount") or 0), 2),
                "last_activity": c.get("last_activity"),
            })
        return {"clients": rows}

    @router.get("/clients/{email}")
    async def client_detail(email: str, user: dict = Depends(get_current_user)):
        email = email.lower()
        # Auto-link same-domain identities
        domain = email.split("@")[-1] if "@" in email else ""
        query = {"user_id": user["_id"]}
        if domain:
            query["counterparty_email"] = {"$regex": f"@{domain}$", "$options": "i"}
        else:
            query["counterparty_email"] = email
        cursor = db.invoices.find(query).sort("created_at", -1)
        invoices = []
        identities: dict[str, int] = {}
        total_open = 0.0
        primary_name = None
        async for doc in cursor:
            if doc.get("balance_remaining") is None:
                doc["balance_remaining"] = float(doc.get("amount") or 0)
            invoices.append(_serialize(doc))
            ident = doc.get("counterparty_email")
            if ident:
                identities[ident] = identities.get(ident, 0) + 1
            if not primary_name and doc.get("counterparty_name"):
                primary_name = doc["counterparty_name"]
            if doc.get("status") in _OPEN_STATUSES:
                total_open += float(doc.get("balance_remaining") or doc.get("amount") or 0)
        if not invoices:
            raise HTTPException(status_code=404, detail="Client not found")

        stats = _compute_client_stats(invoices)

        return {
            "email": email,
            "name": primary_name,
            "identities": [{"email": e, "message_count": n} for e, n in sorted(identities.items(), key=lambda x: -x[1])],
            "invoices": invoices,
            "total_open": round(total_open, 2),
            "stats": stats,  # None when payment_cycles < 2
        }

    # ---- Review queue -----------------------------------------------------
    @router.get("/review-queue")
    async def list_review(user: dict = Depends(get_current_user)):
        cursor = db.review_items.find({"user_id": user["_id"], "review_status": "pending"}).sort("created_at", -1)
        items = []
        async for doc in cursor:
            items.append(_serialize(doc))
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
        elif action == "write_off":
            patch["status"] = "written_off"
        elif action == "dispute":
            patch["status"] = "disputed"
        elif action == "resolve_dispute":
            patch["status"] = "invoiced"
        elif action == "pause":
            patch["chasing_paused"] = True
        elif action == "resume":
            patch["chasing_paused"] = False
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
        """Recompute date-driven transitions: overdue + promise_broken."""
        today = datetime.now(timezone.utc).date()
        settings_doc = await db.user_settings.find_one({"user_id": user["_id"]}) or {}
        grace_days = int(settings_doc.get("grace_days", 1))
        overdue_updates = 0
        broken_updates = 0
        # Invoiced -> Overdue
        async for inv in db.invoices.find({"user_id": user["_id"], "status": "invoiced", "due_date": {"$ne": None}}):
            try:
                due = datetime.fromisoformat(inv["due_date"]).date()
            except Exception:
                continue
            if (today - due).days > grace_days:
                await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"status": "overdue"}})
                overdue_updates += 1
        # Promised -> Promise broken
        async for inv in db.invoices.find({"user_id": user["_id"], "status": "promised", "promise_date": {"$ne": None}}):
            try:
                pd = datetime.fromisoformat(inv["promise_date"]).date()
            except Exception:
                continue
            if (today - pd).days > grace_days:
                await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"status": "promise_broken"}})
                broken_updates += 1
        return {"ok": True, "overdue": overdue_updates, "promise_broken": broken_updates}

    # ---- Today digest ----------------------------------------------------
    @router.get("/digest/today")
    async def digest_today(user: dict = Depends(get_current_user)):
        today = datetime.now(timezone.utc).date()
        due_overdue = []
        broken = []
        needs_reply = []  # placeholder — populated when sync detects unanswered questions
        resolved = []
        async for inv in db.invoices.find({"user_id": user["_id"]}):
            s = inv.get("status")
            row = _serialize(inv)
            if s in ("overdue",):
                due_overdue.append(row)
            elif s == "invoiced" and inv.get("due_date"):
                try:
                    due = datetime.fromisoformat(inv["due_date"]).date()
                    if due <= today:
                        due_overdue.append(row)
                except Exception:
                    pass
            elif s == "promise_broken":
                broken.append(row)
            elif s == "disputed":
                needs_reply.append(row)
            elif s == "paid":
                paid_at = inv.get("paid_at")
                try:
                    d = datetime.fromisoformat(paid_at).date() if paid_at else None
                    if d and (today - d).days <= 1:
                        resolved.append(row)
                except Exception:
                    pass
        return {
            "due_overdue": due_overdue,
            "broken_promises": broken,
            "needs_reply": needs_reply,
            "resolved": resolved,
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
        sys = (
            "You draft short, professional payment follow-up emails for a small business owner. "
            "Under 120 words. Plain professional tone. No 'hope this finds you well'. "
            "Always include invoice ref (if any), amount, due date. On a broken promise, quote the client's own stated date verbatim. "
            "Never sound templated or AI-written. Output STRICT JSON: {\"subject\": string, \"body\": string}."
        )
        user_msg = (
            f"Client: {inv.get('counterparty_name') or inv.get('counterparty_email')}\n"
            f"Invoice ref: {inv.get('invoice_ref') or 'n/a'}\n"
            f"Amount: {inv.get('amount')} {inv.get('currency','USD')}\n"
            f"Due date: {inv.get('due_date') or 'n/a'}\n"
            f"Promise date: {inv.get('promise_date') or 'n/a'}\n"
            f"Status: {inv.get('status')}\n"
            f"Tone: {tone}\n"
            f"Client's own words (if broken promise): {inv.get('evidence_sentence') or ''}\n"
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
        from gmail_client import get_access_token
        import httpx, base64
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
        raw = f"From: {from_addr}\r\nTo: {to_addr}\r\nSubject: {payload.subject}\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n{payload.body}"
        encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")
        body = {"raw": encoded}
        if inv.get("source_thread_id"):
            body["threadId"] = inv["source_thread_id"]
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                             headers={"Authorization": f"Bearer {access}", "Content-Type":"application/json"}, json=body)
            if r.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Gmail send failed: {r.text[:200]}")
        await db.chase_sends.insert_one({
            "user_id": user["_id"], "invoice_id": inv["_id"], "to": to_addr, "subject": payload.subject,
            "body": payload.body, "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.invoices.update_one({"_id": inv["_id"]}, {"$set": {"last_chase_at": datetime.now(timezone.utc).isoformat()}, "$inc": {"chase_count": 1}})
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
        from gmail_client import get_access_token
        import base64
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
        raw = (
            f"From: {from_addr}\r\n"
            f"To: {to_addr}\r\n"
            f"Subject: {draft.get('subject','')}\r\n"
            f"Content-Type: text/plain; charset=UTF-8\r\n\r\n"
            f"{draft.get('body','')}"
        )
        encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")
        body = {"raw": encoded}
        if draft.get("thread_id"):
            body["threadId"] = draft["thread_id"]
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
                json=body,
            )
            if r.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"Gmail send failed: {r.text[:200]}")
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.chase_drafts.update_one(
            {"_id": draft["_id"]}, {"$set": {"status": "sent", "sent_at": now_iso}}
        )
        await db.chase_sends.insert_one({
            "user_id": user["_id"], "invoice_id": draft.get("invoice_id"),
            "to": to_addr, "subject": draft.get("subject", ""), "body": draft.get("body", ""),
            "sent_at": now_iso, "chase_draft_id": draft["_id"],
        })
        await db.invoices.update_one(
            {"_id": draft.get("invoice_id"), "user_id": user["_id"]},
            {"$set": {"last_chase_at": now_iso}, "$inc": {"chase_count": 1}},
        )
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
