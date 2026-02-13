"""
Intel MongoDB persistence nodes using Beanie ODM.

These nodes persist graph outputs to MongoDB using Beanie document models.
They are designed to work with the entity_candidates_connected_graph.
"""
from __future__ import annotations

from typing import Any, Dict, List
from beanie import PydanticObjectId

from research_agent.human_upgrade.logger import logger
from research_agent.models.base.enums import PipelineStatus

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

from research_agent.human_upgrade.structured_outputs.candidates_outputs import (
    SeedExtraction,
    OfficialStarterSources,
    DomainCatalogSet,
    CandidateSourcesConnected,
)
from research_agent.models.mongo.entities.docs.candidate_entities import IntelCandidateEntityDoc

PIPELINE_VERSION_DEFAULT = "entity-intel-v1"


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
    
    return {
        "domain_catalog_set_doc_id": doc_id,
    }


# =============================================================================
# Node: Persist Connected Candidates (per-domain slice)
# =============================================================================
async def persist_connected_candidates_slice_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a single ConnectedCandidates slice (per-domain output).
    
    This node is typically called from within a fanout/map-reduce pattern,
    so it operates on a single domain's output at a time.
    
    Writes:
      - intel_connected_candidates (via Beanie)
    
    Returns:
      - connected_candidates_slice_doc_id
    """
    run_id = state.get("intel_run_id")
    if not run_id:
        # In some fanout scenarios, run_id may not be propagated
        logger.warning("⚠️ intel_run_id not found; skipping slice persist.")
        return {}
    
    # This would come from the slice fanout state
    catalog = state.get("catalog")
    if catalog is None:
        logger.warning("⚠️ No catalog in slice state; skipping slice persist.")
        return {}
    
    base_domain = catalog.get("baseDomain") or "unknown"
    query = state.get("query", "")
    pipeline_version = state.get("intel_pipeline_version") or PIPELINE_VERSION_DEFAULT
    
    # Extract the ConnectedCandidates from slice output
    slice_outputs = state.get("candidate_sources_slice_outputs", []) or []
    if not slice_outputs:
        logger.warning("⚠️ No candidate_sources_slice_outputs; skipping slice persist.")
        return {}
    
    # Take the last slice output (most recent for this fanout)
    last_slice = slice_outputs[-1]
    connected_list = last_slice.connected if hasattr(last_slice, "connected") else (last_slice.get("connected") or [])
    
    if not connected_list:
        logger.warning("⚠️ No connected candidates in slice; skipping slice persist.")
        return {}
    
    # Persist each ConnectedCandidates in the slice
    doc_ids: List[PydanticObjectId] = []
    for connected in connected_list:
        doc_id = await upsert_connected_candidates_doc(
            run_id=run_id,
            query=query,
            base_domain=base_domain,
            connected_candidates=connected,
            pipeline_version=pipeline_version,
        )
        doc_ids.append(doc_id)
    
    logger.info("✅ Persisted connected candidates slice: runId=%s domain=%s docs=%s", run_id, base_domain, len(doc_ids))
    
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
    from research_agent.human_upgrade.structured_outputs.candidates_outputs import ConnectedCandidates
    
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
    
    # 5. Update run outputs and stats
    await update_run_outputs(run_id, connected_graph_doc_id=graph_doc_id)
    await update_run_stats(
        run_id,
        candidate_entity_count=len(entity_docs),
        dedupe_group_count=len(set(dedupe_group_map.values())),
    )
    
    # 6. Mark run as complete
    await update_run_status(run_id, PipelineStatus.complete)
    
    logger.info(
        "✅ Persisted merged graph + entities: runId=%s entities=%s groups=%s",
        run_id,
        len(entity_docs),
        len(set(dedupe_group_map.values())),
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
