"""
Intel MongoDB persistence nodes using Beanie ODM.

These nodes persist graph outputs to MongoDB using Beanie document models.
They are designed to work with the entity_candidates_connected_graph.

These nodes also publish progress events to Redis Streams for real-time WebSocket updates.
"""
from __future__ import annotations

from typing import Any, Dict, List
from beanie import PydanticObjectId

from research_agent.utils.logger import logger
from research_agent.models.base.enums import PipelineStatus
from research_agent.infrastructure.storage.redis.client import get_streams_manager
from research_agent.infrastructure.storage.redis.streams_manager import StreamAddress
from research_agent.infrastructure.storage.redis.event_registry import (
    GROUP_GRAPH,
    CHANNEL_ENTITY_DISCOVERY,
    EVENT_TYPE_INITIALIZED,
    EVENT_TYPE_SEEDS_COMPLETE,
    EVENT_TYPE_OFFICIAL_SOURCES_COMPLETE,
    EVENT_TYPE_DOMAIN_CATALOGS_COMPLETE,
    EVENT_TYPE_PERSISTENCE_COMPLETE,
)

# Import repository functions
from research_agent.services.mongo.candidates import (
    # Runs
    create_or_get_candidate_run,
    update_run_status,
    update_run_outputs,
    update_run_stats,
    
    # Seeds
    upsert_candidate_seed_doc,
    
    # Official Sources
    upsert_official_starter_sources_doc,
    
    # Domain Catalogs
    upsert_domain_catalog_set_doc,
    
    # Connected Candidates
    upsert_connected_candidates_doc,
    
    # Candidate Sources (merged graph)
    upsert_candidate_sources_connected_doc,
    
    # Entities
    bulk_insert_candidate_entities,
    delete_candidate_entities_for_run,
    upsert_dedupe_group_and_add_member,
    flatten_connected_candidates_to_entity_docs,
)

from research_agent.structured_outputs.candidates_outputs import (
    SeedExtraction,
    OfficialStarterSources,
    DomainCatalogSet,
    CandidateSourcesConnected,
)
from research_agent.models.mongo.entities.docs.candidate_entities import IntelCandidateEntityDoc

PIPELINE_VERSION_DEFAULT = "entity-intel-v1"


# =============================================================================
# Helper: Publish Progress Event
# =============================================================================
async def _publish_progress(
    run_id: str,
    event_type: str,
    data: Dict[str, Any],
) -> None:
    """
    Helper to publish progress events to Redis Streams.
    
    This allows real-time WebSocket updates as the graph executes.
    """
    try:
        manager = await get_streams_manager()
        addr = StreamAddress(
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key=run_id,
        )
        await manager.publish(addr, event_type=event_type, data=data)
    except Exception as e:
        # Don't fail the node if event publishing fails
        logger.warning(f"Failed to publish progress event {event_type}: {e}")


# =============================================================================
# Node: Initialize Run
# =============================================================================
async def initialize_run_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initialize or retrieve the candidate run document.
    This should be the first persistence node in the graph.
    
    Writes:
      - intel_candidate_runs (via Beanie)
    
    Returns:
      - intel_run_id
      - intel_pipeline_version
    """
    run_id = state.get("intel_run_id")
    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT
    
    query = state.get("query", "")
    starter_sources = state.get("starter_sources", []) or []
    starter_content = state.get("starter_content", "")
    
    # Create or get existing run
    run_doc = await create_or_get_candidate_run(
        run_id=run_id,
        query=query,
        starter_sources=starter_sources,
        starter_content=starter_content,
        pipeline_version=pipeline_version,
    )
    
    # Update status to running
    await update_run_status(run_doc.runId, PipelineStatus.running)
    
    logger.info("✅ Initialized candidate run: runId=%s", run_doc.runId)
    
    # Publish progress event
    await _publish_progress(
        run_id=run_doc.runId,
        event_type=EVENT_TYPE_INITIALIZED,
        data={
            "intel_run_id": run_doc.runId,
            "pipeline_version": pipeline_version,
        },
    )
    
    return {
        "intel_run_id": run_doc.runId,
        "intel_pipeline_version": pipeline_version,
    }


# =============================================================================
# Node: Persist Seeds
# =============================================================================
async def persist_seeds_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist seed extraction output.
    
    Writes:
      - intel_candidate_seeds (via Beanie)
    
    Updates:
      - intel_candidate_runs.outputs.seedsDocId
    
    Returns:
      - seeds_doc_id
    """
    run_id = state.get("intel_run_id")
    if not run_id:
        raise ValueError("intel_run_id required before persisting seeds")
    
    seed_extraction: SeedExtraction | None = state.get("seed_extraction")
    if seed_extraction is None:
        logger.info("ℹ️ No seed_extraction present in state; skipping persist.")
        return {}
    
    query = state.get("query", "")
    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT
    
    # Upsert seed doc
    doc_id = await upsert_candidate_seed_doc(
        run_id=run_id,
        query=query,
        seed_extraction=seed_extraction,
        pipeline_version=pipeline_version,
    )
    
    # Update run outputs
    await update_run_outputs(run_id, seeds_doc_id=doc_id)
    
    logger.info("✅ Persisted seed extraction: runId=%s docId=%s", run_id, doc_id)
    
    # Publish progress event
    await _publish_progress(
        run_id=run_id,
        event_type=EVENT_TYPE_SEEDS_COMPLETE,
        data={
            "people_count": len(seed_extraction.people_candidates or []),
            "org_count": len(seed_extraction.organization_candidates or []),
            "product_count": len(seed_extraction.product_candidates or []),
            "compound_count": len(seed_extraction.compound_candidates or []),
            "tech_count": len(seed_extraction.technology_candidates or []),
        },
    )
    
    return {
        "seeds_doc_id": doc_id,
    }


