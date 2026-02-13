"""Repository for IntelCandidateEntityDoc and IntelDedupeGroupDoc operations."""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Any

from research_agent.models.mongo.entities.docs.candidate_entities import IntelCandidateEntityDoc
from research_agent.models.mongo.entities.docs.dedupe_groups import IntelDedupeGroupDoc
from research_agent.models.mongo.entities.embedded.dedupe_members import DedupeMemberModel
from research_agent.models.mongo.candidates.embedded.entity_sources import SourceCandidateModel
from research_agent.models.base.enums import EntityTypeHint, CandidateStatus, DedupeResolutionStatus
from research_agent.utils.datetime_helpers import utc_now
from research_agent.human_upgrade.structured_outputs.candidates_outputs import (
    ConnectedCandidates,
    EntitySourceResult,
)


def build_entity_key(type_hint: EntityTypeHint, normalized_name: str) -> str:
    """Build stable entity key for deduplication."""
    return f"{type_hint.value}:{normalized_name.lower().strip()}"


def _convert_source_candidate(source: Dict[str, Any]) -> SourceCandidateModel:
    """Convert source candidate dict to model."""
    return SourceCandidateModel(**source)


def _flatten_entity_source_result_to_candidate_entities(
    run_id: str,
    pipeline_version: str,
    base_domain: Optional[str],
    mapped_from_url: Optional[str],
    entity_result: EntitySourceResult,
) -> IntelCandidateEntityDoc:
    """
    Convert an EntitySourceResult to an IntelCandidateEntityDoc.
    """
    type_hint = entity_result.typeHint
    if not isinstance(type_hint, EntityTypeHint):
        type_hint = EntityTypeHint(type_hint)
    
    entity_key = build_entity_key(type_hint, entity_result.normalizedName)
    
    # Convert candidates to models
    source_models = [
        _convert_source_candidate(
            c.model_dump() if hasattr(c, "model_dump") else dict(c)
        )
        for c in (entity_result.candidates or [])
    ]
    
    doc = IntelCandidateEntityDoc(
        candidateEntityId=str(uuid.uuid4()),
        runId=run_id,
        pipelineVersion=pipeline_version,
        typeHint=type_hint,
        inputName=entity_result.inputName,
        normalizedName=entity_result.normalizedName,
        canonicalName=entity_result.canonicalName,
        canonicalConfidence=entity_result.canonicalConfidence,
        entityKey=entity_key,
        candidateSources=source_models,
        baseDomain=base_domain,
        mappedFromUrl=mapped_from_url,
        status=CandidateStatus.new,
        notes=entity_result.notes,
    )
    return doc


def flatten_connected_candidates_to_entity_docs(
    run_id: str,
    pipeline_version: str,
    connected_candidates: ConnectedCandidates,
) -> List[IntelCandidateEntityDoc]:
    """
    Extract all entities from a ConnectedCandidates slice into IntelCandidateEntityDoc list.
    """
    docs: List[IntelCandidateEntityDoc] = []
    
    base_domain = connected_candidates.baseDomain
    mapped_from_url = connected_candidates.mappedFromUrl
    
    bundle = connected_candidates.intel_bundle
    
    # Organization
    if bundle.organization:
        docs.append(_flatten_entity_source_result_to_candidate_entities(
            run_id, pipeline_version, base_domain, mapped_from_url, bundle.organization
        ))
    
    # People
    for person in (bundle.people or []):
        docs.append(_flatten_entity_source_result_to_candidate_entities(
            run_id, pipeline_version, base_domain, mapped_from_url, person
        ))
    
    # Technologies
    for tech in (bundle.technologies or []):
        docs.append(_flatten_entity_source_result_to_candidate_entities(
            run_id, pipeline_version, base_domain, mapped_from_url, tech
        ))
    
    # Products (with compounds)
    for product_with_compounds in (bundle.products or []):
        product = product_with_compounds.product
        docs.append(_flatten_entity_source_result_to_candidate_entities(
            run_id, pipeline_version, base_domain, mapped_from_url, product
        ))
        
        # Compounds linked to this product
        for compound in (product_with_compounds.compounds or []):
            docs.append(_flatten_entity_source_result_to_candidate_entities(
                run_id, pipeline_version, base_domain, mapped_from_url, compound
            ))
    
    # Business-level compounds
    for compound in (bundle.businessLevelCompounds or []):
        docs.append(_flatten_entity_source_result_to_candidate_entities(
            run_id, pipeline_version, base_domain, mapped_from_url, compound
        ))
    
    # Related organizations
    for org in (bundle.relatedOrganizations or []):
        docs.append(_flatten_entity_source_result_to_candidate_entities(
            run_id, pipeline_version, base_domain, mapped_from_url, org
        ))
    
    return docs


async def bulk_insert_candidate_entities(docs: List[IntelCandidateEntityDoc]) -> List[str]:
    """
    Bulk insert candidate entities.
    
    Returns:
        List of candidateEntityIds inserted
    """
    if not docs:
        return []
    
    await IntelCandidateEntityDoc.insert_many(docs)
    return [doc.candidateEntityId for doc in docs]


async def delete_candidate_entities_for_run(run_id: str) -> int:
    """
    Delete all candidate entities for a run (for rerun safety).
    
    Returns:
        Count of deleted docs
    """
    result = await IntelCandidateEntityDoc.find(IntelCandidateEntityDoc.runId == run_id).delete()
    return result.deleted_count if result else 0


async def get_candidate_entities_by_run_id(run_id: str) -> List[IntelCandidateEntityDoc]:
    """Retrieve all candidate entities for a run."""
    return await IntelCandidateEntityDoc.find(IntelCandidateEntityDoc.runId == run_id).to_list()


async def upsert_dedupe_group_and_add_member(
    type_hint: EntityTypeHint,
    entity_key: str,
    canonical_name: str,
    member: Dict[str, Any],
) -> IntelDedupeGroupDoc:
    """
    Upsert a dedupe group and add a member.
    
    Args:
        type_hint: Entity type
        entity_key: Stable entity key (TYPE:normalized_name)
        canonical_name: Canonical name for this entity
        member: Dict with candidateEntityId, runId, optional entityDocId
        
    Returns:
        The dedupe group doc
    """
    # Try to find existing group
    existing = await IntelDedupeGroupDoc.find_one(
        IntelDedupeGroupDoc.entityKey == entity_key
    )
    
    member_model = DedupeMemberModel(**member)
    
    if existing:
        # Check if member already exists
        member_ids = {m.candidateEntityId for m in existing.members}
        if member_model.candidateEntityId not in member_ids:
            existing.members.append(member_model)
            existing.updatedAt = utc_now()
            await existing.save()
        return existing
    else:
        # Create new group
        doc = IntelDedupeGroupDoc(
            dedupeGroupId=str(uuid.uuid4()),
            typeHint=type_hint,
            entityKey=entity_key,
            canonicalName=canonical_name,
            members=[member_model],
            resolutionStatus=DedupeResolutionStatus.unresolved,
        )
        await doc.insert()
        return doc


async def get_dedupe_group_by_entity_key(entity_key: str) -> Optional[IntelDedupeGroupDoc]:
    """Retrieve dedupe group by entity key."""
    return await IntelDedupeGroupDoc.find_one(IntelDedupeGroupDoc.entityKey == entity_key)


async def get_all_dedupe_groups_for_type(type_hint: EntityTypeHint) -> List[IntelDedupeGroupDoc]:
    """Retrieve all dedupe groups for a given entity type."""
    return await IntelDedupeGroupDoc.find(IntelDedupeGroupDoc.typeHint == type_hint).to_list()
