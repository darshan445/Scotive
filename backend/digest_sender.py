"""Daily digest email sender (F9c).

Once per day per user, sends a summary of the Today card via the user's own
connected Gmail. Silent when nothing to report. Never runs more than once
per calendar day per user.

The digest deliberately mirrors the shape of the dashboard Today card:
  - Due / Overdue
  - Broken promises
  - Needs reply (disputes / scope questions)
  - Resolved yesterday

If the totals of all four sections come to zero, we skip sending.
"""
from __future__ import annotations

import base64
import html
import logging
import os
from datetime import datetime, timezone, timedelta

import httpx

from gmail_client import get_access_token, GmailAuthError

logger = logging.getLogger("scotive.digest")

_OPEN = ("invoiced", "overdue", "promised", "partially_paid", "promise_broken")


def _fmt_money(amount, currency="USD"):
    try:
        a = float(amount or 0)
    except (TypeError, ValueError):
        return "$0"
    sign = "-" if a < 0 else ""
    a = abs(a)
    if a >= 1000:
        return f"{sign}${a:,.0f}" if currency == "USD" else f"{sign}{a:,.0f} {currency}"
    return f"{sign}${a:,.2f}" if currency == "USD" else f"{sign}{a:,.2f} {currency}"


def _client_label(inv: dict) -> str:
    return inv.get("counterparty_name") or inv.get("counterparty_email") or "Unknown client"


