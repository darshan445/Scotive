"""Cross-domain client identity: detect likely duplicates and apply user merges."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from ledger_reconcile import (
    client_identity_key,
    dedupe_existing_invoices,
    pick_display_name,
    pick_primary_email,
    sender_domain,
)

logger = logging.getLogger("scotive.client_merge")

NAME_STOPWORDS = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|plc|gmbh|sa|pty)\b",
    re.I,
)


def normalize_client_name(name: str | None) -> str:
    if not name or not str(name).strip():
        return ""
    s = re.sub(r"[^\w\s]", " ", str(name).lower())
    s = NAME_STOPWORDS.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _key_domain(key: str) -> str:
    if key.startswith("domain:"):
        return key[7:]
    if key.startswith("email:"):
        return sender_domain(key[6:])
    return ""


def keys_are_cross_domain(key_a: str, key_b: str) -> bool:
    if key_a == key_b:
        return False
    da, db_ = _key_domain(key_a), _key_domain(key_b)
    if not da or not db_:
        return True
    return da != db_


def pair_key(keys: list[str]) -> str:
    return "|".join(sorted(set(keys)))


async def resolve_client_key_for_user(db, user_id, email: str) -> str:
    """Map an email to its canonical client_identity_key after user merges."""
    base = client_identity_key(email)
    row = await db.client_merges.find_one({"user_id": user_id, "alias_keys": base})
    return row["canonical_key"] if row else base


async def load_alias_map(db, user_id) -> dict[str, str]:
    out: dict[str, str] = {}
    async for row in db.client_merges.find({"user_id": user_id}):
        canonical = row.get("canonical_key")
        if not canonical:
            continue
        for alias in row.get("alias_keys") or []:
            out[alias] = canonical
    return out


async def _client_profiles(db, user_id) -> dict[str, dict[str, Any]]:
    """Aggregate invoice rows into per client_identity_key profiles."""
    profiles: dict[str, dict[str, Any]] = {}
    async for inv in db.invoices.find({"user_id": user_id}):
        key = inv.get("client_identity_key") or client_identity_key(inv.get("counterparty_email") or "")
        if key not in profiles:
            profiles[key] = {
                "client_key": key,
                "emails": set(),
                "names": [],
                "invoice_refs": set(),
                "amount_refs": set(),
            }
        p = profiles[key]
        em = (inv.get("counterparty_email") or "").lower().strip()
        if em:
            p["emails"].add(em)
        if inv.get("counterparty_name"):
            p["names"].append(inv["counterparty_name"])
        ref = inv.get("invoice_ref_normalized") or inv.get("invoice_ref")
        if ref:
            p["invoice_refs"].add(str(ref).upper())
            amt = inv.get("amount")
            cur = (inv.get("currency") or "USD").upper()
            if amt is not None:
                p["amount_refs"].add((str(ref).upper(), round(float(amt), 2), cur))
    return profiles


async def _is_pair_blocked(db, user_id, keys: list[str]) -> bool:
    pk = pair_key(keys)
    if await db.client_merge_prompts.find_one(
        {"user_id": user_id, "pair_key": pk, "status": "dismissed"},
    ):
        return True
    alias_map = await load_alias_map(db, user_id)
    resolved = {alias_map.get(k, k) for k in keys}
    return len(resolved) < 2


async def detect_cross_domain_merge_prompts(db, user_id) -> int:
    """Surface one-time merge prompts for likely same-client cross-domain identities."""
    profiles = await _client_profiles(db, user_id)
    if len(profiles) < 2:
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    created = 0
    seen_pairs: set[str] = set()

    # Heuristic 1: same normalized company name across different domains
    by_name: dict[str, list[str]] = {}
    for key, p in profiles.items():
        norm = normalize_client_name(pick_display_name(p["names"]))
        if len(norm) < 3:
            continue
        by_name.setdefault(norm, []).append(key)

    for norm, keys in by_name.items():
        unique = list(dict.fromkeys(keys))
        if len(unique) < 2:
            continue
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                ka, kb = unique[i], unique[j]
                if not keys_are_cross_domain(ka, kb):
                    continue
                pk = pair_key([ka, kb])
                if pk in seen_pairs:
                    continue
                seen_pairs.add(pk)
                if await _is_pair_blocked(db, user_id, [ka, kb]):
                    continue
                if await db.client_merge_prompts.find_one(
                    {"user_id": user_id, "pair_key": pk, "status": "pending"},
                ):
                    continue
                pa, pb = profiles[ka], profiles[kb]
                emails = sorted(pa["emails"] | pb["emails"])
                display = pick_display_name(pa["names"] + pb["names"]) or norm.title()
                await db.client_merge_prompts.insert_one({
                    "user_id": user_id,
                    "pair_key": pk,
                    "status": "pending",
                    "keys": [ka, kb],
                    "emails": emails,
                    "display_name": display,
                    "match_reason": "same_name",
                    "match_label": f"Both appear as “{display}”",
                    "created_at": now_iso,
                })
                created += 1

    # Heuristic 2: same invoice # + amount on different client keys
    ref_index: dict[tuple, list[str]] = {}
    for key, p in profiles.items():
        for triple in p["amount_refs"]:
            ref_index.setdefault(triple, []).append(key)

    for triple, keys in ref_index.items():
        unique = list(dict.fromkeys(keys))
        if len(unique) < 2:
            continue
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                ka, kb = unique[i], unique[j]
                if not keys_are_cross_domain(ka, kb):
                    continue
                pk = pair_key([ka, kb])
                if pk in seen_pairs:
                    continue
                seen_pairs.add(pk)
                if await _is_pair_blocked(db, user_id, [ka, kb]):
                    continue
                if await db.client_merge_prompts.find_one(
                    {"user_id": user_id, "pair_key": pk, "status": "pending"},
                ):
                    continue
                ref, amt, cur = triple
                pa, pb = profiles[ka], profiles[kb]
                emails = sorted(pa["emails"] | pb["emails"])
                display = pick_display_name(pa["names"] + pb["names"]) or ref
                await db.client_merge_prompts.insert_one({
                    "user_id": user_id,
                    "pair_key": pk,
                    "status": "pending",
                    "keys": [ka, kb],
                    "emails": emails,
                    "display_name": display,
                    "match_reason": "same_invoice",
                    "match_label": f"Same invoice {ref} · {amt} {cur}",
                    "created_at": now_iso,
                })
                created += 1

    if created:
        logger.info("merge prompts user=%s created=%s", user_id, created)
    return created


async def list_pending_merge_prompts(db, user_id) -> list[dict]:
    rows = []
    async for doc in db.client_merge_prompts.find(
        {"user_id": user_id, "status": "pending"},
    ).sort("created_at", -1):
        rows.append({
            "_id": str(doc["_id"]),
            "keys": doc.get("keys") or [],
            "emails": doc.get("emails") or [],
            "display_name": doc.get("display_name"),
            "match_reason": doc.get("match_reason"),
            "match_label": doc.get("match_label"),
            "created_at": doc.get("created_at"),
        })
    return rows


async def apply_client_merge(db, user_id, prompt_id: str) -> dict:
    try:
        prompt = await db.client_merge_prompts.find_one(
            {"_id": ObjectId(prompt_id), "user_id": user_id, "status": "pending"},
        )
    except Exception:
        raise ValueError("Prompt not found")
    if not prompt:
        raise ValueError("Prompt not found")

    keys = list(prompt.get("keys") or [])
    emails = list(prompt.get("emails") or [])
    if len(keys) < 2:
        raise ValueError("Invalid merge prompt")

    primary_email = pick_primary_email(emails) if emails else ""
    canonical_key = client_identity_key(primary_email) if primary_email else keys[0]
    if canonical_key not in keys:
        canonical_key = keys[0]
    keys_to_remap = [k for k in keys if k != canonical_key]

    now_iso = datetime.now(timezone.utc).isoformat()
    all_keys = list(dict.fromkeys(keys))

    for alias in keys_to_remap:
        await db.invoices.update_many(
            {"user_id": user_id, "client_identity_key": alias},
            {"$set": {"client_identity_key": canonical_key, "updated_at": now_iso}},
        )

    existing = await db.client_merges.find_one({"user_id": user_id, "canonical_key": canonical_key})
    if existing:
        merged_aliases = list(dict.fromkeys((existing.get("alias_keys") or []) + keys_to_remap))
        await db.client_merges.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "alias_keys": merged_aliases,
                "emails": list(dict.fromkeys((existing.get("emails") or []) + emails)),
                "updated_at": now_iso,
            }},
        )
    else:
        await db.client_merges.insert_one({
            "user_id": user_id,
            "canonical_key": canonical_key,
            "alias_keys": keys_to_remap,
            "primary_email": primary_email,
            "display_name": prompt.get("display_name"),
            "emails": emails,
            "merged_at": now_iso,
        })

    deduped = await dedupe_existing_invoices(db, user_id, now_iso)

    await db.client_merge_prompts.update_one(
        {"_id": prompt["_id"]},
        {"$set": {"status": "merged", "resolved_at": now_iso, "canonical_key": canonical_key}},
    )
    # Close duplicate pending prompts involving merged keys
    await db.client_merge_prompts.update_many(
        {
            "user_id": user_id,
            "status": "pending",
            "_id": {"$ne": prompt["_id"]},
            "keys": {"$elemMatch": {"$in": all_keys}},
        },
        {"$set": {"status": "superseded", "resolved_at": now_iso}},
    )

    return {"canonical_key": canonical_key, "invoices_deduped": deduped}


async def dismiss_merge_prompt(db, user_id, prompt_id: str) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    res = await db.client_merge_prompts.update_one(
        {"_id": ObjectId(prompt_id), "user_id": user_id, "status": "pending"},
        {"$set": {"status": "dismissed", "resolved_at": now_iso}},
    )
    if res.matched_count == 0:
        raise ValueError("Prompt not found")


async def resolve_canonical_key_for_lookup(db, user_id, email: str) -> str:
    """Resolve email → canonical client key for client detail queries."""
    base = client_identity_key(email)
    row = await db.client_merges.find_one({
        "user_id": user_id,
        "$or": [{"canonical_key": base}, {"alias_keys": base}],
    })
    if row:
        return row["canonical_key"]
    return base
