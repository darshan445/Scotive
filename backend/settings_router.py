"""User settings + suppressed senders + delete-account endpoints (F8d)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from feature_flags import chasing_timing_enabled
from scan_settings import attach_scan_metadata

logger = logging.getLogger("scotive.settings")


DEFAULT_SETTINGS: dict = {
    "escalation_offsets": [-3, 0, 3, 10],  # days relative to due date
    "follow_up_interval_days": 3,
    "late_fee_enabled": False,
    "late_fee_text": "",
    "scan_window_months": 12,
    "daily_digest_enabled": True,
    "daily_digest_hour": 9,           # local hour in daily_digest_timezone
    "daily_digest_timezone": "UTC",   # IANA name
}

# Curated list surfaced to the UI. `Intl.supportedValuesOf('timeZone')` in the
# browser can return 400+; we deliberately keep this focused.
COMMON_TIMEZONES = [
    ("UTC", "UTC"),
    ("America/New_York", "US Eastern (New York)"),
    ("America/Chicago", "US Central (Chicago)"),
    ("America/Denver", "US Mountain (Denver)"),
    ("America/Phoenix", "US Arizona (no DST)"),
    ("America/Los_Angeles", "US Pacific (Los Angeles)"),
    ("America/Anchorage", "US Alaska"),
    ("America/Honolulu", "US Hawaii"),
    ("America/Toronto", "Canada Eastern (Toronto)"),
    ("America/Vancouver", "Canada Pacific (Vancouver)"),
    ("America/Mexico_City", "Mexico City"),
    ("America/Sao_Paulo", "São Paulo"),
    ("Europe/London", "UK (London)"),
    ("Europe/Dublin", "Ireland (Dublin)"),
    ("Europe/Paris", "Paris"),
    ("Europe/Berlin", "Berlin"),
    ("Europe/Amsterdam", "Amsterdam"),
    ("Europe/Madrid", "Madrid"),
    ("Europe/Rome", "Rome"),
    ("Europe/Stockholm", "Stockholm"),
    ("Europe/Warsaw", "Warsaw"),
    ("Europe/Athens", "Athens"),
    ("Europe/Istanbul", "Istanbul"),
    ("Asia/Dubai", "Dubai"),
    ("Asia/Kolkata", "India (Kolkata)"),
    ("Asia/Karachi", "Pakistan (Karachi)"),
    ("Asia/Bangkok", "Bangkok"),
    ("Asia/Singapore", "Singapore"),
    ("Asia/Hong_Kong", "Hong Kong"),
    ("Asia/Shanghai", "Shanghai"),
    ("Asia/Tokyo", "Tokyo"),
    ("Asia/Seoul", "Seoul"),
    ("Australia/Sydney", "Sydney"),
    ("Australia/Melbourne", "Melbourne"),
    ("Pacific/Auckland", "Auckland"),
]

_CURATED_TZ = {z for z, _ in COMMON_TIMEZONES}

# Browsers still return legacy IANA aliases (e.g. Asia/Calcutta). Map them onto
# the curated dropdown values so Settings Select isn't blank.
TIMEZONE_ALIASES = {
    "Asia/Calcutta": "Asia/Kolkata",
    "US/Eastern": "America/New_York",
    "US/Central": "America/Chicago",
    "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
    "US/Arizona": "America/Phoenix",
    "US/Hawaii": "America/Honolulu",
    "US/Alaska": "America/Anchorage",
    "Canada/Eastern": "America/Toronto",
    "Canada/Pacific": "America/Vancouver",
    "GMT": "UTC",
    "Etc/UTC": "UTC",
    "Etc/GMT": "UTC",
}


def _valid_iana_zone(name: str) -> bool:
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return True
    except Exception:
        return False


def resolve_timezone(name: str | None) -> str:
    """Return a curated IANA zone when possible, else a valid zone, else UTC.

    Prefer dropdown-listed names so Settings always has a matching Select value.
    """
    if not name or not isinstance(name, str):
        return DEFAULT_SETTINGS["daily_digest_timezone"]
    cleaned = name.strip()
    if not cleaned:
        return DEFAULT_SETTINGS["daily_digest_timezone"]
    cleaned = TIMEZONE_ALIASES.get(cleaned, cleaned)
    if cleaned in _CURATED_TZ:
        return cleaned
    if _valid_iana_zone(cleaned):
        # Valid but not curated — still store it; UI will add a fallback option.
        return cleaned
    return DEFAULT_SETTINGS["daily_digest_timezone"]


async def seed_user_settings(db, user_id, *, tz_name: str | None = None) -> dict:
    """Create default user_settings for a newly registered account.

    Hour stays 9 AM local; timezone is taken from the browser when valid.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "user_id": user_id,
        **DEFAULT_SETTINGS,
        "daily_digest_timezone": resolve_timezone(tz_name),
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.user_settings.update_one(
        {"user_id": user_id},
        {"$setOnInsert": doc},
        upsert=True,
    )
    return doc


