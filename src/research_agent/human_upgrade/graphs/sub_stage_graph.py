from __future__ import annotations

import asyncio
import operator
from typing import Any, Dict, List, Optional, Union

from research_agent.human_upgrade.graphs.outputs.agent_instance_output import AgentInstanceOutput
from research_agent.human_upgrade.graphs.outputs.substage_output import SubStageOutput
from typing_extensions import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from research_agent.human_upgrade.utils.research_tools_map import RESEARCH_TOOLS_MAP
from research_agent.human_upgrade.utils.default_tools_by_agent_type import (
    FULL_ENTITIES_BASIC_DEFAULT_TOOL_MAP,
)
from research_agent.human_upgrade.structured_outputs.research_plans_outputs import (
    AgentInstancePlanWithSources,
    StagePlan,
    SubStagePlan, 
    StageMode, 
    AgentType, 
)
from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference 
from research_agent.human_upgrade.base_models import gpt_5_mini

from research_agent.human_upgrade.graphs.reducers.reducers import merge_dict_of_lists, merge_dict, merge_dict_of_latest 
from research_agent.human_upgrade.tools.utils.agent_workspace_root_helpers import workspace_for
from research_agent.human_upgrade.graphs.agent_instance_factory import build_worker_agent, run_worker_once


# =============================================================================
# SubStage State
# =============================================================================

SubStageOutputItem = Union[FileReference, str]


class SubStageState(TypedDict, total=False):
    # identity / routing
    mission_id: str

    stage_id: str
    stage_plan: StagePlan 
    stage_mode: StageMode 

    substage_id: str
    substage_name: str
    substage_plan: SubStagePlan

    # work items
    instances: List[AgentInstancePlanWithSources] 

    instance_outputs: Annotated[Dict[str, AgentInstanceOutput], merge_dict_of_latest]  

    substage_output: Annotated[Dict[str, SubStageOutput], merge_dict_of_latest]



    logs: Annotated[List[str], operator.add]

    # NEW: global “substage produced outputs” accumulator (append-only)
    # outputs: Annotated[List[SubStageOutputItem], operator.add]    
    # Agent instance id will be unique, sub stage id will be unique so we don't need another 
    # append only accumulator of everything we just need to save results and turn results into 
    # vector store documents and API DB storage calls. 


    default_semaphore: Optional[int] = None 

   


# =============================================================================
# Tools helpers
# =============================================================================

def _select_tools(tool_names: List[str]) -> List[Any]:
    tools: List[Any] = []
    for name in tool_names:
        tool = RESEARCH_TOOLS_MAP.get(name)
        if tool is not None:
            tools.append(tool)
    return tools


def tools_for_agent_type(tool_map: dict[str, list[str]], agent_type: str) -> List[Any]:
    tool_names = tool_map.get(agent_type, []) or []
    return _select_tools(tool_names)


# =============================================================================
# Nodes
# =============================================================================

async def dispatch_instances_node(state: SubStageState) -> Dict[str, Any]:
    instances = state.get("instances") or []
    sub_id = state.get("substage_id", "")
    sub_name = state.get("substage_name", "")
    return {"logs": [f"Dispatching {len(instances)} instance(s) for {sub_id} {sub_name}."]}


def fanout_to_workers(state: SubStageState) -> List[Send]:
    instances = state.get("instances") or []
    sends: List[Send] = []

    for inst in instances:
        sends.append(
            Send(
                "run_instance",
                {
                    # identity
                    "mission_id": state["mission_id"],
                    "stage_id": state["stage_id"],
                    "substage_id": state["substage_id"],
                    "substage_name": state["substage_name"],
                    # plans (optional but very useful for downstream prompts/debugging)
                    "stage_plan": state.get("stage_plan"),
                    "substage_plan": state.get("substage_plan"),
                    # instance
                    "instance": inst,
                    # carry shared artifacts down (baseline)
                    "artifacts": state.get("artifacts") or {},
                },
            )
        )
    return sends


async def run_instance_node(state: SubStageState, config: RunnableConfig, store: BaseStore | None = None, checkpointer: BaseCheckpointSaver | None = None) -> SubStageState:
    """
    Runs exactly one agent instance.
    Uses the new sub_agent_factory interface:
      - state passed to worker includes agent_instance_plan + workspace_root
    """
    cfg = config.get("configurable") or {} 

    # TODO: Can you serialize a semaphore ? 
    sem: asyncio.Semaphore | None = None   
    if state.get("default_semaphore") is not None:
        sem = asyncio.Semaphore(state["default_semaphore"]) 

    inst: AgentInstancePlanWithSources = state["instance"] 

    agent_type: AgentType = inst.agent_type

    workspace = workspace_for(
        state["mission_id"],
        state["stage_id"],
        f"{state['substage_id']}_{state['substage_name']}",
        f"{inst.agent_type}_{inst.instance_id}",
    )
    workspace_root = str(workspace)

    tools = tools_for_agent_type(FULL_ENTITIES_BASIC_DEFAULT_TOOL_MAP, inst.agent_type)
    agent_graph = build_worker_agent(tools=tools,agent_type=agent_type, model=gpt_5_mini, store=store if store else None, checkpointer=checkpointer if checkpointer else None) 



    async def _run():
        return await run_worker_once(
            agent_graph=agent_graph,
            agent_instance_plan=inst,
            workspace_root=workspace_root,
            mission_id=state["mission_id"],
            stage_id=state["stage_id"],
            substage_id=state["substage_id"],
            substage_name=state.get("substage_name", ""),
            config=config,
        )

    if sem is None:
        out = await _run()
    else:
        async with sem:
            out = await _run()

     
    return {
        "instance_outputs": {
            inst.instance_id: AgentInstanceOutput(
                instance_id=inst.instance_id,
                agent_type=inst.agent_type,
                final_report=out.get("final_report", None),
                file_refs=out.get("file_refs", []),
                workspace_root=workspace_root,
            )
        },
    "logs": [
        f"Completed instance={inst.instance_id} agent_type={inst.agent_type}"
    ],
}



async def substage_reduce_node(state: SubStageState) -> SubStageState: 
    """ 
    
    Reduces the instance outputs into a substage output. 
    """
    sub_id = state["substage_id"]
    sub_name = state["substage_name"]

    instance_outputs = state.get("instance_outputs", {})

    substage_output = SubStageOutput(
        substage_id=sub_id,
        substage_name=sub_name,
        instance_ids=list(instance_outputs.keys()),
        instance_outputs=instance_outputs,
    )

    mission_id = state["mission_id"]
    stage_id = state["stage_id"]

    registry_updates = {
        f"substage:{mission_id}:{stage_id}:{sub_id}": substage_output,
        **{
            f"instance:{mission_id}:{stage_id}:{sub_id}:{iid}": inst_out
            for iid, inst_out in instance_outputs.items()
        },
    }

    return {
        "substage_output": {sub_id: substage_output},
        "output_registry": registry_updates,
        "logs": [f"Reduced substage {sub_id} with {len(instance_outputs)} instances"],
    }

def build_substage_graph():
    builder = StateGraph(SubStageState)

    builder.add_node("dispatch", dispatch_instances_node)
    builder.add_node("run_instance", run_instance_node)
    builder.add_node("reduce", substage_reduce_node)

    builder.add_edge(START, "dispatch")
    builder.add_conditional_edges("dispatch", fanout_to_workers, ["run_instance"])  
    # I am not sure if this go to node is needed here. It is part of the Send API 
    builder.add_edge("run_instance", "reduce")
    builder.add_edge("reduce", END)

    return builder.compile()