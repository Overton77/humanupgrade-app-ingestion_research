from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


# -------------------------
# Shared base + enums
# -------------------------

class MongoModel(BaseModel):
    """
    Mongo-friendly base:
    - accepts `_id` as alias for `id`
    - permissive schema while you're iterating
    """
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",  # flip to "forbid" once stabilized
        str_strip_whitespace=True,
    )

    id: Optional[str] = Field(default=None, alias="_id")


class PipelineStatus(str, Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    failed = "failed"


class CandidateStatus(str, Enum):
    # based on your sample, likely lifecycle states
    new = "new"
    accepted = "accepted"
    rejected = "rejected"
    merged = "merged"
    archived = "archived"


class EntityType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    PRODUCT = "PRODUCT"
    COMPOUND = "COMPOUND"
    PLATFORM = "PLATFORM"


class SourceType(str, Enum):
    OFFICIAL = "OFFICIAL"
    NEWS_OR_PR = "NEWS_OR_PR"
    ACADEMIC = "ACADEMIC"
    SOCIAL = "SOCIAL"
    WIKI = "WIKI"
    OTHER = "OTHER"


class ValidationLevel(str, Enum):
    ENTITY_MATCH = "ENTITY_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    WEAK_MATCH = "WEAK_MATCH"
    UNVERIFIED = "UNVERIFIED"


class DedupeResolutionStatus(str, Enum):
    unresolved = "unresolved"
    resolved = "resolved"
    ignored = "ignored"


# -------------------------
# Reusable nested models
# -------------------------


class DomainCatalogSetRef(MongoModel):
    """
    Reference to a DomainCatalogSet stored elsewhere (e.g., intel_artifacts).
    Kept tiny for provenance + rehydration.
    """
    domainCatalogSetId: str = Field(..., description="ID of the DomainCatalogSet artifact (e.g., intel_artifacts.artifactId).")
    domainCatalogExtractedAt: datetime = Field(..., description="When the catalog set was extracted/created.")
    # Optional convenience fields (safe to keep None until you want them)
    artifactType: Optional[str] = Field(default="domain_catalog_set", description="Type discriminator for the artifact store.")
    artifactVersion: Optional[str] = Field(default=None, description="Optional schema/pipeline version for the artifact payload.")
    notes: Optional[str] = None

class CandidateSource(MongoModel):
    url: HttpUrl
    label: Optional[str] = None
    sourceType: SourceType = SourceType.OTHER
    rank: Optional[int] = None
    score: Optional[float] = None
    signals: List[str] = Field(default_factory=list)
    validationLevel: Optional[ValidationLevel] = None


class EntityRef(MongoModel):
    """
    The nested object shape used inside the connected bundle:
    guest/business/product/platform/compound all look like this.
    """
    inputName: str
    normalizedName: str
    typeHint: EntityType
    canonicalName: Optional[str] = None
    canonicalConfidence: Optional[float] = None
    candidates: List[CandidateSource] = Field(default_factory=list)
    notes: Optional[str] = None


class ProductWithCompounds(MongoModel):
    product: EntityRef
    compounds: List[EntityRef] = Field(default_factory=list)
    compoundLinkNotes: Optional[str] = None
    compoundLinkConfidence: Optional[float] = None


class BusinessBundle(MongoModel):
    business: EntityRef
    products: List[ProductWithCompounds] = Field(default_factory=list)
    platforms: List[EntityRef] = Field(default_factory=list)
    notes: Optional[str] = None


class ConnectedNode(MongoModel):
    guest: EntityRef
    businesses: List[BusinessBundle] = Field(default_factory=list)
    notes: Optional[str] = None


class ConnectedBundle(MongoModel):
    connected: List[ConnectedNode] = Field(default_factory=list)
    globalNotes: Optional[str] = None


class CandidateRunPayload(MongoModel):
    connectedBundleHash: str
    connectedBundle: ConnectedBundle
    candidateEntityCount: int
    dedupeGroupCount: int


# -------------------------
# intel_candidate_runs
# -------------------------

class IntelCandidateRun(MongoModel):
    runId: str
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    episodeId: str
    episodeUrl: HttpUrl

    pipelineVersion: str
    status: PipelineStatus

    payload: CandidateRunPayload 

    domainCatalog: Optional[DomainCatalogSetRef] = Field(
        default=None,
        description="Reference to DomainCatalogSet artifact generated during the run (Node B).",
    )



# -------------------------
# intel_candidate_entities
# -------------------------

class IntelCandidateEntity(MongoModel):
    candidateEntityId: str
    runId: str
    pipelineVersion: str

    episodeId: str
    episodeUrl: HttpUrl

    type: EntityType

    inputName: str
    normalizedName: str

    canonicalName: Optional[str] = None
    canonicalConfidence: Optional[float] = None

    entityKey: str
    bestUrl: Optional[HttpUrl] = None

    candidateSources: List[CandidateSource] = Field(default_factory=list)
    notes: Optional[str] = None

    status: CandidateStatus = CandidateStatus.new
    createdAt: datetime


# -------------------------
# intel_dedupe_groups
# -------------------------

class DedupeMember(MongoModel):
    candidateEntityId: str
    episodeId: str
    runId: str


class IntelDedupeGroup(MongoModel):
    dedupeGroupId: str

    type: EntityType
    entityKey: str

    canonicalName: Optional[str] = None

    members: List[DedupeMember] = Field(default_factory=list)

    resolutionStatus: DedupeResolutionStatus = DedupeResolutionStatus.unresolved

    createdAt: datetime
    updatedAt: Optional[datetime] = None



class PlanStatus(str, Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    failed = "failed"


class DirectionType(str, Enum):
    GUEST = "GUEST"
    BUSINESS = "BUSINESS"
    PRODUCT = "PRODUCT"
    COMPOUND = "COMPOUND"
    PLATFORM = "PLATFORM"


class StarterSourceType(str, Enum):
    OFFICIAL = "OFFICIAL"
    REPUTABLE_SECONDARY = "REPUTABLE_SECONDARY"
    ACADEMIC = "ACADEMIC"
    NEWS_OR_PR = "NEWS_OR_PR"
    SOCIAL = "SOCIAL"
    OTHER = "OTHER"


class StarterSourceUse(str, Enum):
    # Union across the sample; add more later without breaking by keeping extra="allow"
    ROLE_AFFILIATION = "ROLE_AFFILIATION"
    BIO = "BIO"
    TIMELINE = "TIMELINE"
    PUBLIC_SPEECHES = "PUBLIC_SPEECHES"
    CREDENTIALS = "CREDENTIALS"
    SOCIAL_LINKS = "SOCIAL_LINKS"
    NEWS = "NEWS"
    OVERVIEW = "OVERVIEW"
    EXEC_TEAM = "EXEC_TEAM"
    CONTACTS = "CONTACTS"
    PRODUCT_LINE = "PRODUCT_LINE"
    MARKETING_CLAIMS = "MARKETING_CLAIMS"
    TECHNOLOGY_DESCRIPTION = "TECHNOLOGY_DESCRIPTION"
    PLATFORM = "PLATFORM"
    BUSINESS_MODEL = "BUSINESS_MODEL"
    CDMO = "CDMO"
    FUNDING = "FUNDING"
    COMPANY_HISTORY = "COMPANY_HISTORY"
    PRODUCT_DETAILS = "PRODUCT_DETAILS"
    INGREDIENTS = "INGREDIENTS"
    DOSAGE = "DOSAGE"
    SUPPLEMENT_FACTS = "SUPPLEMENT_FACTS"
    VARIANTS = "VARIANTS"
    CERTIFICATIONS = "CERTIFICATIONS"
    DOSAGE_CLAIMS = "DOSAGE_CLAIMS"
    IDENTIFICATION = "IDENTIFICATION"
    SOURCES = "SOURCES"
    CLASSIFICATION = "CLASSIFICATION"
    CHEMICAL_PROPERTIES = "CHEMICAL_PROPERTIES"
    ALIASES = "ALIASES"
    ALIAS_CHECK = "ALIAS_CHECK"
    BIOACTIVITY = "BIOACTIVITY"
    PATENTS = "PATENTS"
    IP_SEARCH = "IP_SEARCH"
    TECHNICAL_CONTEXT = "TECHNICAL_CONTEXT"
    BACKGROUND = "BACKGROUND"
    OUTPUTS = "OUTPUTS"
    PROCESS_FLOW = "PROCESS_FLOW"


# -------------------------
# Nested: directions
# -------------------------

class StarterSource(MongoModel):
    url: HttpUrl
    sourceType: StarterSourceType = StarterSourceType.OTHER
    usedFor: List[StarterSourceUse] = Field(default_factory=list)
    reason: Optional[str] = None
    confidence: Optional[float] = None


class ChosenDirectionBase(MongoModel):
    objective: str
    starterSources: List[StarterSource] = Field(default_factory=list)
    scopeNotes: Optional[str] = None
    riskFlags: List[str] = Field(default_factory=list)


class GuestChosenDirection(ChosenDirectionBase):
    guestCanonicalName: str


class BusinessChosenDirection(ChosenDirectionBase):
    businessNames: List[str] = Field(default_factory=list)


class ProductsChosenDirection(ChosenDirectionBase):
    productNames: List[str] = Field(default_factory=list)


class CompoundsChosenDirection(ChosenDirectionBase):
    compoundNames: List[str] = Field(default_factory=list)


class PlatformsChosenDirection(ChosenDirectionBase):
    platformNames: List[str] = Field(default_factory=list)


class GuestDirection(MongoModel):
    chosenDirection: GuestChosenDirection
    requiredFields: List[str] = Field(default_factory=list)


class BusinessDirection(MongoModel):
    chosenDirection: BusinessChosenDirection
    requiredFields: List[str] = Field(default_factory=list)


class ProductsDirection(MongoModel):
    chosenDirection: ProductsChosenDirection
    requiredFields: List[str] = Field(default_factory=list)


class CompoundsDirection(MongoModel):
    chosenDirection: CompoundsChosenDirection
    requiredFields: List[str] = Field(default_factory=list)


class PlatformsDirection(MongoModel):
    chosenDirection: PlatformsChosenDirection
    requiredFields: List[str] = Field(default_factory=list)


class ResearchDirections(MongoModel):
    bundleId: str

    guestDirection: Optional[GuestDirection] = None
    businessDirection: Optional[BusinessDirection] = None
    productsDirection: Optional[ProductsDirection] = None
    compoundsDirection: Optional[CompoundsDirection] = None
    platformsDirection: Optional[PlatformsDirection] = None

    notes: Optional[str] = None


# -------------------------
# Nested: targets
# -------------------------

class ResearchTargets(MongoModel):
    guestCanonicalName: Optional[str] = None
    businessNames: List[str] = Field(default_factory=list)
    productNames: List[str] = Field(default_factory=list)
    compoundNames: List[str] = Field(default_factory=list)
    platformNames: List[str] = Field(default_factory=list)


# -------------------------
# Nested: execution artifacts
# -------------------------

class FileReference(MongoModel):
    file_path: str
    description: Optional[str] = None
    bundle_id: Optional[str] = None
    entity_key: Optional[str] = None


class ExecutionMeta(MongoModel):
    executionRunId: str
    threadId: str
    bundleId: str

    # note: in your sample this is a string with a space, not ISO8601
    completedAt: Optional[str] = None

    finalReports: List[FileReference] = Field(default_factory=list)
    fileRefs: List[FileReference] = Field(default_factory=list)


# -------------------------
# intel_research_plans
# -------------------------

class IntelResearchPlan(MongoModel):
    planId: str
    bundleId: str

    createdAt: datetime
    updatedAt: Optional[datetime] = None

    startedAt: Optional[datetime] = None
    finishedAt: Optional[datetime] = None

    runId: str
    pipelineVersion: str
    status: PlanStatus

    episodeId: str
    episodeUrl: HttpUrl

    dedupeGroupIds: List[str] = Field(default_factory=list)

    directions: ResearchDirections
    targets: ResearchTargets

    execution: Optional[ExecutionMeta] = None 


INTEL_ARTIFACTS_COLLECTION: str = "intel_artifacts"


class IntelArtifactKind(str, Enum):
    """
    A small discriminator enum for the artifact store.
    Keep this permissive — you can add kinds without breaking older data.
    """
    domain_catalog_set = "domain_catalog_set"
    # future:
    # official_starter_sources = "official_starter_sources"
    # subagent_plan = "subagent_plan"
    # subagent_run = "subagent_run"
    # case_study_harvest = "case_study_harvest"
    other = "other"


class IntelArtifact(MongoModel):
    """
    Generic artifact store document.

    Stores large / evolving payloads (DomainCatalogSet, SubAgentPlans, tool outputs, etc.)
    so the "core" collections stay stable and smaller.

    Collection: intel_artifacts
    """
    artifactId: str

    # provenance
    runId: str
    episodeId: str
    episodeUrl: HttpUrl
    pipelineVersion: str

    kind: IntelArtifactKind = IntelArtifactKind.other
    payloadHash: str

    # timing
    createdAt: datetime
    updatedAt: Optional[datetime] = None
    extractedAt: Optional[datetime] = None  # "when computed" convenience

    # opaque payload (schema varies by kind)
    payload: Dict[str, Any] = Field(default_factory=dict)

    # optional
    notes: Optional[str] = None


def validate_intel_artifact(doc: Dict[str, Any]) -> IntelArtifact:
    return IntelArtifact.model_validate(doc)

# -------------------------
# quick validation helpers
# -------------------------

def validate_candidate_run(doc: Dict[str, Any]) -> IntelCandidateRun:
    return IntelCandidateRun.model_validate(doc)

def validate_candidate_entity(doc: Dict[str, Any]) -> IntelCandidateEntity:
    return IntelCandidateEntity.model_validate(doc)

def validate_dedupe_group(doc: Dict[str, Any]) -> IntelDedupeGroup:
    return IntelDedupeGroup.model_validate(doc)


def validate_research_plan(doc: Dict[str, Any]) -> IntelResearchPlan:
    return IntelResearchPlan.model_validate(doc)