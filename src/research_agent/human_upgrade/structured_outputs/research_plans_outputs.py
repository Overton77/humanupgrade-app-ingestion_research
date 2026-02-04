from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional 
from research_agent.human_upgrade.structured_outputs.candidates_outputs import ConnectedCandidates


StageMode = Literal["full_entities_standard", "full_entities_basic", "full_entities_deep"] 

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
    # Stage 2
    "ProductSpecAgent",
    "TechnologyProcessAndManufacturingAgent",
    "ClaimsExtractorAndTaxonomyMapperAgent",
    "ProductReviewsAgent",
    # Stage 3
    "CaseStudyHarvestAgent",
    "EvidenceClassifierAgent",
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
    title: Optional[str] = None
    notes: Optional[str] = None
    # Optionally precomputed metadata
    language: Optional[str] = "en"


class CuratedSourcesBundle(BaseModel):
    sources: List[CuratedSource] = Field(default_factory=list)
    notes: Optional[str] = None


class SourceExpansion(BaseModel):
    competitorUrls: List[str] = Field(default_factory=list, description="URLs of competitor websites and companies")
    researchUrls: List[str] = Field(default_factory=list, description="URLs of research papers, case studies, and scholarly sources")
    otherUrls: List[str] = Field(default_factory=list, description="Other supplementary URLs (news, press releases, industry reports, etc.)")
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




class AgentInstancePlanWithoutSources(BaseModel):
    instance_id: str
    agent_type: AgentType 
    stage_id: str
    sub_stage_id: str

    slice: Optional[SliceSpec] = None
    objectives: List[Objective] = []
   

    requires_artifacts: List[str] = []
    produces_artifacts: List[str] = []

    notes: Optional[str] = None


class AgentInstancePlanWithSources(BaseModel):
    instance_id: str
    agent_type: AgentType 
    stage_id: str
    sub_stage_id: str

    slice: Optional[SliceSpec] = None
    objectives: List[Objective] = []
    starter_sources: Optional[List[CuratedSource]] = None  

    requires_artifacts: List[str] = []
    produces_artifacts: List[str] = []

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




class InitialResearchPlan(BaseModel):
    mission_id: str
    stage_mode: StageMode = "full_entities_standard"

    # Entities in scope
    target_businesses: List[str] = Field(default_factory=list)  # business names
    target_people: List[str] = Field(default_factory=list)      # names
    target_products: List[str] = Field(default_factory=list)    # names

    # Top-level goals (using Objective objects to match agent instance objectives)
    mission_objectives: List[Objective] = Field(default_factory=list)

    # The actual plan (without sources)
    stages: List[StagePlan]
    agent_instances: List[AgentInstancePlanWithoutSources]

    notes: Optional[str] = None


class ResearchMissionPlanFinal(BaseModel):
    mission_id: str
    stage_mode: StageMode = "full_entities_standard"

    # Entities in scope
    target_businesses: List[str] = Field(default_factory=list)  # business names
    target_people: List[str] = Field(default_factory=list)      # names
    target_products: List[str] = Field(default_factory=list)    # names

    # Top-level goals (using Objective objects to match agent instance objectives)
    mission_objectives: List[Objective] = Field(default_factory=list)

    # The actual plan (with sources attached)
    stages: List[StagePlan]
    agent_instances: List[AgentInstancePlanWithSources]

    notes: Optional[str] = None