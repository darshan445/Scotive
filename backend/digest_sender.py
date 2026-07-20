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
from ledger_reconcile import sort_by_email_date

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
    from invoice_lifecycle import has_pending_payment_claim

    today = datetime.now(timezone.utc).date()
    due_overdue = []
    broken = []
    needs_reply = []
    resolved = []
    confirm_prompts = []
    stale_prompts = []
    watching = []
    async for inv in db.invoices.find({"user_id": user_id}):
        if inv.get("tracking_paused"):
            continue
        s = inv.get("status")
        if has_pending_payment_claim(inv):
            confirm_prompts.append(inv)
        elif s == "stale" and inv.get("stale_prompt_pending"):
            stale_prompts.append(inv)
        elif inv.get("needs_reply") and s in ("invoiced", "overdue"):
            # Client asked a question — answering beats chasing.
            needs_reply.append(inv)
        elif s == "overdue":
            if inv.get("watching_for_reply") or inv.get("ladder_exhausted"):
                watching.append(inv)
            else:
                due_overdue.append(inv)
        elif s == "invoiced" and inv.get("due_date"):
            d = _parse_date(inv.get("due_date"))
            if d and d < today:
                if inv.get("watching_for_reply"):
                    watching.append(inv)
                else:
                    due_overdue.append(inv)
        elif s == "promise_broken":
            if inv.get("watching_for_reply") or inv.get("ladder_exhausted"):
                watching.append(inv)
            else:
                broken.append(inv)
        elif s == "disputed":
            if inv.get("watching_for_reply"):
                watching.append(inv)
            else:
                needs_reply.append(inv)
        elif s in ("promised", "partially_paid"):
            watching.append(inv)
        elif s == "invoiced" and not inv.get("due_date"):
            watching.append(inv)
        elif s == "paid":
            d = _parse_date(inv.get("paid_at"))
            if d and (today - d).days <= 1:
                resolved.append(inv)
    sync_state = await db.gmail_sync_state.find_one({"user_id": user_id}) or {}
    return {
        "due_overdue": sort_by_email_date(due_overdue),
        "broken_promises": sort_by_email_date(broken),
        "needs_reply": sort_by_email_date(needs_reply),
        "resolved": sort_by_email_date(resolved),
        "watching": sort_by_email_date(watching),
        "confirm_prompts": sort_by_email_date(confirm_prompts),
        "stale_prompts": sort_by_email_date(stale_prompts),
        "followup_prompts": list(sync_state.get("pending_followup_prompts") or []),
    }


def _totals(sections: dict) -> dict:
    from invoice_lifecycle import outstanding_balance

    return {
        "due_overdue": len(sections["due_overdue"]),
        "broken_promises": len(sections["broken_promises"]),
        "needs_reply": len(sections["needs_reply"]),
        "confirm_prompts": len(sections.get("confirm_prompts") or []),
        "stale_prompts": len(sections.get("stale_prompts") or []),
        "watching": len(sections.get("watching") or []),
        "followup_prompts": len(sections.get("followup_prompts") or []),
        "resolved": len(sections["resolved"]),
        "total_open_amount": round(sum(
            outstanding_balance(i)
            for i in sections["due_overdue"] + sections["broken_promises"]
        ), 2),
    }


def _action_count(totals: dict) -> int:
    """Items that need a decision — excludes passive 'watching' and resolved."""
    return (
        int(totals.get("due_overdue") or 0)
        + int(totals.get("broken_promises") or 0)
        + int(totals.get("needs_reply") or 0)
        + int(totals.get("confirm_prompts") or 0)
        + int(totals.get("stale_prompts") or 0)
        + int(totals.get("followup_prompts") or 0)
    )


def _row_amount(row: dict) -> str:
    from invoice_lifecycle import outstanding_balance

    if "amount" in row and "status" not in row and "due_date" not in row:
        # follow-up prompt shape
        return _fmt_money(row.get("amount"), row.get("currency") or "USD")
    try:
        return _fmt_money(outstanding_balance(row), row.get("currency") or "USD")
    except Exception:
        return _fmt_money(row.get("amount") or row.get("balance_remaining"), row.get("currency") or "USD")


def _row_client(row: dict) -> str:
    return row.get("counterparty_name") or row.get("counterparty_email") or "Unknown client"


def _fmt_short_date(d) -> str:
    if not d:
        return "—"
    return d.strftime("%b %d, %Y")


_LOGO_CID = "scotive-logo@scotive"


