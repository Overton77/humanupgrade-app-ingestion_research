"""Repository for IntelCandidateRunDoc operations."""
from __future__ import annotations

import uuid
from typing import List, Optional
from beanie import PydanticObjectId

from research_agent.models.mongo.entities.docs.candidate_runs import IntelCandidateRunDoc
from research_agent.models.mongo.entities.embedded.run_inputs import (
    CandidateRunInputsModel,
    StarterSourceRefModel,
    StarterContentRefModel,
)
from research_agent.models.mongo.entities.embedded.run_output_refs import CandidateRunOutputsRefsModel
from research_agent.models.base.enums import PipelineStatus
from research_agent.utils.datetime_helpers import utc_now


async def create_or_get_candidate_run(
    run_id: Optional[str] = None,
    query: str = "",
    starter_sources: Optional[List[str]] = None,
    starter_content: Optional[str] = None,
    pipeline_version: str = "v1",
) -> IntelCandidateRunDoc:
    """
    Create a new candidate run or retrieve existing one.
    
    Args:
        run_id: Optional run ID. If not provided, generates a new UUID.
        query: The research query
        starter_sources: List of starter source URLs
        starter_content: Optional starter content text
        pipeline_version: Pipeline version string
        
    Returns:
        The IntelCandidateRunDoc (either newly created or existing)
    """
    if run_id:
        # Try to find existing
        existing = await IntelCandidateRunDoc.find_one(IntelCandidateRunDoc.runId == run_id)
        if existing:
            return existing
    else:
        # Generate new run ID
        run_id = str(uuid.uuid4())
    
    # Convert starter sources to refs
    source_refs = [
        StarterSourceRefModel(url=url)
        for url in (starter_sources or [])
    ]
    
    # Build inputs
    inputs = CandidateRunInputsModel(
        query=query,
        starterSources=source_refs,
        starterContent=StarterContentRefModel(urls=starter_sources or []) if starter_content else None,
        notes=starter_content if starter_content else None,
    )
    
    # Create new run doc
    doc = IntelCandidateRunDoc(
        runId=run_id,
        pipelineVersion=pipeline_version,
        status=PipelineStatus.queued,
        inputs=inputs,
        outputs=CandidateRunOutputsRefsModel(),
    )
    await doc.insert()
    return doc


async def update_run_status(
    run_id: str,
    status: PipelineStatus,
    notes: Optional[str] = None,
) -> None:
    """Update run status."""
    doc = await IntelCandidateRunDoc.find_one(IntelCandidateRunDoc.runId == run_id)
    if doc:
        doc.status = status
        doc.updatedAt = utc_now()
        if notes:
            doc.notes = notes
        await doc.save()


async def update_run_outputs(
    run_id: str,
    seeds_doc_id: Optional[PydanticObjectId] = None,
    official_starter_sources_doc_id: Optional[PydanticObjectId] = None,
    domain_catalog_set_doc_id: Optional[PydanticObjectId] = None,
    connected_candidates_doc_ids: Optional[List[PydanticObjectId]] = None,
    connected_graph_doc_id: Optional[PydanticObjectId] = None,
) -> None:
    """Update run output references."""
    doc = await IntelCandidateRunDoc.find_one(IntelCandidateRunDoc.runId == run_id)
    if not doc:
        return
    
    if seeds_doc_id:
        doc.outputs.seedsDocId = seeds_doc_id
    if official_starter_sources_doc_id:
        doc.outputs.officialStarterSourcesDocId = official_starter_sources_doc_id
    if domain_catalog_set_doc_id:
        doc.outputs.domainCatalogSetDocId = domain_catalog_set_doc_id
    if connected_candidates_doc_ids:
        doc.outputs.connectedCandidatesDocIds = connected_candidates_doc_ids
    if connected_graph_doc_id:
        doc.outputs.connectedGraphDocId = connected_graph_doc_id
    
    doc.updatedAt = utc_now()
    await doc.save()


async def update_run_stats(
    run_id: str,
    candidate_entity_count: Optional[int] = None,
    dedupe_group_count: Optional[int] = None,
    domain_count: Optional[int] = None,
) -> None:
    """Update run statistics."""
    doc = await IntelCandidateRunDoc.find_one(IntelCandidateRunDoc.runId == run_id)
    if not doc:
        return
    
    if candidate_entity_count is not None:
        doc.candidateEntityCount = candidate_entity_count
    if dedupe_group_count is not None:
        doc.dedupeGroupCount = dedupe_group_count
    if domain_count is not None:
        doc.domainCount = domain_count
    
    doc.updatedAt = utc_now()
    await doc.save()


async def get_candidate_run_by_id(run_id: str) -> Optional[IntelCandidateRunDoc]:
    """Retrieve candidate run by ID."""
    return await IntelCandidateRunDoc.find_one(IntelCandidateRunDoc.runId == run_id)


async def get_candidate_runs_by_query(query: str, limit: int = 10) -> List[IntelCandidateRunDoc]:
    """Retrieve candidate runs by query string."""
    return await IntelCandidateRunDoc.find(
        IntelCandidateRunDoc.inputs.query == query
    ).sort("-createdAt").limit(limit).to_list()