def _parse_date(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
        except Exception:
            return None


async def collect_today_sections(db, user_id) -> dict:
    """Same buckets as GET /api/digest/today, but pure-python (no HTTP hop)."""
    today = datetime.now(timezone.utc).date()
    due_overdue = []
    broken = []
    needs_reply = []
    resolved = []
    async for inv in db.invoices.find({"user_id": user_id}):
        s = inv.get("status")
        if s == "overdue":
            due_overdue.append(inv)
        elif s == "invoiced" and inv.get("due_date"):
            d = _parse_date(inv.get("due_date"))
            if d and d <= today:
                due_overdue.append(inv)
        elif s == "promise_broken":
            broken.append(inv)
        elif s == "disputed":
            needs_reply.append(inv)
        elif s == "paid":
            d = _parse_date(inv.get("paid_at"))
            if d and (today - d).days <= 1:
                resolved.append(inv)
    return {
        "due_overdue": due_overdue,
        "broken_promises": broken,
        "needs_reply": needs_reply,
        "resolved": resolved,
    }


def _totals(sections: dict) -> dict:
    return {
        "due_overdue": len(sections["due_overdue"]),
        "broken_promises": len(sections["broken_promises"]),
        "needs_reply": len(sections["needs_reply"]),
        "resolved": len(sections["resolved"]),
        "total_open_amount": round(sum(
            float(i.get("balance_remaining") or i.get("amount") or 0)
            for i in sections["due_overdue"] + sections["broken_promises"]
        ), 2),
    }


def build_digest_email(user: dict, sections: dict, totals: dict) -> dict:
    """Return {subject, body_text, body_html}."""
    date_str = datetime.now(timezone.utc).strftime("%A, %b %d")
    subject_bits = []
    if totals["due_overdue"]:
        subject_bits.append(f"{totals['due_overdue']} due")
    if totals["broken_promises"]:
        subject_bits.append(f"{totals['broken_promises']} broken")
    if totals["needs_reply"]:
        subject_bits.append(f"{totals['needs_reply']} needs reply")
    if totals["resolved"]:
        subject_bits.append(f"{totals['resolved']} resolved")
    subject_summary = " · ".join(subject_bits) if subject_bits else "You're all caught up"
    subject = f"Scotive · {subject_summary} · {date_str}"

    # --------- Plain text -------------------------------------------------
    lines = [f"Scotive daily digest · {date_str}", ""]

    def bucket_text(title, rows, label_getter):
        if not rows:
            return
        lines.append(f"{title} ({len(rows)})")
        for inv in rows[:10]:
            bal = inv.get("balance_remaining")
            if bal in (None, 0):
                bal = inv.get("amount")
            lines.append(f"  · {_client_label(inv)} — {_fmt_money(bal, inv.get('currency','USD'))}"
                         + (f" · {inv.get('invoice_ref')}" if inv.get('invoice_ref') else "")
                         + (f" · {label_getter(inv)}" if label_getter(inv) else ""))
        if len(rows) > 10:
            lines.append(f"  · … and {len(rows) - 10} more")
        lines.append("")

    def _due_label(inv):
        d = _parse_date(inv.get("due_date"))
        if not d:
            return ""
        days = (datetime.now(timezone.utc).date() - d).days
        if days > 0:
            return f"{days}d overdue"
        if days == 0:
            return "due today"
        return f"due in {-days}d"

    def _promise_label(inv):
        d = _parse_date(inv.get("promise_date"))
        if not d:
            return "broken promise"
        return f"promised {d.isoformat()}"

    def _resolved_label(inv):
        d = _parse_date(inv.get("paid_at"))
        return f"paid {d.isoformat()}" if d else "paid"

    bucket_text("Due / Overdue", sections["due_overdue"], _due_label)
    bucket_text("Broken promises", sections["broken_promises"], _promise_label)
    bucket_text("Needs reply", sections["needs_reply"], lambda i: i.get("status") or "")
    bucket_text("Resolved (last 24h)", sections["resolved"], _resolved_label)

    if totals["due_overdue"] or totals["broken_promises"]:
        lines.append(f"Total open in these buckets: {_fmt_money(totals['total_open_amount'])}")
        lines.append("")
    lines.append(f"Open the dashboard: {os.environ.get('FRONTEND_URL', '')}/dashboard")
    body_text = "\n".join(lines)

    # --------- HTML -------------------------------------------------------
    def html_bucket(title, rows, color, label_getter):
        if not rows:
            return ""
        items = []
        for inv in rows[:10]:
            bal = inv.get("balance_remaining")
            if bal in (None, 0):
                bal = inv.get("amount")
            label = label_getter(inv)
            items.append(
                "<tr>"
                f"<td style='padding:6px 0;color:#111;font-weight:500'>{html.escape(_client_label(inv))}</td>"
                f"<td style='padding:6px 0;text-align:right;font-variant-numeric:tabular-nums;font-weight:600;color:#111'>{html.escape(_fmt_money(bal, inv.get('currency','USD')))}</td>"
                f"<td style='padding:6px 0 6px 16px;color:#6b7280;font-size:12px'>{html.escape(label or '')}</td>"
                "</tr>"
            )
        overflow = ""
        if len(rows) > 10:
            overflow = f"<div style='margin-top:6px;color:#6b7280;font-size:12px'>… and {len(rows)-10} more</div>"
        return (
            f"<div style='margin:20px 0'>"
            f"<div style='color:{color};font-size:12px;letter-spacing:.2em;text-transform:uppercase;font-weight:600;margin-bottom:6px'>"
            f"{html.escape(title)} · {len(rows)}</div>"
            f"<table style='width:100%;border-collapse:collapse'>{''.join(items)}</table>"
            f"{overflow}</div>"
        )

    frontend = os.environ.get("FRONTEND_URL", "")
    hero_bits = " · ".join([f"<span style='color:#111;font-weight:600'>{b}</span>" for b in subject_bits]) or "<span style='color:#059669;font-weight:600'>You're all caught up</span>"
    body_html = (
        "<html><body style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#fff;color:#111;margin:0;padding:24px'>"
        "<div style='max-width:640px;margin:0 auto'>"
        f"<div style='color:#6b7280;font-size:12px;letter-spacing:.2em;text-transform:uppercase;margin-bottom:4px'>Scotive · {html.escape(date_str)}</div>"
        f"<h1 style='font-size:22px;margin:4px 0 0 0'>{hero_bits}</h1>"
        f"{html_bucket('Due / Overdue', sections['due_overdue'], '#b91c1c', _due_label)}"
        f"{html_bucket('Broken promises', sections['broken_promises'], '#b45309', _promise_label)}"
        f"{html_bucket('Needs reply', sections['needs_reply'], '#1d4ed8', lambda i: i.get('status') or '')}"
        f"{html_bucket('Resolved (last 24h)', sections['resolved'], '#059669', _resolved_label)}"
    )
    if totals["due_overdue"] or totals["broken_promises"]:
        body_html += (
            f"<div style='margin-top:20px;padding:12px 14px;border:1px solid #e5e7eb;border-radius:8px;color:#111;font-size:14px'>"
            f"Total open in these buckets: <b>{html.escape(_fmt_money(totals['total_open_amount']))}</b></div>"
        )
    if frontend:
        body_html += (
            f"<div style='margin-top:20px'><a href='{html.escape(frontend)}/dashboard' "
            f"style='display:inline-block;padding:10px 16px;background:#111;color:#fff;text-decoration:none;border-radius:6px;font-size:14px'>Open dashboard</a></div>"
        )
    body_html += (
        "<div style='margin-top:32px;color:#9ca3af;font-size:11px'>Sent by Scotive · You're getting this because daily digest is on in Settings.</div>"
        "</div></body></html>"
    )

    return {"subject": subject, "body_text": body_text, "body_html": body_html}


def _mime_message(from_addr, to_addr, subject, body_text, body_html):
    boundary = "sctvbndry" + os.urandom(4).hex()
    return (
        f"From: {from_addr}\r\n"
        f"To: {to_addr}\r\n"
        f"Subject: {subject}\r\n"
        f"MIME-Version: 1.0\r\n"
        f"Content-Type: multipart/alternative; boundary=\"{boundary}\"\r\n\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/plain; charset=UTF-8\r\n\r\n"
        f"{body_text}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: text/html; charset=UTF-8\r\n\r\n"
        f"{body_html}\r\n"
        f"--{boundary}--"
    )


async def send_digest_for_user(db, user_id, force: bool = False) -> dict:
    """Build + send the digest for one user. Returns a status dict; never raises."""
    result = {"status": "skipped", "reason": None, "counts": {}}
    user = await db.users.find_one({"_id": user_id})
    if not user:
        return {**result, "reason": "user_not_found"}
    conn = await db.gmail_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        return {**result, "reason": "no_gmail"}
    if not conn.get("can_send"):
        return {**result, "reason": "no_send_scope"}
    settings = await db.user_settings.find_one({"user_id": user_id}) or {}
    if not force and settings.get("daily_digest_enabled") is False:
        return {**result, "reason": "digest_disabled"}

    # Already sent today?
    if not force:
        last = settings.get("last_digest_sent_at")
        if last:
            try:
                last_d = datetime.fromisoformat(str(last).replace("Z", "+00:00")).date()
                if last_d == datetime.now(timezone.utc).date():
                    return {**result, "reason": "already_sent_today"}
            except Exception:
                pass

    sections = await collect_today_sections(db, user_id)
    totals = _totals(sections)
    counts = {**totals}
    if (totals["due_overdue"] + totals["broken_promises"] + totals["needs_reply"] + totals["resolved"]) == 0:
        # Still update last_digest_sent_at so we don't recompute over and over today
        await db.user_settings.update_one(
            {"user_id": user_id},
            {"$set": {"last_digest_sent_at": datetime.now(timezone.utc).isoformat(),
                      "last_digest_status": "empty"}},
            upsert=True,
        )
        return {**result, "reason": "empty", "counts": counts}

    email = build_digest_email(user, sections, totals)

    try:
        access = await get_access_token(db, user_id)
    except GmailAuthError as e:
        return {**result, "reason": f"auth_error:{e}", "counts": counts}

    from_addr = conn.get("email")
    to_addr = user.get("email")  # digest goes to the app-account email
    raw = _mime_message(from_addr, to_addr, email["subject"], email["body_text"], email["body_html"])
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")

    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
                json={"raw": encoded},
            )
            if r.status_code >= 400:
                logger.warning("Digest send failed: %s %s", r.status_code, r.text[:200])
                return {**result, "reason": "gmail_send_failed", "counts": counts}
    except Exception as e:  # pragma: no cover
        logger.exception("Digest send exception: %s", e)
        return {**result, "reason": "exception", "counts": counts}

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.user_settings.update_one(
        {"user_id": user_id},
        {"$set": {"last_digest_sent_at": now_iso, "last_digest_status": "sent",
                  "last_digest_counts": counts}},
        upsert=True,
    )
    await db.digest_sends.insert_one({
        "user_id": user_id, "to": to_addr, "from": from_addr,
        "subject": email["subject"], "counts": counts, "sent_at": now_iso,
    })
    return {"status": "sent", "counts": counts, "sent_at": now_iso}


async def send_daily_digests(db) -> dict:
    """Iterate every connected user whose digest is due (opt-in + current hour matches)."""
    now_hour = datetime.now(timezone.utc).hour
    totals = {"users_considered": 0, "sent": 0, "skipped": 0}
    async for conn in db.gmail_connections.find({"status": "connected"}):
        uid = conn.get("user_id")
        if not uid:
            continue
        totals["users_considered"] += 1
        settings = await db.user_settings.find_one({"user_id": uid}) or {}
        if settings.get("daily_digest_enabled") is False:
            totals["skipped"] += 1
            continue
        target_hour = int(settings.get("daily_digest_hour_utc", 14))
        if now_hour != target_hour:
            totals["skipped"] += 1
            continue
        res = await send_digest_for_user(db, uid)
        if res.get("status") == "sent":
            totals["sent"] += 1
        else:
            totals["skipped"] += 1
    return totals