def _digest_logo_bytes() -> bytes | None:
    """Load the squircle mark shipped with the frontend (for CID-inline in digests)."""
    from pathlib import Path

    here = Path(__file__).resolve().parent
    candidates = [
        here / "static" / "scotive-icon.png",
        here.parent / "frontend" / "public" / "scotive-icon.png",
    ]
    for path in candidates:
        try:
            if path.is_file():
                return path.read_bytes()
        except OSError:
            continue
    return None


def _digest_logo_url() -> str:
    base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    return f"{base}/scotive-icon.png" if base else ""


def build_digest_email(user: dict, sections: dict, totals: dict) -> dict:
    """Return {subject, body_text, body_html}."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %b %d")
    date_short = now.strftime("%b %d")
    actions = _action_count(totals)

    # Short, scannable subject — no middle-dot (encoding-safe) and no watching noise.
    if actions == 0:
        subject = f"Scotive digest: you're caught up ({date_short})"
    elif actions == 1:
        subject = f"Scotive digest: 1 item needs you ({date_short})"
    else:
        subject = f"Scotive digest: {actions} items need you ({date_short})"

    def _due_note(inv):
        d = _parse_date(inv.get("due_date"))
        return f"Due {_fmt_short_date(d)}" if d else "Past due"

    def _promise_note(inv):
        d = _parse_date(inv.get("promise_date"))
        return f"Promised {_fmt_short_date(d)}" if d else "Broken promise"

    def _resolved_note(inv):
        d = _parse_date(inv.get("paid_at"))
        return f"Paid {_fmt_short_date(d)}" if d else "Paid"

    def _followup_note(p):
        step = (p.get("step_label") or "follow-up").replace("_", " ")
        return f"No reply yet — {step}"

    def _status_note(inv):
        return (inv.get("status") or "open").replace("_", " ")

    # Ordered action sections (same urgency as the Today card).
    buckets = [
        ("Past due", sections.get("due_overdue") or [], _due_note),
        ("Broken promises", sections.get("broken_promises") or [], _promise_note),
        ("Confirm payment", sections.get("confirm_prompts") or [], lambda _i: "Client says paid"),
        ("Gone quiet", sections.get("stale_prompts") or [], lambda _i: "No activity 120+ days"),
        ("Needs your reply", sections.get("needs_reply") or [], _status_note),
        ("Follow-up ready", sections.get("followup_prompts") or [], _followup_note),
    ]
    resolved = sections.get("resolved") or []
    watching_n = len(sections.get("watching") or [])

    # --------- Plain text -------------------------------------------------
    lines = [
        "SCOTIVE DAILY DIGEST",
        date_str,
        "",
        f"{actions} item{'s' if actions != 1 else ''} need your attention"
        if actions
        else "Nothing needs you right now.",
        "",
    ]
    if totals.get("total_open_amount") and (totals.get("due_overdue") or totals.get("broken_promises")):
        lines.append(f"At risk (past due + broken): {_fmt_money(totals['total_open_amount'])}")
        lines.append("")

    for title, rows, note_fn in buckets:
        if not rows:
            continue
        lines.append(f"{title.upper()} ({len(rows)})")
        lines.append("-" * 40)
        for row in rows[:12]:
            ref = f"  [{row.get('invoice_ref')}]" if row.get("invoice_ref") else ""
            lines.append(
                f"  {_row_client(row)}{ref}"
                f"\n    {_row_amount(row)}  |  {note_fn(row)}"
            )
        if len(rows) > 12:
            lines.append(f"  ... and {len(rows) - 12} more")
        lines.append("")

    if resolved:
        lines.append(f"RESOLVED (last 24h): {len(resolved)}")
        for inv in resolved[:5]:
            lines.append(f"  {_row_client(inv)}  {_row_amount(inv)}  {_resolved_note(inv)}")
        lines.append("")

    if watching_n:
        lines.append(f"Also watching {watching_n} open invoice{'s' if watching_n != 1 else ''} (no action needed).")
        lines.append("")

    dash = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    if dash:
        lines.append(f"Open dashboard: {dash}/dashboard")
    body_text = "\n".join(lines)

    # --------- HTML -------------------------------------------------------
    BRAND = "#114B3F"
    CREAM = "#F7F5F0"
    INK = "#142824"
    MUTED = "#5A6B66"
    BORDER = "#E4E0D8"

    def html_section(title: str, rows: list, note_fn) -> str:
        if not rows:
            return ""
        head = (
            f"<tr>"
            f"<td style='padding:10px 12px;font-size:11px;font-weight:700;letter-spacing:.06em;"
            f"text-transform:uppercase;color:{MUTED};border-bottom:1px solid {BORDER}'>Client</td>"
            f"<td style='padding:10px 12px;font-size:11px;font-weight:700;letter-spacing:.06em;"
            f"text-transform:uppercase;color:{MUTED};border-bottom:1px solid {BORDER};text-align:right'>Amount</td>"
            f"<td style='padding:10px 12px;font-size:11px;font-weight:700;letter-spacing:.06em;"
            f"text-transform:uppercase;color:{MUTED};border-bottom:1px solid {BORDER}'>Detail</td>"
            f"</tr>"
        )
        body_rows = []
        for row in rows[:12]:
            client = html.escape(_row_client(row))
            ref = row.get("invoice_ref")
            if ref:
                client = (
                    f"{client}<br>"
                    f"<span style='font-size:12px;color:{MUTED}'>{html.escape(str(ref))}</span>"
                )
            body_rows.append(
                "<tr>"
                f"<td style='padding:12px;border-bottom:1px solid {BORDER};color:{INK};font-size:14px;"
                f"vertical-align:top'>{client}</td>"
                f"<td style='padding:12px;border-bottom:1px solid {BORDER};color:{INK};font-size:14px;"
                f"font-weight:600;text-align:right;white-space:nowrap;vertical-align:top;"
                f"font-variant-numeric:tabular-nums'>{html.escape(_row_amount(row))}</td>"
                f"<td style='padding:12px;border-bottom:1px solid {BORDER};color:{MUTED};font-size:13px;"
                f"vertical-align:top'>{html.escape(note_fn(row) or '')}</td>"
                "</tr>"
            )
        more = ""
        if len(rows) > 12:
            more = (
                f"<div style='padding:10px 12px;font-size:12px;color:{MUTED}'>"
                f"And {len(rows) - 12} more in this section</div>"
            )
        return (
            f"<div style='margin:0 0 22px 0'>"
            f"<div style='margin:0 0 8px 0;font-size:15px;font-weight:700;color:{INK}'>"
            f"{html.escape(title)}"
            f"<span style='margin-left:8px;display:inline-block;padding:2px 8px;border-radius:999px;"
            f"background:{CREAM};color:{BRAND};font-size:12px;font-weight:700'>{len(rows)}</span>"
            f"</div>"
            f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
            f"style='width:100%;border-collapse:collapse;background:#ffffff;"
            f"border:1px solid {BORDER};border-radius:10px;overflow:hidden'>"
            f"{head}{''.join(body_rows)}</table>{more}</div>"
        )

    summary_chips = []
    chip_defs = [
        ("Past due", totals.get("due_overdue") or 0),
        ("Broken", totals.get("broken_promises") or 0),
        ("Confirm", totals.get("confirm_prompts") or 0),
        ("Quiet", totals.get("stale_prompts") or 0),
        ("Reply", totals.get("needs_reply") or 0),
        ("Follow-up", totals.get("followup_prompts") or 0),
    ]
    for label, n in chip_defs:
        if not n:
            continue
        summary_chips.append(
            f"<span style='display:inline-block;margin:0 8px 8px 0;padding:6px 10px;"
            f"border-radius:8px;background:{CREAM};color:{INK};font-size:13px'>"
            f"<b>{n}</b> {html.escape(label)}</span>"
        )

    hero_line = (
        f"{actions} item{'s' if actions != 1 else ''} need your attention"
        if actions
        else "You're caught up — nothing needs action today."
    )

    sections_html = "".join(html_section(t, rows, fn) for t, rows, fn in buckets)

    resolved_html = ""
    if resolved:
        bits = ", ".join(
            f"{html.escape(_row_client(i))} ({html.escape(_row_amount(i))})"
            for i in resolved[:5]
        )
        extra = f" +{len(resolved) - 5} more" if len(resolved) > 5 else ""
        resolved_html = (
            f"<div style='margin:0 0 22px 0;padding:12px 14px;border-radius:10px;"
            f"background:#ECF6F1;color:{BRAND};font-size:13px'>"
            f"<b>Resolved in the last 24h ({len(resolved)}):</b> {bits}{extra}"
            f"</div>"
        )

    watching_html = ""
    if watching_n:
        watching_html = (
            f"<div style='margin:0 0 22px 0;font-size:13px;color:{MUTED}'>"
            f"Also watching <b style='color:{INK}'>{watching_n}</b> open invoice"
            f"{'s' if watching_n != 1 else ''} — no action needed."
            f"</div>"
        )

    at_risk_html = ""
    if totals.get("total_open_amount") and (totals.get("due_overdue") or totals.get("broken_promises")):
        at_risk_html = (
            f"<div style='margin:0 0 22px 0;padding:14px 16px;border-radius:10px;"
            f"border:1px solid {BORDER};background:#fff'>"
            f"<div style='font-size:12px;color:{MUTED};text-transform:uppercase;"
            f"letter-spacing:.06em;font-weight:700'>At risk right now</div>"
            f"<div style='margin-top:4px;font-size:22px;font-weight:700;color:{INK};"
            f"font-variant-numeric:tabular-nums'>"
            f"{html.escape(_fmt_money(totals['total_open_amount']))}</div>"
            f"<div style='margin-top:2px;font-size:12px;color:{MUTED}'>"
            f"Past due + broken promises</div></div>"
        )

    cta = ""
    if dash:
        cta = (
            f"<div style='margin:28px 0 8px 0'>"
            f"<a href='{html.escape(dash)}/dashboard' "
            f"style='display:inline-block;padding:12px 18px;background:{BRAND};color:#F7F5F0;"
            f"text-decoration:none;border-radius:10px;font-size:14px;font-weight:600'>"
            f"Open Scotive dashboard</a></div>"
        )

    logo_url = _digest_logo_url()
    # Prefer CID (attached inline); fall back to hosted URL if attach fails at send time.
    logo_src = f"cid:{_LOGO_CID}" if _digest_logo_bytes() else (logo_url or "")
    if logo_src:
        brand_header = (
            f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' style='margin:0 0 4px 0'>"
            f"<tr>"
            f"<td style='vertical-align:middle;padding:0 10px 0 0'>"
            f"<img src='{html.escape(logo_src)}' width='36' height='36' alt='Scotive' "
            f"style='display:block;width:36px;height:36px;border:0;border-radius:8px;'/>"
            f"</td>"
            f"<td style='vertical-align:middle;'>"
            f"<div style='font-size:16px;font-weight:700;color:{BRAND};letter-spacing:-0.01em;line-height:1.2;'>Scotive</div>"
            f"<div style='font-size:12px;color:{MUTED};margin-top:2px;'>Daily digest</div>"
            f"</td>"
            f"</tr></table>"
        )
    else:
        brand_header = (
            f"<div style='font-size:13px;font-weight:700;color:{BRAND};letter-spacing:.04em;'>SCOTIVE</div>"
        )

    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{CREAM};color:{INK};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:640px;margin:0 auto;padding:28px 16px 40px 16px;">
    {brand_header}
    <div style="margin-top:14px;font-size:12px;color:{MUTED};">{html.escape(date_str)}</div>
    <h1 style="margin:8px 0 8px 0;font-size:24px;line-height:1.25;color:{INK};font-weight:700;">
      {html.escape(hero_line)}
    </h1>
    <div style="margin:12px 0 24px 0;">{"".join(summary_chips)}</div>
    {at_risk_html}
    {sections_html}
    {resolved_html}
    {watching_html}
    {cta}
    <div style="margin-top:28px;padding-top:16px;border-top:1px solid {BORDER};font-size:11px;color:{MUTED};line-height:1.5;">
      Sent by Scotive to {html.escape(user.get("email") or "you")}.
      You can turn this off anytime in Settings → Daily digest.
    </div>
  </div>
</body>
</html>"""

    return {"subject": subject, "body_text": body_text, "body_html": body_html}


