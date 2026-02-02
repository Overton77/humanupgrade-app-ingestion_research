from __future__ import annotations

import asyncio
import operator
from typing import Any, Dict, List
from typing_extensions import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from .reducers import merge_dict_of_lists, merge_dict
from .fs import workspace_for
from .tools import TOOL_REGISTRY
from .agent_factory import build_worker_agent, run_worker_once


class AgentInstance(TypedDict):
    instance_id: str
    agent_type: str
    objective: str
    tool_names: List[str]
    seed_context: Dict[str, Any]


class SubStageState(TypedDict, total=False):
    mission_id: str
    stage_id: str
    substage_id: str
    substage_name: str

    instances: List[AgentInstance]

    # fan-in accumulators
    instance_outputs: Annotated[Dict[str, List[Any]], merge_dict_of_lists]
    artifacts: Annotated[Dict[str, Any], merge_dict]
    logs: Annotated[List[str], operator.add]


def _select_tools(tool_names: List[str]):
    tools = []
    for name in tool_names:
        t = TOOL_REGISTRY.get(name)
        if t is not None:
            tools.append(t)
    return tools


async def dispatch_instances_node(state: SubStageState) -> Dict[str, Any]:
    # No-op update; fan-out happens in conditional edge.
    return {"logs": [f"Dispatching {len(state.get('instances', []))} instance(s)."]}


def fanout_to_workers(state: SubStageState):
    instances = state.get("instances", []) or []
    sends: List[Send] = []
    for inst in instances:
        sends.append(
            Send(
                "run_instance",
                {
                    "mission_id": state["mission_id"],
                    "stage_id": state["stage_id"],
                    "substage_id": state["substage_id"],
                    "substage_name": state["substage_name"],
                    "instance": inst,
                },
            )
        )
    return sends


async def run_instance_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """
    Runs exactly one agent instance.
    Concurrency is controlled via a shared semaphore passed in RunnableConfig.configurable.
    """
    sem: asyncio.Semaphore | None = None
    cfg = (config.get("configurable") or {})
    sem = cfg.get("mission_semaphore")

    inst: AgentInstance = state["instance"]

    workspace = workspace_for(
        state["mission_id"],
        state["stage_id"],
        f"{state['substage_id']}_{state['substage_name']}",
        f"{inst['agent_type']}_{inst['instance_id']}",
    )
    workspace_root = str(workspace)

    tools = _select_tools(inst.get("tool_names", []))
    agent_graph = build_worker_agent(tools=tools)

    async def _run():
        out = await run_worker_once(
            agent_graph=agent_graph,
            workspace_root=workspace_root,
            objective=inst["objective"],
            seed_context=inst.get("seed_context", {}),
            config=config,
        )
        return out

    if sem is None:
        out = await _run()
    else:
        async with sem:
            out = await _run()

    # Fan-in: store something lightweight; big content should be written to files by the agent.
    return {
        "instance_outputs": {inst["instance_id"]: [out]},
        "logs": [f"Completed instance={inst['instance_id']} agent_type={inst['agent_type']} workspace={workspace_root}"],
    }


async def substage_reduce_node(state: SubStageState) -> Dict[str, Any]:
    """
    Runs once after all run_instance branches complete (barrier).
    This is where you can:
      - write substage index files
      - compute coverage stats
      - produce a substage summary artifact
    """
    n = len(state.get("instances", []) or [])
    got = sum(len(v) for v in (state.get("instance_outputs") or {}).values())
    return {"logs": [f"Substage reduce: expected={n} outputs_received={got}"]}


def build_substage_graph():
    builder = StateGraph(SubStageState)

    builder.add_node("dispatch", dispatch_instances_node)
    builder.add_node("run_instance", run_instance_node)
    builder.add_node("reduce", substage_reduce_node)

    builder.add_edge(START, "dispatch")
    builder.add_conditional_edges("dispatch", fanout_to_workers, ["run_instance"])
    builder.add_edge("run_instance", "reduce")
    builder.add_edge("reduce", END)

    return builder.compile()
