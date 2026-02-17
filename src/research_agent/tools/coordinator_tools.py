"""Tools specifically designed for the Coordinator Agent.

These tools help the coordinator agent collaborate with research administrators
to design and create research plans.
"""

from langchain.tools import tool, ToolRuntime 
from typing import List, Optional, Annotated
from datetime import datetime
import json

from research_agent.structured_outputs.simplified_research_plan import (
    SimplifiedResearchPlan,
    Stage,
    SubStage,
    AgentInstance,
    ResearchObjective,
    BudgetConstraints,
)


@tool(
    description=(
        "Create a research plan after discussing with the research administrator. "
        "This plan outlines stages, substages, agent instances, objectives, and estimates. "
        "The plan will be presented to the administrator for review and approval."
    ),
    parse_docstring=False,
)
async def create_research_plan(
    runtime: ToolRuntime,
    mission_title: Annotated[str, "Brief, descriptive title for this research mission"],
    mission_description: Annotated[str, "Clear overview of what we're researching and why"],
    target_entities: Annotated[
        List[str],
        "List of entities to research (companies, products, people, topics)"
    ],
    research_objectives: Annotated[
        str,
        "JSON string of research objectives array. Each objective should have: objective (str), rationale (str), success_criteria (list[str])"
    ],
    stages: Annotated[
        str,
        "JSON string of stages array. Each stage should have: name, description, substages (array), stage_objectives (array). "
        "Each substage should have: name, description, agent_instances (array), can_run_parallel (bool), estimated_duration (str). "
        "Each agent_instance should have: agent_name, purpose, target_entities (array), key_questions (array), estimated_cost (str)"
    ],
    max_budget_usd: Annotated[
        Optional[float],
        "Maximum budget in USD (omit or set to null for no hard limit)"
    ] = None,
    max_duration_hours: Annotated[
        Optional[float],
        "Maximum duration in hours (omit or set to null for no hard limit)"
    ] = None,
    priority: Annotated[
        str,
        "Optimization priority: 'speed', 'cost', 'depth', or 'balanced'"
    ] = "balanced",
    budget_notes: Annotated[
        Optional[str],
        "Additional budget notes or considerations"
    ] = None,
    estimated_total_cost: Annotated[
        Optional[str],
        "Estimated total cost for entire plan (e.g., '$50-75', 'low', 'medium')"
    ] = None,
    estimated_total_duration: Annotated[
        Optional[str],
        "Estimated total duration (e.g., '2-3 hours', '1 day')"
    ] = None,
    run_immediately_if_approved: Annotated[
        bool,
        "If approved by administrator, whether to run immediately or wait for explicit trigger"
    ] = False,
    notes: Annotated[
        Optional[str],
        "Additional notes, caveats, or considerations about this plan"
    ] = None,
) -> str:
    """Create a research plan for administrator review and approval."""
    
    try:
        # Parse JSON strings
        objectives_data = json.loads(research_objectives)
        stages_data = json.loads(stages)
        
        # Get thread_id from runtime config
        thread_id = runtime.config.get("configurable", {}).get("thread_id", "unknown")
        
        # Build research objectives
        objectives = [
            ResearchObjective(
                objective=obj["objective"],
                rationale=obj["rationale"],
                success_criteria=obj.get("success_criteria", [])
            )
            for obj in objectives_data
        ]
        
        # Build stages
        stage_objects = []
        for stage_data in stages_data:
            substage_objects = []
            for substage_data in stage_data.get("substages", []):
                agent_objects = [
                    AgentInstance(
                        agent_name=agent["agent_name"],
                        purpose=agent["purpose"],
                        target_entities=agent.get("target_entities", []),
                        key_questions=agent.get("key_questions", []),
                        estimated_cost=agent.get("estimated_cost")
                    )
                    for agent in substage_data.get("agent_instances", [])
                ]
                
                substage_objects.append(
                    SubStage(
                        name=substage_data["name"],
                        description=substage_data["description"],
                        agent_instances=agent_objects,
                        can_run_parallel=substage_data.get("can_run_parallel", True),
                        estimated_duration=substage_data.get("estimated_duration")
                    )
                )
            
            stage_objects.append(
                Stage(
                    name=stage_data["name"],
                    description=stage_data["description"],
                    substages=substage_objects,
                    stage_objectives=stage_data.get("stage_objectives", [])
                )
            )
        
        # Build budget constraints
        budget = BudgetConstraints(
            max_budget_usd=max_budget_usd,
            max_duration_hours=max_duration_hours,
            priority=priority,
            notes=budget_notes
        )
        
        # Create the plan
        plan = SimplifiedResearchPlan(
            mission_title=mission_title,
            mission_description=mission_description,
            target_entities=target_entities,
            research_objectives=objectives,
            budget_constraints=budget,
            stages=stage_objects,
            estimated_total_cost=estimated_total_cost,
            estimated_total_duration=estimated_total_duration,
            requires_approval=True,
            run_immediately_if_approved=run_immediately_if_approved,
            notes=notes
        )
        
        # Generate unique plan ID: sanitized_mission_title:thread_id
        sanitized_title = mission_title.lower().replace(" ", "_")[:50]  # Limit length
        plan_id = f"{sanitized_title}:{thread_id}"
        
        # Write plan to state using runtime
        current_plans = dict(runtime.state.get("research_plans") or {})
        current_plans[plan_id] = plan
        
        # Update state with the new plan
        runtime.state["research_plans"] = current_plans
        runtime.state["last_plan_id"] = plan_id
        
        # Format output for administrator review
        output = [
            "=" * 80,
            "RESEARCH PLAN CREATED",
            "=" * 80,
            "",
            f"Title: {plan.mission_title}",
            f"Description: {plan.mission_description}",
            "",
            f"Target Entities: {', '.join(plan.target_entities)}",
            "",
            "RESEARCH OBJECTIVES:",
            ""
        ]
        
        for i, obj in enumerate(plan.research_objectives, 1):
            output.append(f"{i}. {obj.objective}")
            output.append(f"   Rationale: {obj.rationale}")
            if obj.success_criteria:
                output.append(f"   Success Criteria: {', '.join(obj.success_criteria)}")
            output.append("")
        
        output.extend([
            "BUDGET & CONSTRAINTS:",
            f"  Max Budget: ${plan.budget_constraints.max_budget_usd}" if plan.budget_constraints.max_budget_usd else "  Max Budget: No hard limit",
            f"  Max Duration: {plan.budget_constraints.max_duration_hours} hours" if plan.budget_constraints.max_duration_hours else "  Max Duration: No hard limit",
            f"  Priority: {plan.budget_constraints.priority}",
            ""
        ])
        
        if plan.budget_constraints.notes:
            output.append(f"  Notes: {plan.budget_constraints.notes}")
            output.append("")
        
        output.extend([
            "RESEARCH STAGES:",
            ""
        ])
        
        for stage_num, stage in enumerate(plan.stages, 1):
            output.append(f"Stage {stage_num}: {stage.name}")
            output.append(f"  Description: {stage.description}")
            if stage.stage_objectives:
                output.append(f"  Objectives: {', '.join(stage.stage_objectives)}")
            output.append("")
            
            for substage_num, substage in enumerate(stage.substages, 1):
                output.append(f"  Substage {stage_num}.{substage_num}: {substage.name}")
                output.append(f"    Description: {substage.description}")
                output.append(f"    Parallel Execution: {'Yes' if substage.can_run_parallel else 'No'}")
                if substage.estimated_duration:
                    output.append(f"    Estimated Duration: {substage.estimated_duration}")
                output.append("")
                
                for agent_num, agent in enumerate(substage.agent_instances, 1):
                    output.append(f"    Agent {stage_num}.{substage_num}.{agent_num}: {agent.agent_name}")
                    output.append(f"      Purpose: {agent.purpose}")
                    if agent.target_entities:
                        output.append(f"      Targets: {', '.join(agent.target_entities)}")
                    if agent.key_questions:
                        output.append(f"      Key Questions:")
                        for q in agent.key_questions:
                            output.append(f"        - {q}")
                    if agent.estimated_cost:
                        output.append(f"      Estimated Cost: {agent.estimated_cost}")
                    output.append("")
        
        output.extend([
            "OVERALL ESTIMATES:",
            f"  Total Cost: {plan.estimated_total_cost or 'TBD'}",
            f"  Total Duration: {plan.estimated_total_duration or 'TBD'}",
            "",
            f"Run Immediately if Approved: {'Yes' if plan.run_immediately_if_approved else 'No'}",
            ""
        ])
        
        if plan.notes:
            output.extend([
                "ADDITIONAL NOTES:",
                plan.notes,
                ""
            ])
        
        output.extend([
            "=" * 80,
            "STATUS: AWAITING ADMINISTRATOR APPROVAL",
            "=" * 80,
            "",
            "The research administrator will now review this plan and either:",
            "  1. Approve it (optionally with modifications)",
            "  2. Request revisions",
            "  3. Reject it",
            "",
            f"Plan ID: {plan_id}",
            f"Thread ID: {thread_id}",
            f"Created: {plan.created_at.isoformat()}",
            "",
            "Note: This plan has been saved to the conversation state and can be",
            "referenced or modified in future messages.",
        ])
        
        return "\n".join(output)
        
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse JSON data. {str(e)}\n\nPlease ensure research_objectives and stages are valid JSON strings."
    except Exception as e:
        return f"Error creating research plan: {str(e)}\n\nPlease check your inputs and try again."


