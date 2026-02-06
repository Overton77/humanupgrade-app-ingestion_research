from research_agent.human_upgrade.structured_outputs.research_plans_outputs import StagePlan, SubStagePlan, ResearchMissionPlanFinal, AgentInstancePlanWithSources 
from typing import List, Dict, Any, Set  

def _stage_id(stage: StagePlan) -> str:
    return getattr(stage, "id", None) or getattr(stage, "stage_id")

def _stage_name(stage: StagePlan) -> str:
    return getattr(stage, "name", "")

def _stage_substages(stage: StagePlan) -> List[SubStagePlan]:
    return getattr(stage, "sub_stages", None) or getattr(stage, "sub_stages", None) or getattr(stage, "substages", None) or []

def _substage_id(ss: SubStagePlan) -> str:
    return getattr(ss, "id", None) or getattr(ss, "sub_stage_id") or getattr(ss, "substage_id")

def _substage_name(ss: SubStagePlan) -> str:
    return getattr(ss, "name", "")

def _substage_depends_on(ss: SubStagePlan) -> List[str]:
    # your JSON uses depends_on_substages
    return getattr(ss, "depends_on_substages", None) or getattr(ss, "depends_on", None) or []

def _substage_instance_ids(ss: SubStagePlan) -> List[str]:
    return getattr(ss, "agent_instances", None) or getattr(ss, "instance_ids", None) or []


def _instances_for_substage(plan: ResearchMissionPlanFinal, stage_id: str, substage_id: str) -> List[AgentInstancePlanWithSources]:
    """
    Resolve AgentInstancePlans from plan.agent_instances for a given (stage_id, substage_id).
    Returns the actual AgentInstancePlanWithSources objects (Pydantic models).
    """
    from research_agent.human_upgrade.structured_outputs.research_plans_outputs import AgentInstancePlanWithSources
    
    all_instances = getattr(plan, "agent_instances", []) or []
    out: List[AgentInstancePlanWithSources] = []

    for inst in all_instances:
        inst_stage_id = getattr(inst, "stage_id", None)
        inst_substage_id = getattr(inst, "sub_stage_id", None) or getattr(inst, "substage_id", None)

        if inst_stage_id != stage_id or inst_substage_id != substage_id:
            continue

        # Return the actual Pydantic object
        out.append(inst)

    return out


def _select_next_substage(stage: StagePlan, done: Set[str]) -> SubStagePlan | None:
    """
    Dependency-aware selection within a stage.
    Stays sequential but respects depends_on_substages for correctness.
    """
    for ss in _stage_substages(stage):
        sid = _substage_id(ss)
        if sid in done:
            continue
        deps = _substage_depends_on(ss)
        if all(d in done for d in deps):
            return ss
    return None