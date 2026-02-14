"""Repository for CandidateSeedDoc operations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from beanie import PydanticObjectId

from research_agent.models.mongo.candidates.docs.candidate_seeds import CandidateSeedDoc
from research_agent.models.mongo.candidates.embedded.seeds import SeedExtractionModel
from research_agent.structured_outputs.candidates_outputs import SeedExtraction
from research_agent.utils.datetime_helpers import utc_now


def _convert_seed_extraction_to_model(seed: SeedExtraction) -> SeedExtractionModel:
    """Convert structured output to embedded model."""
    if hasattr(seed, "model_dump"):
        payload = seed.model_dump()
    else:
        payload = dict(seed)
    return SeedExtractionModel(**payload)


async def upsert_candidate_seed_doc(
    run_id: str,
    query: str,
    seed_extraction: SeedExtraction,
    pipeline_version: str = "v1",
) -> PydanticObjectId:
    """
    Upsert a CandidateSeedDoc for a given run.
    
    Returns:
        The document ID (MongoDB ObjectId)
    """
    payload = _convert_seed_extraction_to_model(seed_extraction)
    
    # Try to find existing doc for this run
    existing = await CandidateSeedDoc.find_one(CandidateSeedDoc.runId == run_id)
    
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
        doc = CandidateSeedDoc(
            runId=run_id,
            query=query,
            payload=payload,
            pipelineVersion=pipeline_version,
        )
        await doc.insert()
        return doc.id


async def get_candidate_seed_doc_by_run_id(run_id: str) -> Optional[CandidateSeedDoc]:
    """Retrieve seed doc by run ID."""
    return await CandidateSeedDoc.find_one(CandidateSeedDoc.runId == run_id)


async def delete_candidate_seed_doc_by_run_id(run_id: str) -> int:
    """Delete seed doc for a run. Returns count of deleted docs."""
    result = await CandidateSeedDoc.find(CandidateSeedDoc.runId == run_id).delete()
    return result.deleted_count if result else 0
