"""QuickBooks Online Accounting API client (read helpers for Module 2+)."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger("scotive.qbo_client")

QBO_MINOR_VERSION = int(os.environ.get("QBO_MINOR_VERSION", "75"))
PAGE_SIZE = 100


def extract_intuit_tid(response: httpx.Response) -> str:
    """Intuit correlation id from response headers (for support / troubleshooting)."""
    if response is None:
        return ""
    headers = response.headers
    for key in ("intuit_tid", "intuit-tid", "Intuit_Tid", "Intuit-Tid"):
        val = headers.get(key)
        if val:
            return str(val).strip()
    # httpx headers are case-insensitive; try common form once more
    return (headers.get("intuit_tid") or headers.get("intuit-tid") or "").strip()


def api_base_url(env: Optional[str] = None) -> str:
    e = (env or os.environ.get("QBO_ENV") or "sandbox").strip().lower()
    if e == "production":
        return "https://quickbooks.api.intuit.com"
    return "https://sandbox-quickbooks.api.intuit.com"


async def qbo_query(
    access_token: str,
    realm_id: str,
    sql: str,
    *,
    env: Optional[str] = None,
    include: Optional[str] = None,
) -> dict[str, Any]:
    """Run a QBO query; returns parsed QueryResponse (or empty dict)."""
    base = api_base_url(env)
    url = (
        f"{base}/v3/company/{realm_id}/query"
        f"?query={quote(sql)}&minorversion={QBO_MINOR_VERSION}"
    )
    if include:
        url += f"&include={include}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.get(url, headers=headers)
        tid = extract_intuit_tid(r)
        if r.status_code != 200:
            logger.warning(
                "QBO query failed: %s intuit_tid=%s %s | sql=%s",
                r.status_code, tid or "-", r.text[:500], sql[:200],
            )
            r.raise_for_status()
        if tid:
            logger.debug("QBO query ok intuit_tid=%s", tid)
        data = r.json()
        return data.get("QueryResponse") or {}


async def qbo_get(
    access_token: str,
    realm_id: str,
    path: str,
    *,
    env: Optional[str] = None,
    include: Optional[str] = None,
) -> dict[str, Any]:
    base = api_base_url(env)
    url = f"{base}/v3/company/{realm_id}/{path.lstrip('/')}?minorversion={QBO_MINOR_VERSION}"
    if include:
        url += f"&include={include}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers)
        tid = extract_intuit_tid(r)
        if r.status_code != 200:
            logger.warning(
                "QBO GET failed: %s intuit_tid=%s %s | path=%s",
                r.status_code, tid or "-", r.text[:500], path,
            )
            r.raise_for_status()
        if tid:
            logger.debug("QBO GET ok intuit_tid=%s path=%s", tid, path)
        return r.json()


async def qbo_post(
    access_token: str,
    realm_id: str,
    path: str,
    body: dict[str, Any],
    *,
    env: Optional[str] = None,
) -> dict[str, Any]:
    """POST JSON to a QBO resource (e.g. payment to zero an invoice balance)."""
    base = api_base_url(env)
    url = f"{base}/v3/company/{realm_id}/{path.lstrip('/')}?minorversion={QBO_MINOR_VERSION}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.post(url, headers=headers, json=body)
        tid = extract_intuit_tid(r)
        if r.status_code not in (200, 201):
            logger.warning(
                "QBO POST failed: %s intuit_tid=%s %s | path=%s",
                r.status_code, tid or "-", r.text[:800], path,
            )
            r.raise_for_status()
        if tid:
            logger.debug("QBO POST ok intuit_tid=%s path=%s", tid, path)
        return r.json()


async def resolve_undeposited_funds_account_id(
    access_token: str,
    realm_id: str,
    *,
    env: Optional[str] = None,
) -> Optional[str]:
    """Account Id for Undeposited Funds (typical deposit target when marking invoice paid)."""
    sql = (
        "SELECT Id, Name, AccountType FROM Account "
        "WHERE AccountType = 'Other Current Asset' AND Name = 'Undeposited Funds'"
    )
    try:
        qr = await qbo_query(access_token, realm_id, sql, env=env)
        rows = qr.get("Account") or []
        if isinstance(rows, dict):
            rows = [rows]
        if rows:
            return str(rows[0].get("Id") or "") or None
    except Exception as e:
        logger.warning("QBO Undeposited Funds lookup failed: %s", e)
    # Fallback: any Other Current Asset named like undeposited
    try:
        qr = await qbo_query(
            access_token, realm_id,
            "SELECT Id, Name FROM Account WHERE AccountType = 'Other Current Asset' MAXRESULTS 20",
            env=env,
        )
        rows = qr.get("Account") or []
        if isinstance(rows, dict):
            rows = [rows]
        for row in rows:
            name = (row.get("Name") or "").lower()
            if "undeposited" in name:
                return str(row.get("Id") or "") or None
    except Exception as e:
        logger.warning("QBO account fallback lookup failed: %s", e)
    return None


async def create_payment_against_invoice(
    access_token: str,
    realm_id: str,
    *,
    customer_id: str,
    invoice_id: str,
    amount: float,
    deposit_account_id: str,
    txn_date: Optional[str] = None,
    private_note: Optional[str] = None,
    env: Optional[str] = None,
) -> dict[str, Any]:
    """Link a Payment to an Invoice so QBO Balance drops (marks invoice paid/partial).

    QBO has no writable Invoice.Status=Paid — Balance is updated only via Payment.
    """
    amt = round(float(amount), 2)
    if amt <= 0:
        raise ValueError("Payment amount must be positive")
    body: dict[str, Any] = {
        "TotalAmt": amt,
        "CustomerRef": {"value": str(customer_id)},
        "DepositToAccountRef": {"value": str(deposit_account_id)},
        "Line": [{
            "Amount": amt,
            "LinkedTxn": [{
                "TxnId": str(invoice_id),
                "TxnType": "Invoice",
            }],
        }],
        "PrivateNote": (private_note or "Marked paid in Scotive")[:4000],
    }
    if txn_date:
        body["TxnDate"] = txn_date[:10]
    data = await qbo_post(access_token, realm_id, "payment", body, env=env)
    return data.get("Payment") or data


async def list_invoices(
    access_token: str,
    realm_id: str,
    *,
    env: Optional[str] = None,
) -> list[dict[str, Any]]:
    """All Invoice entities (any balance / status), paginated."""
    out: list[dict[str, Any]] = []
    start = 1
    while True:
        sql = (
            "SELECT * FROM Invoice "
            f"ORDERBY MetaData.LastUpdatedTime "
            f"STARTPOSITION {start} MAXRESULTS {PAGE_SIZE}"
        )
        try:
            qr = await qbo_query(
                access_token, realm_id, sql, env=env, include="invoiceLink",
            )
        except Exception as e:
            logger.warning("QBO list invoices with invoiceLink failed (%s); retrying without", e)
            qr = await qbo_query(access_token, realm_id, sql, env=env)
        batch = qr.get("Invoice") or []
        if isinstance(batch, dict):
            batch = [batch]
        out.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return out


async def list_unpaid_invoices(
    access_token: str,
    realm_id: str,
    *,
    env: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Compatibility alias — import now pulls every invoice, not only unpaid."""
    return await list_invoices(access_token, realm_id, env=env)


