from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from research_agent.structured_outputs.research_plans_outputs import (
    ResearchMissionPlanFinal,
    StagePlan,
    SubStagePlan,
    AgentInstancePlanWithSources,
    InstanceOutputRequirement,
)

from research_agent.mission_queue.schemas import MissionDAG, TaskDefinition, TaskType


# -----------------------------
# Deterministic Task ID builders
# -----------------------------

def task_id_instance_run(mission_id: str, instance_id: str) -> str:
    return f"instance::{mission_id}::{instance_id}"


def task_id_substage_reduce(mission_id: str, stage_id: str, sub_stage_id: str) -> str:
    return f"substage_reduce::{mission_id}::{stage_id}::{sub_stage_id}"


def task_key_instance(mission_id: str, instance: AgentInstancePlanWithSources) -> str:
    return f"instance:{mission_id}:{instance.stage_id}:{instance.sub_stage_id}:{instance.instance_id}"


def task_key_substage_reduce(mission_id: str, stage_id: str, sub_stage_id: str) -> str:
    return f"substage_reduce:{mission_id}:{stage_id}:{sub_stage_id}"


# -----------------------------
# Helpers to index plan contents
# -----------------------------

def _index_instances(plan: ResearchMissionPlanFinal) -> Dict[str, AgentInstancePlanWithSources]:
    by_id: Dict[str, AgentInstancePlanWithSources] = {}
    for inst in plan.agent_instances:
        by_id[inst.instance_id] = inst
    return by_id


def _index_substages(plan: ResearchMissionPlanFinal) -> Dict[Tuple[str, str], SubStagePlan]:
    """
    Returns {(stage_id, sub_stage_id): SubStagePlan}
    """
    out: Dict[Tuple[str, str], SubStagePlan] = {}
    for st in plan.stages:
        for ss in st.sub_stages:
            out[(st.stage_id, ss.sub_stage_id)] = ss
    return out


def _stage_by_id(plan: ResearchMissionPlanFinal) -> Dict[str, StagePlan]:
    return {st.stage_id: st for st in plan.stages}


# -----------------------------
# Edge building utilities
# -----------------------------

def _add_edge(
    dependents: Dict[str, List[str]],
    parents: Dict[str, List[str]],
    parent_task_id: str,
    child_task_id: str,
) -> None:
    dependents.setdefault(parent_task_id, []).append(child_task_id)
    parents.setdefault(child_task_id, []).append(parent_task_id)


def _compute_deps_remaining(
    tasks: Dict[str, TaskDefinition],
    parents: Dict[str, List[str]],
) -> Dict[str, int]:
    deps_remaining: Dict[str, int] = {}
    for tid in tasks.keys():
        deps_remaining[tid] = len(parents.get(tid, []))
    return deps_remaining


# -----------------------------
# Main builder
# -----------------------------