# =============================================================================
# Node: Persist Official Sources
# =============================================================================
async def persist_official_sources_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist official starter sources output.
    
    Writes:
      - intel_official_starter_sources (via Beanie)
    
    Updates:
      - intel_candidate_runs.outputs.officialStarterSourcesDocId
    
    Returns:
      - official_sources_doc_id
    """
    run_id = state.get("intel_run_id")
    if not run_id:
        raise ValueError("intel_run_id required before persisting official sources")
    
    official_sources: OfficialStarterSources | None = state.get("official_starter_sources")
    if official_sources is None:
        logger.info("ℹ️ No official_starter_sources present in state; skipping persist.")
        return {}
    
    query = state.get("query", "")
    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT
    
    # Upsert official sources doc
    doc_id = await upsert_official_starter_sources_doc(
        run_id=run_id,
        query=query,
        official_sources=official_sources,
        pipeline_version=pipeline_version,
    )
    
    # Update run outputs
    await update_run_outputs(run_id, official_starter_sources_doc_id=doc_id)
    
    logger.info("✅ Persisted official sources: runId=%s docId=%s", run_id, doc_id)
    
    # Publish progress event - count total sources across all entity targets
    source_count = 0
    if hasattr(official_sources, "people"):
        source_count += sum(len(target.sources) for target in official_sources.people)
    if hasattr(official_sources, "organizations"):
        source_count += sum(len(target.sources) for target in official_sources.organizations)
    if hasattr(official_sources, "products"):
        source_count += sum(len(target.sources) for target in official_sources.products)
    if hasattr(official_sources, "technologies"):
        source_count += sum(len(target.sources) for target in official_sources.technologies)
    
    # Get primary entity info from seed_extraction (if available in state)
    seed_extraction = state.get("seed_extraction")
    has_primary_org = False
    has_primary_person = False
    if seed_extraction:
        has_primary_org = getattr(seed_extraction, "primary_organization", None) is not None
        has_primary_person = getattr(seed_extraction, "primary_person", None) is not None
    
    await _publish_progress(
        run_id=run_id,
        event_type=EVENT_TYPE_OFFICIAL_SOURCES_COMPLETE,
        data={
            "source_count": source_count,
            "has_primary_org": has_primary_org,
            "has_primary_person": has_primary_person,
        },
    )
    
    return {
        "official_sources_doc_id": doc_id,
    }


# =============================================================================
# Node: Persist Domain Catalogs
# =============================================================================
async def persist_domain_catalogs_node_beanie(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist domain catalog set output.
    
    Writes:
      - intel_domain_catalog_sets (via Beanie)
    
    Updates:
      - intel_candidate_runs.outputs.domainCatalogSetDocId
      - intel_candidate_runs.domainCount
    
    Returns:
      - domain_catalog_set_doc_id
    """
    run_id = state.get("intel_run_id")
    if not run_id:
        raise ValueError("intel_run_id required before persisting domain catalogs")
    
    domain_catalogs: DomainCatalogSet | None = state.get("domain_catalogs")
    if domain_catalogs is None:
        logger.info("ℹ️ No domain_catalogs present in state; skipping persist.")
        return {}
    
    query = state.get("query", "")
    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT
    
    # Upsert domain catalog set doc
    doc_id = await upsert_domain_catalog_set_doc(
        run_id=run_id,
        query=query,
        domain_catalogs=domain_catalogs,
        pipeline_version=pipeline_version,
    )
    
    # Count domains
    if hasattr(domain_catalogs, "catalogs"):
        catalog_list = domain_catalogs.catalogs
    else:
        catalog_dict = dict(domain_catalogs)
        catalog_list = catalog_dict.get("catalogs", [])
    domain_count = len(catalog_list) if catalog_list else 0
    
    # Update run outputs and stats
    await update_run_outputs(run_id, domain_catalog_set_doc_id=doc_id)
    await update_run_stats(run_id, domain_count=domain_count)
    
    logger.info("✅ Persisted domain catalogs: runId=%s docId=%s domains=%s", run_id, doc_id, domain_count)
    
    # Publish progress event - extract domains safely from Pydantic models or dicts
    domains = []
    if catalog_list:
        for cat in catalog_list:
            if hasattr(cat, "baseDomain"):
                # Pydantic model - use attribute access
                domains.append(cat.baseDomain or "unknown")
            elif isinstance(cat, dict):
                # Dict - use .get()
                domains.append(cat.get("baseDomain", "unknown"))
            else:
                domains.append("unknown")
    await _publish_progress(
        run_id=run_id,
        event_type=EVENT_TYPE_DOMAIN_CATALOGS_COMPLETE,
        data={
            "catalog_count": domain_count,
            "domains": domains[:10],  # Send first 10 to avoid huge payloads
        },
    )
    
    return {
        "domain_catalog_set_doc_id": doc_id,
    }