@tool(
    description=(
        "Retrieve a previously created research plan from the conversation state. "
        "Use this to review, reference, or discuss a plan that was created earlier."
    ),
    parse_docstring=False,
)
async def get_research_plan(
    runtime: ToolRuntime,
    plan_id: Annotated[
        Optional[str],
        "Plan ID to retrieve (format: 'mission_title:thread_id'). If omitted, retrieves the most recently created plan."
    ] = None,
) -> str:
    """Retrieve a research plan from state."""
    
    try:
        research_plans = runtime.state.get("research_plans", {})
        
        if not research_plans:
            return "No research plans have been created in this conversation yet."
        
        # If no plan_id provided, get the last created plan
        if plan_id is None:
            plan_id = runtime.state.get("last_plan_id")
            if not plan_id:
                return "No research plans found in state."
        
        # Retrieve the plan
        plan = research_plans.get(plan_id)
        
        if not plan:
            available_ids = list(research_plans.keys())
            return (
                f"Plan '{plan_id}' not found.\n\n"
                f"Available plan IDs in this conversation:\n" +
                "\n".join(f"  - {pid}" for pid in available_ids)
            )
        
        # Format the plan for display
        output = [
            "=" * 80,
            "RESEARCH PLAN RETRIEVED",
            "=" * 80,
            "",
            f"Plan ID: {plan_id}",
            f"Title: {plan.mission_title}",
            f"Description: {plan.mission_description}",
            "",
            f"Status: {'AWAITING APPROVAL' if plan.requires_approval else 'APPROVED'}",
            f"Created: {plan.created_at.isoformat()}",
            "",
            f"Target Entities: {', '.join(plan.target_entities)}",
            "",
            "RESEARCH OBJECTIVES:",
            ""
        ]
        
        for i, obj in enumerate(plan.research_objectives, 1):
            output.append(f"{i}. {obj.objective}")
            output.append(f"   Rationale: {obj.rationale}")
            if obj.success_criteria:
                output.append(f"   Success Criteria: {', '.join(obj.success_criteria)}")
            output.append("")
        
        output.extend([
            "BUDGET & CONSTRAINTS:",
            f"  Max Budget: ${plan.budget_constraints.max_budget_usd}" if plan.budget_constraints.max_budget_usd else "  Max Budget: No hard limit",
            f"  Max Duration: {plan.budget_constraints.max_duration_hours} hours" if plan.budget_constraints.max_duration_hours else "  Max Duration: No hard limit",
            f"  Priority: {plan.budget_constraints.priority}",
            "",
        ])
        
        output.extend([
            f"RESEARCH STAGES: ({len(plan.stages)} stages)",
            ""
        ])
        
        for stage_num, stage in enumerate(plan.stages, 1):
            total_agents = sum(len(substage.agent_instances) for substage in stage.substages)
            output.append(f"Stage {stage_num}: {stage.name} ({len(stage.substages)} substages, {total_agents} agents)")
            
        output.extend([
            "",
            "ESTIMATES:",
            f"  Total Cost: {plan.estimated_total_cost or 'TBD'}",
            f"  Total Duration: {plan.estimated_total_duration or 'TBD'}",
            "",
            "Use the plan_id above to reference this specific plan in future conversations.",
        ])
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error retrieving research plan: {str(e)}"


@tool(
    description="List all research plans created in this conversation.",
    parse_docstring=False,
)
async def list_research_plans(runtime: ToolRuntime) -> str:
    """List all research plans in the conversation state."""
    
    try:
        research_plans = runtime.state.get("research_plans", {})
        
        if not research_plans:
            return "No research plans have been created in this conversation yet."
        
        output = [
            "=" * 80,
            "RESEARCH PLANS IN THIS CONVERSATION",
            "=" * 80,
            "",
            f"Total Plans: {len(research_plans)}",
            ""
        ]
        
        for plan_id, plan in research_plans.items():
            status = "AWAITING APPROVAL" if plan.requires_approval else "APPROVED"
            output.extend([
                f"Plan ID: {plan_id}",
                f"  Title: {plan.mission_title}",
                f"  Status: {status}",
                f"  Entities: {', '.join(plan.target_entities[:3])}{'...' if len(plan.target_entities) > 3 else ''}",
                f"  Stages: {len(plan.stages)}",
                f"  Created: {plan.created_at.isoformat()}",
                ""
            ])
        
        output.append("Use get_research_plan with a plan_id to view full details.")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error listing research plans: {str(e)}"
