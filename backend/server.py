from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Annotated, Any, Optional

import asyncio
import bcrypt
import jwt
from bson import ObjectId
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

from gmail_oauth import build_router as build_gmail_router
from qbo_oauth import build_router as build_qbo_router
from scan_router import build_router as build_scan_router
from settings_router import build_router as build_settings_router, seed_user_settings
from admin_router import build_router as build_admin_router
from contact_router import build_router as build_contact_router
from incremental_sync import sync_all_users
from escalation_scheduler import escalate_all_users
from digest_sender import send_daily_digests


# ---------------------------------------------------------------------------
# Mongo connection
# ---------------------------------------------------------------------------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

_sync_task: Optional[asyncio.Task] = None
_escalation_task: Optional[asyncio.Task] = None
_digest_task: Optional[asyncio.Task] = None


# ---------------------------------------------------------------------------
# MongoDB helpers
# ---------------------------------------------------------------------------
def _coerce_object_id(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str):
        return v
    raise ValueError(f"Cannot coerce {type(v)} to ObjectId string")


PyObjectId = Annotated[str, BeforeValidator(_coerce_object_id)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True, extra="ignore")

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        if "_id" in data and isinstance(data["_id"], str):
            try:
                data["_id"] = ObjectId(data["_id"])
            except Exception:
                data.pop("_id")
        return data

    @classmethod
    def from_mongo(cls, doc: Optional[dict]):
        if doc is None:
            return None
        if "_id" in doc and isinstance(doc["_id"], ObjectId):
            doc["_id"] = str(doc["_id"])
        return cls(**doc)


# ---------------------------------------------------------------------------
# Auth constants + helpers
# ---------------------------------------------------------------------------
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 24  # 24h for MVP dev comfort
REFRESH_TOKEN_DAYS = 30

FAILED_ATTEMPT_LIMIT = 5
LOCKOUT_MINUTES = 15


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def _is_https_env() -> bool:
    frontend = os.environ.get("FRONTEND_URL", "")
    return frontend.startswith("https://")


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    secure = _is_https_env()
    samesite = "none" if secure else "lax"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=ACCESS_TOKEN_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class UserDoc(BaseDocument):
    email: str
    password_hash: str
    name: Optional[str] = None
    role: str = "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserPublic(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    role: str
    created_at: datetime


def user_to_public(doc: dict) -> UserPublic:
    return UserPublic(
        id=str(doc["_id"]),
        email=doc["email"],
        name=doc.get("name"),
        role=doc.get("role", "user"),
        created_at=doc.get("created_at") or datetime.now(timezone.utc),
    )


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: Optional[str] = Field(default=None, max_length=120)
    # Browser IANA timezone (e.g. Asia/Kolkata) — seeds daily_digest_timezone.
    timezone: Optional[str] = Field(default=None, max_length=64)


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ForgotPasswordInput(BaseModel):
    email: EmailStr


class ResetPasswordInput(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=200)


# ---------------------------------------------------------------------------
# get_current_user dependency
# ---------------------------------------------------------------------------
async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
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
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    try:
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token subject")
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# Brute-force helpers
# ---------------------------------------------------------------------------
def _attempt_identifier(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}:{email.lower()}"


async def check_lockout(request: Request, email: str) -> None:
    identifier = _attempt_identifier(request, email)
    doc = await db.login_attempts.find_one({"identifier": identifier})
    if not doc:
        return
    if doc.get("locked_until"):
        locked_until = doc["locked_until"]
        if isinstance(locked_until, str):
            locked_until = datetime.fromisoformat(locked_until)
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=429,
                detail="Too many failed attempts. Try again in a few minutes.",
            )


