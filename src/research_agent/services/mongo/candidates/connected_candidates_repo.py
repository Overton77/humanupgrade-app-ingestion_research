"""Repository for ConnectedCandidatesDoc operations."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from beanie import PydanticObjectId

from research_agent.models.mongo.candidates.docs.connected_candidates import ConnectedCandidatesDoc
from research_agent.models.mongo.candidates.embedded.entities_connected import ConnectedCandidatesModel
from research_agent.human_upgrade.structured_outputs.candidates_outputs import ConnectedCandidates
from research_agent.utils.datetime_helpers import utc_now


def _convert_connected_candidates_to_model(candidates: ConnectedCandidates) -> ConnectedCandidatesModel:
    """Convert structured output to embedded model."""
    if hasattr(candidates, "model_dump"):
        payload = candidates.model_dump()
    else:
        payload = dict(candidates)
    return ConnectedCandidatesModel(**payload)


async def upsert_connected_candidates_doc(
    run_id: str,
    query: str,
    base_domain: str,
    connected_candidates: ConnectedCandidates,
    pipeline_version: str = "v1",
) -> PydanticObjectId:
    """
    Upsert a ConnectedCandidatesDoc for a given run and domain.
    
    Returns:
        The document ID (MongoDB ObjectId)
    """
    payload = _convert_connected_candidates_to_model(connected_candidates)
    
    # Try to find existing doc for this run + domain
    existing = await ConnectedCandidatesDoc.find_one(
        ConnectedCandidatesDoc.runId == run_id,
        ConnectedCandidatesDoc.baseDomain == base_domain
    )
    
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
        doc = ConnectedCandidatesDoc(
            runId=run_id,
            query=query,
            baseDomain=base_domain,
            payload=payload,
            pipelineVersion=pipeline_version,
        )
        await doc.insert()
        return doc.id


async def get_connected_candidates_docs_by_run_id(run_id: str) -> List[ConnectedCandidatesDoc]:
    """Retrieve all connected candidates docs for a run (multiple domains)."""
    return await ConnectedCandidatesDoc.find(ConnectedCandidatesDoc.runId == run_id).to_list()


async def get_connected_candidates_doc_by_run_and_domain(
    run_id: str,
    base_domain: str
) -> Optional[ConnectedCandidatesDoc]:
    """Retrieve connected candidates doc by run ID and domain."""
    return await ConnectedCandidatesDoc.find_one(
        ConnectedCandidatesDoc.runId == run_id,
        ConnectedCandidatesDoc.baseDomain == base_domain
    )


async def delete_connected_candidates_docs_by_run_id(run_id: str) -> int:
    """Delete all connected candidates docs for a run. Returns count of deleted docs."""
    result = await ConnectedCandidatesDoc.find(ConnectedCandidatesDoc.runId == run_id).delete()
    return result.deleted_count if result else 0
