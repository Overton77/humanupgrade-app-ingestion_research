"""Repository for CandidateSourcesConnectedDoc operations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from beanie import PydanticObjectId

from research_agent.models.mongo.candidates.docs.candidate_sources_connected import CandidateSourcesConnectedDoc
from research_agent.models.mongo.candidates.embedded.entities_connected import CandidateSourcesConnectedModel
from research_agent.human_upgrade.structured_outputs.candidates_outputs import CandidateSourcesConnected
from research_agent.utils.datetime_helpers import utc_now


def _convert_candidate_sources_connected_to_model(sources: CandidateSourcesConnected) -> CandidateSourcesConnectedModel:
    """Convert structured output to embedded model."""
    if hasattr(sources, "model_dump"):
        payload = sources.model_dump()
    else:
        payload = dict(sources)
    return CandidateSourcesConnectedModel(**payload)


async def upsert_candidate_sources_connected_doc(
    run_id: str,
    query: str,
    candidate_sources: CandidateSourcesConnected,
    pipeline_version: str = "v1",
) -> PydanticObjectId:
    """
    Upsert a CandidateSourcesConnectedDoc (merged graph output) for a given run.
    
    Returns:
        The document ID (MongoDB ObjectId)
    """
    payload = _convert_candidate_sources_connected_to_model(candidate_sources)
    
    # Try to find existing doc for this run
    existing = await CandidateSourcesConnectedDoc.find_one(CandidateSourcesConnectedDoc.runId == run_id)
    
    if existing:
        # Update existing
        existing.query = query
        existing.payload = payload
        existing.pipelineVersion = pipeline_version
        existing.updatedAt = utc_now()
        await existing.save()
        return existing.id
    else:
        # Create new
        doc = CandidateSourcesConnectedDoc(
            runId=run_id,
            query=query,
            payload=payload,
            pipelineVersion=pipeline_version,
        )
        await doc.insert()
        return doc.id


async def get_candidate_sources_connected_doc_by_run_id(run_id: str) -> Optional[CandidateSourcesConnectedDoc]:
    """Retrieve merged graph doc by run ID."""
    return await CandidateSourcesConnectedDoc.find_one(CandidateSourcesConnectedDoc.runId == run_id)


async def delete_candidate_sources_connected_doc_by_run_id(run_id: str) -> int:
    """Delete merged graph doc for a run. Returns count of deleted docs."""
    result = await CandidateSourcesConnectedDoc.find(CandidateSourcesConnectedDoc.runId == run_id).delete()
    return result.deleted_count if result else 0
