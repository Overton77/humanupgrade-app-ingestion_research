from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StageName(str, Enum):
    S0_SCOPE = "stage_0_scope_inputs"
    S1_GROUND_TRUTH = "stage_1_ground_truth"
    S2_DEPENDENT_ENRICHMENT = "stage_2_dependent_enrichment"
    S3_TRIAGE_SYNTHESIS = "stage_3_triage_synthesis"


class SubAgentType(str, Enum):
    # Stage 0
    DomainCatalogExpansionAgent = "DomainCatalogExpansionAgent"
    SourceSetCuratorAgent = "SourceSetCuratorAgent"

    # Stage 1
    BusinessIdentityAndLeadershipAgent = "BusinessIdentityAndLeadershipAgent"
    ProductSpecAgent = "ProductSpecAgent"
    HelpCenterAgent = "HelpCenterAgent"
    PressAndReputationAgent = "PressAndReputationAgent"
    PersonBioAndAffiliationsAgent = "PersonBioAndAffiliationsAgent"

    # Stage 2
    ContraindicationsAndSafetyAgent = "ContraindicationsAndSafetyAgent"
    CaseStudyHarvestAgent = "CaseStudyHarvestAgent"

    # Stage 3
    ClinicalEvidenceTriageAgent = "ClinicalEvidenceTriageAgent"
    TechnologyProcessAgent = "TechnologyProcessAgent"


class ToolBundle(str, Enum):
    # Keep symbolic; runtime maps these to actual langchain tool lists
    CORE_SEARCH = "CORE_SEARCH"     # tavily_search + fallbacks (exa/serper/ddg/brave)
    CORE_EXTRACT = "CORE_EXTRACT"   # tavily_extract
    MAP = "MAP"                     # tavily_map
    BROWSER = "BROWSER"             # playwright / computer use
    WIKI = "WIKI"                   # wikipedia/wikidata
    MED_DB = "MED_DB"               # pubmed / semantic scholar etc.
    FINANCE_NEWS = "FINANCE_NEWS"   # finance/news APIs (e.g. Yahoo Finance, Polygon, SEC/EDGAR helpers)


class SourceBucket(str, Enum):
    # Must match your DomainCatalog buckets
    productIndexUrls = "productIndexUrls"
    productPageUrls = "productPageUrls"
    platformUrls = "platformUrls"
    leadershipUrls = "leadershipUrls"
    helpCenterUrls = "helpCenterUrls"
    caseStudyUrls = "caseStudyUrls"
    documentationUrls = "documentationUrls"
    policyUrls = "policyUrls"
    pressUrls = "pressUrls"


class SourceBudget(BaseModel):
    """
    Cheap + explicit. You can enforce budgets in your tool wrappers.
    """
    max_search_calls: int = 5
    max_extract_calls: int = 10
    max_map_calls: int = 0
    max_browser_steps: int = 0
    max_pages_total: int = 50
    notes: Optional[str] = None


class SourceSetPlan(BaseModel):
    """
    Declarative: how SourceSetCurator should build a SourceSet for a subagent.
    """
    include_buckets: List[SourceBucket] = Field(default_factory=list)
    seed_urls: List[str] = Field(default_factory=list, description="Must-hit URLs (high signal).")
    include_domains: List[str] = Field(default_factory=list, description="Allowed/preferred domains.")
    exclude_patterns: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class SubAgentPlan(BaseModel):
    agentType: SubAgentType
    stage: StageName
    objective: str

    dependsOn: List[SubAgentType] = Field(default_factory=list)

    # How the agent should be seeded
    sourcePlan: SourceSetPlan
    budget: SourceBudget
    toolBundles: List[ToolBundle] = Field(default_factory=list)

    # Scale knobs (for later expansion)
    maxEntitiesPerBatch: int = 25
    concurrency: int = 2
    enabled: bool = True
    notes: Optional[str] = None


class StagePlan(BaseModel):
    stage: StageName
    agents: List[SubAgentPlan] = Field(default_factory=list)
    concurrency: int = 4
    gateNotes: Optional[str] = None


class BundleResearchPlan(BaseModel):
    """
    This replaces the old 'research directions' output as your runnable plan.
    """
    planId: str = Field(..., description="Stable UUID generated at plan creation time.")
    bundleId: str

    runId: str
    pipelineVersion: str

    episodeId: str
    episodeUrl: str

    guestName: str

    # Link to the DomainCatalog artifact (intel_artifacts)
    domainCatalogSetId: str
    domainCatalogExtractedAt: Optional[str] = None

    # Domains included for this bundle (often 1, but supports multiple)
    businessDomains: List[str] = Field(default_factory=list)

    depthHint: str = Field(default="default", description="light|default|deep")
    notes: Optional[str] = None

    stages: List[StagePlan] = Field(default_factory=list)