# =============================================================================
# Node: Persist Connected Candidates Slices (ALL per-domain slices)
# =============================================================================
async def persist_connected_candidates_slices_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist ALL ConnectedCandidates slices (per-domain outputs) after merging.
    
    This is called AFTER merge to persist each domain slice separately,
    then updates the run with the list of slice doc IDs.
    
    Writes:
      - intel_connected_candidates (via Beanie, one doc per domain)
    
    Updates:
      - intel_candidate_runs.outputs.connectedCandidatesDocIds
    
    Returns:
      - connected_candidates_slice_doc_ids
    """
    run_id = state.get("intel_run_id")
    if not run_id:
        logger.warning("⚠️ intel_run_id not found; skipping slice persist.")
        return {}
    
    query = state.get("query", "")
    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT
    
    # Get all slice outputs from state (accumulated during fanout)
    slice_outputs = state.get("candidate_sources_slice_outputs", []) or []
    if not slice_outputs:
        logger.warning("⚠️ No candidate_sources_slice_outputs; skipping slice persist.")
        return {}
    
    # Persist each slice
    doc_ids: List[PydanticObjectId] = []
    for slice_output in slice_outputs:
        # Extract connected list safely (might be Pydantic model or dict)
        if hasattr(slice_output, "connected"):
            connected_list = slice_output.connected
        elif isinstance(slice_output, dict):
            connected_list = slice_output.get("connected") or []
        else:
            connected_list = []
        
        if not connected_list:
            continue
        
        # Persist each ConnectedCandidates in this slice
        for connected in connected_list:
            # Extract base_domain from the connected candidate
            if hasattr(connected, "baseDomain"):
                base_domain = connected.baseDomain or "unknown"
            elif isinstance(connected, dict):
                base_domain = connected.get("baseDomain", "unknown")
            else:
                base_domain = "unknown"
            
            doc_id = await upsert_connected_candidates_doc(
                run_id=run_id,
                query=query,
                base_domain=base_domain,
                connected_candidates=connected,
                pipeline_version=pipeline_version,
            )
            doc_ids.append(doc_id)
    
    # Update run outputs with slice doc IDs
    if doc_ids:
        await update_run_outputs(run_id, connected_candidates_doc_ids=doc_ids)
    
    logger.info("✅ Persisted connected candidates slices: runId=%s docs=%s", run_id, len(doc_ids))
    
    return {
        "connected_candidates_slice_doc_ids": doc_ids,
    }


# =============================================================================
# Node: Persist Merged Graph & Entities
# =============================================================================
async def persist_candidates_node_beanie(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist final merged graph output and flatten into candidate entities.
    
    This is the main "finalization" node that:
    1. Persists CandidateSourcesConnected (merged graph)
    2. Flattens all entities into IntelCandidateEntityDoc
    3. Creates dedupe groups
    4. Updates run status to complete
    
    Writes:
      - intel_candidate_sources_connected (via Beanie)
      - intel_candidate_entities (via Beanie)
      - intel_dedupe_groups (via Beanie)
    
    Updates:
      - intel_candidate_runs.outputs.connectedGraphDocId
      - intel_candidate_runs.candidateEntityCount
      - intel_candidate_runs.dedupeGroupCount
      - intel_candidate_runs.status = complete
    
    Returns:
      - connected_graph_doc_id
      - candidate_entity_ids
      - dedupe_group_map (entityKey -> dedupeGroupId)
    """
    run_id = state.get("intel_run_id")
    if not run_id:
        raise ValueError("intel_run_id required before persisting candidates")
    
    candidate_sources: CandidateSourcesConnected | None = state.get("candidate_sources")
    if candidate_sources is None:
        raise ValueError("candidate_sources required")
    
    query = state.get("query", "")
    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT
    
    # 1. Persist merged graph
    graph_doc_id = await upsert_candidate_sources_connected_doc(
        run_id=run_id,
        query=query,
        candidate_sources=candidate_sources,
        pipeline_version=pipeline_version,
    )
    
    # 2. Flatten to entity docs
    from research_agent.structured_outputs.candidates_outputs import ConnectedCandidates
    
    connected_payload = candidate_sources.model_dump() if hasattr(candidate_sources, "model_dump") else dict(candidate_sources)
    
    # Rerun safety: delete old entities for this run
    await delete_candidate_entities_for_run(run_id=run_id)
    
    entity_docs: List[IntelCandidateEntityDoc] = []
    for bundle in (connected_payload.get("connected") or []):
        # Convert dict back to ConnectedCandidates for typing
        if isinstance(bundle, dict):
            bundle_obj = ConnectedCandidates(**bundle)
        else:
            bundle_obj = bundle
        
        entity_docs.extend(
            flatten_connected_candidates_to_entity_docs(
                run_id=run_id,
                pipeline_version=pipeline_version,
                connected_candidates=bundle_obj,
            )
        )
    
    # 3. Bulk insert entities
    candidate_entity_ids = await bulk_insert_candidate_entities(entity_docs)
    
    # 4. Create dedupe groups
    dedupe_group_map: Dict[str, str] = {}
    dedupe_group_ids_set: set[str] = set()
    doc: IntelCandidateEntityDoc
    for doc in entity_docs:
        group = await upsert_dedupe_group_and_add_member(
            type_hint=doc.typeHint,
            entity_key=doc.entityKey,
            canonical_name=doc.canonicalName or doc.inputName or "unknown",
            member={
                "candidateEntityId": doc.candidateEntityId,
                "runId": doc.runId,
            },
        )
        dedupe_group_map[doc.entityKey] = group.dedupeGroupId
        dedupe_group_ids_set.add(group.dedupeGroupId)
    
    dedupe_group_ids = list(dedupe_group_ids_set)
    
    # 5. Update run outputs and stats (including dedupe group IDs)
    await update_run_outputs(run_id, connected_graph_doc_id=graph_doc_id)
    await update_run_stats(
        run_id,
        candidate_entity_count=len(entity_docs),
        dedupe_group_count=len(dedupe_group_ids),
        dedupe_group_ids=dedupe_group_ids,
    )
    
    # 6. Mark run as complete
    await update_run_status(run_id, PipelineStatus.complete)
    
    logger.info(
        "✅ Persisted merged graph + entities: runId=%s entities=%s groups=%s",
        run_id,
        len(entity_docs),
        len(set(dedupe_group_map.values())),
    )
    
    # 7. Publish final persistence event
    await _publish_progress(
        run_id=run_id,
        event_type=EVENT_TYPE_PERSISTENCE_COMPLETE,
        data={
            "entity_count": len(entity_docs),
            "dedupe_group_count": len(set(dedupe_group_map.values())),
        },
    )
    
    return {
        "connected_graph_doc_id": graph_doc_id,
        "candidate_entity_ids": candidate_entity_ids,
        "dedupe_group_map": dedupe_group_map,
    }


# =============================================================================
# Error Handler Node (optional)
# =============================================================================
async def handle_run_error_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mark run as failed if an error occurred.
    
    This should be called from an error edge in the graph.
    """
    run_id = state.get("intel_run_id")
    if not run_id:
        logger.warning("⚠️ No intel_run_id; cannot mark run as failed.")
        return {}
    
    error_msg = state.get("error", "Unknown error")
    
    await update_run_status(run_id, PipelineStatus.failed, notes=error_msg)
    
    logger.error("❌ Marked run as failed: runId=%s error=%s", run_id, error_msg)
    
    return {}
