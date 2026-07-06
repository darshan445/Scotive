"""Cheap pre-AI filters for sent-mail invoice discovery."""
from __future__ import annotations

import re
from typing import Optional

from client_sweep import (
    _extract_email_addr,
    _is_vendor,
    _sender_domain,
    anchor_recipients,
    has_amount_token,
    is_mailing_list,
)

# Promo / marketing language in sent mail that is not client invoicing
PROMO_SUBJECT_RE = re.compile(
    r"unsubscribe|newsletter|webinar|black\s*friday|cyber\s*monday|"
    r"limited\s*time|%\s*off|discount\s*code|flash\s*sale|promo\b|"
    r"special\s*offer|join\s*us\s*live|free\s*trial\s*ending",
    re.I,
)

INVOICE_SIGNAL_RE = re.compile(
    r"invoice|payment\s+due|amount\s+due|balance\s+due|outstanding|"
    r"please\s+pay|please\s+transfer|kindly\s+transfer|send\s+payment|"
    r"net\s*\d+|remit|\btransfer\b|wire\s+transfer|ach\b|"
    r"statement|bill\s+for|services\s+rendered|hours\s+worked|"
    r"work\s+done|completed\s+the|as\s+discussed|payment\s+for",
    re.I,
)

GMAIL_PROMO_LABELS = frozenset({"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES"})


def seed_cheap_filter(
    msg: dict,
    my_email: str,
    blocklist: set[str],
) -> tuple[bool, str, Optional[str]]:
    """
    Return (keep, reason, client_email).

    Surviving messages proceed to PDF enrichment + AI — no amount required here.
    """
    my = my_email.lower()
    sender = _extract_email_addr(msg.get("from", ""))
    if sender != my:
        return False, "not_sent_by_user", None

    if is_mailing_list(msg):
        return False, "mailing_list", None

    labels = set(msg.get("label_ids") or [])
    if labels & GMAIL_PROMO_LABELS:
        subj = msg.get("subject") or ""
        body = " ".join([
            subj,
            msg.get("body") or "",
            msg.get("snippet") or "",
        ])
        if not INVOICE_SIGNAL_RE.search(body) and not msg.get("has_attachment") and not has_amount_token(msg):
            return False, "gmail_category_promo", None

    recipients = anchor_recipients(msg, my_email)
    if not recipients:
        return False, "no_recipient", None
    if len(recipients) > 10:
        return False, "bulk_send", None

    client = recipients[0].lower()
    domain = _sender_domain(client)
    if client in blocklist or domain in blocklist or _is_vendor(domain):
        return False, "blocked_client", None

    hay = " ".join([
        msg.get("subject") or "",
        msg.get("body") or "",
        msg.get("snippet") or "",
        " ".join(msg.get("attachment_names") or []),
    ])

    subj = msg.get("subject") or ""
    if PROMO_SUBJECT_RE.search(subj) and not INVOICE_SIGNAL_RE.search(hay):
        return False, "promo_subject", None

    if msg.get("has_attachment"):
        return True, "pdf_attachment", client
    if has_amount_token(msg):
        return True, "amount_token", client
    if INVOICE_SIGNAL_RE.search(hay):
        return True, "invoice_language", client

    return False, "no_invoice_signal", None
