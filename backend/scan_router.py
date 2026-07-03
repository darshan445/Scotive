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

    # ---- Chase drafts (Feature 7) ----------------------------------------
    class ChaseDraftInput(BaseModel):
        tone: str | None = None  # friendly | firm | final
        note: str | None = None

    class ChaseSendInput(BaseModel):
        subject: str
        body: str

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

    class QuickComposeInput(BaseModel):
        invoice_id: str
        intent: str

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

    return router
