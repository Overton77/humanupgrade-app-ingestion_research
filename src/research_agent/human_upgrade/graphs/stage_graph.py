from __future__ import annotations

import operator
from typing import Any, Dict, List, Set, Union, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import Annotated, TypedDict

from research_agent.human_upgrade.structured_outputs.research_plans_outputs import (
    ResearchMissionPlanFinal,
    StagePlan,
    SubStagePlan,
)
from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference

from research_agent.human_upgrade.graphs.utils.stage_graphs_helpers import (
    _select_next_substage,
    _substage_id,
    _substage_name,
    _stage_substages,
    _instances_for_substage,
)
from research_agent.human_upgrade.graphs.reducers.reducers import merge_dict, union_sets, merge_dict_of_latest
from research_agent.human_upgrade.graphs.sub_stage_graph import build_substage_graph
from research_agent.human_upgrade.graphs.outputs.substage_output import SubStageOutput
from research_agent.human_upgrade.graphs.outputs.stage_output import StageOutput

# -----------------------------------------------------------------------------
# Stage State
# -----------------------------------------------------------------------------

StageOutputItem = Union[FileReference, str]



class StageState(TypedDict, total=False):
    plan: ResearchMissionPlanFinal
    mission_id: str

    stage_id: str
    stage_name: str
    stage_plan: StagePlan

    # progress
    substages_done: Annotated[Set[str], union_sets]

    default_semaphore: Optional[int] = None
  
    logs: Annotated[List[str], operator.add] 

    substage_outputs: Annotated[
        Dict[str, SubStageOutput],
        merge_dict_of_latest
    ]

    # stage_id -> StageOutput
    stage_output: Annotated[
        Dict[str, StageOutput],
        merge_dict_of_latest
    ]  

   



async def init_stage_node(state: StageState) -> Dict[str, Any]:
    return {
        "substages_done": set(),
        "substage_outputs": {},
        "stage_output": {},
        "logs": [f"Init stage: {state['stage_id']} {state.get('stage_name','')}"],
        # do not wipe artifacts / outputs / substage_outputs (they come from mission)
    }


def build_stage_subgraph(stage_plan: StagePlan) -> CompiledStateGraph:
    """
    Stage subgraph:
      START -> init -> run_substages -> END

    run_substages loops sequentially through substages, invoking substage graph each time.
    """
    builder = StateGraph(StageState)

    builder.add_node("init", init_stage_node)

    # Compiled once; parameterized by input state each invoke
    substage_graph = build_substage_graph()

    async def run_substages_node(state: StageState, config: RunnableConfig) -> Dict[str, Any]:
        plan: ResearchMissionPlanFinal = state["plan"]
        stage_id = state["stage_id"]

        done: Set[str] = set(state.get("substages_done") or set())
        logs: List[str] = []

        # carry-through accumulators
        
        substage_outputs: Dict[str, SubStageOutput] = state.get("substage_outputs", {}) 

        while True:
            nxt: SubStagePlan | None = _select_next_substage(stage_plan, done)
            if nxt is None:
                remaining = [
                    _substage_id(ss)
                    for ss in _stage_substages(stage_plan)
                    if _substage_id(ss) not in done
                ]
                if remaining:
                    logs.append(
                        f"Substage dependency deadlock in stage={stage_id}. "
                        f"remaining={remaining} done={sorted(done)}"
                    )
                else:
                    logs.append(f"All substages completed for stage={stage_id}.")
                break

            sub_id = _substage_id(nxt)
            sub_name = _substage_name(nxt)

            logs.append(f"Running substage {sub_id} {sub_name}")

            instances = _instances_for_substage(plan, stage_id=stage_id, substage_id=sub_id)

            out = await substage_graph.ainvoke(
                {
                    "mission_id": state["mission_id"],
                    "stage_id": stage_id,
                    "stage_plan": stage_plan,
                    "substage_id": sub_id,
                    "substage_name": sub_name,
                    "substage_plan": nxt,
                    "instances": instances, 
                    "default_semaphore": state.get("default_semaphore", 3),  
                    "instance_outputs": {}, 
                    "logs": [],
                    "substage_output": {},
                },
                config,
            )

            # mark done
            done.add(sub_id) 

            substage_outputs = state.get("substage_outputs", {})   

            substage_outputs.update(out.get("substage_output", {}))   



            # logs
            logs.append(f"Substage done: {sub_id} {sub_name}")
            logs.extend(out.get("logs") or [])  

        
        stage_output = StageOutput( 
            stage_id=stage_id,  
            stage_name=state.get("stage_name", ""), 
            substages=substage_outputs, 
        )
        return {
            "substages_done": done,
            "substage_outputs": substage_outputs,  
            "stage_output": {stage_id: stage_output},   
            "output_registry": { 
                f"stage:{state['mission_id']}:{stage_id}": stage_output, 
            },
            "logs": logs,
        }

    builder.add_node("run_substages", run_substages_node)

    builder.add_edge(START, "init")
    builder.add_edge("init", "run_substages")
    builder.add_edge("run_substages", END)

    return builder.compile()
