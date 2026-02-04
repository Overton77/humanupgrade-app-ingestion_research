from research_agent.human_upgrade.constants.research_plans_prebuilt_models import PrebuiltResearchPlan, AgentTypeDefinition, SubStageDefinition, StageDefinition
from typing import Dict

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
            ],
        ),
       StageDefinition(
    stage_id="S2",
    name="Products, Specifications, Technology & Claims",
    description="Precisely define what is offered, how it works/is made, and what is promised.",
    purpose="Products, Specifications, Technology & Claims",
    dependencies=(
        "S2.1 can run with a provided product catalog (preferred) or a minimal set of product URLs. "
        "S2.2 benefits from S2.1 outputs (product specs + evidence); can run per-product batch. "
        "S2.3 can run standalone on platform/tech pages. "
        "S2.4 benefits from product URLs and/or S2.1 evidence snippets."
    ),
    parallelization=(
        "S2.1 runs per batch of products (e.g., up to 5 per instance). "
        "After S2.1 produces specs/evidence for a batch, S2.2 (if used), S2.3, and S2.4 can run in parallel. "
        "Playwright is only invoked by S2.1/S2.2 when required fields are missing."
    ),
    sub_stages=[
        SubStageDefinition(
            sub_stage_id="S2.1",
            name="Product Specs + Conditional Playwright Request (Batch)",
            description=(
                "Given a provided product catalog (up to ~5 products), extract core product specs via static sources first; "
                "when required fields are missing, request a bounded Playwright workflow from an external tool and merge results."
            ),
            purpose="Get 'good enough' product facts (price + ingredients + directions + official warnings) at minimal credit cost.",
            responsibilities=[
                # Inputs / assumptions
                "Accept an input list of products with canonical product URLs (catalog is assumed mostly complete).",
                "Normalize product identifiers and confirm each product has at least one usable official detail URL.",

                # Static-first pass (cheap)
                "Perform a static-first extraction per product using crawl/extract: read visible HTML text, metadata, and JSON-LD/offers when present.",
                "Attempt to fill required fields from static content: price or price range (if present), ingredient/material list (names), directions/schedule (if present), and official warnings (explicit only).",

                # Decide whether to escalate (key credit saver)
                "Compute a simple per-product completeness check for required fields (e.g., price missing and/or ingredients missing).",
                "Only if required fields are missing, prepare a targeted Playwright request specifying the missing fields and the minimal interactions likely needed "
                "(e.g., choose default variant, toggle subscription, open Ingredients/Supplement Facts accordion/tab, read price block).",

                # Playwright delegation (agent does NOT control browser)
                "Call a separate Playwright workflow tool (worker agent) to execute the interaction plan; do not attempt UI control inside this agent.",
                "Receive structured Playwright results (snippets + values + evidence) and merge them back into the per-product spec record.",

                # Evidence + reuse
                "Attach lightweight evidence pointers for extracted fields (URL + section label and/or selector reference) so S2.4 can reuse without re-scraping.",
                "Emit a compact coverage note per product indicating which fields were found statically vs via Playwright, and which remain missing.",
            ],
            agent_type="ProductSpecAgent",
            outputs=[
                # keep these generic; you said you’ll define types later
                "BatchProductSpecs",
                "BatchSpecEvidence",
                "BatchCoverageNotes",
                "PlaywrightRequestsMade",
            ],
            source_focus="official_product_detail + official_label/facts pages or PDFs + official help snippets (static-first; Playwright only when missing required fields)",
            parallelization_notes="Run in batches of <=5 products per instance. Only request Playwright for products failing the required-fields completeness check.",
            is_required=True,
        ),



        SubStageDefinition(
            sub_stage_id="S2.2",
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
            sub_stage_id="S2.3",
            name="Claims Extraction, Normalization & Salience",
            description="Claims Extraction, Normalization & Salience",
            purpose="What outcomes are being promised — and which matter most?",
            responsibilities=[
                "Extract explicit claims from: product pages, help/FAQ, landing pages, books/course descriptions",
                "Prefer claims that are easy to find and directly stated (minimal claims) and link them to evidence where possible",
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
            default_tools=["tavily.search", "tavily.extract", "fs.write", "fs.read", "think", "wiki.search"],
            typical_outputs=["EntityBiography", "OperatingPostureSummary", "HighLevelTimeline"],
            source_focus="official_home/about/blog/press + third-party corroboration",
        ),
        "PersonBioAndAffiliationsAgent": AgentTypeDefinition(
            name="PersonBioAndAffiliationsAgent",
            description="Enriches people profiles with roles, credentials, affiliations, and prior work",
            default_tools=["tavily.search", "tavily.extract", "fs.write", "fs.read", "think", "wiki.search"],
            typical_outputs=["PeopleProfiles", "RoleResponsibilityMap", "CredentialAnchors"],
            source_focus="official_leadership + scholarly/pub profiles",
        ),
        "EcosystemMapperAgent": AgentTypeDefinition(
            name="EcosystemMapperAgent",
            description="Maps entity position in biotech/biohacking/wellness ecosystem: competitors, partners, market category",
            default_tools=["tavily.extract", "exa.search", "exa.find_similar", "fs.write", "fs.read", "think"],
            typical_outputs=["CompetitorSet", "PartnerAndPlatformGraph", "MarketCategoryPlacement"],
            source_focus="press_news + official_platform/about + search-based discovery",
        ),
    
        "EvidenceClassifierAgent": AgentTypeDefinition(
            name="EvidenceClassifierAgent",
            description="Classifies evidence by type (human/animal/in vitro), study design (RCT/obs/mechanistic), and independence",
            default_tools=["fs.read", "fs.write", "think", "pubmed.literature_search", "pubmed.fulltext"],
            typical_outputs=["EvidenceClassificationTable"],
            source_focus="evidence artifacts from discovery",
        ),
        "ProductSpecAgent": AgentTypeDefinition(
            name="ProductSpecAgent",
            description="Extracts detailed product specifications: ingredients, dosages, usage, pricing, warnings",
            default_tools=["browser.playwright", "tavily.search", "tavily.crawl", "tavily.extract", "fs.write", "fs.read", "think"],
            typical_outputs=["ProductSpecs", "IngredientOrMaterialLists", "UsageAndWarningSnippets"],
            source_focus="official_product_detail + official_docs_manuals + help snippets",
        ),
        "TechnologyProcessAndManufacturingAgent": AgentTypeDefinition(
            name="TechnologyProcessAndManufacturingAgent",
            description="Extracts technology mechanisms, manufacturing processes, QA claims, patents",
            default_tools=["tavily.extract", "wiki.search", "fs.write", "fs.read", "think"],
            typical_outputs=["TechnologyMechanismSummaries", "ManufacturingAndQAClaims", "PatentAndProcessReferences"],
            source_focus="official_research/platform pages + disclosed QA/GMP/ISO/testing + patents/whitepapers",
        ),
        "ClaimsExtractorAndTaxonomyMapperAgent": AgentTypeDefinition(
            name="ClaimsExtractorAndTaxonomyMapperAgent",
            description="Extracts, normalizes, and ranks all explicit claims from product/landing/help pages",
            default_tools=["tavily.extract", "fs.write", "fs.read", "think"],
            typical_outputs=["ClaimsLedger", "NormalizedClaimMap", "ClaimSalienceRanking"],
            source_focus="product pages + landing pages + help_center + book/course blurbs + labels",
        ),
        "ProductReviewsAgent": AgentTypeDefinition(
            name="ProductReviewsAgent",
            description="Aggregates user feedback and reviews (anecdotal, clearly labeled)",
            default_tools=["browser.playwright", "tavily.search", "tavily.extract", "fs.write", "fs.read", "think"],
            typical_outputs=["UserFeedbackSummary", "AnecdotalSignalNotes"],
            source_focus="marketplace_reviews + social_community + first-party testimonials",
        ),
        "CaseStudyHarvestAgent": AgentTypeDefinition(
            name="CaseStudyHarvestAgent",
            description="Harvests evidence artifacts: studies, trials, whitepapers, case studies with affiliation labeling",
            default_tools=["tavily.search", "tavily.extract", "fs.write", "fs.read", "think"],
            typical_outputs=["EvidenceArtifacts"],
            source_focus="company-controlled evidence + independent studies + trials",
        ),
       

      
        "KnowledgeSynthesizerAgent": AgentTypeDefinition(
            name="KnowledgeSynthesizerAgent",
            description="Synthesizes all research outputs into coherent entity representation (KG-ready)",
            default_tools=["fs.read", "fs.write"],
            typical_outputs=["EntityResearchSummary"],
            source_focus="all artifacts from S1-S3",
        ),
        "ClaimConfidenceScorerAgent": AgentTypeDefinition(
            name="ClaimConfidenceScorerAgent",
            description="Assigns confidence tiers (Proven/Plausible/Speculative/Unsupported) with rationale",
            default_tools=["fs.read", "fs.write"],
            typical_outputs=["ClaimConfidenceScores"],
            source_focus="claims ledger + evidence classification + strength assessment",
        ),
        "NarrativeAnalystAgent": AgentTypeDefinition(
            name="NarrativeAnalystAgent",
            description="Contrasts marketing narrative vs evidentiary reality, highlights tensions and adoption drivers",
            default_tools=["fs.read", "fs.write"],
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

