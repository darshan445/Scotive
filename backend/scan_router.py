"""Scan + ledger endpoints."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from scan_pipeline import run_historical_scan


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

        months = (payload.months if payload else 12) or 12
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

    @router.get("/ledger")
    async def get_ledger(user: dict = Depends(get_current_user)):
        cursor = db.invoices.find({"user_id": user["_id"]}).sort("created_at", -1)
        rows = []
        total_open = 0.0
        clients: set[str] = set()
        async for doc in cursor:
            rows.append(_serialize(doc))
            if doc.get("status") in ("invoiced", "overdue", "promised", "partially_paid", "promise_broken"):
                total_open += float(doc.get("amount") or 0)
                if doc.get("counterparty_email"):
                    clients.add(doc["counterparty_email"])
        return {"invoices": rows, "total_open": round(total_open, 2), "client_count": len(clients)}

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
                        {"$in": ["$status", ["invoiced", "overdue", "promised", "partially_paid", "promise_broken"]]},
                        "$amount",
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
            invoices.append(_serialize(doc))
            ident = doc.get("counterparty_email")
            if ident:
                identities[ident] = identities.get(ident, 0) + 1
            if not primary_name and doc.get("counterparty_name"):
                primary_name = doc["counterparty_name"]
            if doc.get("status") in ("invoiced", "overdue", "promised", "partially_paid", "promise_broken"):
                total_open += float(doc.get("amount") or 0)
        if not invoices:
            raise HTTPException(status_code=404, detail="Client not found")
        return {
            "email": email,
            "name": primary_name,
            "identities": [{"email": e, "message_count": n} for e, n in sorted(identities.items(), key=lambda x: -x[1])],
            "invoices": invoices,
            "total_open": round(total_open, 2),
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
    class InvoiceActionInput(BaseModel):
        action: str  # mark_paid | write_off | dispute | resolve_dispute | pause | resume

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
        patch: dict = {"status_updated_at": now}
        if action == "mark_paid":
            patch["status"] = "paid"
            patch["paid_at"] = now
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
        })
        return {"ok": True}

    @router.post("/lifecycle/run")
    async def run_lifecycle(user: dict = Depends(get_current_user)):
        """Recompute date-driven transitions: overdue + promise_broken."""
        today = datetime.now(timezone.utc).date()
        grace_days = 1
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

    return router
