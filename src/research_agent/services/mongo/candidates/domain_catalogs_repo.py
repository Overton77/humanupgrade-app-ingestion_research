"""Repository for DomainCatalogSetDoc operations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from beanie import PydanticObjectId

from research_agent.models.mongo.domains.docs.domain_catalog_sets import DomainCatalogSetDoc
from research_agent.models.mongo.domains.domain_catalog_set import DomainCatalogSetModel
from research_agent.human_upgrade.structured_outputs.candidates_outputs import DomainCatalogSet
from research_agent.utils.datetime_helpers import utc_now


def _convert_domain_catalog_set_to_model(catalogs: DomainCatalogSet) -> DomainCatalogSetModel:
    """Convert structured output to embedded model."""
    if hasattr(catalogs, "model_dump"):
        payload = catalogs.model_dump()
    else:
        payload = dict(catalogs)
    return DomainCatalogSetModel(**payload)


async def upsert_domain_catalog_set_doc(
    run_id: str,
    query: str,
    domain_catalogs: DomainCatalogSet,
    pipeline_version: str = "v1",
) -> PydanticObjectId:
    """
    Upsert a DomainCatalogSetDoc for a given run.
    
    Returns:
        The document ID (MongoDB ObjectId)
    """
    payload = _convert_domain_catalog_set_to_model(domain_catalogs)
    
    # Try to find existing doc for this run
    existing = await DomainCatalogSetDoc.find_one(DomainCatalogSetDoc.runId == run_id)
    
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
        doc = DomainCatalogSetDoc(
            runId=run_id,
            query=query,
            payload=payload,
            pipelineVersion=pipeline_version,
        )
        await doc.insert()
        return doc.id


async def get_domain_catalog_set_doc_by_run_id(run_id: str) -> Optional[DomainCatalogSetDoc]:
    """Retrieve domain catalog set doc by run ID."""
    return await DomainCatalogSetDoc.find_one(DomainCatalogSetDoc.runId == run_id)


async def delete_domain_catalog_set_doc_by_run_id(run_id: str) -> int:
    """Delete domain catalog set doc for a run. Returns count of deleted docs."""
    result = await DomainCatalogSetDoc.find(DomainCatalogSetDoc.runId == run_id).delete()
    return result.deleted_count if result else 0
