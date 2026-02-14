from pydantic import BaseModel
from typing import Optional, List


# ============================================================================
# Lifecycle Events (Start/Complete/Error)
# ============================================================================
class EntityCandidateRunStart(BaseModel):
    query: str
    thread_id: str
    checkpoint_ns: str


class EntityCandidateRunComplete(BaseModel):
    intel_run_id: str
    pipeline_version: str
    has_candidates: bool
    entity_count: Optional[int] = None
    dedupe_group_count: Optional[int] = None


class EntityCandidateRunError(BaseModel):
    error: str
    error_type: str
    node: Optional[str] = None  # Which node failed


# ============================================================================
# Progress Events (Stage Updates)
# ============================================================================
class EntityCandidateRunInitialized(BaseModel):
    """Run initialization complete - persistence ready"""
    intel_run_id: str
    pipeline_version: str


class EntityCandidateRunSeedsComplete(BaseModel):
    """Seed extraction complete"""
    people_count: int
    org_count: int
    product_count: int
    compound_count: int
    tech_count: int


class EntityCandidateRunOfficialSourcesComplete(BaseModel):
    """Official sources discovery complete"""
    source_count: int
    has_primary_org: bool
    has_primary_person: bool


class EntityCandidateRunDomainCatalogsComplete(BaseModel):
    """Domain catalog mapping complete"""
    catalog_count: int
    domains: List[str]


class EntityCandidateRunSliceStarted(BaseModel):
    """Fan-out slice processing started"""
    base_domain: str
    slice_index: int
    total_slices: int


class EntityCandidateRunSliceComplete(BaseModel):
    """Fan-out slice processing complete"""
    base_domain: str
    slice_index: int
    total_slices: int
    candidate_count: int


class EntityCandidateRunMergeComplete(BaseModel):
    """All slices merged"""
    total_candidates: int
    total_slices: int


class EntityCandidateRunPersistenceComplete(BaseModel):
    """Final persistence complete"""
    entity_count: int
    dedupe_group_count: int