def _mime_message(from_addr, to_addr, subject, body_text, body_html) -> bytes:
    """Build a proper MIME message with RFC 2047-encoded subject + inline logo."""
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    logo = _digest_logo_bytes()
    if logo:
        # Attach as related to the HTML part so cid:scotive-logo@scotive resolves.
        html_part = msg.get_payload()[-1]
        html_part.add_related(
            logo,
            maintype="image",
            subtype="png",
            cid=_LOGO_CID,
            filename="scotive-icon.png",
            disposition="inline",
        )
    return msg.as_bytes()


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
    if (totals["due_overdue"] + totals["broken_promises"] + totals["needs_reply"]
            + totals["resolved"] + totals.get("watching", 0) + totals.get("followup_prompts", 0)) == 0:
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
    encoded = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

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
    """Iterate every connected user whose digest is due (opt-in + current hour matches
    in the user's configured IANA timezone)."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    now_utc = datetime.now(timezone.utc)
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
        # Target hour lives in the user's local timezone. Backward compat: fall
        # back to the legacy `daily_digest_hour_utc` field so old rows keep working.
        target_hour = settings.get("daily_digest_hour")
        if target_hour is None:
            target_hour = settings.get("daily_digest_hour_utc", 9)
        target_hour = int(target_hour)
        tz_name = settings.get("daily_digest_timezone", "UTC") or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, Exception):
            tz = timezone.utc
        local_hour = now_utc.astimezone(tz).hour
        if local_hour != target_hour:
            totals["skipped"] += 1
            continue
        res = await send_digest_for_user(db, uid)
        if res.get("status") == "sent":
            totals["sent"] += 1
        else:
            totals["skipped"] += 1
    return totals
