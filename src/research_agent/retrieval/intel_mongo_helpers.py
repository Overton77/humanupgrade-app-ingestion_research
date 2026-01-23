from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, TypedDict

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase  # type: ignore[import]
from pymongo.errors import DuplicateKeyError


# -----------------------------------------------------------------------------
# Basics
# -----------------------------------------------------------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_jsonish(obj: Any) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


_slug_re = re.compile(r"[^a-z0-9]+")


def normalize_name(s: str) -> str:
    s = (s or "").strip().lower()
    s = _slug_re.sub(" ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_domain(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"https?://([^/]+)/?", url.strip().lower())
    if not m:
        return None
    host = m.group(1).replace("www.", "")
    return host


def compute_entity_key(
    *,
    type_: str,
    canonical_name: str,
    best_url: Optional[str],
    org_domain: Optional[str],
) -> str:
    t = type_.upper()
    name_norm = normalize_name(canonical_name)

    if t == "PERSON":
        return f"person:{name_norm}"

    if t in ("ORGANIZATION", "BUSINESS"):
        domain = normalize_domain(best_url or "") or org_domain
        if domain:
            return f"org:{domain}"
        return f"org:{name_norm}"

    if t == "PRODUCT":
        domain = normalize_domain(best_url or "") or org_domain or "unknown-org"
        return f"product:{domain}:{name_norm}"

    if t == "COMPOUND":
        return f"compound:{name_norm}"

    if t == "PLATFORM":
        domain = normalize_domain(best_url or "") or org_domain or "unknown-org"
        return f"platform:{domain}:{name_norm}"

    return f"{t.lower()}:{name_norm}"


# -----------------------------------------------------------------------------
# Collections
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class IntelCollections:
    candidate_runs: str = "intel_candidate_runs"
    candidate_entities: str = "intel_candidate_entities"
    dedupe_groups: str = "intel_dedupe_groups"
    research_plans: str = "intel_research_plans"


# -----------------------------------------------------------------------------
# Indexes (safe to call frequently; Mongo is idempotent for same index spec)
# -----------------------------------------------------------------------------

async def ensure_intel_indexes(db: AsyncDatabase) -> None:
    c = IntelCollections()

    # candidate runs
    await db[c.candidate_runs].create_index([("runId", 1)], unique=True)
    await db[c.candidate_runs].create_index([("episodeId", 1), ("createdAt", -1)])
    await db[c.candidate_runs].create_index([("pipelineVersion", 1), ("status", 1), ("createdAt", -1)])

    # candidate entities
    await db[c.candidate_entities].create_index([("candidateEntityId", 1)], unique=True)
    await db[c.candidate_entities].create_index([("runId", 1), ("type", 1)])
    await db[c.candidate_entities].create_index([("episodeId", 1), ("type", 1)])
    await db[c.candidate_entities].create_index([("type", 1), ("entityKey", 1)])
    await db[c.candidate_entities].create_index([("runId", 1), ("entityKey", 1)])

    # dedupe groups
    await db[c.dedupe_groups].create_index([("dedupeGroupId", 1)], unique=True)
    await db[c.dedupe_groups].create_index([("type", 1), ("entityKey", 1)], unique=True)

    # research plans
    await db[c.research_plans].create_index([("planId", 1)], unique=True)
    await db[c.research_plans].create_index([("episodeId", 1), ("createdAt", -1)])
    await db[c.research_plans].create_index([("status", 1), ("createdAt", -1)])
    await db[c.research_plans].create_index([("runId", 1)])
    await db[c.research_plans].create_index([("dedupeGroupIds", 1)])
    await db[c.research_plans].create_index([("bundleId", 1)])


# -----------------------------------------------------------------------------
# Run record helpers
# -----------------------------------------------------------------------------

async def upsert_candidate_run(
    *,
    db: AsyncDatabase,
    run_id: str,
    episode_id: str,
    episode_url: str,
    pipeline_version: str,
    status: str,
    payload: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    c = IntelCollections()

    update: Dict[str, Any] = {
        "$set": {
            "runId": run_id,
            "episodeId": episode_id,
            "episodeUrl": episode_url,
            "pipelineVersion": pipeline_version,
            "status": status,
            "updatedAt": utcnow(),
        },
        "$setOnInsert": {
            "createdAt": utcnow(),
        },
    }

    if payload is not None:
        update["$set"]["payload"] = payload
    if error:
        update["$set"]["error"] = error

    doc = await db[c.candidate_runs].find_one_and_update(
        {"runId": run_id},
        update,
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc


async def delete_candidate_entities_for_run(*, db: AsyncDatabase, run_id: str) -> None:
    c = IntelCollections()
    await db[c.candidate_entities].delete_many({"runId": run_id})


async def bulk_insert_candidate_entities(*, db: AsyncDatabase, docs: List[Dict[str, Any]]) -> None:
    if not docs:
        return
    c = IntelCollections()
    await db[c.candidate_entities].insert_many(docs, ordered=False)


# -----------------------------------------------------------------------------
# Dedupe group upsert (robust to duplicate key races)
# -----------------------------------------------------------------------------

async def upsert_dedupe_group_and_add_member(
    *,
    db: AsyncDatabase,
    type_: str,
    entity_key: str,
    canonical_name: str,
    member: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Idempotent:
      - creates group (unique: type+entityKey) if missing
      - adds member with $addToSet
    Handles race conditions with DuplicateKeyError.
    """
    c = IntelCollections()
    now = utcnow()
    selector = {"type": type_.upper(), "entityKey": entity_key}

    update = {
        "$setOnInsert": {
            "dedupeGroupId": str(uuid.uuid4()),
            "type": type_.upper(),
            "entityKey": entity_key,
            "canonicalName": canonical_name,
            "resolutionStatus": "unresolved",
            "createdAt": now,
        },
        "$set": {"updatedAt": now},
        "$addToSet": {"members": member},
    }

    try:
        doc = await db[c.dedupe_groups].find_one_and_update(
            selector,
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc
    except DuplicateKeyError:
        # Another worker created it concurrently; retry as pure update
        doc = await db[c.dedupe_groups].find_one_and_update(
            selector,
            {"$set": {"updatedAt": now}, "$addToSet": {"members": member}},
            upsert=False,
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            # extremely rare; last resort: fetch
            doc = await db[c.dedupe_groups].find_one(selector)
            if doc is None:
                raise
        return doc


# -----------------------------------------------------------------------------
# Research plans
# -----------------------------------------------------------------------------

async def upsert_research_plan(
    *,
    db: AsyncDatabase,
    plan_id: str,
    bundle_id: str,
    run_id: str,
    episode_id: str,
    episode_url: str,
    pipeline_version: str,
    dedupe_group_ids: List[str],
    directions: Dict[str, Any],
    status: str = "draft",
    targets: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    c = IntelCollections()
    now = utcnow()

    update: Dict[str, Any] = {
        "$set": {
            "planId": plan_id,
            "bundleId": bundle_id,
            "runId": run_id,
            "episodeId": episode_id,
            "episodeUrl": episode_url,
            "pipelineVersion": pipeline_version,
            "dedupeGroupIds": dedupe_group_ids,
            "directions": directions,
            "status": status,
            "updatedAt": now,
        },
        "$setOnInsert": {"createdAt": now},
    }
    if targets is not None:
        update["$set"]["targets"] = targets

    doc = await db[c.research_plans].find_one_and_update(
        {"planId": plan_id},
        update,
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc


# -----------------------------------------------------------------------------
# CandidateSourcesConnected flattening
# -----------------------------------------------------------------------------

def best_candidate_url(candidates: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    if not candidates:
        return None
    best = max(candidates, key=lambda x: (x.get("score", 0), -x.get("rank", 9999)))
    return best.get("url")


def flatten_connected_bundle_to_candidate_entities(
    *,
    episode: Dict[str, Any],
    run_id: str,
    pipeline_version: str,
    connected_bundle: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Flatten ONE connected bundle into many candidate entity docs.
    """
    episode_id = str(episode.get("id") or episode.get("_id") or "")
    episode_url = episode.get("episodePageUrl") or ""

    docs: List[Dict[str, Any]] = []

    # --- guest
    guest = connected_bundle.get("guest") or {}
    guest_type = (guest.get("typeHint") or "PERSON").upper()
    guest_canonical = guest.get("canonicalName") or guest.get("inputName") or "unknown"
    guest_best_url = best_candidate_url(guest.get("candidates"))
    guest_key = compute_entity_key(
        type_=guest_type,
        canonical_name=guest_canonical,
        best_url=guest_best_url,
        org_domain=None,
    )

    docs.append(
        {
            "candidateEntityId": str(uuid.uuid4()),
            "runId": run_id,
            "pipelineVersion": pipeline_version,
            "episodeId": episode_id,
            "episodeUrl": episode_url,
            "type": guest_type,
            "inputName": guest.get("inputName"),
            "normalizedName": guest.get("normalizedName"),
            "canonicalName": guest_canonical,
            "canonicalConfidence": guest.get("canonicalConfidence"),
            "entityKey": guest_key,
            "bestUrl": guest_best_url,
            "candidateSources": guest.get("candidates") or [],
            "notes": guest.get("notes"),
            "status": "new",
            "createdAt": utcnow(),
        }
    )

    # --- businesses
    for b in connected_bundle.get("businesses") or []:
        business = b.get("business") or {}
        b_type = (business.get("typeHint") or "ORGANIZATION").upper()
        b_canonical = business.get("canonicalName") or business.get("inputName") or "unknown"
        b_best_url = best_candidate_url(business.get("candidates"))
        b_domain = normalize_domain(b_best_url or "")
        b_key = compute_entity_key(type_=b_type, canonical_name=b_canonical, best_url=b_best_url, org_domain=b_domain)

        docs.append(
            {
                "candidateEntityId": str(uuid.uuid4()),
                "runId": run_id,
                "pipelineVersion": pipeline_version,
                "episodeId": episode_id,
                "episodeUrl": episode_url,
                "type": b_type,
                "inputName": business.get("inputName"),
                "normalizedName": business.get("normalizedName"),
                "canonicalName": b_canonical,
                "canonicalConfidence": business.get("canonicalConfidence"),
                "entityKey": b_key,
                "bestUrl": b_best_url,
                "candidateSources": business.get("candidates") or [],
                "notes": business.get("notes"),
                "status": "new",
                "createdAt": utcnow(),
            }
        )

        # --- products under business
        for p in b.get("products") or []:
            product = p.get("product") or {}
            p_type = (product.get("typeHint") or "PRODUCT").upper()
            p_canonical = product.get("canonicalName") or product.get("inputName") or "unknown"
            p_best_url = best_candidate_url(product.get("candidates"))
            p_key = compute_entity_key(type_=p_type, canonical_name=p_canonical, best_url=p_best_url, org_domain=b_domain)

            docs.append(
                {
                    "candidateEntityId": str(uuid.uuid4()),
                    "runId": run_id,
                    "pipelineVersion": pipeline_version,
                    "episodeId": episode_id,
                    "episodeUrl": episode_url,
                    "type": p_type,
                    "inputName": product.get("inputName"),
                    "normalizedName": product.get("normalizedName"),
                    "canonicalName": p_canonical,
                    "canonicalConfidence": product.get("canonicalConfidence"),
                    "entityKey": p_key,
                    "bestUrl": p_best_url,
                    "candidateSources": product.get("candidates") or [],
                    "notes": product.get("notes"),
                    "status": "new",
                    "createdAt": utcnow(),
                }
            )

            # --- compounds under product
            for comp in p.get("compounds") or []:
                c_type = (comp.get("typeHint") or "COMPOUND").upper()
                c_canonical = comp.get("canonicalName") or comp.get("inputName") or "unknown"
                c_best_url = best_candidate_url(comp.get("candidates"))
                c_key = compute_entity_key(type_=c_type, canonical_name=c_canonical, best_url=c_best_url, org_domain=b_domain)

                docs.append(
                    {
                        "candidateEntityId": str(uuid.uuid4()),
                        "runId": run_id,
                        "pipelineVersion": pipeline_version,
                        "episodeId": episode_id,
                        "episodeUrl": episode_url,
                        "type": c_type,
                        "inputName": comp.get("inputName"),
                        "normalizedName": comp.get("normalizedName"),
                        "canonicalName": c_canonical,
                        "canonicalConfidence": comp.get("canonicalConfidence"),
                        "entityKey": c_key,
                        "bestUrl": c_best_url,
                        "candidateSources": comp.get("candidates") or [],
                        "notes": comp.get("notes"),
                        "status": "new",
                        "createdAt": utcnow(),
                        "linkContext": {
                            "linkedFromProductEntityKey": p_key,
                            "linkNotes": p.get("compoundLinkNotes"),
                            "linkConfidence": p.get("compoundLinkConfidence"),
                        },
                    }
                )

        # --- platforms under business
        for platform in b.get("platforms") or []:
            pl_type = (platform.get("typeHint") or "PLATFORM").upper()
            pl_canonical = platform.get("canonicalName") or platform.get("inputName") or "unknown"
            pl_best_url = best_candidate_url(platform.get("candidates"))
            pl_key = compute_entity_key(type_=pl_type, canonical_name=pl_canonical, best_url=pl_best_url, org_domain=b_domain)

            docs.append(
                {
                    "candidateEntityId": str(uuid.uuid4()),
                    "runId": run_id,
                    "pipelineVersion": pipeline_version,
                    "episodeId": episode_id,
                    "episodeUrl": episode_url,
                    "type": pl_type,
                    "inputName": platform.get("inputName"),
                    "normalizedName": platform.get("normalizedName"),
                    "canonicalName": pl_canonical,
                    "canonicalConfidence": platform.get("canonicalConfidence"),
                    "entityKey": pl_key,
                    "bestUrl": pl_best_url,
                    "candidateSources": platform.get("candidates") or [],
                    "notes": platform.get("notes"),
                    "status": "new",
                    "createdAt": utcnow(),
                }
            )

    return docs


# -----------------------------------------------------------------------------
# Plan target resolution (THIS is how we fill dedupeGroupIds now)
# -----------------------------------------------------------------------------

class PlanTargets(TypedDict, total=False):
    guestCanonicalName: str
    businessNames: List[str]
    productNames: List[str]
    compoundNames: List[str]
    platformNames: List[str]


def extract_plan_targets_from_bundle(bundle: Dict[str, Any]) -> PlanTargets:
    targets: PlanTargets = {}

    gd = (((bundle.get("guestDirection") or {}).get("chosenDirection")) or {})
    if gd.get("guestCanonicalName"):
        targets["guestCanonicalName"] = gd["guestCanonicalName"]

    bd = (((bundle.get("businessDirection") or {}).get("chosenDirection")) or {})
    if bd.get("businessNames"):
        targets["businessNames"] = list(bd["businessNames"])

    pd = (((bundle.get("productsDirection") or {}).get("chosenDirection")) or {})
    if pd.get("productNames"):
        targets["productNames"] = list(pd["productNames"])

    cd = (((bundle.get("compoundsDirection") or {}).get("chosenDirection")) or {})
    if cd.get("compoundNames"):
        targets["compoundNames"] = list(cd["compoundNames"])

    pld = (((bundle.get("platformsDirection") or {}).get("chosenDirection")) or {})
    if pld.get("platformNames"):
        targets["platformNames"] = list(pld["platformNames"])

    return targets


def _canon_compound_name_for_matching(name: str) -> str:
    # compounds often come like "Spirulina (Arthrospira / blue-green algae)"
    # match on leading token before "("
    base = (name or "").split("(")[0].strip()
    return base


async def resolve_dedupe_group_ids_for_plan(
    *,
    db: AsyncDatabase,
    run_id: str,
    targets: PlanTargets,
) -> List[str]:
    """
    Resolve plan targets using the candidate entities from the SAME run_id.
    This avoids fuzzy global matching and is deterministic.

    Matching strategy:
      PERSON: canonicalName normalized equals guestCanonicalName normalized
      ORG: canonicalName normalized equals any businessNames normalized
      PRODUCT: canonicalName normalized equals any productNames normalized
      COMPOUND: canonicalName normalized equals base(compoundName) normalized
      PLATFORM: canonicalName normalized equals any platformNames normalized
    """
    c = IntelCollections()
    docs = await db[c.candidate_entities].find({"runId": run_id}).to_list(length=None)

    # build (type, normalized canonicalName) -> entityKey
    lookup: Dict[Tuple[str, str], str] = {}
    for d in docs:
        t = (d.get("type") or "").upper()
        n = normalize_name(d.get("canonicalName") or d.get("inputName") or "")
        k = d.get("entityKey")
        if t and n and k:
            lookup[(t, n)] = k

    dedupe_group_ids: Set[str] = set()

    async def _add(type_: str, name: str) -> None:
        key = lookup.get((type_.upper(), normalize_name(name)))
        if not key:
            return
        # fetch group id via unique key
        group = await db[c.dedupe_groups].find_one({"type": type_.upper(), "entityKey": key}, {"dedupeGroupId": 1})
        if group and group.get("dedupeGroupId"):
            dedupe_group_ids.add(group["dedupeGroupId"])

    if targets.get("guestCanonicalName"):
        await _add("PERSON", targets["guestCanonicalName"])

    for n in targets.get("businessNames") or []:
        await _add("ORGANIZATION", n)

    for n in targets.get("productNames") or []:
        await _add("PRODUCT", n)

    for n in targets.get("platformNames") or []:
        await _add("PLATFORM", n)

    for n in targets.get("compoundNames") or []:
        await _add("COMPOUND", _canon_compound_name_for_matching(n))

    return sorted(dedupe_group_ids) 


async def find_plan_by_id(*, db, plan_id: str) -> Optional[Dict[str, Any]]:
    return await db["intel_research_plans"].find_one({"planId": plan_id})



async def set_plan_status(*, db, plan_id: str, status: str, error: Optional[str] = None) -> None:
    update: Dict[str, Any] = {"status": status, "updatedAt": utcnow()}
    if status == "running":
        update["startedAt"] = utcnow()
    if status in ("complete", "failed"):
        update["finishedAt"] = utcnow()
    if error:
        update["error"] = error

    await db["intel_research_plans"].update_one({"planId": plan_id}, {"$set": update}) 


async def find_plans(
    *,
    db,
    status: Optional[str] = None,
    episode_url: Optional[str] = None,
    episode_id: Optional[str] = None,
    bundle_id: Optional[str] = None,
    pipeline_version: Optional[str] = None,
    dedupe_group_id: Optional[str] = None,
    limit: int = 50,
    sort_newest: bool = False,
) -> List[Dict[str, Any]]:
    """
    Flexible plan finder. Returns list of plan docs.
    """
    q: Dict[str, Any] = {}
    if status is not None:
        q["status"] = status
    if episode_url is not None:
        q["episodeUrl"] = episode_url
    if episode_id is not None:
        q["episodeId"] = episode_id
    if bundle_id is not None:
        q["bundleId"] = bundle_id
    if pipeline_version is not None:
        q["pipelineVersion"] = pipeline_version
    if dedupe_group_id is not None:
        q["dedupeGroupIds"] = dedupe_group_id

    sort = [("createdAt", -1 if sort_newest else 1)]
    cursor = db["intel_research_plans"].find(q).sort(sort).limit(int(limit))
    return await cursor.to_list(length=int(limit))


async def claim_next_plan(
    *,
    db,
    pipeline_version: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Atomically claim one plan from draft -> queued.
    Optionally constrain by pipelineVersion.
    """
    q: Dict[str, Any] = {"status": "draft"}
    if pipeline_version:
        q["pipelineVersion"] = pipeline_version

    return await db["intel_research_plans"].find_one_and_update(
        q,
        {"$set": {"status": "queued", "queuedAt": utcnow(), "updatedAt": utcnow()}},
        return_document=ReturnDocument.AFTER,
    )


async def mark_plan_execution_meta(
    *,
    db,
    plan_id: str,
    execution: Dict[str, Any],
) -> None:
    """
    Stores execution metadata (file refs, run ids, etc) back onto the plan.
    """
    await db["intel_research_plans"].update_one(
        {"planId": plan_id},
        {"$set": {"execution": execution, "updatedAt": utcnow()}},
        
        )


async def get_plan_by_plan_id(
    *,
    db: AsyncDatabase,
    plan_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch a single intel_research_plans doc by planId.
    """
    c = IntelCollections()
    return await db[c.research_plans].find_one({"planId": plan_id})


async def get_candidate_run_by_run_id(
    *,
    db: AsyncDatabase,
    run_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch a single intel_candidate_runs doc by runId.
    """
    c = IntelCollections()
    return await db[c.candidate_runs].find_one({"runId": run_id})