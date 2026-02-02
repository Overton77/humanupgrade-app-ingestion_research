from __future__ import annotations

from typing import Any, Dict, Optional
from typing_extensions import NotRequired
from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import before_agent, dynamic_prompt
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

# NOTE: In your project you likely use init_chat_model(...) or your own model objects.
DEFAULT_MODEL = "openai:gpt-4.1"


class WorkerAgentState(AgentState):
    """
    Minimal extension. Keep this small; store big artifacts in files.
    """
    workspace_root: NotRequired[str]
    objective: NotRequired[str]
    seed_context: NotRequired[Dict[str, Any]]
    tool_budget: NotRequired[Dict[str, Any]]


@before_agent(state_schema=WorkerAgentState)
def init_worker_state(state: WorkerAgentState, runtime) -> Optional[Dict[str, Any]]:
    # Good place to enforce that workspace_root is present, etc.
    if not state.get("workspace_root"):
        return {"workspace_root": "agent_outputs/_missing_workspace"}
    return None


@dynamic_prompt
def worker_dynamic_prompt(request) -> str:
    s = request.state
    obj = s.get("objective", "Do the task.")
    root = s.get("workspace_root", "")
    return (
        "You are a research sub-agent.\n"
        f"- Objective: {obj}\n"
        f"- Workspace root: {root}\n"
        "Write key outputs into the workspace as files.\n"
        "Be evidence-anchored. Prefer curated sources.\n"
    )


def build_worker_agent(*, tools: list, model: str = DEFAULT_MODEL):
    """
    Returns a compiled agent graph runnable (LangGraph under the hood).
    """
    middleware = [init_worker_state, worker_dynamic_prompt]
    return create_agent(
        name="research_worker_agent",
        model=model,
        tools=tools,
        middleware=middleware,
        state_schema=WorkerAgentState,
        # You can add checkpointer/store here if you want per-agent persistence.
    )


async def run_worker_once(
    *,
    agent_graph,
    workspace_root: str,
    objective: str,
    seed_context: Dict[str, Any],
    config: RunnableConfig,
) -> Dict[str, Any]:
    """
    Single invocation entrypoint for a worker. The agent itself may loop tool calls.
    """
    init_state: WorkerAgentState = {
        "messages": [HumanMessage(content="Start. Follow your objective exactly.")],
        "workspace_root": workspace_root,
        "objective": objective,
        "seed_context": seed_context,
        "tool_budget": seed_context.get("tool_budget", {}),
    }
    return await agent_graph.ainvoke(init_state, config)