def build_mission_dag(plan: ResearchMissionPlanFinal) -> MissionDAG:
    """
    Build a DAG from ResearchMissionPlanFinal with these task types:
      - INSTANCE_RUN (one per agent instance in plan.agent_instances)
      - SUBSTAGE_REDUCE (one per substage in plan.stages[].sub_stages[])

    Dependencies implemented now:
      1) Structural:
         - substage depends_on_substages: dep's SUBSTAGE_REDUCE -> this substage's tasks
         - stage depends_on_stages: dep stage's all SUBSTAGE_REDUCE -> this stage's substages (conservative)
      2) Fan-in:
         - each INSTANCE_RUN in a substage -> SUBSTAGE_REDUCE(substage)
      3) Temporary explicit instance-output deps:
         - requires_instance_output: from_instance INSTANCE_RUN -> this INSTANCE_RUN

    NOTE:
      - We are NOT implementing requires_artifacts/produces_artifacts yet.
    """
    mission_id = plan.mission_id

    instances_by_id = _index_instances(plan)
    substages_by_key = _index_substages(plan)
    stages_by_id = _stage_by_id(plan)

    tasks: Dict[str, TaskDefinition] = {}
    dependents: Dict[str, List[str]] = {}
    parents: Dict[str, List[str]] = {}

    # 1) Create INSTANCE_RUN tasks
    for inst in plan.agent_instances:
        tid = task_id_instance_run(mission_id, inst.instance_id)
        tasks[tid] = TaskDefinition(
            task_id=tid,
            mission_id=mission_id,
            task_type=TaskType.INSTANCE_RUN,
            task_key=task_key_instance(mission_id, inst),
            inputs={
                # Keep minimal routing inputs. Scheduler/worker can load full plan later if desired.
                "instance_id": inst.instance_id,
                "agent_type": inst.agent_type,
                "stage_id": inst.stage_id,
                "sub_stage_id": inst.sub_stage_id,
            },
            metadata={
                "plan_ref": {"mission_id": mission_id},  # placeholder for later Mongo refs
            },
        )

    # 2) Create SUBSTAGE_REDUCE tasks
    for st in plan.stages:
        for ss in st.sub_stages:
            tid = task_id_substage_reduce(mission_id, st.stage_id, ss.sub_stage_id)
            tasks[tid] = TaskDefinition(
                task_id=tid,
                mission_id=mission_id,
                task_type=TaskType.SUBSTAGE_REDUCE,
                task_key=task_key_substage_reduce(mission_id, st.stage_id, ss.sub_stage_id),
                inputs={
                    "stage_id": st.stage_id,
                    "sub_stage_id": ss.sub_stage_id,
                    "instance_ids": list(ss.agent_instances or []),
                },
                metadata={},
            )

    # 3) Fan-in: INSTANCE_RUN -> SUBSTAGE_REDUCE for each instance in substage
    for st in plan.stages:
        for ss in st.sub_stages:
            reduce_tid = task_id_substage_reduce(mission_id, st.stage_id, ss.sub_stage_id)
            for instance_id in ss.agent_instances or []:
                inst_tid = task_id_instance_run(mission_id, instance_id)
                if inst_tid not in tasks:
                    raise ValueError(
                        f"Substage references instance_id={instance_id} but it was not found in plan.agent_instances"
                    )
                _add_edge(dependents, parents, inst_tid, reduce_tid)

    # 4) Substage dependency edges (depends_on_substages)
    #
    # Conservative rule for now:
    #   dep_substage_reduce -> (all instance tasks in this substage) AND -> this substage reduce
    #
    # This ensures nothing in SS runs until dependent substage has fully reduced.
    for st in plan.stages:
        for ss in st.sub_stages:
            this_reduce_tid = task_id_substage_reduce(mission_id, st.stage_id, ss.sub_stage_id)
            for dep_sub_id in ss.depends_on_substages or []:
                dep_key = (st.stage_id, dep_sub_id)
                if dep_key not in substages_by_key:
                    raise ValueError(
                        f"Substage dependency refers to sub_stage_id={dep_sub_id} "
                        f"but it was not found in stage_id={st.stage_id}"
                    )
                dep_reduce_tid = task_id_substage_reduce(mission_id, st.stage_id, dep_sub_id)

                # Gate all instance runs in this substage
                for instance_id in ss.agent_instances or []:
                    inst_tid = task_id_instance_run(mission_id, instance_id)
                    _add_edge(dependents, parents, dep_reduce_tid, inst_tid)

                # Also gate the reduce itself (redundant but harmless)
                _add_edge(dependents, parents, dep_reduce_tid, this_reduce_tid)

    # 5) Stage dependency edges (depends_on_stages)
    #
    # Conservative rule for now:
    #   ALL reduces in dep stage gate ALL instances in this stage + all reduces in this stage.
    #
    # This aligns with your current mission-level sequential selection behavior.
    for st in plan.stages:
        for dep_stage_id in st.depends_on_stages or []:
            if dep_stage_id not in stages_by_id:
                raise ValueError(
                    f"Stage dependency refers to stage_id={dep_stage_id} but it was not found in plan.stages"
                )
            dep_stage = stages_by_id[dep_stage_id]

            dep_reduce_tids = [
                task_id_substage_reduce(mission_id, dep_stage.stage_id, dep_ss.sub_stage_id)
                for dep_ss in dep_stage.sub_stages
            ]

            # Gate all instances and reduces in this stage on completion of dep stage substages.
            for ss in st.sub_stages:
                this_reduce_tid = task_id_substage_reduce(mission_id, st.stage_id, ss.sub_stage_id)

                for dep_reduce_tid in dep_reduce_tids:
                    # gate reduces
                    _add_edge(dependents, parents, dep_reduce_tid, this_reduce_tid)

                    # gate all instances in this stage substage
                    for instance_id in ss.agent_instances or []:
                        inst_tid = task_id_instance_run(mission_id, instance_id)
                        _add_edge(dependents, parents, dep_reduce_tid, inst_tid)

    # 6) Temporary explicit instance-output dependencies:
    #    requires_instance_output: from_instance INSTANCE_RUN -> this INSTANCE_RUN
    #
    # NOTE: Your field name is requires_instance_output (singular) but holds a list.
    for inst in plan.agent_instances:
        reqs: List[InstanceOutputRequirement] = getattr(inst, "requires_instance_output", []) or []
        if not reqs:
            continue

        consumer_tid = task_id_instance_run(mission_id, inst.instance_id)

        for req in reqs:
            if not req.required:
                # Optional deps are ignored for gating in this initial version.
                continue
            if req.output_type != "final_report":
                raise ValueError(
                    f"Unsupported InstanceOutputRequirement.output_type={req.output_type} "
                    f"for consumer instance_id={inst.instance_id}. Only 'final_report' supported."
                )

            producer_instance_id = req.from_instance_id
            if producer_instance_id not in instances_by_id:
                raise ValueError(
                    f"InstanceOutputRequirement refers to from_instance_id={producer_instance_id} "
                    f"but it was not found in plan.agent_instances"
                )

            producer_tid = task_id_instance_run(mission_id, producer_instance_id)
            _add_edge(dependents, parents, producer_tid, consumer_tid)

    # 7) Compute deps_remaining and initial ready tasks
    deps_remaining = _compute_deps_remaining(tasks, parents)
    initial_ready = [tid for tid, n in deps_remaining.items() if n == 0]

    return MissionDAG(
        mission_id=mission_id,
        tasks=tasks,
        deps_remaining=deps_remaining,
        dependents=dependents,
        parents=parents,
        initial_ready=sorted(initial_ready),
    )


# -----------------------------
# Optional: Debug printing helper
# -----------------------------

def format_dag_summary(dag: MissionDAG, max_ready: int = 20) -> str:
    s = dag.summarize()
    lines = [
        f"MissionDAG mission_id={s['mission_id']}",
        f"  tasks={s['num_tasks']} edges={s['num_edges']}",
        f"  by_type={s['by_type']}",
        f"  initial_ready={s['initial_ready']} (showing up to {max_ready})",
    ]
    for tid in dag.initial_ready[:max_ready]:
        t = dag.tasks[tid]
        lines.append(f"    - {t.task_type.value} {t.task_key}")
    return "\n".join(lines)