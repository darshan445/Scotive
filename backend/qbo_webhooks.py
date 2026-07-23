"""Module 6 — QuickBooks webhooks (Invoice / Payment change notifications).

Public endpoint (no JWT). Authenticated via Intuit HMAC signature + verifier token.
Acknowledges quickly; processes upsert / paid / conversation match in the background.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request

logger = logging.getLogger("scotive.qbo_webhooks")


def webhook_verifier_token() -> str:
    return (os.environ.get("QBO_WEBHOOK_VERIFIER_TOKEN") or "").strip()


def webhook_public_url() -> str:
    """URL to paste in Intuit Developer → Webhooks (must be HTTPS / ngrok)."""
    return (os.environ.get("QBO_WEBHOOK_URL") or "").strip()


def verify_intuit_signature(raw_body: bytes, signature: Optional[str]) -> bool:
    """HMAC-SHA256(body, verifier) → base64, compared to intuit-signature header."""
    token = webhook_verifier_token()
    if not token or not signature:
        return False
    digest = hmac.new(token.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature.strip())


def _entities_from_payload(payload: dict) -> list[tuple[str, str, str, str]]:
    """Return list of (realm_id, entity_name, entity_id, operation)."""
    out: list[tuple[str, str, str, str]] = []

    # Classic Intuit webhook shape
    for note in payload.get("eventNotifications") or []:
        realm = str(note.get("realmId") or "")
        dce = note.get("dataChangeEvent") or {}
        for ent in dce.get("entities") or []:
            name = str(ent.get("name") or "")
            eid = str(ent.get("id") or "")
            op = str(ent.get("operation") or "")
            if realm and name and eid:
                out.append((realm, name, eid, op))

    # CloudEvents-style (single or batch)
    events = payload.get("eventNotifications")
    if not out and isinstance(payload.get("type"), str):
        # Single CloudEvent
        events = [payload]
    if not out and isinstance(payload.get("events"), list):
        events = payload["events"]

    if not out and events:
        for ev in events:
            if not isinstance(ev, dict):
                continue
            realm = str(ev.get("intuitaccountid") or ev.get("realmId") or "")
            eid = str(ev.get("intuitentityid") or ev.get("id") or "")
            typ = str(ev.get("type") or "")
            # type like qbo.invoice.create.v1 or similar
            parts = typ.lower().split(".")
            name = ""
            op = ""
            for p in parts:
                if p in ("invoice", "payment", "customer"):
                    name = p.capitalize() if p != "invoice" else "Invoice"
                    if p == "payment":
                        name = "Payment"
                    if p == "customer":
                        name = "Customer"
                if p in ("create", "update", "delete", "void", "merge"):
                    op = p.capitalize()
            if name == "invoice":
                name = "Invoice"
            if realm and name and eid:
                out.append((realm, name, eid, op or "Update"))

    return out


async def _process_entities(db, entities: list[tuple[str, str, str, str]]) -> None:
    from qbo_conversation import enqueue_qbo_conversation_match
    from qbo_import import import_unpaid_invoices
    from qbo_paid_sync import sync_qbo_paid_status

    # Group by realm
    by_realm: dict[str, list[tuple[str, str, str]]] = {}
    for realm, name, eid, op in entities:
        by_realm.setdefault(realm, []).append((name, eid, op))

    for realm, items in by_realm.items():
        conn = await db.qbo_connections.find_one({
            "realm_id": str(realm),
            "status": "connected",
        })
        if not conn:
            logger.info("qbo.webhook skip realm=%s (no connected user)", realm)
            continue
        user_id = conn["user_id"]
        names = {n for n, _, _ in items}
        try:
            if "Invoice" in names:
                # Upsert open invoices; paid sync catches Balance=0 on known rows
                await import_unpaid_invoices(db, user_id)
                await enqueue_qbo_conversation_match(db, user_id)
            if "Payment" in names or "Invoice" in names:
                await sync_qbo_paid_status(db, user_id)
        except Exception:
            logger.exception("qbo.webhook process fail realm=%s user=%s", realm, user_id)


def build_webhook_routes(db) -> APIRouter:
    """Unauthenticated routes mounted under /qbo."""
    router = APIRouter()

    @router.get("/webhooks/info")
    async def webhooks_info():
        """Helper for local setup — shows the URL to paste in Intuit Developer."""
        url = webhook_public_url()
        token_set = bool(webhook_verifier_token())
        return {
            "webhook_url": url or None,
            "verifier_token_configured": token_set,
            "hint": (
                "In Intuit Developer → your app → Webhooks (Sandbox), "
                "paste webhook_url, subscribe to Invoice + Payment (Create, Update), "
                "copy the Verifier Token into QBO_WEBHOOK_VERIFIER_TOKEN, restart backend."
            ),
        }

    @router.post("/webhooks")
    async def webhooks(
        request: Request,
        intuit_signature: Optional[str] = Header(None, alias="intuit-signature"),
    ):
        raw = await request.body()
        if not webhook_verifier_token():
            logger.error("qbo.webhook rejected: QBO_WEBHOOK_VERIFIER_TOKEN not set")
            raise HTTPException(status_code=503, detail="Webhook verifier not configured")
        if not verify_intuit_signature(raw, intuit_signature):
            logger.warning("qbo.webhook bad signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

        try:
            import json
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {}

        entities = _entities_from_payload(payload if isinstance(payload, dict) else {})
        logger.info(
            "qbo.webhook ok entities=%s at=%s",
            [(r, n, i, o) for r, n, i, o in entities[:20]],
            datetime.now(timezone.utc).isoformat(),
        )

        if entities:
            asyncio.create_task(_process_entities(db, entities))

        # Intuit requires a fast 200
        return {"ok": True}

    return router
