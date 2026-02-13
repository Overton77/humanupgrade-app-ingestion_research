"""Repository for OfficialStarterSourcesDoc operations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from beanie import PydanticObjectId

from research_agent.models.mongo.candidates.docs.official_starter_sources import OfficialStarterSourcesDoc
from research_agent.models.mongo.candidates.embedded.official_sources import OfficialStarterSourcesModel
from research_agent.human_upgrade.structured_outputs.candidates_outputs import OfficialStarterSources
from research_agent.utils.datetime_helpers import utc_now


def _convert_official_sources_to_model(sources: OfficialStarterSources) -> OfficialStarterSourcesModel:
    """Convert structured output to embedded model."""
    if hasattr(sources, "model_dump"):
        payload = sources.model_dump()
    else:
        payload = dict(sources)
    return OfficialStarterSourcesModel(**payload)


async def upsert_official_starter_sources_doc(
    run_id: str,
    query: str,
    official_sources: OfficialStarterSources,
    pipeline_version: str = "v1",
) -> PydanticObjectId:
    """
    Upsert an OfficialStarterSourcesDoc for a given run.
    
    Returns:
        The document ID (MongoDB ObjectId)
    """
    payload = _convert_official_sources_to_model(official_sources)
    
    # Try to find existing doc for this run
    existing = await OfficialStarterSourcesDoc.find_one(OfficialStarterSourcesDoc.runId == run_id)
    
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
        doc = OfficialStarterSourcesDoc(
            runId=run_id,
            query=query,
            payload=payload,
            pipelineVersion=pipeline_version,
        )
        await doc.insert()
        return doc.id


async def get_official_starter_sources_doc_by_run_id(run_id: str) -> Optional[OfficialStarterSourcesDoc]:
    """Retrieve official sources doc by run ID."""
    return await OfficialStarterSourcesDoc.find_one(OfficialStarterSourcesDoc.runId == run_id)


async def delete_official_starter_sources_doc_by_run_id(run_id: str) -> int:
    """Delete official sources doc for a run. Returns count of deleted docs."""
    result = await OfficialStarterSourcesDoc.find(OfficialStarterSourcesDoc.runId == run_id).delete()
    return result.deleted_count if result else 0
