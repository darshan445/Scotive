"""Public contact form — stores inbound messages for admin review."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger("scotive.contact")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_PER_EMAIL_PER_DAY = 5
MAX_PER_IP_PER_HOUR = 10


class ContactSubmit(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    message: str = Field(..., min_length=1, max_length=5000)
    company: Optional[str] = Field(None, max_length=200)
    # Honeypot — bots fill this; humans leave it empty.
    website: Optional[str] = Field(None, max_length=200)


def build_router(db):
    router = APIRouter(prefix="/contact", tags=["contact"])

    @router.post("")
    async def submit_contact(payload: ContactSubmit, request: Request):
        # Honeypot trip → pretend success so bots don't retry smarter.
        if (payload.website or "").strip():
            return {"ok": True}

        name = (payload.name or "").strip()
        email = str(payload.email or "").strip().lower()
        message = (payload.message or "").strip()
        company = (payload.company or "").strip() or None

        if not name or not message:
            raise HTTPException(status_code=400, detail="Name and message are required.")
        if not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Enter a valid email address.")

        client_ip = None
        if request.client:
            client_ip = request.client.host
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip() or client_ip

        now = datetime.now(timezone.utc)
        day_ago = (now - timedelta(days=1)).isoformat()
        hour_ago = (now - timedelta(hours=1)).isoformat()

        email_count = await db.contact_messages.count_documents(
            {"email": email, "created_at": {"$gte": day_ago}}
        )
        if email_count >= MAX_PER_EMAIL_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail="Too many messages from this email today. Email us at contact@scotive.com instead.",
            )

        if client_ip:
            ip_count = await db.contact_messages.count_documents(
                {"ip": client_ip, "created_at": {"$gte": hour_ago}}
            )
            if ip_count >= MAX_PER_IP_PER_HOUR:
                raise HTTPException(
                    status_code=429,
                    detail="Too many messages right now. Email us at contact@scotive.com instead.",
                )

        doc = {
            "name": name,
            "email": email,
            "company": company,
            "message": message,
            "ip": client_ip,
            "user_agent": (request.headers.get("user-agent") or "")[:400],
            "status": "new",
            "created_at": now.isoformat(),
        }
        result = await db.contact_messages.insert_one(doc)
        logger.info(
            "contact.submit id=%s email=%s name=%s",
            result.inserted_id,
            email,
            name[:40],
        )
        return {"ok": True}

    return router
