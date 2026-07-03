"""User settings + suppressed senders + delete-account endpoints (F8d)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("scotive.settings")


DEFAULT_SETTINGS: dict = {
    "grace_days": 1,
    "escalation_offsets": [-3, 0, 3, 10],  # days relative to due date
    "late_fee_enabled": False,
    "late_fee_text": "",
    "scan_window_months": 12,
}


class SettingsPatch(BaseModel):
    grace_days: Optional[int] = Field(default=None, ge=0, le=30)
    escalation_offsets: Optional[list[int]] = None
    late_fee_enabled: Optional[bool] = None
    late_fee_text: Optional[str] = Field(default=None, max_length=280)
    scan_window_months: Optional[int] = Field(default=None, ge=1, le=36)

    @field_validator("escalation_offsets")
    @classmethod
    def _sorted_unique(cls, v):
        if v is None:
            return v
        if len(v) > 8:
            raise ValueError("Too many escalation steps (max 8).")
        for n in v:
            if not isinstance(n, int) or n < -30 or n > 90:
                raise ValueError("Each offset must be between -30 and 90 days.")
        return sorted(set(v))


class DeleteAccountInput(BaseModel):
    confirm_email: str


async def get_settings_doc(db, user_id) -> dict:
    doc = await db.user_settings.find_one({"user_id": user_id})
    if not doc:
        doc = {"user_id": user_id, **DEFAULT_SETTINGS,
               "created_at": datetime.now(timezone.utc).isoformat()}
        await db.user_settings.insert_one(doc)
    # Fill in any missing keys with defaults (forward compat)
    merged = {**DEFAULT_SETTINGS, **{k: v for k, v in doc.items() if k in DEFAULT_SETTINGS}}
    merged["user_id"] = user_id
    return merged


def build_router(db, get_current_user):
    router = APIRouter(tags=["settings"])

    @router.get("/settings")
    async def get_settings(user: dict = Depends(get_current_user)):
        s = await get_settings_doc(db, user["_id"])
        s.pop("user_id", None)
        return s

    @router.patch("/settings")
    async def patch_settings(payload: SettingsPatch, user: dict = Depends(get_current_user)):
        patch = payload.model_dump(exclude_none=True)
        if not patch:
            raise HTTPException(status_code=400, detail="No changes provided.")
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.user_settings.update_one(
            {"user_id": user["_id"]}, {"$set": patch}, upsert=True
        )
        s = await get_settings_doc(db, user["_id"])
        s.pop("user_id", None)
        return s

    @router.get("/suppressed-senders")
    async def list_suppressed(user: dict = Depends(get_current_user)):
        rows = []
        async for doc in db.suppressed_senders.find({"user_id": user["_id"]}).sort("created_at", -1):
            rows.append({
                "email": doc.get("email"),
                "created_at": doc.get("created_at"),
            })
        return {"senders": rows, "count": len(rows)}

    @router.delete("/suppressed-senders/{email}")
    async def unsuppress(email: str, user: dict = Depends(get_current_user)):
        res = await db.suppressed_senders.delete_one({
            "user_id": user["_id"], "email": email.lower(),
        })
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Sender not found in suppression list.")
        return {"ok": True}

    @router.delete("/account")
    async def delete_account(payload: DeleteAccountInput, response: Response, user: dict = Depends(get_current_user)):
        # Explicit email match confirmation — protects against accidental clicks.
        if (payload.confirm_email or "").strip().lower() != (user.get("email") or "").lower():
            raise HTTPException(status_code=400, detail="Email confirmation does not match.")
        uid = user["_id"]

        # Wipe every per-user collection we've built.
        for coll in (
            "invoices", "receipts", "invoice_events", "review_items",
            "suppressed_senders", "gmail_connections", "scan_jobs",
            "chase_sends", "user_settings", "login_attempts",
            "oauth_states", "password_reset_tokens",
        ):
            try:
                await db[coll].delete_many({"user_id": uid})
            except Exception as e:  # pragma: no cover
                logger.warning("Failed to purge %s for %s: %s", coll, uid, e)
        # And the user record itself.
        try:
            await db.users.delete_one({"_id": uid})
        except Exception as e:  # pragma: no cover
            logger.warning("Failed to delete user %s: %s", uid, e)

        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")
        return {"ok": True}

    return router
