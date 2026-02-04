from typing import Dict, List 
from research_agent.human_upgrade.structured_outputs.research_plans_outputs import StageMode  
from research_agent.human_upgrade.constants.export_plans import PREBUILT_RESEARCH_PLANS


def _generate_mode_spec_blueprint(stage_mode: str) -> str:
    plan = PREBUILT_RESEARCH_PLANS.get(stage_mode)
    if not plan:
        return f"MODE {stage_mode} not found in prebuilt plans."

    lines: List[str] = []
    lines += [
        f"MODE_BLUEPRINT: {plan.stage_mode}",
        "",
        "YOU MUST OUTPUT an InitialResearchPlan with:",
        "- stages: List[StagePlan] (matches blueprint below)",
        "- agent_instances: List[AgentInstancePlanWithoutSources]",
        "",
        "StagePlan schema:",
        '{ "stage_id": "S#", "name": "...", "description": "...", "sub_stages": [SubStagePlan...], "depends_on_stages": [] }',
        "",
        "SubStagePlan schema:",
        '{ "sub_stage_id": "S#.X", "name": "...", "description": "...", "agent_instances": ["instance_id", ...], "can_run_in_parallel": true/false, "depends_on_substages": ["S#.Y", ...] }',
        "",
        "=" * 80,
        "STAGES + SUBSTAGES BLUEPRINT (OUTPUT-SHAPED):",
        "",
    ]

    for stage in plan.stages:
        lines += [
            f"STAGE_PLAN:",
            f'- stage_id: "{stage.stage_id}"',
            f'- name: "{stage.name}"',
            f'- description: "{stage.description}"',
            f'- depends_on_stages: []  (fill if needed based on dependencies)',
            f"- sub_stages:",
        ]

        for ss in stage.sub_stages:
            lines += [
                "  SUB_STAGE_PLAN:",
                f'  - sub_stage_id: "{ss.sub_stage_id}"',
                f'    name: "{ss.name}"',
                f'    description: "{ss.description}"',
                f"    depends_on_substages: {ss.depends_on_substages or []}",
                f'    can_run_in_parallel: true  (use parallelization_notes: "{ss.parallelization_notes or ""}")',
                '    agent_instances: ["<instance_id_1>", "<instance_id_2>", ...]  # MUST be filled',
                f'    agent_type_for_instances: "{ss.agent_type}"',
                "",
            ]

        lines += ["-" * 40, ""]

    lines += [
        "=" * 80,
        "AGENT TYPE DEFINITIONS (BRIEF):",
        "",
    ]
    for agent_type_name in sorted(plan.agent_type_definitions.keys()):
        agent_def = plan.agent_type_definitions[agent_type_name]
        lines += [
            f"- {agent_type_name}: {agent_def.description}",
            f"  default_tools: {agent_def.default_tools}",
            f"  typical_outputs: {agent_def.typical_outputs}",
            f"  source_focus: {agent_def.source_focus or ''}",
            "",
        ]

    lines += [
        "=" * 80,
        "IMPORTANT: The blueprint describes the StagePlan/SubStagePlan structure. You must populate agent_instances lists with instance_ids you create.",
    ]

    return "\n".join(lines)


FULL_ENTITIES_STANDARD_V2_MODE_SPEC_TEXT = _generate_mode_spec_blueprint("full_entities_standard")


def format_initial_research_plan_prompt(
    stage_mode: StageMode,
    connected_candidates_json: str,
    mode_and_agent_recommendations_json: str,
    tool_recommendations_json: str,
    slicing_inputs_json: str,
) -> str:
    """
    Helper function to format the initial research plan prompt with all required inputs.
    
    Args:
        stage_mode: The research mode (e.g., "full_entities_standard")
        connected_candidates_json: JSON string of ConnectedCandidates
        mode_and_agent_recommendations_json: JSON string of ModeAndAgentRecommendationsBundle
        tool_recommendations_json: JSON string of ToolRecommendationsBundle
        slicing_inputs_json: JSON string of SLICING_INPUTS
        
    Returns:
        Formatted prompt string ready to use with the LLM
    """
    prompt_template = INITIAL_RESEARCH_PLAN_PROMPTS.get(stage_mode)
    if not prompt_template:
        raise ValueError(f"No prompt template found for stage_mode: {stage_mode}")
    
    mode_spec = _generate_mode_spec_blueprint(stage_mode)
    
    return prompt_template.format(
        MODE_SPEC=mode_spec,
        CONNECTED_CANDIDATES_JSON=connected_candidates_json,
        MODE_AND_AGENT_RECOMMENDATIONS_JSON=mode_and_agent_recommendations_json,
        TOOL_RECOMMENDATIONS_JSON=tool_recommendations_json,
        SLICING_INPUTS_JSON=slicing_inputs_json,
    )


