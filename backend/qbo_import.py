"""Import unpaid QuickBooks invoices into the Scotive ledger (Module 2)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from client_merge import resolve_client_key_for_user
from invoice_lifecycle import apply_past_due_transitions
from ledger_reconcile import enrich_invoice_doc, find_invoice_by_key, normalize_invoice_ref
from qbo_client import fetch_company_info, fetch_customers_by_ids, list_unpaid_invoices
from qbo_oauth import QboAuthError, get_qbo_access_token

logger = logging.getLogger("scotive.qbo_import")


def _customer_email(customer: Optional[dict]) -> Optional[str]:
    if not customer:
        return None
    addr = customer.get("PrimaryEmailAddr") or {}
    if isinstance(addr, dict):
        raw = (addr.get("Address") or "").strip().lower()
        if raw and "@" in raw:
            return raw
    return None


def _customer_name(customer: Optional[dict], invoice: dict) -> Optional[str]:
    if customer:
        for key in ("DisplayName", "CompanyName", "FullyQualifiedName"):
            val = (customer.get(key) or "").strip()
            if val:
                return val
    ref = invoice.get("CustomerRef") or {}
    name = (ref.get("name") or "").strip()
    return name or None


def _qbo_date(raw: Any) -> Optional[str]:
    if not raw:
        return None
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def map_qbo_invoice_to_doc(
    invoice: dict,
    customer: Optional[dict],
    *,
    user_id,
    realm_id: str,
    now_iso: str,
) -> dict[str, Any]:
    qbo_id = str(invoice.get("Id") or "")
    cust_ref = invoice.get("CustomerRef") or {}
    qbo_customer_id = str(cust_ref.get("value") or "") or None
    email = _customer_email(customer)
    amount = float(invoice.get("TotalAmt") or 0)
    balance = float(invoice.get("Balance") or 0)
    if balance < 0:
        balance = 0.0
    paid = max(0.0, round(amount - balance, 2))
    currency = ((invoice.get("CurrencyRef") or {}).get("value") or "USD").upper()
    doc_number = (invoice.get("DocNumber") or "").strip() or None
    txn_date = _qbo_date(invoice.get("TxnDate"))
    due_date = _qbo_date(invoice.get("DueDate"))

    doc: dict[str, Any] = {
        "user_id": user_id,
        "qbo_id": qbo_id,
        "qbo_customer_id": qbo_customer_id,
        "qbo_realm_id": str(realm_id),
        "counterparty_email": email or "",
        "counterparty_name": _customer_name(customer, invoice),
        "amount": amount,
        "balance_remaining": balance,
        "paid_amount": paid,
        "currency": currency,
        "invoice_ref": doc_number,
        "due_date": due_date,
        "due_date_assumed": False,
        "source_date": txn_date or now_iso[:10],
        "source_message_id": f"qbo:{realm_id}:{qbo_id}",
        "source_thread_id": None,
        "source_subject": f"QuickBooks invoice {doc_number}" if doc_number else "QuickBooks invoice",
        "source": "quickbooks",
        "kind": "invoice_sent",
        "status": "invoiced",
        "confidence": 1.0,
        "evidence_sentence": "Imported from QuickBooks",
        "created_at": now_iso,
        "last_activity_at": now_iso,
        "updated_at": now_iso,
    }
    enrich_invoice_doc(doc, email or "")
    if not email and qbo_customer_id:
        doc["client_identity_key"] = f"qbo:customer:{qbo_customer_id}"
    elif not email:
        doc["client_identity_key"] = f"qbo:invoice:{realm_id}:{qbo_id}"
    # Ensure DocNumber survives normalize edge cases
    if doc_number and not doc.get("invoice_ref_normalized"):
        norm = normalize_invoice_ref(doc_number, None)
        if norm:
            doc["invoice_ref"] = doc_number
            doc["invoice_ref_normalized"] = norm
    return doc


async def upsert_qbo_ledger_invoice(
    db,
    user_id,
    doc: dict,
    *,
    now_iso: str,
) -> tuple[str, Any]:
    """Insert or update by qbo_id; merge onto Gmail row by ref when possible.

    Returns (created|updated|merged, invoice_id).
    """
    qbo_id = doc.get("qbo_id")
    if not qbo_id:
        raise ValueError("qbo_id required")

    email = (doc.get("counterparty_email") or "").strip().lower()
    if email:
        doc["client_identity_key"] = await resolve_client_key_for_user(db, user_id, email)

    existing = await db.invoices.find_one({"user_id": user_id, "qbo_id": qbo_id})
    merge_target = existing
    linking_gmail = False

    if not merge_target and doc.get("invoice_ref_normalized") and email:
        by_ref = await find_invoice_by_key(
            db, user_id, doc["client_identity_key"], doc["invoice_ref_normalized"],
        )
        if by_ref and not by_ref.get("qbo_id"):
            merge_target = by_ref
            linking_gmail = True

    money_fields = {
        "amount": doc["amount"],
        "balance_remaining": doc["balance_remaining"],
        "paid_amount": doc["paid_amount"],
        "currency": doc["currency"],
        "invoice_ref": doc.get("invoice_ref"),
        "invoice_ref_normalized": doc.get("invoice_ref_normalized"),
        "due_date": doc.get("due_date"),
        "due_date_assumed": False,
        "source_date": doc.get("source_date"),
        "counterparty_name": doc.get("counterparty_name"),
        "qbo_id": qbo_id,
        "qbo_customer_id": doc.get("qbo_customer_id"),
        "qbo_realm_id": doc.get("qbo_realm_id"),
        "source_message_id": doc.get("source_message_id"),
        "updated_at": now_iso,
        "last_activity_at": now_iso,
    }
    if email:
        money_fields["counterparty_email"] = email
        money_fields["client_identity_key"] = doc["client_identity_key"]
    elif doc.get("client_identity_key"):
        money_fields["client_identity_key"] = doc["client_identity_key"]

    if merge_target:
        if linking_gmail:
            action = "merged"
            new_source = "both"
        else:
            action = "updated"
            prev = merge_target.get("source") or "quickbooks"
            new_source = "both" if prev in ("gmail", "manual", "both") else "quickbooks"

        patch = {**money_fields, "source": new_source}
        await db.invoices.update_one({"_id": merge_target["_id"]}, {"$set": patch})
        await db.invoice_events.insert_one({
            "user_id": user_id,
            "invoice_id": merge_target["_id"],
            "action": "qbo_merge" if action == "merged" else "qbo_import",
            "at": now_iso,
            "meta": {
                "qbo_id": qbo_id,
                "outcome": action,
                "amount": doc["amount"],
                "balance_remaining": doc["balance_remaining"],
            },
        })
        return action, merge_target["_id"]

    insert_doc = dict(doc)
    insert_doc["source"] = "quickbooks"
    res = await db.invoices.insert_one(insert_doc)
    await db.invoice_events.insert_one({
        "user_id": user_id,
        "invoice_id": res.inserted_id,
        "action": "qbo_import",
        "at": now_iso,
        "meta": {
            "qbo_id": qbo_id,
            "outcome": "created",
            "amount": doc["amount"],
            "balance_remaining": doc["balance_remaining"],
        },
    })
    return "created", res.inserted_id


async def import_unpaid_invoices(db, user_id) -> dict[str, Any]:
    """Pull unpaid QBO invoices into the ledger. Idempotent by qbo_id."""
    conn = await db.qbo_connections.find_one({"user_id": user_id})
    if not conn or conn.get("status") != "connected":
        raise QboAuthError("No QuickBooks connection")

    realm_id = conn.get("realm_id")
    if not realm_id:
        raise QboAuthError("QuickBooks connection missing realm_id")

    env = conn.get("env")
    access = await get_qbo_access_token(db, user_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Company name backfill (best-effort)
    if not (conn.get("company_name") or "").strip():
        info = await fetch_company_info(access, realm_id, env=env)
        name = None
        if info:
            name = (info.get("CompanyName") or info.get("LegalName") or "").strip() or None
        if name:
            await db.qbo_connections.update_one(
                {"user_id": user_id},
                {"$set": {"company_name": name, "updated_at": now_iso}},
            )

    invoices = await list_unpaid_invoices(access, realm_id, env=env)
    cust_ids = []
    for inv in invoices:
        cid = ((inv.get("CustomerRef") or {}).get("value"))
        if cid:
            cust_ids.append(str(cid))
    customers = await fetch_customers_by_ids(access, realm_id, cust_ids, env=env)

    counts = {
        "fetched": len(invoices),
        "created": 0,
        "updated": 0,
        "merged": 0,
        "skipped": 0,
        "past_due_flipped": 0,
    }

    for inv in invoices:
        qbo_id = str(inv.get("Id") or "")
        if not qbo_id:
            counts["skipped"] += 1
            continue
        try:
            balance = float(inv.get("Balance") or 0)
        except (TypeError, ValueError):
            counts["skipped"] += 1
            continue
        if balance <= 0:
            counts["skipped"] += 1
            continue

        cid = str(((inv.get("CustomerRef") or {}).get("value")) or "")
        customer = customers.get(cid) if cid else None
        doc = map_qbo_invoice_to_doc(
            inv, customer, user_id=user_id, realm_id=realm_id, now_iso=now_iso,
        )
        try:
            outcome, _ = await upsert_qbo_ledger_invoice(db, user_id, doc, now_iso=now_iso)
            counts[outcome] = counts.get(outcome, 0) + 1
        except Exception as e:
            logger.exception("QBO upsert failed qbo_id=%s: %s", qbo_id, e)
            counts["skipped"] += 1

    counts["past_due_flipped"] = await apply_past_due_transitions(db, user_id)

    # Module 5: any previously-open QBO rows that are now Balance=0 → Paid.
    try:
        from qbo_paid_sync import sync_qbo_paid_status
        counts["qbo_paid"] = await sync_qbo_paid_status(db, user_id)
    except Exception as e:
        logger.exception("QBO paid sync after import failed: %s", e)
        counts["qbo_paid"] = {"errors": 1, "skipped": "exception"}

    # Module 4: conversation match + status re-eval runs in the background
    # so import / Next stay fast; dashboard shows pipeline progress.
    try:
        from qbo_conversation import enqueue_qbo_conversation_match
        counts["conversation_match"] = await enqueue_qbo_conversation_match(db, user_id)
    except Exception as e:
        logger.exception("QBO conversation match enqueue failed: %s", e)
        counts["conversation_match"] = {"errors": 1, "skipped": "exception"}

    await db.qbo_connections.update_one(
        {"user_id": user_id},
        {"$set": {"last_invoice_import_at": now_iso, "updated_at": now_iso}},
    )
    logger.info("QBO import user=%s counts=%s", user_id, counts)
    return counts
