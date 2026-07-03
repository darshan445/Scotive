"""Scan + ledger endpoints."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from scan_pipeline import run_historical_scan

logger = logging.getLogger("scotive.scan_router")


class StartScanInput(BaseModel):
    months: int = 12


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
            doc["_id"] = str(doc["_id"])
            doc["user_id"] = str(doc["user_id"]) if doc.get("user_id") else None
            rows.append(doc)
            if doc.get("status") in ("invoiced", "overdue", "promised", "partially_paid", "promise_broken"):
                total_open += float(doc.get("amount") or 0)
                if doc.get("counterparty_email"):
                    clients.add(doc["counterparty_email"])
        return {
            "invoices": rows,
            "total_open": round(total_open, 2),
            "client_count": len(clients),
        }

    return router
