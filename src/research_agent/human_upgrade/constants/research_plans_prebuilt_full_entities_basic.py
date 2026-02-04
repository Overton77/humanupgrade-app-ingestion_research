from research_agent.human_upgrade.constants.research_plans_prebuilt_models import PrebuiltResearchPlan, AgentTypeDefinition, SubStageDefinition, StageDefinition
from typing import Dict

# ============================================================================
# FULL ENTITIES BASIC DEFINITION
# ============================================================================

FULL_ENTITIES_BASIC_PLAN = PrebuiltResearchPlan(
    stage_mode="full_entities_basic",
    goal=(
        "Produce a minimal, essential overview of an organization "
        "(company, clinic, brand, author platform, researcher, or biotech entrepreneur) covering: "
        "who they are, what they offer, and what evidence exists. "
        "This is a streamlined mode focused on core entity information and basic product specifications."
    ),
    description=(
        "Minimal ResearchPlan blueprint for essential entity overview. "
        "Focused on core identity, people, ecosystem positioning, product specs, and basic evidence discovery. "
        "Designed for quick triage and routing decisions."
    ),
    planning_rule=(
        "ResearchPlan must fully specify stages/substages/agent_instances/objectives/slicing, "
        "but MUST NOT bind starter_sources yet. "
        "Final binding happens after DomainCatalogExpansion + SourceSetCurator."
    ),
    execution_model=(
        "Stages are ordered by dependency artifacts. "
        "Within a stage, substages may run in parallel if their required artifacts are satisfied. "
        "Agent instances within a substage may run in parallel if slices are disjoint (people/products). "
        "Use slicing when People/Products are large to keep instances bounded."
    ),
    stages=[
        StageDefinition(
            stage_id="S1",
            name="Entity Biography, Identity & Ecosystem",
            description="Establish who this entity is, who leads it, and how it positions itself.",
            purpose="Entity Biography, Identity & Ecosystem",
            assumptions=(
                "Entity name, major people, and major products are already provided as inputs. "
                "This stage enriches and contextualizes, not merely identifies."
            ),
            dependencies="No required upstream deps beyond provided entity inputs; can run immediately.",
            parallelization="S1.1, S1.2, and S1.3 can run in parallel. S1.2 can be split per person.",
            sub_stages=[
                SubStageDefinition(
                    sub_stage_id="S1.1",
                    name="Organization Identity & Structure",
                    description="Entity Biography & Organizational Overview",
                    purpose="What is this organization/person, really? How do they describe themselves vs how others describe them?",
                    responsibilities=[
                        "Produce a concise but information-dense biography / overview",
                        "Clarify the entity's core mission, audience, and operating posture",
                        "Summarize the origin story and major inflection points",
                        "Identify primary lines of business",
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
            name="Product Specifications",
            description="Extract core product specifications and details.",
            purpose="Product Specifications",
            dependencies=(
                "S2.1 can run with a provided product catalog (preferred) or a minimal set of product URLs. "
                "No dependencies on other stages."
            ),
            parallelization=(
                "S2.1 runs per batch of products (e.g., up to 5 per instance). "
                "Multiple instances can run in parallel for different product batches."
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
                        "Accept an input list of products with canonical product URLs (catalog is assumed mostly complete).",
                        "Normalize product identifiers and confirm each product has at least one usable official detail URL.",
                        "Perform a static-first extraction per product using crawl/extract: read visible HTML text, metadata, and JSON-LD/offers when present.",
                        "Attempt to fill required fields from static content: price or price range (if present), ingredient/material list (names), directions/schedule (if present), and official warnings (explicit only).",
                        "Compute a simple per-product completeness check for required fields (e.g., price missing and/or ingredients missing).",
                        "Only if required fields are missing, prepare a targeted Playwright request specifying the missing fields and the minimal interactions likely needed.",
                        "Call a separate Playwright workflow tool (worker agent) to execute the interaction plan; do not attempt UI control inside this agent.",
                        "Receive structured Playwright results (snippets + values + evidence) and merge them back into the per-product spec record.",
                        "Attach lightweight evidence pointers for extracted fields (URL + section label and/or selector reference).",
                        "Emit a compact coverage note per product indicating which fields were found statically vs via Playwright, and which remain missing.",
                    ],
                    agent_type="ProductSpecAgent",
                    outputs=[
                        "BatchProductSpecs",
                        "BatchSpecEvidence",
                        "BatchCoverageNotes",
                        "PlaywrightRequestsMade",
                    ],
                    source_focus="official_product_detail + official_label/facts pages or PDFs + official help snippets (static-first; Playwright only when missing required fields)",
                    parallelization_notes="Run in batches of <=5 products per instance. Only request Playwright for products failing the required-fields completeness check.",
                    is_required=True,
                ),
            ],
        ),
        StageDefinition(
            stage_id="S3",
            name="Evidence Discovery",
            description="Harvest basic evidence artifacts.",
            purpose="Evidence Discovery",
            dependencies=(
                "S3.1 can start with product information from S2 if available, "
                "but can also run independently with basic entity/product names."
            ),
            parallelization=(
                "Evidence discovery can be split by product batches or claim clusters. "
                "Multiple instances can run in parallel for different products/claims."
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
                        "Focus on readily available evidence (company websites, published studies, basic trial registrations)",
                    ],
                    agent_type="CaseStudyHarvestAgent",
                    outputs=["EvidenceArtifacts"],
                    source_focus="company-controlled evidence + independent studies + trials",
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
        "ProductSpecAgent": AgentTypeDefinition(
            name="ProductSpecAgent",
            description="Extracts detailed product specifications: ingredients, dosages, usage, pricing, warnings",
            default_tools=["browser.playwright", "tavily.search", "tavily.crawl", "tavily.extract", "fs.write", "fs.read", "think"],
            typical_outputs=["ProductSpecs", "IngredientOrMaterialLists", "UsageAndWarningSnippets"],
            source_focus="official_product_detail + official_docs_manuals + help snippets",
        ),
        "CaseStudyHarvestAgent": AgentTypeDefinition(
            name="CaseStudyHarvestAgent",
            description="Harvests evidence artifacts: studies, trials, whitepapers, case studies with affiliation labeling",
            default_tools=["tavily.search", "tavily.extract", "fs.write", "fs.read", "think"],
            typical_outputs=["EvidenceArtifacts"],
            source_focus="company-controlled evidence + independent studies + trials",
        ),
    },
    global_tool_expectations=(
        "Static HTML: search + extract; JS-heavy: playwright + extract fallback. "
        "PDFs/manuals/COAs: doc.pdf_text; screenshot_ocr only if table/diagram blocks text extraction. "
        "Scholarly/clinical: scholar.pubmed + scholar.semantic_scholar + registry.clinicaltrials. "
        "Focus on official sources and readily available evidence."
    ),
    what_this_mode_intentionally_does_not_do=[
        "Claims extraction and normalization",
        "Evidence classification and quality assessment",
        "Technology/manufacturing deep dive",
        "Confidence scoring",
        "Narrative analysis",
        "Research routing recommendations",
        "Full regulatory adjudication",
        "Financial modeling",
    ],
    why_ready_to_implement=[
        "Streamlined agent set with clear responsibilities",
        "Minimal dependencies between stages",
        "Focused on essential information gathering",
        "Works whether agents are run: standalone, per stage, or in a LangGraph DAG",
    ],
)
