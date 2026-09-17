"""Send a chase from the owner's mailbox (manual or Friendly cadence)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from post_chase import ack_followup_prompts, mark_chase_sent

logger = logging.getLogger("scotive.chase_send")


async def deliver_chase_email(
    db,
    user_id,
    inv: dict,
    *,
    subject: str,
    body: str,
    step_index: Optional[int] = None,
    draft_id=None,
) -> dict[str, Any]:
    """Send via Gmail/Outlook. Returns {ok, reason?, sent}."""
    from gmail_client import get_access_token, resolve_mailbox_connection, send_gmail_reply
    from cadence import ensure_pay_link, invoice_pay_url

    to_addr = (inv.get("counterparty_email") or "").strip()
    if not to_addr or "@" not in to_addr:
        return {"ok": False, "reason": "no_recipient"}

    body = ensure_pay_link(body, invoice_pay_url(inv))

    conn = await resolve_mailbox_connection(
        db,
        user_id,
        provider=inv.get("mailbox_provider"),
        email=inv.get("mailbox_email"),
    )
    if not conn or not conn.get("can_send"):
        return {"ok": False, "reason": "no_send"}

    access = await get_access_token(
        db, user_id, provider=conn.get("provider"), email=conn.get("email"),
    )
    from_addr = conn.get("email")
    try:
        sent = await send_gmail_reply(
            access,
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            body=body,
            thread_id=inv.get("source_thread_id"),
            reply_to_message_id=inv.get("source_message_id"),
        )
    except Exception as e:
        logger.warning("chase send failed inv=%s err=%s", inv.get("_id"), e)
        return {"ok": False, "reason": "send_failed", "error": str(e)[:200]}

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.chase_sends.insert_one({
        "user_id": user_id,
        "invoice_id": inv.get("_id"),
        "to": to_addr,
        "subject": sent.get("subject") or subject,
        "body": body,
        "sent_at": now_iso,
        "gmail_thread_id": sent.get("thread_id"),
        "chase_draft_id": draft_id,
        "auto": step_index is not None,
    })
    await mark_chase_sent(db, user_id, inv["_id"], step_index=step_index, now_iso=now_iso)
    await ack_followup_prompts(db, user_id, [str(inv["_id"])])
    await db.invoices.update_one({"_id": inv["_id"]}, {"$inc": {"chase_count": 1}})
    try:
        from incremental_sync import reeval_after_user_outbound_send
        await reeval_after_user_outbound_send(
            db, user_id, inv,
            access=access,
            my_email=from_addr or "",
            subject=sent.get("subject") or subject,
            body=body,
            gmail_message_id=sent.get("gmail_message_id"),
            thread_id=sent.get("thread_id") or inv.get("source_thread_id"),
        )
    except Exception:
        logger.exception("post-send reeval failed inv=%s", inv.get("_id"))
    return {"ok": True, "sent": sent, "sent_at": now_iso, "from_addr": from_addr}