class EntityBundlesResearchPlans(BaseModel):
    plans: List[BundleResearchPlan] = Field(default_factory=list)
    globalNotes: Optional[str] = None 



## Example of output 

def make_default_stage_plans(
    *,
    base_domains: List[str],
    has_help_center: bool,
) -> List[StagePlan]:
    """
    Deterministic default stage layout using DomainCatalog buckets.
    SourceSetCurator will turn include_buckets into real URLs later.
    """

    stage0 = StagePlan(
        stage=StageName.S0_SCOPE,
        concurrency=2,
        agents=[
            SubAgentPlan(
                agentType=SubAgentType.DomainCatalogExpansionAgent,
                stage=StageName.S0_SCOPE,
                objective="Expand official domain coverage (products/help/docs/case studies) beyond initial DomainCatalog.",
                dependsOn=[],
                sourcePlan=SourceSetPlan(
                    include_domains=base_domains,
                    include_buckets=[
                        SourceBucket.productIndexUrls,
                        SourceBucket.platformUrls,
                        SourceBucket.helpCenterUrls,
                        SourceBucket.caseStudyUrls,
                        SourceBucket.documentationUrls,
                    ],
                    notes="Prefer official domains; expand only if gaps found.",
                ),
                budget=SourceBudget(max_map_calls=2, max_extract_calls=4, max_search_calls=4, max_pages_total=200),
                toolBundles=[ToolBundle.MAP, ToolBundle.CORE_EXTRACT, ToolBundle.CORE_SEARCH, ToolBundle.BROWSER],
                concurrency=1,
            ),
            SubAgentPlan(
                agentType=SubAgentType.SourceSetCuratorAgent,
                stage=StageName.S0_SCOPE,
                objective="Produce curated SourceSets per subagent type with budgets and notes.",
                dependsOn=[SubAgentType.DomainCatalogExpansionAgent],
                sourcePlan=SourceSetPlan(
                    include_domains=base_domains,
                    include_buckets=[
                        SourceBucket.productIndexUrls,
                        SourceBucket.productPageUrls,
                        SourceBucket.platformUrls,
                        SourceBucket.leadershipUrls,
                        SourceBucket.helpCenterUrls,
                        SourceBucket.caseStudyUrls,
                        SourceBucket.documentationUrls,
                        SourceBucket.policyUrls,
                        SourceBucket.pressUrls,
                    ],
                    notes="Turn DomainCatalog buckets into per-agent URL lists; dedupe and cap.",
                ),
                budget=SourceBudget(max_search_calls=3, max_extract_calls=6, max_pages_total=120),
                toolBundles=[ToolBundle.CORE_SEARCH, ToolBundle.CORE_EXTRACT],
                concurrency=1,
            ),
        ],
        gateNotes="S0 produces Expanded DomainCatalog + per-agent SourceSets.",
    )

    stage1_agents = [
        SubAgentPlan(
            agentType=SubAgentType.BusinessIdentityAndLeadershipAgent,
            stage=StageName.S1_GROUND_TRUTH,
            objective="Establish canonical company overview (name, description, domains, locations) and leadership, including tickers if publicly traded.",
            dependsOn=[SubAgentType.SourceSetCuratorAgent],
            sourcePlan=SourceSetPlan(
                include_buckets=[SourceBucket.platformUrls, SourceBucket.leadershipUrls, SourceBucket.pressUrls],
                include_domains=base_domains,
            ),
            budget=SourceBudget(max_search_calls=4, max_extract_calls=10, max_pages_total=80),
            toolBundles=[ToolBundle.CORE_SEARCH, ToolBundle.CORE_EXTRACT, ToolBundle.BROWSER, ToolBundle.WIKI],
            concurrency=2,
        ),
        SubAgentPlan(
            agentType=SubAgentType.PersonBioAndAffiliationsAgent,
            stage=StageName.S1_GROUND_TRUTH,
            objective="Enrich key people with bios, roles, affiliations, prior companies, and credibility anchors.",
            dependsOn=[SubAgentType.BusinessIdentityAndLeadershipAgent],
            sourcePlan=SourceSetPlan(
                include_buckets=[
                    SourceBucket.leadershipUrls,
                    SourceBucket.pressUrls,
                    SourceBucket.platformUrls,
                ],
                include_domains=base_domains,
                notes="Start from official leadership/Team pages, then branch to high-signal external profiles when needed.",
            ),
            budget=SourceBudget(max_search_calls=6, max_extract_calls=15, max_pages_total=120),
            toolBundles=[ToolBundle.CORE_SEARCH, ToolBundle.CORE_EXTRACT, ToolBundle.BROWSER, ToolBundle.WIKI],
            concurrency=2,
        ),
        SubAgentPlan(
            agentType=SubAgentType.PressAndReputationAgent,
            stage=StageName.S1_GROUND_TRUTH,
            objective="Gather recent press coverage, major news, and high-level reputation signals; identify tickers and recent SEC filings when applicable.",
            dependsOn=[SubAgentType.BusinessIdentityAndLeadershipAgent],
            sourcePlan=SourceSetPlan(
                include_buckets=[
                    SourceBucket.pressUrls,
                    SourceBucket.platformUrls,
                ],
                include_domains=base_domains,
                notes="Blend official news/press pages with high-authority external coverage to surface latest material changes.",
            ),
            budget=SourceBudget(max_search_calls=8, max_extract_calls=15, max_pages_total=150),
            toolBundles=[ToolBundle.CORE_SEARCH, ToolBundle.CORE_EXTRACT, ToolBundle.BROWSER, ToolBundle.FINANCE_NEWS],
            concurrency=2,
        ),
        SubAgentPlan(
            agentType=SubAgentType.ProductSpecAgent,
            stage=StageName.S1_GROUND_TRUTH,
            objective="Extract product specs/variants/price/components/manuals/warnings for all products.",
            dependsOn=[SubAgentType.SourceSetCuratorAgent],
            sourcePlan=SourceSetPlan(
                include_buckets=[SourceBucket.productIndexUrls, SourceBucket.productPageUrls, SourceBucket.documentationUrls, SourceBucket.policyUrls],
                include_domains=base_domains,
            ),
            budget=SourceBudget(max_search_calls=4, max_extract_calls=20, max_browser_steps=200, max_pages_total=250),
            toolBundles=[ToolBundle.BROWSER, ToolBundle.CORE_EXTRACT, ToolBundle.CORE_SEARCH],
            concurrency=2,
            maxEntitiesPerBatch=15,
        ),
    ]

    if has_help_center:
        stage1_agents.append(
            SubAgentPlan(
                agentType=SubAgentType.HelpCenterAgent,
                stage=StageName.S1_GROUND_TRUTH,
                objective="Mine help center for usage guidance, troubleshooting, warranty language, contraindications language.",
                dependsOn=[SubAgentType.SourceSetCuratorAgent],
                sourcePlan=SourceSetPlan(
                    include_buckets=[SourceBucket.helpCenterUrls, SourceBucket.policyUrls],
                    include_domains=base_domains,
                ),
                budget=SourceBudget(max_search_calls=3, max_extract_calls=15, max_pages_total=120),
                toolBundles=[ToolBundle.CORE_SEARCH, ToolBundle.CORE_EXTRACT, ToolBundle.BROWSER],
                concurrency=2,
            )
        )

    stage1 = StagePlan(
        stage=StageName.S1_GROUND_TRUTH,
        concurrency=7,
        agents=stage1_agents,
        gateNotes="S1 produces business identity + leadership, enriched person bios, company press/news + reputation, and product specs (+ help center corpus if present).",
    )

    stage2 = StagePlan(
        stage=StageName.S2_DEPENDENT_ENRICHMENT,
        concurrency=4,
        agents=[
            SubAgentPlan(
                agentType=SubAgentType.ContraindicationsAndSafetyAgent,
                stage=StageName.S2_DEPENDENT_ENRICHMENT,
                objective="Collect contraindications/warnings/safety guidance from official + reputable sources.",
                dependsOn=[SubAgentType.ProductSpecAgent] + ([SubAgentType.HelpCenterAgent] if has_help_center else []),
                sourcePlan=SourceSetPlan(
                    include_buckets=[SourceBucket.productPageUrls, SourceBucket.helpCenterUrls, SourceBucket.policyUrls, SourceBucket.documentationUrls],
                    include_domains=base_domains,
                ),
                budget=SourceBudget(max_search_calls=5, max_extract_calls=12, max_pages_total=120),
                toolBundles=[ToolBundle.CORE_SEARCH, ToolBundle.CORE_EXTRACT, ToolBundle.BROWSER, ToolBundle.MED_DB],
                concurrency=2,
            ),
            SubAgentPlan(
                agentType=SubAgentType.CaseStudyHarvestAgent,
                stage=StageName.S2_DEPENDENT_ENRICHMENT,
                objective="Harvest company-controlled evidence artifacts (case studies/whitepapers/research pages).",
                dependsOn=[SubAgentType.SourceSetCuratorAgent],
                sourcePlan=SourceSetPlan(
                    include_buckets=[SourceBucket.caseStudyUrls, SourceBucket.platformUrls, SourceBucket.pressUrls],
                    include_domains=base_domains,
                ),
                budget=SourceBudget(max_search_calls=6, max_extract_calls=20, max_pages_total=200),
                toolBundles=[ToolBundle.CORE_SEARCH, ToolBundle.CORE_EXTRACT, ToolBundle.BROWSER],
                concurrency=2,
            ),
        ],
        gateNotes="S2 produces harvested claims/evidence + safety guidance.",
    )

    stage3 = StagePlan(
        stage=StageName.S3_TRIAGE_SYNTHESIS,
        concurrency=3,
        agents=[
            SubAgentPlan(
                agentType=SubAgentType.ClinicalEvidenceTriageAgent,
                stage=StageName.S3_TRIAGE_SYNTHESIS,
                objective="Triage harvested claims and evidence: find plausible clinical anchors and shortlist references.",
                dependsOn=[SubAgentType.CaseStudyHarvestAgent],
                sourcePlan=SourceSetPlan(
                    include_buckets=[SourceBucket.caseStudyUrls],
                    include_domains=base_domains,
                    notes="Operate on harvested claim snippets + citations; do not deeply validate yet.",
                ),
                budget=SourceBudget(max_search_calls=6, max_extract_calls=4, max_pages_total=80),
                toolBundles=[ToolBundle.MED_DB, ToolBundle.WIKI, ToolBundle.CORE_SEARCH],
                concurrency=1,
            ),
            SubAgentPlan(
                agentType=SubAgentType.TechnologyProcessAgent,
                stage=StageName.S3_TRIAGE_SYNTHESIS,
                objective="Synthesize a 'how it works' view: core mechanisms, protocols, manufacturing/QA, and material/process claims.",
                dependsOn=[SubAgentType.ProductSpecAgent] + ([SubAgentType.HelpCenterAgent] if has_help_center else []),
                sourcePlan=SourceSetPlan(
                    include_buckets=[
                        SourceBucket.documentationUrls,
                        SourceBucket.productPageUrls,
                        SourceBucket.platformUrls,
                        SourceBucket.policyUrls,
                        SourceBucket.helpCenterUrls,
                    ],
                    include_domains=base_domains,
                    notes="Prefer technical docs, manuals, and process statements; de-emphasize purely marketing pages.",
                ),
                budget=SourceBudget(max_search_calls=6, max_extract_calls=16, max_browser_steps=120, max_pages_total=180),
                toolBundles=[ToolBundle.CORE_SEARCH, ToolBundle.CORE_EXTRACT, ToolBundle.BROWSER],
                concurrency=1,
            ),
        ],
        gateNotes="S3 produces a shortlist of clinical anchors and credibility notes plus a synthesized technology/process narrative.",
    )

    return [stage0, stage1, stage2, stage3] 


