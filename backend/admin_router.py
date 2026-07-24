"""Admin console API — separate `admins` collection, cookie auth, ops dashboard."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional

import jwt
from bson import ObjectId
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

ADMIN_ACCESS_COOKIE = "admin_access_token"
ADMIN_TOKEN_HOURS = 12
JWT_ALGORITHM = "HS256"

OPEN_INVOICE_STATUSES = (
    "invoiced",
    "overdue",
    "promised",
    "partially_paid",
    "promise_broken",
    "disputed",
)


class AdminLoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class AdminPublic(BaseModel):
    id: str
    email: str
    name: Optional[str] = None


class AdminUserRow(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    created_at: Optional[datetime] = None
    gmail_connected: bool
    gmail_email: Optional[str] = None
    qbo_connected: bool
    qbo_company: Optional[str] = None
    invoice_count: int
    open_invoice_count: int


class AdminStats(BaseModel):
    total_users: int
    gmail_connected: int
    qbo_connected: int
    both_connected: int
    neither_connected: int
    total_invoices: int


class AdminDashboard(BaseModel):
    stats: AdminStats
    users: list[AdminUserRow]


class AdminInvoiceRow(BaseModel):
    id: str
    invoice_ref: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    counterparty_email: Optional[str] = None
    counterparty_name: Optional[str] = None
    source: Optional[str] = None
    source_subject: Optional[str] = None
    evidence_sentence: Optional[str] = None
    source_date: Optional[str] = None
    due_date: Optional[str] = None
    created_at: Optional[str] = None


class AdminInvoiceList(BaseModel):
    user_id: str
    user_email: Optional[str] = None
    invoices: list[AdminInvoiceRow]


def build_router(db, *, hash_password, verify_password, get_jwt_secret, is_https_env):
    router = APIRouter(prefix="/admin", tags=["admin"])

    def _create_admin_token(admin_id: str, email: str) -> str:
        payload = {
            "sub": admin_id,
            "email": email,
            "type": "admin_access",
            "exp": datetime.now(timezone.utc) + timedelta(hours=ADMIN_TOKEN_HOURS),
        }
        return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

    def _set_admin_cookie(response: Response, token: str) -> None:
        secure = is_https_env()
        response.set_cookie(
            key=ADMIN_ACCESS_COOKIE,
            value=token,
            httponly=True,
            secure=secure,
            samesite="none" if secure else "lax",
            max_age=ADMIN_TOKEN_HOURS * 3600,
            path="/",
        )

    def _clear_admin_cookie(response: Response) -> None:
        response.delete_cookie(ADMIN_ACCESS_COOKIE, path="/")

    def _admin_to_public(doc: dict) -> AdminPublic:
        return AdminPublic(
            id=str(doc["_id"]),
            email=doc["email"],
            name=doc.get("name"),
        )

    async def get_current_admin(request: Request) -> dict:
        token = request.cookies.get(ADMIN_ACCESS_COOKIE)
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
        try:
            payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
        if payload.get("type") != "admin_access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        try:
            admin = await db.admins.find_one({"_id": ObjectId(payload["sub"])})
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token subject")
        if not admin:
            raise HTTPException(status_code=401, detail="Admin not found")
        return admin

    async def seed_admins() -> None:
        await db.admins.create_index("email", unique=True)
        email = os.environ.get("ADMIN_EMAIL", "admin@scotive.com").lower().strip()
        password = os.environ.get("ADMIN_PASSWORD", "Admin@Scotive1")
        name = (os.environ.get("ADMIN_NAME") or "Scotive Admin").strip() or "Scotive Admin"
        existing = await db.admins.find_one({"email": email})
        now = datetime.now(timezone.utc)
        if existing is None:
            await db.admins.insert_one({
                "email": email,
                "password_hash": hash_password(password),
                "name": name,
                "created_at": now,
            })
            logger.info("Seeded admin account %s in admins collection", email)
        else:
            patch = {}
            if not verify_password(password, existing.get("password_hash", "")):
                patch["password_hash"] = hash_password(password)
            if name and existing.get("name") != name:
                patch["name"] = name
            if patch:
                patch["updated_at"] = now
                await db.admins.update_one({"email": email}, {"$set": patch})
                logger.info("Updated admin account %s", email)

    router.seed_admins = seed_admins  # type: ignore[attr-defined]

    @router.post("/login", response_model=AdminPublic)
    async def admin_login(
        payload: Annotated[AdminLoginInput, Body()],
        response: Response,
    ):
        email = payload.email.lower().strip()
        admin = await db.admins.find_one({"email": email})
        if not admin or not verify_password(payload.password, admin.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Incorrect email or password.")
        token = _create_admin_token(str(admin["_id"]), email)
        _set_admin_cookie(response, token)
        return _admin_to_public(admin)

    @router.post("/logout")
    async def admin_logout(response: Response, _admin: dict = Depends(get_current_admin)):
        _clear_admin_cookie(response)
        return {"ok": True}

    @router.get("/me", response_model=AdminPublic)
    async def admin_me(admin: dict = Depends(get_current_admin)):
        return _admin_to_public(admin)

    @router.get("/dashboard", response_model=AdminDashboard)
    async def admin_dashboard(_admin: dict = Depends(get_current_admin)):
        gmail_by_user = {}
        async for conn in db.gmail_connections.find({"status": "connected"}):
            gmail_by_user[conn["user_id"]] = conn

        qbo_by_user = {}
        async for conn in db.qbo_connections.find({"status": "connected"}):
            qbo_by_user[conn["user_id"]] = conn

        inv_counts: dict = {}
        open_counts: dict = {}
        async for row in db.invoices.aggregate([
            {
                "$group": {
                    "_id": "$user_id",
                    "total": {"$sum": 1},
                    "open": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$status", list(OPEN_INVOICE_STATUSES)]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            }
        ]):
            inv_counts[row["_id"]] = int(row.get("total") or 0)
            open_counts[row["_id"]] = int(row.get("open") or 0)

        users: list[AdminUserRow] = []
        gmail_n = qbo_n = both_n = neither_n = 0
        async for user in db.users.find({}).sort("created_at", -1):
            uid = user["_id"]
            g = gmail_by_user.get(uid)
            q = qbo_by_user.get(uid)
            gmail_ok = bool(g)
            qbo_ok = bool(q)
            if gmail_ok:
                gmail_n += 1
            if qbo_ok:
                qbo_n += 1
            if gmail_ok and qbo_ok:
                both_n += 1
            if not gmail_ok and not qbo_ok:
                neither_n += 1

            created = user.get("created_at")
            if isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created)
                except ValueError:
                    created = None

            users.append(
                AdminUserRow(
                    id=str(uid),
                    email=user.get("email") or "",
                    name=user.get("name"),
                    created_at=created,
                    gmail_connected=gmail_ok,
                    gmail_email=(g or {}).get("email"),
                    qbo_connected=qbo_ok,
                    qbo_company=(q or {}).get("company_name"),
                    invoice_count=inv_counts.get(uid, 0),
                    open_invoice_count=open_counts.get(uid, 0),
                )
            )

        total_invoices = await db.invoices.count_documents({})
        stats = AdminStats(
            total_users=len(users),
            gmail_connected=gmail_n,
            qbo_connected=qbo_n,
            both_connected=both_n,
            neither_connected=neither_n,
            total_invoices=total_invoices,
        )
        return AdminDashboard(stats=stats, users=users)

    @router.get("/users/{user_id}/invoices", response_model=AdminInvoiceList)
    async def admin_user_invoices(
        user_id: str,
        _admin: dict = Depends(get_current_admin),
        limit: int = 100,
    ):
        try:
            uid = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid user id.")
        user = await db.users.find_one({"_id": uid})
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        lim = max(1, min(int(limit or 100), 200))
        rows: list[AdminInvoiceRow] = []
        cursor = db.invoices.find({"user_id": uid}).sort(
            [("created_at", -1), ("source_date", -1)]
        ).limit(lim)
        async for inv in cursor:
            evidence = inv.get("evidence_sentence") or inv.get("approval_quote") or inv.get(
                "needs_reply_quote"
            ) or inv.get("payment_claim_quote")
            if evidence and len(str(evidence)) > 400:
                evidence = str(evidence)[:397] + "..."
            created = inv.get("created_at")
            if created is not None and not isinstance(created, str):
                try:
                    created = created.isoformat()
                except Exception:
                    created = str(created)
            source = inv.get("source")
            if not source and str(inv.get("source_message_id") or "").startswith("qbo:"):
                source = "quickbooks"
            elif not source and inv.get("source_message_id"):
                source = "gmail"
            rows.append(
                AdminInvoiceRow(
                    id=str(inv["_id"]),
                    invoice_ref=inv.get("invoice_ref"),
                    amount=float(inv["amount"]) if inv.get("amount") is not None else None,
                    currency=inv.get("currency"),
                    status=inv.get("status"),
                    counterparty_email=inv.get("counterparty_email"),
                    counterparty_name=inv.get("counterparty_name"),
                    source=source,
                    source_subject=inv.get("source_subject"),
                    evidence_sentence=evidence,
                    source_date=inv.get("source_date") if isinstance(inv.get("source_date"), str) else None,
                    due_date=inv.get("due_date") if isinstance(inv.get("due_date"), str) else None,
                    created_at=created,
                )
            )
        return AdminInvoiceList(
            user_id=user_id,
            user_email=user.get("email"),
            invoices=rows,
        )

    return router
