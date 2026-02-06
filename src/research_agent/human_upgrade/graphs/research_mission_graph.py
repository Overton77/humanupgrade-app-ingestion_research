from __future__ import annotations

import asyncio
import operator
from typing import Any, Dict, List, Set, Union, Optional

from langgraph.graph.state import CompiledStateGraph
from typing_extensions import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END

from research_agent.human_upgrade.structured_outputs.research_plans_outputs import (
    ResearchMissionPlanFinal,
    StagePlan,
)
from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference

from research_agent.human_upgrade.graphs.reducers.reducers import merge_dict, union_sets, merge_dict_of_latest
from research_agent.human_upgrade.graphs.stage_graph import build_stage_subgraph
from research_agent.human_upgrade.graphs.outputs.stage_output import StageOutput
from research_agent.human_upgrade.graphs.outputs.mission_output import MissionOutput


MissionOutputItem = Union[FileReference, str]




class ResearchMissionState(TypedDict, total=False):
    plan: ResearchMissionPlanFinal
    mission_id: str

    # progress
    stages_done: Annotated[Set[str], union_sets]

    # outputs
    logs: Annotated[List[str], operator.add] 

    default_semaphore: Optional[int] = None   
    stage_outputs: Annotated[
        Dict[str, StageOutput],
        merge_dict_of_latest
    ]

    # mission_id -> MissionOutput
    mission_output: Annotated[
        Dict[str, MissionOutput],
        merge_dict_of_latest
    ]

    # 🔑 pluck-anything-by-key
    output_registry: Annotated[
        Dict[str, object],
        merge_dict_of_latest
    ]

    


async def init_mission_node(state: ResearchMissionState) -> ResearchMissionState:
    plan = state["plan"]
    mode = getattr(plan, "stage_mode", None) or getattr(plan, "mode", None)
    return {
        "mission_id": plan.mission_id,
        "stages_done": set(),
        "stage_outputs": {},
        "mission_output": {},
        "output_registry": {},
        "logs": [f"Init mission: {plan.mission_id} mode={mode} stages={len(plan.stages)}"],
    }


def _select_next_stage(plan: ResearchMissionPlanFinal, done: Set[str]) -> StagePlan | None:
    for st in plan.stages:
        # NOTE: align with your StagePlan fields (stage_id / depends_on_stages)
        sid = getattr(st, "stage_id", None) or getattr(st, "id", None)
        deps = getattr(st, "depends_on_stages", None) or getattr(st, "depends_on", None) or []
        if sid in done:
            continue
        if all(dep in done for dep in deps):
            return st
    return None


def build_mission_graph(plan: ResearchMissionPlanFinal, config: RunnableConfig) -> CompiledStateGraph:
    """
    START -> init -> run_stages -> end -> END
    """
    builder = StateGraph(ResearchMissionState)

    builder.add_node("init", init_mission_node)

    # Build stage subgraphs once
    stage_graphs: Dict[str, Any] = {}
    for st in plan.stages:
        sid = getattr(st, "stage_id", None) or getattr(st, "id", None)
        stage_graphs[sid] = build_stage_subgraph(st)

    async def run_stages_node(state: ResearchMissionState, config: RunnableConfig) -> Dict[str, Any]:
        plan_: ResearchMissionPlanFinal = state["plan"]

        done: Set[str] = set(state.get("stages_done") or set())
        logs: List[str] = []  

        



        while True:
            nxt = _select_next_stage(plan_, done)
            if nxt is None:
                remaining = [
                    (getattr(st, "stage_id", None) or getattr(st, "id", None))
                    for st in plan_.stages
                    if (getattr(st, "stage_id", None) or getattr(st, "id", None)) not in done
                ]
                if remaining:
                    logs.append(f"Stage dependency deadlock. Remaining: {remaining} done={sorted(done)}")
                else:
                    logs.append("All stages completed.")
                break

            stage_id = getattr(nxt, "stage_id", None) or getattr(nxt, "id", None)
            stage_name = getattr(nxt, "name", None) or ""

            sg = stage_graphs[stage_id]
            logs.append(f"Running stage {stage_id} {stage_name}")

            out = await sg.ainvoke(
                {
                    "plan": plan_,
                    "mission_id": state["mission_id"],
                    "stage_id": stage_id,
                    "stage_name": stage_name,
                    "stage_plan": nxt,
                    "default_semaphore": state.get("default_semaphore", 3),
                    # stage-level accumulators
                    "substages_done": set(),
                    "logs": [],
                   
                    "substage_outputs": {},
                    "stage_output": {},
                },
                config,
            )

            done.add(stage_id) 

            stage_outputs = state.get("stage_outputs", {})   
            stage_outputs.update(out.get("stage_output", {}))    


             
            # logs
            logs.append(f"Stage done: {stage_id} {stage_name}")
            logs.extend(out.get("logs") or []) 

        mission_output = MissionOutput( 
            mission_id=state["mission_id"], 
            stages=stage_outputs, 
        )

        return {
            "stages_done": done,
            "stage_outputs": stage_outputs, 
            "mission_output": {state["mission_id"]: mission_output},  
            "output_registry": { 
                f"mission:{state['mission_id']}": mission_output, 
            },
            "logs": logs,
        }

    builder.add_node("run_stages", run_stages_node)
    builder.add_node("end", lambda state: {"logs": [f"Mission complete: {state['mission_id']}"]})

    builder.add_edge(START, "init")
    builder.add_edge("init", "run_stages")
    builder.add_edge("run_stages", "end")
    builder.add_edge("end", END)

    return builder.compile()