## Mongo Models needed 


class MongoArtifactRef(BaseModel):
    artifactId: str
    kind: str
    extractedAt: Optional[str] = None
    payloadHash: Optional[str] = None


class MongoResearchPlan(BaseModel):
    planId: str
    bundleId: str

    runId: str
    pipelineVersion: str
    episodeId: str
    episodeUrl: str

    status: str  # queued/running/complete/failed
    createdAt: str
    updatedAt: Optional[str] = None

    # ✅ tie to artifact store
    domainCatalogSet: MongoArtifactRef

    # ✅ your “tradeoff set” plan
    stages: List[StagePlan] = Field(default_factory=list)

    # ✅ materialized curated source sets
    sourceSetIds: List[str] = Field(default_factory=list)

    # optional
    notes: Optional[str] = None 
 


class MongoSourceSet(BaseModel):
    sourceSetId: str
    planId: str
    bundleId: str
    runId: str

    agentType: str  # SubAgentType
    createdAt: str
    updatedAt: Optional[str] = None

    urls: List[str] = Field(default_factory=list)
    byBucket: Dict[str, List[str]] = Field(default_factory=dict)

    budget: SourceBudget
    notes: Optional[str] = None


class MongoAgentRun(BaseModel):
    agentRunId: str
    planId: str
    bundleId: str
    runId: str

    agentType: str
    stage: str

    status: str  # queued/running/complete/failed
    createdAt: str
    startedAt: Optional[str] = None
    finishedAt: Optional[str] = None
    error: Optional[str] = None

    # tie to artifact store for outputs
    outputArtifactIds: List[str] = Field(default_factory=list)

    notes: Optional[str] = None