async def record_failed_attempt(request: Request, email: str) -> None:
    identifier = _attempt_identifier(request, email)
    doc = await db.login_attempts.find_one({"identifier": identifier})
    now = datetime.now(timezone.utc)
    count = (doc.get("count", 0) if doc else 0) + 1
    update = {"identifier": identifier, "count": count, "updated_at": now.isoformat()}
    if count >= FAILED_ATTEMPT_LIMIT:
        update["locked_until"] = (now + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
        update["count"] = 0
    await db.login_attempts.update_one(
        {"identifier": identifier}, {"$set": update}, upsert=True
    )


async def clear_failed_attempts(request: Request, email: str) -> None:
    identifier = _attempt_identifier(request, email)
    await db.login_attempts.delete_one({"identifier": identifier})


# ---------------------------------------------------------------------------
# FastAPI app + router
# ---------------------------------------------------------------------------
app = FastAPI(title="Scotive API")
api_router = APIRouter(prefix="/api")
auth_router = APIRouter(prefix="/auth", tags=["auth"])


@api_router.get("/")
async def root():
    return {"service": "scotive", "status": "ok"}


@api_router.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# -----------------------------
# Auth endpoints
# -----------------------------
@auth_router.post("/register", response_model=UserPublic)
async def register(payload: RegisterInput, response: Response):
    email = payload.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user_doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name,
        "role": "user",
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    await seed_user_settings(db, result.inserted_id, tz_name=payload.timezone)
    access = create_access_token(str(result.inserted_id), email)
    refresh = create_refresh_token(str(result.inserted_id))
    set_auth_cookies(response, access, refresh)
    return user_to_public(user_doc)


@auth_router.post("/login", response_model=UserPublic)
async def login(payload: LoginInput, request: Request, response: Response):
    email = payload.email.lower().strip()
    await check_lockout(request, email)
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await record_failed_attempt(request, email)
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    await clear_failed_attempts(request, email)
    access = create_access_token(str(user["_id"]), email)
    refresh = create_refresh_token(str(user["_id"]))
    set_auth_cookies(response, access, refresh)
    return user_to_public(user)


@auth_router.post("/logout")
async def logout(response: Response, _user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}


@auth_router.get("/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    return user_to_public(user)


@auth_router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Wrong token type")
    try:
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid subject")
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    access = create_access_token(str(user["_id"]), user["email"])
    new_refresh = create_refresh_token(str(user["_id"]))
    set_auth_cookies(response, access, new_refresh)
    return {"ok": True}


@auth_router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordInput):
    """Always returns success (do not leak account existence).
    If the account exists, we generate + store a reset token and log the reset link
    to the server logs (real email sending is deferred per user's MVP choice).
    """
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if user:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.password_reset_tokens.insert_one({
            "user_id": user["_id"],
            "token": token,
            "expires_at": expires_at,
            "used": False,
            "created_at": datetime.now(timezone.utc),
        })
        frontend_url = os.environ.get("FRONTEND_URL", "")
        reset_link = f"{frontend_url}/reset-password?token={token}"
        logger.info("Password reset requested for %s -> %s", email, reset_link)
    return {"ok": True, "message": "If the email is registered, a reset link has been sent."}


@auth_router.post("/reset-password")
async def reset_password(payload: ResetPasswordInput):
    token_doc = await db.password_reset_tokens.find_one({"token": payload.token})
    if not token_doc or token_doc.get("used"):
        raise HTTPException(status_code=400, detail="Invalid or expired token.")
    expires_at = token_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expired.")
    new_hash = hash_password(payload.password)
    await db.users.update_one({"_id": token_doc["user_id"]}, {"$set": {"password_hash": new_hash}})
    await db.password_reset_tokens.update_one(
        {"_id": token_doc["_id"]}, {"$set": {"used": True, "used_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"ok": True}


# Wire routers
admin_router = build_admin_router(
    db,
    hash_password=hash_password,
    verify_password=verify_password,
    get_jwt_secret=get_jwt_secret,
    is_https_env=_is_https_env,
)
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(build_contact_router(db))
api_router.include_router(build_gmail_router(db, get_current_user))
api_router.include_router(build_qbo_router(db, get_current_user))
api_router.include_router(build_scan_router(db, get_current_user))
api_router.include_router(build_settings_router(db, get_current_user))
app.include_router(api_router)


# CORS
frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
allowed_origins = [frontend_url]
extra_origins = os.environ.get("CORS_ORIGINS", "")
if extra_origins and extra_origins != "*":
    allowed_origins.extend([o.strip() for o in extra_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=list({o for o in allowed_origins if o}),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("scotive")


# ---------------------------------------------------------------------------
# Startup — indexes + admin seed
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.password_reset_tokens.create_index("token")
    try:
        await db.gmail_connections.drop_index("user_id_1")
    except Exception:
        pass
    await db.gmail_connections.create_index(
        [("user_id", 1), ("provider", 1)],
        unique=True,
        name="user_id_1_provider_1",
    )
    await db.gmail_connections.create_index("unipile_account_id")
    # Backfill missing provider on legacy single-mailbox rows
    await db.gmail_connections.update_many(
        {"$or": [{"provider": {"$exists": False}}, {"provider": None}, {"provider": ""}]},
        {"$set": {"provider": "google"}},
    )
    await db.qbo_connections.create_index("user_id", unique=True)
    await db.qbo_connections.create_index("realm_id")
    # Unique only when qbo_id is a real string — sparse unique still indexes
    # qbo_id:null and breaks Gmail/manual inserts (E11000 on second invoice).
    try:
        await db.invoices.drop_index("user_id_1_qbo_id_1")
    except Exception:
        pass
    await db.invoices.create_index(
        [("user_id", 1), ("qbo_id", 1)],
        unique=True,
        name="user_id_1_qbo_id_1_partial",
        partialFilterExpression={"qbo_id": {"$type": "string"}},
    )
    await db.oauth_states.create_index("state", unique=True)
    await db.scan_jobs.create_index([("user_id", 1), ("started_at", -1)])
    await db.invoices.create_index([("user_id", 1), ("created_at", -1)])
    # Multi-invoice emails ("#77 and #81" in one send) create several rows sharing
    # one source message — uniqueness is per invoice number, not per email.
    try:
        await db.invoices.drop_index("user_id_1_source_message_id_1")
    except Exception:
        pass
    await db.invoices.create_index(
        [("user_id", 1), ("source_message_id", 1), ("invoice_ref_normalized", 1)],
        unique=True,
    )
    await db.invoices.create_index([("user_id", 1), ("counterparty_email", 1)])
    await db.invoices.create_index([("user_id", 1), ("client_identity_key", 1), ("invoice_ref_normalized", 1)])
    await db.review_items.create_index([("user_id", 1), ("source_message_id", 1)], unique=True)
    await db.review_items.create_index([("user_id", 1), ("review_status", 1)])
    await db.suppressed_senders.create_index([("user_id", 1), ("email", 1)], unique=True)
    await db.receipts.create_index([("user_id", 1), ("source_message_id", 1)], unique=True)
    await db.receipts.create_index([("user_id", 1), ("match_status", 1)])
    await db.invoice_events.create_index([("user_id", 1), ("invoice_id", 1), ("at", -1)])
    await db.user_settings.create_index("user_id", unique=True)
    await db.gmail_sync_state.create_index("user_id", unique=True)
    await db.chase_drafts.create_index([("user_id", 1), ("invoice_id", 1), ("step_key", 1)])
    await db.chase_drafts.create_index([("user_id", 1), ("status", 1), ("generated_at", -1)])
    await db.digest_sends.create_index([("user_id", 1), ("sent_at", -1)])
    await db.seed_jobs.create_index([("user_id", 1), ("started_at", -1)])
    await db.seed_candidates.create_index([("user_id", 1), ("job_id", 1), ("status", 1)])
    await db.seed_candidates.create_index([("user_id", 1), ("message_id", 1)])
    # Incremental ingestion registry — every Gmail message id seen once; 30d TTL.
    await db.processed_messages.create_index([("user_id", 1), ("message_id", 1)], unique=True)
    await db.processed_messages.create_index("at", expireAfterSeconds=30 * 86400)
    await db.client_merges.create_index([("user_id", 1), ("canonical_key", 1)])
    await db.client_merges.create_index([("user_id", 1), ("alias_keys", 1)])
    await db.client_merge_prompts.create_index([("user_id", 1), ("status", 1), ("created_at", -1)])
    await db.client_merge_prompts.create_index([("user_id", 1), ("pair_key", 1), ("status", 1)])
    await db.contact_messages.create_index([("created_at", -1)])
    await db.contact_messages.create_index([("email", 1), ("created_at", -1)])
    await db.contact_messages.create_index([("ip", 1), ("created_at", -1)])
    await seed_admin()
    # Safe only with a single Uvicorn worker — clears crash-stale locks & resumes seed jobs.
    await recover_interrupted_work()

    # Register Unipile account_status webhook when PUBLIC_API_URL is set (idempotent).
    if os.environ.get("UNIPILE_API_KEY") and os.environ.get("PUBLIC_API_URL"):
        try:
            from unipile_client import ensure_account_status_webhook
            await ensure_account_status_webhook()
        except Exception as e:
            logger.warning("Unipile webhook setup skipped: %s", e)

    # Kick off continuous loops (F9a). Interval 0 disables that loop.
    # Defaults: sync/escalation hourly; digest check every 15m (send still once/day per user).
    global _sync_task, _escalation_task, _digest_task
    interval = int(os.environ.get("SYNC_INTERVAL_SECONDS", "3600"))
    esc_interval = int(os.environ.get("ESCALATION_INTERVAL_SECONDS", "3600"))
    digest_interval = int(os.environ.get("DIGEST_CHECK_INTERVAL_SECONDS", "900"))
    if interval > 0:
        _sync_task = asyncio.create_task(_sync_loop(interval))
        logger.info("Continuous sync loop scheduled every %ss", interval)
    else:
        logger.info("Continuous sync loop disabled (SYNC_INTERVAL_SECONDS=0)")
    from feature_flags import chasing_timing_enabled

    if chasing_timing_enabled() and esc_interval > 0:
        _escalation_task = asyncio.create_task(_escalation_loop(esc_interval))
        logger.info("Escalation loop scheduled every %ss", esc_interval)
    elif not chasing_timing_enabled():
        logger.info("Escalation loop disabled (ENABLE_CHASING_TIMING=false)")
    else:
        logger.info("Escalation loop disabled (ESCALATION_INTERVAL_SECONDS=0)")
    if digest_interval > 0:
        _digest_task = asyncio.create_task(_digest_loop(digest_interval))
        logger.info("Daily digest loop scheduled every %ss", digest_interval)
    else:
        logger.info("Daily digest loop disabled (DIGEST_CHECK_INTERVAL_SECONDS=0)")


async def _sync_loop(interval_seconds: int):
    """Periodically run incremental Gmail sync for every connected user.

    Fires the first tick after a short grace period so the process is fully
    initialized. Failures for a single user do not stop the loop.
    """
    import asyncio as _asyncio
    await _asyncio.sleep(30)
    while True:
        try:
            totals = await sync_all_users(db)
            if totals.get("users"):
                logger.info(
                    "Sync tick: users=%s invoices+%s skipped=%s",
                    totals["users"], totals.get("invoices_created", 0), totals.get("skipped", 0),
                )
        except Exception as e:
            logger.exception("Sync loop iteration failed: %s", e)
        await _asyncio.sleep(interval_seconds)


async def _escalation_loop(interval_seconds: int):
    """Periodically materialize chase drafts based on user_settings.escalation_offsets."""
    import asyncio as _asyncio
    await _asyncio.sleep(60)
    while True:
        try:
            totals = await escalate_all_users(db)
            if totals.get("users"):
                logger.info(
                    "Escalation tick: users=%s drafts+%s",
                    totals["users"], totals["drafts_generated"],
                )
        except Exception as e:
            logger.exception("Escalation loop iteration failed: %s", e)
        await _asyncio.sleep(interval_seconds)


async def _digest_loop(interval_seconds: int):
    """Every ~15 minutes, check whose digest hour has struck and send if due."""
    import asyncio as _asyncio
    await _asyncio.sleep(90)
    while True:
        try:
            totals = await send_daily_digests(db)
            if totals.get("sent"):
                logger.info(
                    "Digest tick: users_considered=%s sent=%s skipped=%s",
                    totals["users_considered"], totals["sent"], totals["skipped"],
                )
        except Exception as e:
            logger.exception("Digest loop iteration failed: %s", e)
        await _asyncio.sleep(interval_seconds)


async def seed_admin():
    """Seed ops admin into separate `admins` collection (used by /admin).

    Also keeps a matching users.role=admin row for legacy/local scripts that
    still look there — password stays in sync with ADMIN_PASSWORD.
    """
    await admin_router.seed_admins()

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@scotive.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@Scotive1")
    admin_name = (os.environ.get("ADMIN_NAME") or "Scotive Admin").strip() or "Scotive Admin"
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": admin_name,
            "role": "admin",
            "created_at": datetime.now(timezone.utc),
        })
        logger.info("Seeded legacy admin user %s in users", admin_email)
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}},
        )
        logger.info("Updated legacy admin password for %s", admin_email)


async def recover_interrupted_work() -> None:
    """Recover workflow state left inconsistent by a process crash/restart.

    Must run once per boot (Uvicorn --workers 1). Re-reads Mongo for the
    to-do list — does not rely on in-memory job queues.
    """
    from seed_scan import run_seed_scan

    now_iso = datetime.now(timezone.utc).isoformat()
    sync_res = await db.gmail_sync_state.update_many(
        {"sync_running": True},
        {"$set": {"sync_running": False, "updated_at": now_iso}},
    )
    if sync_res.modified_count:
        logger.info(
            "Startup recovery: cleared stuck sync_running on %s user(s)",
            sync_res.modified_count,
        )

    resumed = 0
    async for job in db.seed_jobs.find({"status": {"$in": ["queued", "running"]}}):
        uid = job.get("user_id")
        if not uid:
            continue
        await db.seed_jobs.update_one(
            {"_id": job["_id"]},
            {"$set": {"status": "queued", "phase": "queued", "updated_at": now_iso}},
        )
        asyncio.create_task(run_seed_scan(db, uid, job["_id"]))
        resumed += 1
    if resumed:
        logger.info("Startup recovery: resumed %s seed job(s) from Mongo", resumed)


@app.on_event("shutdown")
async def on_shutdown():
    global _sync_task, _escalation_task, _digest_task
    for t in (_sync_task, _escalation_task, _digest_task):
        if t and not t.done():
            t.cancel()
    client.close()