INITIAL_RESEARCH_PLAN_PROMPTS: Dict[StageMode, str] = {
    "full_entities_standard": """SYSTEM:
You are the Initial Research Plan Builder Agent.
You MUST output a complete InitialResearchPlan JSON that configures an end-to-end mission skeleton WITHOUT sources.

OUTPUT MUST MATCH InitialResearchPlan schema exactly:
- mission_id: string
- stage_mode: "full_entities_standard"
- target_businesses: [string]
- target_people: [string]
- target_products: [string]
- mission_objectives: [Objective]  # objects, not strings
- stages: [StagePlan]
- agent_instances: [AgentInstancePlanWithoutSources]
- notes: optional string

Objective object schema (REQUIRED):
{{
  "objective": "string",
  "sub_objectives": ["string", "..."],
  "success_criteria": ["string", "..."]
}}

StagePlan schema (REQUIRED):
{{
  "stage_id": "S#",
  "name": "string",
  "description": "string",
  "sub_stages": [SubStagePlan],
  "depends_on_stages": ["S#", "..."]
}}

SubStagePlan schema (REQUIRED):
{{
  "sub_stage_id": "S#.X",
  "name": "string",
  "description": "string",
  "agent_instances": ["instance_id", "..."],  # REQUIRED: MUST list the instance_ids you create for this substage
  "can_run_in_parallel": true,
  "depends_on_substages": ["S#.Y", "..."]
}}

AgentInstancePlanWithoutSources schema (REQUIRED):
{{
  "instance_id": "string",
  "agent_type": "AgentType",      # must be one of the allowed AgentType values
  "stage_id": "S#",
  "sub_stage_id": "S#.X",
  "slice": SliceSpec OR null,
  "objectives": [Objective],
  "requires_artifacts": ["string", "..."],
  "produces_artifacts": ["string", "..."],
  "notes": "string" OR null
}}

SliceSpec schema (REQUIRED when slicing):
{{
  "dimension": "people" OR "products",
  "slice_id": "string",
  "rationale": "string",
  "product_names": ["string", "..."],
  "person_names": ["string", "..."],
  "source_urls": [],              # MUST be empty at this stage
  "notes": "string" OR null
}}

CRITICAL RULES:
1) NO SOURCES:
- DO NOT include starter_sources anywhere. This is InitialResearchPlan only.

2) STAGES/SUBSTAGES MUST MATCH MODE_SPEC:
- stages and sub_stages MUST follow the provided MODE_SPEC blueprint.
- You MUST create agent_instances and list their instance_id under the correct SubStagePlan.agent_instances.

3) DETERMINISTIC INSTANCE IDS (REQUIRED):
instance_id MUST follow:
"{{agent_type}}:{{stage_id}}:{{sub_stage_id}}:{{slice_id_or_single}}"
- If sliced: use slice.slice_id
- If not sliced: use "single"

Examples:
"BusinessIdentityAndLeadershipAgent:S1:S1.1:single"
"PersonBioAndAffiliationsAgent:S1:S1.2:people_01_of_03"
"ProductSpecAgent:S2:S2.1:products_02_of_05"

SLICING (STRICT, REQUIRED):
You will also receive SLICING_INPUTS with precomputed slices. You MUST follow it exactly.

Definitions:
- One slice = one AgentInstance.
- Product slices apply ONLY to substage S2.1 (ProductSpecAgent).
- People slices apply ONLY to substage S1.2 (PersonBioAndAffiliationsAgent).

Hard requirements:
1) ProductSpecAgent instances:
   - Create EXACTLY len(SLICING_INPUTS.product_slices) instances of agent_type="ProductSpecAgent"
   - Each instance MUST correspond to exactly one slice from product_slices (no mixing).
   - slice.dimension MUST be "products"
   - slice.product_names MUST equal that slice’s list EXACTLY (same order).
   - slice.person_names MUST be []
   - slice.source_urls MUST be [] (always empty in InitialResearchPlan)

2) PersonBioAndAffiliationsAgent instances:
   - Create EXACTLY len(SLICING_INPUTS.person_slices) instances of agent_type="PersonBioAndAffiliationsAgent"
   - slice.dimension MUST be "people"
   - slice.person_names MUST equal that slice’s list EXACTLY (same order).
   - slice.product_names MUST be []
   - slice.source_urls MUST be []

3) instance_id format (REQUIRED):
   instance_id = "{{agent_type}}:{{stage_id}}:{{sub_stage_id}}:{{slice.slice_id}}"

4) slice_id format (REQUIRED):
   - For product slices: "products_{{i:02d}}_of_{{n:02d}}"
   - For people slices: "people_{{i:02d}}_of_{{n:02d}}"

5) If a slice list is empty, create ZERO instances for that agent_type.

Example (illustrative only):
If product_slices = [["P1","P2","P3","P4","P5"],["P6"]] then you MUST create 2 ProductSpecAgent instances:
- instance_id = "ProductSpecAgent:S2:S2.1:products_01_of_02" with slice.product_names ["P1","P2","P3","P4","P5"]
- instance_id = "ProductSpecAgent:S2:S2.1:products_02_of_02" with slice.product_names ["P6"]

CONSISTENCY REQUIREMENTS:
- Every AgentInstancePlanWithoutSources must appear exactly once in some SubStagePlan.agent_instances list.
- Every instance_id listed in SubStagePlan.agent_instances must exist in agent_instances.
- stage_id/sub_stage_id of instances must match the substage they are listed under.
- For sliced substages (S1.2 and S2.1), DO NOT create any additional catch-all instances beyond the slices.

OUTPUT CONSTRAINTS:
- Output ONLY valid JSON (InitialResearchPlan). No markdown. No commentary.
- DO NOT include starter_sources.

USER:
You will receive FOUR JSON bundles:
1) ConnectedCandidates: businesses, people, products, compounds, notes.
2) ModeAndAgentRecommendationsBundle: stage mode recommendation + constraints (max_total_agent_instances, allow_product_reviews, priorities).
3) ToolRecommendationsBundle: allowed tools and default tools per AgentType.
4) SLICING_INPUTS: precomputed slices you MUST follow exactly.

TASK:
Using MODE_SPEC, generate InitialResearchPlan with correct stages/substages, correct agent instances, strict slicing compliance, and consistent linking.

MODE_SPEC:
{MODE_SPEC}

ConnectedCandidates:
{CONNECTED_CANDIDATES_JSON}

ModeAndAgentRecommendationsBundle:
{MODE_AND_AGENT_RECOMMENDATIONS_JSON}

ToolRecommendationsBundle:
{TOOL_RECOMMENDATIONS_JSON}

SLICING_INPUTS:
{SLICING_INPUTS_JSON}

Output ONLY valid JSON. No markdown. No commentary.
""",
    "full_entities_basic": """SYSTEM:
You are the Initial Research Plan Builder Agent.
You MUST output a complete InitialResearchPlan JSON that configures an end-to-end mission skeleton WITHOUT sources.

OUTPUT MUST MATCH InitialResearchPlan schema exactly:
- mission_id: string
- stage_mode: "full_entities_basic"
- target_businesses: [string]
- target_people: [string]
- target_products: [string]
- mission_objectives: [Objective]  # objects, not strings
- stages: [StagePlan]
- agent_instances: [AgentInstancePlanWithoutSources]
- notes: optional string

Objective object schema (REQUIRED):
{{
  "objective": "string",
  "sub_objectives": ["string", "..."],
  "success_criteria": ["string", "..."]
}}

StagePlan schema (REQUIRED):
{{
  "stage_id": "S#",
  "name": "string",
  "description": "string",
  "sub_stages": [SubStagePlan],
  "depends_on_stages": ["S#", "..."]
}}

SubStagePlan schema (REQUIRED):
{{
  "sub_stage_id": "S#.X",
  "name": "string",
  "description": "string",
  "agent_instances": ["instance_id", "..."],  # REQUIRED: MUST list the instance_ids you create for this substage
  "can_run_in_parallel": true,
  "depends_on_substages": ["S#.Y", "..."]
}}

AgentInstancePlanWithoutSources schema (REQUIRED):
{{
  "instance_id": "string",
  "agent_type": "AgentType",      # must be one of the allowed AgentType values
  "stage_id": "S#",
  "sub_stage_id": "S#.X",
  "slice": SliceSpec OR null,
  "objectives": [Objective],
  "requires_artifacts": ["string", "..."],
  "produces_artifacts": ["string", "..."],
  "notes": "string" OR null
}}

SliceSpec schema (REQUIRED when slicing):
{{
  "dimension": "people" OR "products",
  "slice_id": "string",
  "rationale": "string",
  "product_names": ["string", "..."],
  "person_names": ["string", "..."],
  "source_urls": [],              # MUST be empty at this stage
  "notes": "string" OR null
}}

CRITICAL RULES:
1) NO SOURCES:
- DO NOT include starter_sources anywhere. This is InitialResearchPlan only.

2) STAGES/SUBSTAGES MUST MATCH MODE_SPEC:
- stages and sub_stages MUST follow the provided MODE_SPEC blueprint.
- You MUST create agent_instances and list their instance_id under the correct SubStagePlan.agent_instances.
- For full_entities_basic, you will have 3 stages: S1 (Entity Biography, Identity & Ecosystem), S2 (Product Specifications), S3 (Evidence Discovery).

3) DETERMINISTIC INSTANCE IDS (REQUIRED):
instance_id MUST follow:
"{{agent_type}}:{{stage_id}}:{{sub_stage_id}}:{{slice_id_or_single}}"
- If sliced: use slice.slice_id
- If not sliced: use "single"

Examples:
"BusinessIdentityAndLeadershipAgent:S1:S1.1:single"
"PersonBioAndAffiliationsAgent:S1:S1.2:people_01_of_03"
"ProductSpecAgent:S2:S2.1:products_02_of_05"
"CaseStudyHarvestAgent:S3:S3.1:single"

SLICING (STRICT, REQUIRED):
You will also receive SLICING_INPUTS with precomputed slices. You MUST follow it exactly.

Definitions:
- One slice = one AgentInstance.
- Product slices apply ONLY to substage S2.1 (ProductSpecAgent).
- People slices apply ONLY to substage S1.2 (PersonBioAndAffiliationsAgent).

Hard requirements:
1) ProductSpecAgent instances:
   - Create EXACTLY len(SLICING_INPUTS.product_slices) instances of agent_type="ProductSpecAgent"
   - Each instance MUST correspond to exactly one slice from product_slices (no mixing).
   - slice.dimension MUST be "products"
   - slice.product_names MUST equal that slice's list EXACTLY (same order).
   - slice.person_names MUST be []
   - slice.source_urls MUST be [] (always empty in InitialResearchPlan)

2) PersonBioAndAffiliationsAgent instances:
   - Create EXACTLY len(SLICING_INPUTS.person_slices) instances of agent_type="PersonBioAndAffiliationsAgent"
   - slice.dimension MUST be "people"
   - slice.person_names MUST equal that slice's list EXACTLY (same order).
   - slice.product_names MUST be []
   - slice.source_urls MUST be []

3) instance_id format (REQUIRED):
   instance_id = "{{agent_type}}:{{stage_id}}:{{sub_stage_id}}:{{slice.slice_id}}"

4) slice_id format (REQUIRED):
   - For product slices: "products_{{i:02d}}_of_{{n:02d}}"
   - For people slices: "people_{{i:02d}}_of_{{n:02d}}"

5) If a slice list is empty, create ZERO instances for that agent_type.

Example (illustrative only):
If product_slices = [["P1","P2","P3","P4","P5"],["P6"]] then you MUST create 2 ProductSpecAgent instances:
- instance_id = "ProductSpecAgent:S2:S2.1:products_01_of_02" with slice.product_names ["P1","P2","P3","P4","P5"]
- instance_id = "ProductSpecAgent:S2:S2.1:products_02_of_02" with slice.product_names ["P6"]

CONSISTENCY REQUIREMENTS:
- Every AgentInstancePlanWithoutSources must appear exactly once in some SubStagePlan.agent_instances list.
- Every instance_id listed in SubStagePlan.agent_instances must exist in agent_instances.
- stage_id/sub_stage_id of instances must match the substage they are listed under.
- For sliced substages (S1.2 and S2.1), DO NOT create any additional catch-all instances beyond the slices.

OUTPUT CONSTRAINTS:
- Output ONLY valid JSON (InitialResearchPlan). No markdown. No commentary.
- DO NOT include starter_sources.

USER:
You will receive FOUR JSON bundles:
1) ConnectedCandidates: businesses, people, products, compounds, notes.
2) ModeAndAgentRecommendationsBundle: stage mode recommendation + constraints (max_total_agent_instances, allow_product_reviews, priorities).
3) ToolRecommendationsBundle: allowed tools and default tools per AgentType.
4) SLICING_INPUTS: precomputed slices you MUST follow exactly.

TASK:
Using MODE_SPEC, generate InitialResearchPlan with correct stages/substages, correct agent instances, strict slicing compliance, and consistent linking.

MODE_SPEC:
{MODE_SPEC}

ConnectedCandidates:
{CONNECTED_CANDIDATES_JSON}

ModeAndAgentRecommendationsBundle:
{MODE_AND_AGENT_RECOMMENDATIONS_JSON}

ToolRecommendationsBundle:
{TOOL_RECOMMENDATIONS_JSON}

SLICING_INPUTS:
{SLICING_INPUTS_JSON}

Output ONLY valid JSON. No markdown. No commentary.
""",
    "entities_full": "TODO: entities_full prompt (placeholder)",
    "entities_basic": "TODO: entities_basic prompt (placeholder)",
}



