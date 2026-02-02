from __future__ import annotations

import asyncio
import operator
from typing import Any, Dict, List, Set, Literal
from typing_extensions import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from .models import ResearchPlan, StagePlan
from .reducers import merge_dict, union_sets
from .stage_graph import build_stage_subgraph


class MissionState(TypedDict, total=False):
    plan: ResearchPlan
    mission_id: str

    # progress
    stages_done: Annotated[Set[str], union_sets]
    logs: Annotated[List[str], operator.add]
    artifacts: Annotated[Dict[str, Any], merge_dict]


async def init_mission_node(state: MissionState) -> Dict[str, Any]:
    plan = state["plan"]
    return {
        "mission_id": plan.mission_id,
        "stages_done": set(),
        "logs": [f"Init mission: {plan.mission_id} mode={plan.mode} stages={len(plan.stages)}"],
    }


def _stage_node_name(stage: StagePlan) -> str:
    return f"stage__{stage.id}"


def _select_next_stage(plan: ResearchPlan, done: Set[str]) -> StagePlan | None:
    """
    Select next runnable stage whose deps are satisfied.
    This enables parallel stages if multiple deps satisfied.
    We'll route one-at-a-time via Command for clarity.
    """
    for st in plan.stages:
        if st.id in done:
            continue
        if all(dep in done for dep in st.depends_on):
            return st
    return None


async def route_next_stage_node(state: MissionState) -> Command[Literal["end"] | str]:
    plan = state["plan"]
    done = state.get("stages_done") or set()
    nxt = _select_next_stage(plan, done)
    if nxt is None:
        return Command(update={"logs": ["No more runnable stages."]}, goto="end")

    goto = _stage_node_name(nxt)
    return Command(
        update={"logs": [f"Routing to stage {nxt.id} {nxt.name}"]},
        goto=goto,
    )


def build_mission_graph(plan: ResearchPlan):
    builder = StateGraph(MissionState)

    builder.add_node("init", init_mission_node)
    builder.add_node("route", route_next_stage_node)
    builder.add_node("end", lambda state: {"logs": [f"Mission complete: {state['mission_id']}"]})

    # Add each stage as a node by embedding its compiled stage subgraph
    stage_subgraphs: Dict[str, Any] = {}
    for stage in plan.stages:
        stage_subgraphs[stage.id] = build_stage_subgraph(stage)

        async def run_stage_node(state: MissionState, config: RunnableConfig, stage=stage) -> Dict[str, Any]:
            sg = stage_subgraphs[stage.id]
            out = await sg.ainvoke(
                {
                    "plan": state["plan"],
                    "mission_id": state["mission_id"],
                    "stage_id": stage.id,
                    "stage_name": stage.name,
                    "substages_completed": [],
                    "artifacts": {},
                    "logs": [],
                    "substage_outputs": {},
                },
                config,
            )
            return {
                "stages_done": {stage.id},
                "logs": [f"Stage done: {stage.id} {stage.name}"] + (out.get("logs") or []),
            }

        builder.add_node(_stage_node_name(stage), run_stage_node)

    # Wiring:
    builder.add_edge(START, "init")
    builder.add_edge("init", "route")

    # Each stage node goes back to route (Command node decides next)
    for stage in plan.stages:
        builder.add_edge(_stage_node_name(stage), "route")

    builder.add_edge("route", "end")
    builder.add_edge("end", END)

    return builder.compile()


async def run_mission(plan: ResearchPlan):
    """
    Orchestration entrypoint: creates one mission semaphore controlling all worker instances.
    """
    # Global concurrency limiter across the whole mission:
    mission_semaphore = asyncio.Semaphore(8)  # tune this (web calls, CPU, etc.)

    graph = build_mission_graph(plan)
    cfg: RunnableConfig = {"configurable": {"mission_semaphore": mission_semaphore}}

    out = await graph.ainvoke({"plan": plan}, cfg)
    return out
