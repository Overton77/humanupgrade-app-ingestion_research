from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional 
from research_agent.human_upgrade.structured_outputs.candidates_outputs import ConnectedCandidates


StageMode = Literal["full_entities_standard", "full_entities_deep"] 

ToolType = Literal[
    # Search / discovery
    "search.tavily",
    "search.exa",
    "search.serper",
    # Browsing / interaction
    "browser.playwright",
    "fetch.http",
    # Extraction
    "extract.tavily",
    "extract.readability",
    # PDF / docs
    "doc.pdf_text",
    "doc.pdf_screenshot_ocr",
    # Scholarly / registries
    "scholar.pubmed",
    "scholar.semantic_scholar",
    "registry.clinicaltrials",
    # Video (optional if you have it)
    "media.youtube_transcript",
    # Marketplaces/reviews (optional)
    "reviews.web",
    # Filesystem / memory ops
    "fs.read",
    "fs.write",
    "context.summarize",
]

AgentType = Literal[
    # Stage 1
    "BusinessIdentityAndLeadershipAgent",
    "PersonBioAndAffiliationsAgent",
    "EcosystemMapperAgent",
    "CredibilitySignalScannerAgent",
    # Stage 2
    "ProductCatalogerAgent",
    "ProductSpecAgent",
    "TechnologyProcessAndManufacturingAgent",
    "ClaimsExtractorAndTaxonomyMapperAgent",
    "ProductReviewsAgent",
    # Stage 3
    "CaseStudyHarvestAgent",
    "EvidenceClassifierAgent",
    "StrengthAndGapAssessorAgent",
    "ContraindicationsAndSafetyAgent",
    "ClinicalEvidenceTriageAgent",
    # Stage 4
    "KnowledgeSynthesizerAgent",
    "ClaimConfidenceScorerAgent",
    "NarrativeAnalystAgent",
    "ResearchRouterAgent",
]

ContentFormat = Literal["html", "pdf", "video", "image", "text", "json", "other"]

SourceCategory = Literal[
    "official_home",
    "official_about",
    "official_leadership",
    "official_products",
    "official_product_detail",
    "official_help_center",
    "official_docs_manuals",
    "official_research",
    "official_blog",
    "press_news",
    "regulatory",
    "scholarly",
    "clinical_trials",
    "marketplace_reviews",
    "social_community",
    "other",
]

class CuratedSource(BaseModel):
    url: str 
    category: SourceCategory
    format: ContentFormat = "html"
    title: Optional[str] = None
    notes: Optional[str] = None
    # Optionally precomputed metadata
    language: Optional[str] = "en"


class CuratedSourcesBundle(BaseModel):
    sources: List[CuratedSource] = Field(default_factory=list)
    notes: Optional[str] = None

class ToolPolicy(BaseModel):
    allowed: List[ToolType] = Field(default_factory=list)
    preferred: List[ToolType] = Field(default_factory=list)
    forbidden: List[ToolType] = Field(default_factory=list)

class ContextPolicy(BaseModel):
    # Maximum “stuff” the agent should attempt to load into context at once
    max_chars_in_context: int = 60000
    summarization_enabled: bool = True
    summarization_tool: ToolType = "context.summarize"
    file_cache_enabled: bool = True
    file_read_tool: ToolType = "fs.read"
    file_write_tool: ToolType = "fs.write"
    # Optional: summarization triggers
    summarize_when_chars_exceed: int = 70000


class Objective(BaseModel):
    objective: str
    sub_objectives: List[str] = []
    success_criteria: List[str] = []


class ModeAndAgentRecommendationsBundle(BaseModel):
    stage_mode: StageMode = "full_entities_standard"
    recommended_agent_types: List[AgentType] = Field(default_factory=list)
    # Soft constraints / preferences
    priorities: List[str] = Field(default_factory=list)  # e.g. ["safety", "tech", "claims"]
    max_total_agent_instances: Optional[int] = 30
    allow_product_reviews: bool = False
    notes: Optional[str] = None


class ToolRecommendationsBundle(BaseModel):
    # Allowed tools overall for this mission
    allowed_tools: List[ToolType] = Field(default_factory=list)
    # Optional: per-agent defaults
    default_tools_by_agent_type: Dict[AgentType, List[ToolType]] = Field(default_factory=dict)
    notes: Optional[str] = None

class SliceSpec(BaseModel):
    dimension: str
    slice_id: str
    rationale: str
    product_names: List[str] = []
    person_names: List[str] = []
    source_urls: List[str] = []
    notes: Optional[str] = None


class PlanAgentInstance(BaseModel):
    instance_id: str
    agent_type: AgentType
    stage_id: str              # "S1".."S4"
    sub_stage_id: str          # "S1.1" etc.

    slice: Optional[SliceSpec] = None
    objectives: List[Objective] = Field(default_factory=list)

    

    max_search_queries: int = 10

    # still valuable for correctness + planning deps
    requires_artifacts: List[str] = Field(default_factory=list)
    produces_artifacts: List[str] = Field(default_factory=list)

    notes: Optional[str] = None


class AgentInstancePlanWithSources(BaseModel):
    instance_id: str
    agent_type: str
    stage_id: str
    sub_stage_id: str

    slice: Optional[SliceSpec] = None
    objectives: List[Objective] = []
    starter_sources: Optional[List[CuratedSource]] = None  

    # tool_policy: ToolPolicy
    # context_policy: ContextPolicy

    requires_artifacts: List[str] = []
    produces_artifacts: List[str] = []

    max_search_queries: int = 10
    max_pages_to_browse: int = 15
    max_extractions: int = 20
    max_pdfs_to_process: int = 5

    notes: Optional[str] = None


class SubStagePlan(BaseModel):
    sub_stage_id: str
    name: str
    description: str
    agent_instances: List[str] = Field(default_factory=list)  # instance_ids in this substage
    can_run_in_parallel: bool = True
    depends_on_substages: List[str] = Field(default_factory=list)


class StagePlan(BaseModel):
    stage_id: str
    name: str
    description: str
    sub_stages: List[SubStagePlan] = []
    depends_on_stages: List[str] = []



class ResearchPlan(BaseModel):
    mission_id: str
    stage_mode: StageMode = "full_entities_standard"

    # Entities in scope
    target_businesses: List[str] = Field(default_factory=list)
    target_people: List[str] = Field(default_factory=list)
    target_products: List[str] = Field(default_factory=list)

    mission_objectives: List[str] = Field(default_factory=list)

    stages: List[StagePlan] = Field(default_factory=list)
    agent_instances: List[PlanAgentInstance] = Field(default_factory=list)

    agent_instance_counts: Dict[str, int] = Field(default_factory=dict)

    allow_product_reviews: bool = False
    notes: Optional[str] = None

class ResearchMissionPlanFinal(BaseModel):
    mission_id: str
    stage_mode: StageMode = "full_entities_standard"

    # Entities in scope
    target_businesses: List[str] = Field(default_factory=list)  # business names
    target_people: List[str] = Field(default_factory=list)      # names
    target_products: List[str] = Field(default_factory=list)    # names

    # Top-level goals
    mission_objectives: List[str] = Field(default_factory=list)

    # The actual plan
    stages: List[StagePlan]
    agent_instances: List[AgentInstancePlanWithSources]

    # Counts summary (explicit requirement)
    agent_instance_counts: Dict[AgentType, int] = Field(default_factory=dict)

    # Execution preferences
    allow_product_reviews: bool = False
    notes: Optional[str] = None