from typing import Dict 
from research_agent.human_upgrade.structured_outputs.research_plans_outputs import StageMode  
from research_agent.human_upgrade.constants.research_plans_prebuilt import PREBUILT_RESEARCH_PLANS


def _generate_mode_spec_text(stage_mode: str) -> str:
    """Generate a clear, structured mode specification text from prebuilt plan."""
    plan = PREBUILT_RESEARCH_PLANS.get(stage_mode)
    if not plan:
        return f"MODE {stage_mode} not found in prebuilt plans."
    
    lines = [
        f"MODE: {plan.stage_mode}",
        "",
        f"GOAL: {plan.goal}",
        "",
        f"DESCRIPTION: {plan.description}",
        "",
        "PLANNING RULE:",
        plan.planning_rule,
        "",
        "EXECUTION MODEL:",
        plan.execution_model,
        "",
    ]
    
    # Add stages
    for stage in plan.stages:
        lines.extend([
            f"{'='*80}",
            f"STAGE {stage.stage_id} — {stage.name}",
            f"Purpose: {stage.purpose}",
            "",
        ])
        
        if stage.assumptions:
            lines.extend([
                f"Assumptions: {stage.assumptions}",
                "",
            ])
        
        # Add sub-stages
        for sub_stage in stage.sub_stages:
            required_marker = " (REQUIRED)" if sub_stage.is_required else ""
            optional_marker = " (OPTIONAL)" if sub_stage.is_optional else ""
            lines.extend([
                f"  {sub_stage.sub_stage_id} {sub_stage.name}{required_marker}{optional_marker}",
                f"    Agent Type: {sub_stage.agent_type}",
                f"    Purpose: {sub_stage.purpose}",
            ])
            
            if sub_stage.responsibilities:
                lines.append("    Responsibilities:")
                for resp in sub_stage.responsibilities:
                    lines.append(f"      - {resp}")
            
            lines.extend([
                f"    Produces: {', '.join(sub_stage.outputs)}",
                f"    Source Focus: {sub_stage.source_focus}",
            ])
            
            if sub_stage.parallelization_notes:
                lines.append(f"    Parallelization: {sub_stage.parallelization_notes}")
            
            lines.append("")
        
        # Add stage-level dependencies and parallelization
        if stage.dependencies:
            lines.extend([
                f"  {stage.stage_id} DEPENDENCIES:",
                f"    {stage.dependencies}",
                "",
            ])
        
        if stage.parallelization:
            lines.extend([
                f"  {stage.stage_id} PARALLELIZATION:",
                f"    {stage.parallelization}",
                "",
            ])
    
    # Add global tool expectations
    if plan.global_tool_expectations:
        lines.extend([
            f"{'='*80}",
            "GLOBAL TOOL/FORMAT EXPECTATIONS:",
            plan.global_tool_expectations,
            "",
        ])
    
    # Add what this mode does not do
    if plan.what_this_mode_intentionally_does_not_do:
        lines.extend([
            f"{'='*80}",
            "WHAT THIS MODE INTENTIONALLY DOES NOT DO:",
        ])
        for item in plan.what_this_mode_intentionally_does_not_do:
            lines.append(f"  - {item}")
        lines.append("")
    
    return "\n".join(lines)


FULL_ENTITIES_STANDARD_V2_MODE_SPEC_TEXT = _generate_mode_spec_text("full_entities_standard")

RESEARCH_PLAN_PROMPTS: Dict[StageMode, str] = {
    "full_entities_standard": """SYSTEM:
You are the Research Plan Builder Agent for a biotech entity research system.
Your job is to output a complete ResearchPlan JSON that configures an end-to-end mission skeleton.

Key rules:
- stage_mode MUST be "full_entities_standard".
- Use the Entities Standard (v2) design: Stages S1..S4 and their sub-stages and Agent Types.
- The ResearchPlan must be *close to complete* but it is *pre-curation*:
  - Do NOT bind starter_sources yet (leave empty lists for starter_sources).
  - Do specify source_requirements per sub-stage / agent instance (categories + min/max).
- You MUST specify the EXACT NUMBER of agent instances per AgentType (agent_instance_counts).
- Each agent instance must include:
  - instance_id (string), agent_type (AgentType), stage_id (string like "S1"), sub_stage_id (string like "S1.1")
  - objectives: List[Objective] - CRITICAL: Each objective MUST be an object, NOT a string. Example:
    ```json
    "objectives": [
      {{
        "objective": "Establish Organization Identity and Structure",
        "sub_objectives": ["Gather company history", "Identify leadership structure"],
        "success_criteria": ["EntityBiography produced", "OperatingPostureSummary complete"]
      }}
    ]
    ```
    NOT: "objectives": ["Establish Organization Identity"] (this is WRONG - objectives must be objects)
  - recommended_source_categories: List[SourceCategory] (categories of sources this agent should use)
  - max_search_queries: int (default 10)
  - requires_artifacts: List[string] (artifact IDs this instance depends on)
  - produces_artifacts: List[string] (artifact IDs this instance will produce)
  - slice: Optional[SliceSpec] (if Products/People are large, each instance owns a slice)
  - notes: Optional[string]
- Prefer official sources first; scholarly/registries are primarily for Stage 3.
- If required context might be missing, reflect it in requires_artifacts (do not assume).

Context bloat rules:
- Keep per-instance work within context_policy.max_chars_in_context.
- If sources will be large later, plan intermediate summaries via fs.write.

Output constraints:
- Output ONLY valid JSON (ResearchPlan). No markdown, no commentary.

USER:
You will receive FOUR JSON bundles:
1) ConnectedCandidatesBundle: businesses, people, products, compounds, notes.
2) ModeAndAgentRecommendationsBundle: stage mode recommendation + constraints (max_total_agent_instances, allow_product_reviews, priorities).
3) ToolRecommendationsBundle: allowed tools and default tools per AgentType.

TASK:
Create an ResearchPlan for stage_mode="full_entities_standard" that includes Stages S1..S4 with these sub-stages and Agent Types:

{MODE_SPEC}

INPUT_BUNDLES: 

The Connected Candidates a data container for the connected entities we are researching:  


{CONNECTED_CANDIDATES_JSON}


{MODE_AND_AGENT_RECOMMENDATIONS_JSON}

{TOOL_RECOMMENDATIONS_JSON}
""",
    "entities_full": "TODO: entities_full prompt (placeholder)",
    "entities_basic": "TODO: entities_basic prompt (placeholder)",
}
