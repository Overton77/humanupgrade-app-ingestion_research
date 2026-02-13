# research_agent/mission/types.py
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

class StageMode(str, Enum):
    full_entities_basic = "full_entities_basic"
    full_entities_standard = "full_entities_standard"
    full_entities_deep = "full_entities_deep"

class TaskType(str, Enum):
    INSTANCE_RUN = "INSTANCE_RUN"
    SUBSTAGE_REDUCE = "SUBSTAGE_REDUCE"
    STAGE_REDUCE = "STAGE_REDUCE"
    MISSION_REDUCE = "MISSION_REDUCE"

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    ENQUEUED = "ENQUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"

class OutputType(str, Enum):
    # You can expand this list as you formalize outputs.
    EntityBiography = "EntityBiography"
    OperatingPostureSummary = "OperatingPostureSummary"
    HighLevelTimeline = "HighLevelTimeline"
    ProductList = "ProductList"

    PeopleProfiles = "PeopleProfiles"
    RoleResponsibilityMap = "RoleResponsibilityMap"
    CredentialAnchors = "CredentialAnchors"

    CompetitorSet = "CompetitorSet"
    PartnerAndPlatformGraph = "PartnerAndPlatformGraph"
    MarketCategoryPlacement = "MarketCategoryPlacement"

    ProductSpecs = "ProductSpecs"
    IngredientOrMaterialLists = "IngredientOrMaterialLists"
    UsageAndWarningSnippets = "UsageAndWarningSnippets"

    EvidenceArtifacts = "EvidenceArtifacts"

class SourceRef(BaseModel):
    url: str
    category: str
    title: Optional[str] = None
    notes: Optional[str] = None
    language: Optional[str] = "en"

class SliceSpec(BaseModel):
    dimension: Literal["people", "products", "sources", "custom"]
    slice_id: str
    rationale: Optional[str] = None
    product_names: List[str] = []
    person_names: List[str] = []
    source_urls: List[str] = []
    notes: Optional[str] = None

class ObjectiveSpec(BaseModel):
    objective: str
    sub_objectives: List[str] = []
    success_criteria: List[str] = []

class InstanceOutputRequirement(BaseModel):
    from_instance_id: str
    output_type: Literal["final_report", "outputs"] = "final_report"
    required: bool = False
    notes: str = ""

class OutputRequirement(BaseModel):
    # “I need OutputType X, optionally scoped to a subject”
    output_type: OutputType
    required: bool = True
    # optional scoping: specific product/person/etc
    subject_key: Optional[str] = None  # e.g. "person:Brad Pitzele", "product:2000-series EWOT System"
    notes: Optional[str] = None