async def fetch_customers_by_ids(
    access_token: str,
    realm_id: str,
    customer_ids: list[str],
    *,
    env: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """Return map CustomerId -> Customer entity."""
    ids = [str(i) for i in customer_ids if i]
    if not ids:
        return {}
    result: dict[str, dict[str, Any]] = {}
    # QBO IN clause — batch to keep query length reasonable
    chunk_size = 40
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        quoted = ", ".join(f"'{cid}'" for cid in chunk)
        sql = (
            "SELECT Id, DisplayName, PrimaryEmailAddr, CompanyName "
            f"FROM Customer WHERE Id IN ({quoted})"
        )
        try:
            qr = await qbo_query(access_token, realm_id, sql, env=env)
            rows = qr.get("Customer") or []
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                cid = str(row.get("Id") or "")
                if cid:
                    result[cid] = row
        except Exception as e:
            logger.warning("QBO customer batch query failed (%s); falling back to GET", e)
            for cid in chunk:
                if cid in result:
                    continue
                try:
                    data = await qbo_get(
                        access_token, realm_id, f"customer/{cid}", env=env,
                    )
                    cust = data.get("Customer") or data
                    if cust.get("Id"):
                        result[str(cust["Id"])] = cust
                except Exception as ge:
                    logger.warning("QBO customer %s fetch failed: %s", cid, ge)
    return result


async def fetch_invoices_by_ids(
    access_token: str,
    realm_id: str,
    invoice_ids: list[str],
    *,
    env: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """Return map QBO Invoice Id -> Invoice entity (for Balance / paid checks)."""
    ids = [str(i) for i in invoice_ids if i]
    if not ids:
        return {}
    result: dict[str, dict[str, Any]] = {}
    chunk_size = 40
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        quoted = ", ".join(f"'{iid}'" for iid in chunk)
        sql = f"SELECT * FROM Invoice WHERE Id IN ({quoted})"
        try:
            qr = await qbo_query(
                access_token, realm_id, sql, env=env, include="invoiceLink",
            )
            rows = qr.get("Invoice") or []
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                iid = str(row.get("Id") or "")
                if iid:
                    result[iid] = row
        except Exception as e:
            logger.warning("QBO invoice batch query failed (%s); falling back to GET", e)
            for iid in chunk:
                if iid in result:
                    continue
                try:
                    data = await qbo_get(
                        access_token, realm_id, f"invoice/{iid}", env=env,
                        include="invoiceLink",
                    )
                    inv = data.get("Invoice") or data
                    if inv.get("Id"):
                        result[str(inv["Id"])] = inv
                except Exception as ge:
                    logger.warning("QBO invoice %s fetch failed: %s", iid, ge)
    return result


async def cdc_changes(
    access_token: str,
    realm_id: str,
    entities: list[str],
    changed_since: str,
    *,
    env: Optional[str] = None,
) -> dict[str, list[dict[str, Any]]]:
    """Change Data Capture — entities changed since ISO timestamp (max ~30 days).

    Returns map entity name -> list of entity dicts (may include status=Deleted).
    """
    base = api_base_url(env)
    ent = ",".join(entities)
    # QBO accepts ISO-8601; strip overly long fractional seconds if present
    since = (changed_since or "").strip()
    if since.endswith("Z") and "." in since:
        # keep millis ok; leave as-is
        pass
    url = (
        f"{base}/v3/company/{realm_id}/cdc"
        f"?entities={quote(ent)}&changedSince={quote(since)}"
        f"&minorversion={QBO_MINOR_VERSION}"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.get(url, headers=headers)
        tid = extract_intuit_tid(r)
        if r.status_code != 200:
            logger.warning(
                "QBO CDC failed: %s intuit_tid=%s %s",
                r.status_code, tid or "-", r.text[:500],
            )
            r.raise_for_status()
        if tid:
            logger.debug("QBO CDC ok intuit_tid=%s", tid)
        data = r.json()

    out: dict[str, list[dict[str, Any]]] = {e: [] for e in entities}
    # Shape: CDCResponse: [ { QueryResponse: { Invoice: [...], ... } } ]
    responses = data.get("CDCResponse") or []
    if isinstance(responses, dict):
        responses = [responses]
    for block in responses:
        qr = block.get("QueryResponse") or {}
        if isinstance(qr, list):
            for part in qr:
                if not isinstance(part, dict):
                    continue
                for key, val in part.items():
                    if key not in out:
                        continue
                    rows = val if isinstance(val, list) else [val]
                    out[key].extend(rows)
            continue
        if isinstance(qr, dict):
            for key, val in qr.items():
                if key not in out:
                    continue
                rows = val if isinstance(val, list) else ([val] if val else [])
                out[key].extend(rows)
    return out


async def fetch_company_info(
    access_token: str,
    realm_id: str,
    *,
    env: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    try:
        data = await qbo_get(
            access_token, realm_id, f"companyinfo/{realm_id}", env=env,
        )
        return data.get("CompanyInfo") or data
    except Exception as e:
        logger.warning("QBO CompanyInfo failed: %s", e)
        return None