class SettingsPatch(BaseModel):
    escalation_offsets: Optional[list[int]] = None
    follow_up_interval_days: Optional[int] = Field(default=None, ge=1, le=30)
    late_fee_enabled: Optional[bool] = None
    late_fee_text: Optional[str] = Field(default=None, max_length=280)
    scan_window_months: Optional[int] = Field(default=None, ge=1, le=36)
    daily_digest_enabled: Optional[bool] = None
    daily_digest_hour: Optional[int] = Field(default=None, ge=0, le=23)
    daily_digest_timezone: Optional[str] = Field(default=None, max_length=64)

    @field_validator("daily_digest_timezone")
    @classmethod
    def _valid_tz(cls, v):
        if v is None:
            return v
        resolved = resolve_timezone(v)
        if not _valid_iana_zone(resolved):
            raise ValueError(f"Unknown IANA timezone: {v}")
        return resolved

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
    # Backward compat: migrate legacy `daily_digest_hour_utc` → `daily_digest_hour`
    if "daily_digest_hour" not in doc and "daily_digest_hour_utc" in doc:
        doc["daily_digest_hour"] = doc.get("daily_digest_hour_utc") or 9
    # Fill in any missing keys with defaults (forward compat)
    merged = {**DEFAULT_SETTINGS, **{k: v for k, v in doc.items() if k in DEFAULT_SETTINGS}}
    merged["user_id"] = user_id
    # Normalize legacy aliases (Asia/Calcutta → Asia/Kolkata) so the Settings
    # dropdown has a matching option.
    raw_tz = merged.get("daily_digest_timezone")
    resolved_tz = resolve_timezone(raw_tz)
    if resolved_tz != raw_tz:
        merged["daily_digest_timezone"] = resolved_tz
        await db.user_settings.update_one(
            {"user_id": user_id},
            {"$set": {
                "daily_digest_timezone": resolved_tz,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    return merged


def build_router(db, get_current_user):
    router = APIRouter(tags=["settings"])

    def _with_flags(s: dict) -> dict:
        out = attach_scan_metadata(s)
        out["chasing_timing_enabled"] = chasing_timing_enabled()
        return out

    @router.get("/settings")
    async def get_settings(user: dict = Depends(get_current_user)):
        s = await get_settings_doc(db, user["_id"])
        s.pop("user_id", None)
        return _with_flags(s)

    @router.patch("/settings")
    async def patch_settings(payload: SettingsPatch, user: dict = Depends(get_current_user)):
        patch = payload.model_dump(exclude_none=True)
        if not chasing_timing_enabled():
            patch.pop("escalation_offsets", None)
            patch.pop("follow_up_interval_days", None)
        if not patch:
            raise HTTPException(status_code=400, detail="No changes provided.")
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.user_settings.update_one(
            {"user_id": user["_id"]}, {"$set": patch}, upsert=True
        )
        s = await get_settings_doc(db, user["_id"])
        s.pop("user_id", None)
        return _with_flags(s)

    @router.get("/settings/timezones")
    async def list_timezones():
        """Return the curated timezone list rendered in the settings UI."""
        return {"timezones": [{"value": z, "label": l} for z, l in COMMON_TIMEZONES]}

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

        # Wipe every per-user collection we've built (keep in sync with Privacy Policy §7).
        for coll in (
            "invoices", "receipts", "invoice_events", "review_items",
            "suppressed_senders", "gmail_connections", "gmail_sync_state",
            "scan_jobs", "seed_jobs", "chase_drafts", "chase_sends",
            "client_merges", "client_merge_prompts",
            "user_settings", "login_attempts",
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
