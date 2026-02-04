from __future__ import annotations

import uuid
from typing import Any, Dict, List
from datetime import datetime
from research_agent.human_upgrade.logger import logger

# Your DB singleton
from research_agent.retrieval.async_mongo_client import _humanupgrade_db  # <-- update path to your actual module

from research_agent.retrieval.intel_mongo_helpers import (
    bulk_insert_candidate_entities,
    delete_candidate_entities_for_run,
    ensure_intel_indexes,
    extract_plan_targets_from_bundle,
    flatten_connected_bundle_to_candidate_entities,
    resolve_dedupe_group_ids_for_plan,
    sha256_jsonish,
    upsert_candidate_run,
    upsert_dedupe_group_and_add_member,
    upsert_research_plan,
    persist_domain_catalog_set_artifact,
)

from research_agent.human_upgrade.structured_outputs.candidates_outputs import CandidateSourcesConnected
from research_agent.human_upgrade.structured_outputs.research_direction_outputs import EntityBundlesListFinal


PIPELINE_VERSION_DEFAULT = "entity-intel-v1"


async def persist_domain_catalogs_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Writes:
      - intel_artifacts (DomainCatalogSet)

    Returns:
      - domain_catalog_set_id
      - domain_catalog_extracted_at

    Safe behavior:
      - If state has no domain_catalogs, no-op (returns empty dict)
    """
    db = _humanupgrade_db
    await ensure_intel_indexes(db)

    domain_catalogs = state.get("domain_catalogs")
    if domain_catalogs is None:
        logger.info("ℹ️ No domain_catalogs present in state; skipping artifact persist.")
        return {}

    episode = state.get("episode") or {}
    episode_id = str(episode.get("id") or episode.get("_id") or "")
    episode_url = episode.get("episodePageUrl") or "unknown"

    run_id = state.get("intel_run_id")
    if not run_id:
        # If you want strictness, raise; but no-op is also fine.
        raise ValueError("intel_run_id required before persisting domain catalogs")

    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT

    # pydantic -> dict
    if hasattr(domain_catalogs, "model_dump"):
        payload = domain_catalogs.model_dump()
    else:
        payload = domain_catalogs

    artifact_meta = await persist_domain_catalog_set_artifact(
        db=db,
        run_id=run_id,
        episode_id=episode_id,
        episode_url=episode_url,
        pipeline_version=pipeline_version,
        domain_catalog_set_payload=payload,
    )

    logger.info(
        "✅ Persisted domain catalog artifact: runId=%s artifactId=%s",
        run_id,
        artifact_meta["domainCatalogSetId"],
    )

    return {
        "domain_catalog_set_id": artifact_meta["domainCatalogSetId"],
        "domain_catalog_extracted_at": artifact_meta["domainCatalogExtractedAt"],
    }

async def persist_candidates_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Writes:
      - intel_candidate_runs
      - intel_candidate_entities
      - intel_dedupe_groups
    Returns:
      - intel_run_id
      - dedupe_group_map (entityKey -> dedupeGroupId)
      - candidate_entity_ids
    """
    db = _humanupgrade_db
    await ensure_intel_indexes(db) 

    domain_catalog_set_id: str = state.get("domain_catalog_set_id")
    domain_catalog_extracted_at: datetime | str = state.get("domain_catalog_extracted_at")

    episode = state.get("episode") or {}
    episode_id = str(episode.get("id") or episode.get("_id") or "")
    episode_url = episode.get("episodePageUrl") or "unknown"

    candidate_sources: CandidateSourcesConnected | None = state.get("candidate_sources", None)
    if candidate_sources is None:
        raise ValueError("candidate_sources required")

    run_id = state.get("intel_run_id") or str(uuid.uuid4())
    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT

    # running
    await upsert_candidate_run(
        db=db,
        run_id=run_id,
        episode_id=episode_id,
        episode_url=episode_url,
        pipeline_version=pipeline_version,
        status="running",
        domain_catalog_set_id=domain_catalog_set_id,
        domain_catalog_extracted_at=domain_catalog_extracted_at,
    )

    connected_payload = candidate_sources.model_dump()
    payload_hash = sha256_jsonish(connected_payload)

    # store full payload (or you can store just hash + S3/file pointer)
    await upsert_candidate_run(
        db=db,
        run_id=run_id,
        episode_id=episode_id,
        episode_url=episode_url,
        pipeline_version=pipeline_version,
        status="running",
        payload={
            "connectedBundleHash": payload_hash,
            "connectedBundle": connected_payload,
        },
        domain_catalog_set_id=domain_catalog_set_id,
        domain_catalog_extracted_at=domain_catalog_extracted_at,
    )

    # rerun safety
    await delete_candidate_entities_for_run(db=db, run_id=run_id)

    candidate_docs: List[Dict[str, Any]] = []
    for bundle in connected_payload.get("connected") or []:
        candidate_docs.extend(
            flatten_connected_bundle_to_candidate_entities(
                episode=episode,
                run_id=run_id,
                pipeline_version=pipeline_version,
                connected_bundle=bundle,
            )
        )

    await bulk_insert_candidate_entities(db=db, docs=candidate_docs)

    # dedupe group upserts
    dedupe_group_map: Dict[str, str] = {}
    for doc in candidate_docs:
        group = await upsert_dedupe_group_and_add_member(
            db=db,
            type_=doc["type"],
            entity_key=doc["entityKey"],
            canonical_name=doc.get("canonicalName") or doc.get("inputName") or "unknown",
            member={
                "candidateEntityId": doc["candidateEntityId"],
                "episodeId": doc["episodeId"],
                "runId": doc["runId"],
            },
        )
        dedupe_group_map[doc["entityKey"]] = group["dedupeGroupId"]

    await upsert_candidate_run(
        db=db,
        run_id=run_id,
        episode_id=episode_id,
        episode_url=episode_url,
        pipeline_version=pipeline_version,
        status="complete",
        payload={
            "connectedBundleHash": payload_hash,
            "connectedBundle": connected_payload,
            "candidateEntityCount": len(candidate_docs),
            "dedupeGroupCount": len(set(dedupe_group_map.values())),
        },
        domain_catalog_set_id=domain_catalog_set_id,
        domain_catalog_extracted_at=domain_catalog_extracted_at,
    )

    logger.info(
        "✅ Persisted candidates: runId=%s episode=%s entities=%s groups=%s",
        run_id,
        episode_url[:60],
        len(candidate_docs),
        len(set(dedupe_group_map.values())),
    )

    return {
        "intel_run_id": run_id,
        "intel_pipeline_version": pipeline_version,
        "candidate_entity_ids": [d["candidateEntityId"] for d in candidate_docs],
        "dedupe_group_map": dedupe_group_map,
    }