ATTACH_SOURCES_TO_AGENT_INSTANCES_PROMPTS = {
  "full_entities_standard": """
You are given:
1) INITIAL_PLAN_JSON: a research mission plan containing stages and agent_instances WITHOUT sources.
2) SOURCE_EXPANSION_JSON: discovered URLs (competitors/research/other).
3) DOMAIN_CATALOGS_JSON: curated domains / known official sources.

Task:
Return ONLY a JSON object matching AgentInstancePlansWithSourcesOutput:
{{
  "agent_instances": [AgentInstancePlanWithSources...],
  "notes": "optional"
}}

Rules (very important):
- Output one AgentInstancePlanWithSources for EVERY agent instance in INITIAL_PLAN_JSON.agent_instances.
- DO NOT add/remove/reorder instances. Preserve instance_id and keep invariant fields identical:
  instance_id, agent_type, stage_id, sub_stage_id, slice, objectives, requires_artifacts, produces_artifacts.
- Your ONLY job is to add highly-relevant starter_sources to each instance.
- Each starter_sources item must be a CuratedSource with url + category. Title/notes optional.
- Prefer official sources first when appropriate, then scholarly/clinical/regulatory, then press/news.
- Avoid low-quality sources. Avoid duplicates across a single instance where possible.
- If no good sources exist, return starter_sources as an empty list (not null).

CRITICAL: STAGE DEPENDENCIES AND CONTEXT FLOW
- Pay close attention to which stages depend on which stages, and which sub-stages depend on other sub-stages.
- Context flows through the dependency chain: later stages/sub-stages may reuse information from earlier ones.
- If you duplicate a source across > 1 Agent Instance, it MUST be very meaningful and justified.
- Generally, prefer unique sources per instance unless the source is critical for multiple distinct purposes.

PRIORITY SOURCE ASSIGNMENTS (MOST IMPORTANT):
1) BusinessIdentityAndLeadershipAgent (S1.1):
   - HIGHEST PRIORITY: These are the most important starter sources for the entire mission.
   - Include: official homepage, about page, leadership pages, key blog/press releases.
   - These sources establish the foundation that other agents may reference.

2) ProductSpecAgent slices (S2.1):
   - CRITICAL: Every single specific product URL for products in that slice, OR a product index URL.
   - For each product in slice.product_names, find the matching productPageUrl from DomainCatalog.
   - If specific product URLs aren't available, use productIndexUrls.
   - These are essential for product specification extraction.

3) EcosystemMapperAgent (S1.3):
   - HIGH PRIORITY: Competitor URLs from SourceExpansion.competitorUrls.
   - Include: Main entity URL (homepage) for ecosystem context.
   - Include: Press/news URLs mentioning competitors or ecosystem positioning.

4) CaseStudyHarvestAgent (S3.1):
   - HIGH PRIORITY: Research URLs and case study URLs.
   - Include: SourceExpansion.researchUrls (scholarly sources, studies, trials).
   - Include: DomainCatalog.researchUrls and caseStudyUrls.
   - These are essential for evidence discovery.

INITIAL_PLAN_JSON:
{INITIAL_PLAN_JSON}

SOURCE_EXPANSION_JSON:
{SOURCE_EXPANSION_JSON}

DOMAIN_CATALOGS_JSON:
{DOMAIN_CATALOGS_JSON}
""",
  "full_entities_basic": """
You are given:
1) INITIAL_PLAN_JSON: a research mission plan containing stages and agent_instances WITHOUT sources.
2) SOURCE_EXPANSION_JSON: discovered URLs (competitors/research/other).
3) DOMAIN_CATALOGS_JSON: curated domains / known official sources.

Task:
Return ONLY a JSON object matching AgentInstancePlansWithSourcesOutput:
{{
  "agent_instances": [AgentInstancePlanWithSources...],
  "notes": "optional"
}}

Rules (very important):
- Output one AgentInstancePlanWithSources for EVERY agent instance in INITIAL_PLAN_JSON.agent_instances.
- DO NOT add/remove/reorder instances. Preserve instance_id and keep invariant fields identical:
  instance_id, agent_type, stage_id, sub_stage_id, slice, objectives, requires_artifacts, produces_artifacts.
- Your ONLY job is to add highly-relevant starter_sources to each instance.
- Each starter_sources item must be a CuratedSource with url + category. Title/notes optional.
- Prefer official sources first when appropriate, then scholarly/clinical/regulatory, then press/news.
- Avoid low-quality sources. Avoid duplicates across a single instance where possible.
- If no good sources exist, return starter_sources as an empty list (not null).

CRITICAL: STAGE DEPENDENCIES AND CONTEXT FLOW
- Pay close attention to which stages depend on which stages, and which sub-stages depend on other sub-stages.
- Context flows through the dependency chain: later stages/sub-stages may reuse information from earlier ones.
- If you duplicate a source across > 1 Agent Instance, it MUST be very meaningful and justified.
- Generally, prefer unique sources per instance unless the source is critical for multiple distinct purposes.

STAGE DEPENDENCIES FOR FULL_ENTITIES_BASIC:
- S1 (Entity Biography, Identity & Ecosystem): No dependencies, runs first.
- S2 (Product Specifications): Can run with product catalog or independently.
- S3 (Evidence Discovery): Can start with S2 product information if available, but can also run independently.

PRIORITY SOURCE ASSIGNMENTS (MOST IMPORTANT):
1) BusinessIdentityAndLeadershipAgent (S1.1):
   - HIGHEST PRIORITY: These are the most important starter sources for the entire mission.
   - Include: official homepage, about page, leadership pages, key blog/press releases.
   - These sources establish the foundation that other agents may reference.

2) ProductSpecAgent slices (S2.1):
   - CRITICAL: Every single specific product URL for products in that slice, OR a product index URL.
   - For each product in slice.product_names, find the matching productPageUrl from DomainCatalog.
   - If specific product URLs aren't available, use productIndexUrls.
   - These are essential for product specification extraction.

3) EcosystemMapperAgent (S1.3):
   - HIGH PRIORITY: Competitor URLs from SourceExpansion.competitorUrls.
   - Include: Main entity URL (homepage) for ecosystem context.
   - Include: Press/news URLs mentioning competitors or ecosystem positioning.

4) CaseStudyHarvestAgent (S3.1):
   - HIGH PRIORITY: Research URLs and case study URLs.
   - Include: SourceExpansion.researchUrls (scholarly sources, studies, trials).
   - Include: DomainCatalog.researchUrls and caseStudyUrls if available.
   - These are essential for evidence discovery.

INITIAL_PLAN_JSON:
{INITIAL_PLAN_JSON}

SOURCE_EXPANSION_JSON:
{SOURCE_EXPANSION_JSON}

DOMAIN_CATALOGS_JSON:
{DOMAIN_CATALOGS_JSON}
"""
}