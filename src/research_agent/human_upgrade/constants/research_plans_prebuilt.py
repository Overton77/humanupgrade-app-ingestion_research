"""
Pre-built Research Plan Definitions

This module contains comprehensive definitions for research plan modes, including:
- Stage and sub-stage structures
- Agent type definitions with tools and outputs
- Dependencies and parallelization rules
- Detailed descriptions and purposes

These definitions can be used in prompts, validation, and plan generation.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class AgentTypeDefinition(BaseModel):
    """Definition of an agent type with its tools, outputs, and description."""
    name: str
    description: str
    default_tools: List[str] = Field(default_factory=list)
    typical_outputs: List[str] = Field(default_factory=list)
    source_focus: Optional[str] = None


class SubStageDefinition(BaseModel):
    """Definition of a sub-stage within a research plan."""
    sub_stage_id: str  # e.g., "S1.1"
    name: str
    description: str
    purpose: str  # What questions this stage answers
    responsibilities: List[str] = Field(default_factory=list)
    agent_type: str
    outputs: List[str] = Field(default_factory=list)
    source_focus: str
    parallelization_notes: Optional[str] = None
    is_required: bool = True
    is_optional: bool = False
    depends_on_substages: List[str] = Field(default_factory=list)


class StageDefinition(BaseModel):
    """Definition of a stage within a research plan."""
    stage_id: str  # e.g., "S1"
    name: str
    description: str
    purpose: str
    assumptions: Optional[str] = None
    sub_stages: List[SubStageDefinition] = Field(default_factory=list)
    dependencies: str = ""  # Description of stage dependencies
    parallelization: str = ""  # Description of parallelization rules
    what_it_intentionally_does_not_do: Optional[List[str]] = None


class PrebuiltResearchPlan(BaseModel):
    """Complete definition of a pre-built research plan mode."""
    stage_mode: str
    goal: str
    description: str
    planning_rule: str
    execution_model: str
    stages: List[StageDefinition] = Field(default_factory=list)
    agent_type_definitions: Dict[str, AgentTypeDefinition] = Field(default_factory=dict)
    global_tool_expectations: str = ""
    what_this_mode_intentionally_does_not_do: List[str] = Field(default_factory=list)
    why_ready_to_implement: List[str] = Field(default_factory=list)


# ============================================================================
# FULL ENTITIES STANDARD DEFINITION
# ============================================================================

FULL_ENTITIES_STANDARD_PLAN = PrebuiltResearchPlan(
    stage_mode="full_entities_standard",
    goal=(
        "Produce a reliable, evidence-anchored overview of an organization "
        "(company, clinic, brand, author platform, researcher, or biotech entrepreneur) covering: "
        "who they are, what they offer, how it works/is made, what is claimed, "
        "what evidence exists (triage-level), what confidence to assign, and what research to run next. "
        "This mode is intentionally non-exhaustive and designed to route into deeper modes."
    ),
    description=(
        "Pre-curation ResearchPlan blueprint for evidence-anchored overview of an Organization. "
        "Non-exhaustive by design; optimized for determinism + routing into deeper modes."
    ),
    planning_rule=(
        "ResearchPlan must fully specify stages/substages/agent_instances/objectives/slicing/tool_policy/context_policy/budgets, "
        "but MUST NOT bind starter_sources yet. Instead, include per-agent source_requirements (categories + min/max + notes). "
        "Final binding happens after DomainCatalogExpansion + SourceSetCurator."
    ),
    execution_model=(
        "Stages are ordered by dependency artifacts (not implicit chronology). "
        "Within a stage, substages may run in parallel if their required artifacts are satisfied. "
        "Agent instances within a substage may run in parallel if slices are disjoint (people/products/claim clusters). "
        "Use slicing when People/Products are large to keep instances bounded."
    ),
    stages=[
        StageDefinition(
            stage_id="S1",
            name="Entity Biography, Identity & Ecosystem",
            description="Establish who this entity is, who leads it, how it positions itself, and why it matters.",
            purpose="Entity Biography, Identity & Ecosystem",
            assumptions=(
                "Entity name, major people, and major products are already provided as inputs. "
                "This stage enriches and contextualizes, not merely identifies."
            ),
            dependencies="No required upstream deps beyond provided entity inputs; can run immediately.",
            parallelization="S1.1–S1.4 can run in parallel. S1.2 can be split per person.",
            sub_stages=[
                SubStageDefinition(
                    sub_stage_id="S1.1",
                    name="Organization Identity & Structure",
                    description="Entity Biography & Organizational Overview",
                    purpose="What is this organization/person, really? How do they describe themselves vs how others describe them?",
                    responsibilities=[
                        "Produce a concise but information-dense biography / overview",
                        "Clarify the entity's core mission, audience, and operating posture (consumer wellness vs medical-adjacent vs clinical vs media vs hybrid)",
                        "Summarize the origin story and major inflection points",
                        "Identify primary lines of business and how they interrelate",
                    ],
                    agent_type="BusinessIdentityAndLeadershipAgent",
                    outputs=["EntityBiography", "OperatingPostureSummary", "HighLevelTimeline"],
                    source_focus="official_home/about/blog/press + third-party corroboration if needed",
                ),
                SubStageDefinition(
                    sub_stage_id="S1.2",
                    name="People & Roles",
                    description="People, Leadership & Expert Roles",
                    purpose="Who is responsible for the ideas, products, and claims? Who lends credibility or influence?",
                    responsibilities=[
                        "Enrich provided people with: roles, tenure, and functional responsibility",
                        "Education, licenses, certifications (where applicable)",
                        "Prior companies, labs, clinics, or notable projects",
                        "Flag: advisory vs operational roles, public-facing experts vs internal decision-makers",
                    ],
                    agent_type="PersonBioAndAffiliationsAgent",
                    outputs=["PeopleProfiles", "RoleResponsibilityMap", "CredentialAnchors"],
                    source_focus="official_leadership + scholarly/pub profiles where applicable",
                    parallelization_notes="per-person slices if people > 4",
                ),
                SubStageDefinition(
                    sub_stage_id="S1.3",
                    name="Ecosystem Positioning",
                    description="Ecosystem Positioning",
                    purpose="Where does this entity sit in the biotech / biohacking / wellness ecosystem?",
                    responsibilities=[
                        "Identify: direct competitors, adjacent substitutes or alternatives, partners, distributors, platforms, clinics, labs",
                        "Classify ecosystem role: product manufacturer, platform/protocol originator, reseller/educator, clinic or service provider",
                    ],
                    agent_type="EcosystemMapperAgent",
                    outputs=["CompetitorSet", "PartnerAndPlatformGraph", "MarketCategoryPlacement"],
                    source_focus="press_news + official_platform/about + search-based discovery",
                ),
                SubStageDefinition(
                    sub_stage_id="S1.4",
                    name="Credibility & Risk Signals (Light)",
                    description="Credibility & Risk Signals (Light)",
                    purpose="Are there early warning signs or credibility anchors?",
                    responsibilities=[
                        "Surface: notable credentials and affiliations, past controversies or disputes (non-exhaustive), retractions, sanctions, licensing issues if obvious",
                        "Characterize risk posture, not adjudicate it",
                    ],
                    agent_type="CredibilitySignalScannerAgent",
                    outputs=["CredibilitySignals", "RiskFlagsLight"],
                    source_focus="press_news + regulatory signals (surface only; no adjudication)",
                ),
            ],
        ),
        StageDefinition(
            stage_id="S2",
            name="Products, Specifications, Technology & Claims",
            description="Precisely define what is offered, how it works/is made, and what is promised.",
            purpose="Products, Specifications, Technology & Claims",
            dependencies=(
                "S2.2 depends on S2.1 for product selection (soft) OR can run with provided product list. "
                "S2.4 benefits from S2.1 inventory; can run once product URLs exist. "
                "S2.3 benefits from S2.1 inventory but can run standalone on platform/tech pages."
            ),
            parallelization=(
                "After minimal inventory exists (S2.1 partial OK), S2.2 (per-product), S2.3, and S2.4 can run in parallel. "
                "S2.X reviews can run in parallel once product identifiers exist."
            ),
            sub_stages=[
                SubStageDefinition(
                    sub_stage_id="S2.1",
                    name="Product/Service Inventory",
                    description="Product / Service Inventory",
                    purpose="What exactly is being sold or delivered?",
                    responsibilities=[
                        "Enumerate: products, devices, services, programs, books, courses",
                        "Capture: delivery route, intended use, target audience",
                        "De-duplicate overlapping offerings",
                    ],
                    agent_type="ProductCatalogerAgent",
                    outputs=["ProductCatalog", "ProductGroupingMap"],
                    source_focus="official_products + navigation hubs + product index pages",
                ),
                SubStageDefinition(
                    sub_stage_id="S2.2",
                    name="Product Specifications (Deep Slice)",
                    description="Product Specifications (Deep Slice)",
                    purpose="What's actually in this product / how is it used / what does it cost?",
                    responsibilities=[
                        "For selected priority products: ingredients/actives/materials, dosages, directions, schedules",
                        "Pricing, variants, subscriptions, manuals, warranties, what's included",
                        "Extract officially stated warnings (not interpretive)",
                    ],
                    agent_type="ProductSpecAgent",
                    outputs=["ProductSpecs", "IngredientOrMaterialLists", "UsageAndWarningSnippets"],
                    source_focus="official_product_detail + official_docs_manuals + help snippets",
                    parallelization_notes="per-product slices if products > 3 (1 product per instance for priority set)",
                    is_required=True,
                ),
                SubStageDefinition(
                    sub_stage_id="S2.3",
                    name="Manufacturing & Technology Platform",
                    description="Manufacturing & Technology Platform",
                    purpose="How does this product or service actually work? How is it made or delivered?",
                    responsibilities=[
                        "Extract: formulation or delivery technology, device mechanisms or protocols",
                        "QA / GMP / ISO / testing claims, patents or proprietary processes (if disclosed)",
                        "Translate marketing descriptions into technical mechanisms where possible",
                    ],
                    agent_type="TechnologyProcessAndManufacturingAgent",
                    outputs=["TechnologyMechanismSummaries", "ManufacturingAndQAClaims", "PatentAndProcessReferences"],
                    source_focus="official_research/platform pages + disclosed QA/GMP/ISO/testing + patents/whitepapers where available",
                    is_required=True,
                ),
                SubStageDefinition(
                    sub_stage_id="S2.4",
                    name="Claims Extraction, Normalization & Salience",
                    description="Claims Extraction, Normalization & Salience",
                    purpose="What outcomes are being promised — and which matter most?",
                    responsibilities=[
                        "Extract all explicit claims from: product pages, help/FAQ, landing pages, books/course descriptions",
                        "Normalize claims into taxonomy buckets: compounds, pathways, conditions, biomarkers, technologies",
                        "Rank claims by: prominence, differentiation, implied impact",
                    ],
                    agent_type="ClaimsExtractorAndTaxonomyMapperAgent",
                    outputs=["ClaimsLedger", "NormalizedClaimMap", "ClaimSalienceRanking"],
                    source_focus="product pages + landing pages + help_center + book/course blurbs + labels",
                ),
                SubStageDefinition(
                    sub_stage_id="S2.X",
                    name="Product Reviews & User Feedback",
                    description="Optional — Product Reviews & User Feedback",
                    purpose="Capture anecdotal signals without conflating with evidence.",
                    responsibilities=[
                        "Aggregate first- and third-party reviews",
                        "Separate: praise vs complaints, efficacy vs logistics (shipping, UX)",
                        "Clearly label anecdotal nature and bias risks",
                    ],
                    agent_type="ProductReviewsAgent",
                    outputs=["UserFeedbackSummary", "AnecdotalSignalNotes"],
                    source_focus="marketplace_reviews + social_community (if allowed) + first-party testimonials",
                    is_required=False,
                    is_optional=True,
                ),
            ],
        ),
        StageDefinition(
            stage_id="S3",
            name="Evidence & Validation Snapshot (Triage)",
            description="Rapidly assess what evidence exists and where gaps are.",
            purpose="Evidence & Validation Snapshot (Triage)",
            dependencies=(
                "Strongly prefers S2 outputs: ClaimsLedger + ProductSpecs/UsageAndWarningSnippets to focus search. "
                "Can start with partial S2 (top claims/products) if needed."
            ),
            parallelization=(
                "Evidence discovery can be split by claim clusters/products; classification and strength/gaps can follow per cluster. "
                "Safety can run in parallel using help/labels/manuals while evidence discovery runs."
            ),
            sub_stages=[
                SubStageDefinition(
                    sub_stage_id="S3.1",
                    name="Evidence Discovery",
                    description="Evidence Discovery",
                    purpose="Harvest evidence artifacts",
                    responsibilities=[
                        "Harvest: trials, studies, whitepapers, case studies",
                        "Distinguish: company-affiliated vs independent evidence",
                    ],
                    agent_type="CaseStudyHarvestAgent",
                    outputs=["EvidenceArtifacts"],
                    source_focus="company-controlled evidence + independent studies + trials",
                ),
                SubStageDefinition(
                    sub_stage_id="S3.2",
                    name="Evidence Classification",
                    description="Evidence Classification",
                    purpose="Classify evidence by type and quality",
                    responsibilities=[
                        "Classify evidence by: human/animal/in vitro, RCT/observational/mechanistic/anecdotal",
                        "peer-reviewed vs marketing, independent vs affiliated",
                    ],
                    agent_type="EvidenceClassifierAgent",
                    outputs=["EvidenceClassificationTable"],
                    source_focus="evidence artifacts from S3.1",
                ),
                SubStageDefinition(
                    sub_stage_id="S3.3",
                    name="Strength & Gaps Assessment",
                    description="Strength & Gaps Assessment",
                    purpose="Evaluate evidence-claim alignment",
                    responsibilities=[
                        "Evaluate: evidence–claim alignment, overextension or mismatch",
                        "Identify what evidence would be required to strengthen claims",
                    ],
                    agent_type="StrengthAndGapAssessorAgent",
                    outputs=["ClaimSupportMatrix", "EvidenceGapNotes"],
                    source_focus="classified evidence + claims ledger",
                ),
                SubStageDefinition(
                    sub_stage_id="S3.4",
                    name="Safety & Risk Signals",
                    description="Safety & Risk Signals",
                    purpose="Surface safety and risk information",
                    responsibilities=[
                        "Surface: contraindications, adverse effects language",
                        "early regulatory warning signals (non-deep)",
                    ],
                    agent_type="ContraindicationsAndSafetyAgent",
                    outputs=["SafetySignalSummary"],
                    source_focus="help/labels/manuals + regulatory signals",
                ),
            ],
        ),
        StageDefinition(
            stage_id="S4",
            name="Synthesis, Confidence & Research Routing",
            description="Convert research into usable judgment and next actions.",
            purpose="Synthesis, Confidence & Research Routing",
            dependencies=(
                "S4.1 requires S1–S3 core artifacts; S4.2 and S4.3 depend on S4.1 (preferred) or directly on S2–S3 artifacts (acceptable). "
                "S4.4 runs last and depends on outputs from S4.1–S4.3."
            ),
            parallelization="S4.2 and S4.3 can co-run after synthesis inputs exist; routing is final.",
            sub_stages=[
                SubStageDefinition(
                    sub_stage_id="S4.1",
                    name="Entity Synthesis",
                    description="Entity Synthesis",
                    purpose="Merge outputs from Stages 1–3 into a coherent entity representation",
                    responsibilities=[
                        "Merge outputs from Stages 1–3 into a coherent entity representation",
                    ],
                    agent_type="KnowledgeSynthesizerAgent",
                    outputs=["EntityResearchSummary"],
                    source_focus="all artifacts from S1-S3",
                ),
                SubStageDefinition(
                    sub_stage_id="S4.2",
                    name="Claim Confidence Scoring",
                    description="Claim Confidence Scoring",
                    purpose="Assign confidence tiers to claims",
                    responsibilities=[
                        "Assign confidence tiers: Proven / Plausible / Speculative / Unsupported",
                        "Provide rationale tied to evidence type and quality",
                    ],
                    agent_type="ClaimConfidenceScorerAgent",
                    outputs=["ClaimConfidenceScores"],
                    source_focus="claims ledger + evidence classification + strength assessment",
                ),
                SubStageDefinition(
                    sub_stage_id="S4.3",
                    name="Narrative Summary",
                    description="Narrative Summary",
                    purpose="Contrast marketing narrative vs evidentiary reality",
                    responsibilities=[
                        "Contrast: marketing narrative vs evidentiary reality",
                        "Highlight: key stories, adoption drivers, tensions",
                    ],
                    agent_type="NarrativeAnalystAgent",
                    outputs=["NarrativeAndContextSummary"],
                    source_focus="synthesis + confidence scores + original sources",
                ),
                SubStageDefinition(
                    sub_stage_id="S4.4",
                    name="Next-Step Research Routing",
                    description="Next-Step Research Routing",
                    purpose="Recommend escalation paths",
                    responsibilities=[
                        "Recommend escalation paths: Full Entities Deep, Regulatory Deep Dive, Trial-Level Validation, Market or Trend Analysis",
                    ],
                    agent_type="ResearchRouterAgent",
                    outputs=["ResearchRecommendations"],
                    source_focus="all synthesis outputs + confidence scores + gaps",
                ),
            ],
        ),
    ],
    agent_type_definitions={
        "BusinessIdentityAndLeadershipAgent": AgentTypeDefinition(
            name="BusinessIdentityAndLeadershipAgent",
            description="Establishes organization identity, structure, mission, and operating posture",
            default_tools=["search.tavily", "extract.tavily", "browser.playwright", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["EntityBiography", "OperatingPostureSummary", "HighLevelTimeline"],
            source_focus="official_home/about/blog/press + third-party corroboration",
        ),
        "PersonBioAndAffiliationsAgent": AgentTypeDefinition(
            name="PersonBioAndAffiliationsAgent",
            description="Enriches people profiles with roles, credentials, affiliations, and prior work",
            default_tools=["search.exa", "search.tavily", "browser.playwright", "scholar.semantic_scholar", "scholar.pubmed", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["PeopleProfiles", "RoleResponsibilityMap", "CredentialAnchors"],
            source_focus="official_leadership + scholarly/pub profiles",
        ),
        "EcosystemMapperAgent": AgentTypeDefinition(
            name="EcosystemMapperAgent",
            description="Maps entity position in biotech/biohacking/wellness ecosystem: competitors, partners, market category",
            default_tools=["search.tavily", "search.exa", "browser.playwright", "extract.tavily", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["CompetitorSet", "PartnerAndPlatformGraph", "MarketCategoryPlacement"],
            source_focus="press_news + official_platform/about + search-based discovery",
        ),
        "CredibilitySignalScannerAgent": AgentTypeDefinition(
            name="CredibilitySignalScannerAgent",
            description="Surfaces credibility anchors and early warning risk signals (light, non-adjudicative)",
            default_tools=["search.tavily", "search.exa", "browser.playwright", "extract.tavily", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["CredibilitySignals", "RiskFlagsLight"],
            source_focus="press_news + regulatory signals",
        ),
        "EvidenceClassifierAgent": AgentTypeDefinition(
            name="EvidenceClassifierAgent",
            description="Classifies evidence by type (human/animal/in vitro), study design (RCT/obs/mechanistic), and independence",
            default_tools=["fs.read", "fs.write", "context.summarize"],
            typical_outputs=["EvidenceClassificationTable"],
            source_focus="evidence artifacts from discovery",
        ),
        "StrengthAndGapAssessorAgent": AgentTypeDefinition(
            name="StrengthAndGapAssessorAgent",
            description="Assesses evidence-claim alignment, identifies gaps and overextensions",
            default_tools=["fs.read", "fs.write", "context.summarize"],
            typical_outputs=["ClaimSupportMatrix", "EvidenceGapNotes"],
            source_focus="classified evidence + claims ledger",
        ),
        "ProductCatalogerAgent": AgentTypeDefinition(
            name="ProductCatalogerAgent",
            description="Enumerates and catalogs all products, devices, services, programs offered",
            default_tools=["search.tavily", "extract.tavily", "browser.playwright", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["ProductCatalog", "ProductGroupingMap"],
            source_focus="official_products + navigation hubs + product index pages",
        ),
        "ProductSpecAgent": AgentTypeDefinition(
            name="ProductSpecAgent",
            description="Extracts detailed product specifications: ingredients, dosages, usage, pricing, warnings",
            default_tools=["browser.playwright", "extract.tavily", "doc.pdf_text", "doc.pdf_screenshot_ocr", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["ProductSpecs", "IngredientOrMaterialLists", "UsageAndWarningSnippets"],
            source_focus="official_product_detail + official_docs_manuals + help snippets",
        ),
        "TechnologyProcessAndManufacturingAgent": AgentTypeDefinition(
            name="TechnologyProcessAndManufacturingAgent",
            description="Extracts technology mechanisms, manufacturing processes, QA claims, patents",
            default_tools=["search.tavily", "browser.playwright", "extract.tavily", "doc.pdf_text", "scholar.semantic_scholar", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["TechnologyMechanismSummaries", "ManufacturingAndQAClaims", "PatentAndProcessReferences"],
            source_focus="official_research/platform pages + disclosed QA/GMP/ISO/testing + patents/whitepapers",
        ),
        "ClaimsExtractorAndTaxonomyMapperAgent": AgentTypeDefinition(
            name="ClaimsExtractorAndTaxonomyMapperAgent",
            description="Extracts, normalizes, and ranks all explicit claims from product/landing/help pages",
            default_tools=["extract.tavily", "browser.playwright", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["ClaimsLedger", "NormalizedClaimMap", "ClaimSalienceRanking"],
            source_focus="product pages + landing pages + help_center + book/course blurbs + labels",
        ),
        "ProductReviewsAgent": AgentTypeDefinition(
            name="ProductReviewsAgent",
            description="Aggregates user feedback and reviews (anecdotal, clearly labeled)",
            default_tools=["search.exa", "search.tavily", "browser.playwright", "extract.tavily", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["UserFeedbackSummary", "AnecdotalSignalNotes"],
            source_focus="marketplace_reviews + social_community + first-party testimonials",
        ),
        "CaseStudyHarvestAgent": AgentTypeDefinition(
            name="CaseStudyHarvestAgent",
            description="Harvests evidence artifacts: studies, trials, whitepapers, case studies with affiliation labeling",
            default_tools=["search.exa", "search.tavily", "extract.tavily", "browser.playwright", "doc.pdf_text", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["EvidenceArtifacts"],
            source_focus="company-controlled evidence + independent studies + trials",
        ),
        "EvidenceClassifierAgent": AgentTypeDefinition(
            name="EvidenceClassifierAgent",
            description="Classifies evidence by type (human/animal/in vitro), study design (RCT/obs/mechanistic), and independence",
            default_tools=["fs.read", "fs.write", "context.summarize"],
            typical_outputs=["EvidenceClassificationTable"],
            source_focus="evidence artifacts from discovery",
        ),
        "StrengthAndGapAssessorAgent": AgentTypeDefinition(
            name="StrengthAndGapAssessorAgent",
            description="Assesses evidence-claim alignment, identifies gaps and overextensions",
            default_tools=["fs.read", "fs.write", "context.summarize"],
            typical_outputs=["ClaimSupportMatrix", "EvidenceGapNotes"],
            source_focus="classified evidence + claims ledger",
        ),
        "ContraindicationsAndSafetyAgent": AgentTypeDefinition(
            name="ContraindicationsAndSafetyAgent",
            description="Surfaces safety signals: contraindications, adverse effects, regulatory warnings",
            default_tools=["extract.tavily", "browser.playwright", "doc.pdf_text", "search.tavily", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["SafetySignalSummary"],
            source_focus="help/labels/manuals + regulatory signals",
        ),
        "ClinicalEvidenceTriageAgent": AgentTypeDefinition(
            name="ClinicalEvidenceTriageAgent",
            description="Augments evidence discovery using PubMed/Semantic Scholar/ClinicalTrials (optional augmenter)",
            default_tools=["scholar.pubmed", "scholar.semantic_scholar", "registry.clinicaltrials", "search.tavily", "fs.write", "fs.read", "context.summarize"],
            typical_outputs=["ClinicalEvidenceArtifacts"],
            source_focus="PubMed + Semantic Scholar + ClinicalTrials.gov",
        ),
        "KnowledgeSynthesizerAgent": AgentTypeDefinition(
            name="KnowledgeSynthesizerAgent",
            description="Synthesizes all research outputs into coherent entity representation (KG-ready)",
            default_tools=["fs.read", "fs.write", "context.summarize"],
            typical_outputs=["EntityResearchSummary"],
            source_focus="all artifacts from S1-S3",
        ),
        "ClaimConfidenceScorerAgent": AgentTypeDefinition(
            name="ClaimConfidenceScorerAgent",
            description="Assigns confidence tiers (Proven/Plausible/Speculative/Unsupported) with rationale",
            default_tools=["fs.read", "fs.write", "context.summarize"],
            typical_outputs=["ClaimConfidenceScores"],
            source_focus="claims ledger + evidence classification + strength assessment",
        ),
        "NarrativeAnalystAgent": AgentTypeDefinition(
            name="NarrativeAnalystAgent",
            description="Contrasts marketing narrative vs evidentiary reality, highlights tensions and adoption drivers",
            default_tools=["fs.read", "fs.write", "context.summarize"],
            typical_outputs=["NarrativeAndContextSummary"],
            source_focus="synthesis + confidence scores + original sources",
        ),
        "ResearchRouterAgent": AgentTypeDefinition(
            name="ResearchRouterAgent",
            description="Recommends next-step research routes: Deep modes, Regulatory, Trial-level, Market/Trend",
            default_tools=["fs.read", "fs.write"],
            typical_outputs=["ResearchRecommendations"],
            source_focus="all synthesis outputs + confidence scores + gaps",
        ),
    },
    global_tool_expectations=(
        "Static HTML: search + extract; JS-heavy: playwright + extract fallback. "
        "PDFs/manuals/COAs: doc.pdf_text; screenshot_ocr only if table/diagram blocks text extraction. "
        "Scholarly/clinical: scholar.pubmed + scholar.semantic_scholar + registry.clinicaltrials. "
        "Reviews/marketplaces: search + extract; playwright if gated/scrolling; label anecdotal + bias explicitly."
    ),
    what_this_mode_intentionally_does_not_do=[
        "Full regulatory adjudication",
        "Financial modeling",
        "Adversarial red-teaming",
        "Macro trend synthesis",
    ],
    why_ready_to_implement=[
        "Every sub-agent has a single clear responsibility",
        "Stages depend on artifacts, not implicit order",
        "Works whether agents are run: standalone, per stage, or in a LangGraph DAG",
        "Naturally supports partial entry and recomposition",
    ],
)


# ============================================================================
# RESEARCH PLANS DICTIONARY
# ============================================================================

PREBUILT_RESEARCH_PLANS: Dict[str, PrebuiltResearchPlan] = {
    "full_entities_standard": FULL_ENTITIES_STANDARD_PLAN,
    # Add more research plan modes here as they are defined
    # "full_entities_deep": FULL_ENTITIES_DEEP_PLAN,
    # "entities_basic": ENTITIES_BASIC_PLAN,
}