async def persist_research_plans_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Writes:
      - intel_research_plans

    IMPORTANT: This version resolves dedupeGroupIds deterministically using
    candidate entities from the SAME run_id.
    """
    db = _humanupgrade_db
    await ensure_intel_indexes(db)

    episode = state.get("episode") or {}
    episode_id = str(episode.get("id") or episode.get("_id") or "")
    episode_url = episode.get("episodePageUrl") or "unknown"

    run_id = state.get("intel_run_id")
    if not run_id:
        raise ValueError("intel_run_id required (persist_candidates_node must run first)")

    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT

    research_directions: EntityBundlesListFinal | None = state.get("research_directions", None)
    if research_directions is None:
        raise ValueError("research_directions required")

    plan_ids: List[str] = []

    # research_directions is a Pydantic model; dump it safely
    bundles = research_directions.model_dump().get("bundles") or []

    for bundle in bundles:
        plan_id = str(uuid.uuid4())
        bundle_id = bundle.get("bundleId") or "unknown_bundle"

        targets = extract_plan_targets_from_bundle(bundle)
        dedupe_group_ids = await resolve_dedupe_group_ids_for_plan(
            db=db,
            run_id=run_id,
            targets=targets,
        )

        doc = await upsert_research_plan(
            db=db,
            plan_id=plan_id,
            bundle_id=bundle_id,
            run_id=run_id,
            episode_id=episode_id,
            episode_url=episode_url,
            pipeline_version=pipeline_version,
            dedupe_group_ids=dedupe_group_ids,
            directions=bundle,   # store the whole per-bundle directions payload
            status="draft",
            targets=targets,     # makes it easy to debug + query by target names
        )
        plan_ids.append(doc["planId"])

    logger.info(
        "✅ Persisted research plans: runId=%s episode=%s plans=%s",
        run_id,
        episode_url[:60],
        len(plan_ids),
    )

    return {"research_plan_ids": plan_ids}
