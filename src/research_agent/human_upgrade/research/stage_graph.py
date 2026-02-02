from __future__ import annotations

import operator
from typing import Any, Dict, List
from typing_extensions import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END

from .models import ResearchPlan, StagePlan, SubStagePlan
from .reducers import merge_dict, merge_dict_of_lists
from .substage_graph import build_substage_graph


class StageState(TypedDict, total=False):
    plan: ResearchPlan
    mission_id: str
    stage_id: str
    stage_name: str

    # stage-level fan-in
    substages_completed: Annotated[List[str], operator.add]
    artifacts: Annotated[Dict[str, Any], merge_dict]
    logs: Annotated[List[str], operator.add]

    # (optional) keep per-substage outputs lightweight
    substage_outputs: Annotated[Dict[str, List[Any]], merge_dict_of_lists]


def _substage_node_name(sub: SubStagePlan) -> str:
    return f"substage__{sub.id.replace('.', '_')}"


def build_stage_subgraph(stage: StagePlan):
    substage_graph = build_substage_graph()

    builder = StateGraph(StageState)

    # Create one node per substage (static DAG for this stage)
    for sub in stage.substages:

        async def run_substage_node(state: StageState, config: RunnableConfig, sub=sub) -> Dict[str, Any]:
            # Build instances list from planner outputs:
            instances = []
            for agent_cfg in sub.agents:
                for i in range(agent_cfg.count):
                    instances.append(
                        {
                            "instance_id": f"{agent_cfg.agent_type}_{i+1}",
                            "agent_type": agent_cfg.agent_type,
                            "objective": " | ".join(agent_cfg.objectives) or f"Execute {agent_cfg.agent_type}",
                            "tool_names": agent_cfg.tool_names,
                            "seed_context": {
                                "connected": state["plan"].connected.model_dump(),
                                "curated_sources": [ss.model_dump() for ss in state["plan"].curated_sources],
                                "source_set_ids": agent_cfg.source_set_ids,
                                "slice_on": agent_cfg.slice_on,
                                "slice_ids": agent_cfg.slice_ids,
                                "tool_budget": {},
                                "stage_id": state["stage_id"],
                                "substage_id": sub.id,
                                "substage_name": sub.name,
                            },
                        }
                    )

            # Invoke substage graph (fan-out/fan-in inside)
            out = await substage_graph.ainvoke(
                {
                    "mission_id": state["mission_id"],
                    "stage_id": state["stage_id"],
                    "substage_id": sub.id,
                    "substage_name": sub.name,
                    "instances": instances,
                    "instance_outputs": {},
                    "artifacts": {},
                    "logs": [],
                },
                config,
            )

            return {
                "substages_completed": [sub.id],
                "substage_outputs": {sub.id: [out]},
                "logs": [f"Substage done: {sub.id} {sub.name}"],
            }

        builder.add_node(_substage_node_name(sub), run_substage_node)

    async def finalize_stage_node(state: StageState) -> Dict[str, Any]:
        return {
            "logs": [f"Stage finalize: {state['stage_id']} completed_substages={state.get('substages_completed', [])}"]
        }

    builder.add_node("finalize_stage", finalize_stage_node)

    # Wire dependencies:
    # START -> substages with no deps
    # dep_substage -> substage
    # all substages -> finalize_stage (barrier)
    if not stage.substages:
        builder.add_edge(START, "finalize_stage")
        builder.add_edge("finalize_stage", END)
        return builder.compile()

    # Entry edges
    for sub in stage.substages:
        if not sub.depends_on:
            builder.add_edge(START, _substage_node_name(sub))

    # Dependency edges
    by_id = {s.id: s for s in stage.substages}
    for sub in stage.substages:
        for dep in sub.depends_on:
            if dep not in by_id:
                raise ValueError(f"Substage {sub.id} depends_on unknown substage id={dep}")
            builder.add_edge(_substage_node_name(by_id[dep]), _substage_node_name(sub))

    # Fan-in barrier: finalize runs once after all substages finish
    for sub in stage.substages:
        builder.add_edge(_substage_node_name(sub), "finalize_stage")

    builder.add_edge("finalize_stage", END)
    return builder.compile()
