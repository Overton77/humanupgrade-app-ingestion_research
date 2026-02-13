from __future__ import annotations

from typing import Any, Dict, Optional, Annotated, List, Union, Callable
import operator
import uuid

from typing_extensions import NotRequired

from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain.chat_models import BaseChatModel

from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.checkpoint.base import BaseCheckpointSaver

from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import (
    SummarizationMiddleware,
    AgentMiddleware,
    dynamic_prompt,
    ModelRequest,
    after_model,
    after_agent,
)

from research_agent.agent_tools.file_system_functions import write_file
from research_agent.structured_outputs.research_plans_outputs import (
    StageMode,
    AgentType,
    SubStagePlan,
    AgentInstancePlanWithSources,
    Objective,
    SliceSpec,
)
from research_agent.structured_outputs.file_outputs import FileReference
from research_agent.prompts.summary_middleware_prompts import SUMMARY_PROMPT
from research_agent.infrastructure.llm.base_models import gpt_5_mini, gpt_5_nano, gpt_5, gpt_4_1
from research_agent.utils.logger import logger

from research_agent.tools.utils.agent_workspace_root_helpers import (
    _workspace_root_components,
    _relative_to_base,
    _concat_agent_files,
)

from research_agent.graphs.state.agent_instance_state import WorkerAgentState

from research_agent.prompts.sub_agent_prompt_builders import (
    INITIAL_PROMPT_BUILDERS,
    REMINDER_PROMPT_BUILDERS,
    build_initial_prompt,
    build_reminder_prompt,
)
from research_agent.prompts.sub_agent_final_synthesis_prompt_builders import (
    build_final_synthesis_prompt_generic,
    FINAL_SYNTHESIS_PROMPT_BUILDERS,
)

# Default model for worker agents
DEFAULT_MODEL = gpt_5_mini

CONTEXT_WINDOW_TRIGGER_TOKENS = 170_000
SUMMARIZATION_KEEP_TOKENS = 30_000
TRIM_TOKENS_TO_SUMMARIZE = 12_000

summarizer: AgentMiddleware = SummarizationMiddleware(
    model=gpt_4_1,
    trigger=[("tokens", CONTEXT_WINDOW_TRIGGER_TOKENS)],
    keep=("tokens", SUMMARIZATION_KEEP_TOKENS),
    summary_prompt=SUMMARY_PROMPT,
    trim_tokens_to_summarize=TRIM_TOKENS_TO_SUMMARIZE,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _group_sources(starter_sources: Optional[List[Any]]) -> Dict[str, List[str]]:
    """
    Group starter sources by category -> list[url].
    Safe for CuratedSource pydantic models or dicts.
    """
    out: Dict[str, List[str]] = {}
    for s in (starter_sources or []):
        try:
            if isinstance(s, dict):
                url = (s.get("url") or "").strip()
                cat = (s.get("category") or "unknown").strip()
            else:
                url = (getattr(s, "url", "") or "").strip()
                cat = (getattr(s, "category", None) or "unknown")
                cat = str(cat).strip()
            if not url:
                continue
            out.setdefault(cat or "unknown", []).append(url)
        except Exception:
            continue
    return out


# -----------------------------------------------------------------------------
# Final report synthesis (after_agent)
# -----------------------------------------------------------------------------

async def generate_final_report_text(state: WorkerAgentState) -> str:
    """
    Uses gpt_5 to synthesize a final report from all checkpoint files.
    Returns plain-text report (does NOT write to filesystem).
    """
    plan = state["agent_instance_plan"]
    agent_type = str(getattr(plan, "agent_type", state.get("agent_type", "")))
    file_refs: List[FileReference] = state.get("file_refs", []) or []

    concatenated = await _concat_agent_files(file_refs)

    if plan.objectives:
        objective = plan.objectives[0].objective
    else:
        objective = state.get("objective", "Complete the assigned objective.")

    prompt_builder = FINAL_SYNTHESIS_PROMPT_BUILDERS.get(
        agent_type,
        build_final_synthesis_prompt_generic,
    )

    system_prompt = prompt_builder(objective, concatenated, plan)

    final_report_agent = create_agent(
        model=gpt_5,
        system_prompt=system_prompt,
        tools=[],
        middleware=[],
    )

    out = await final_report_agent.ainvoke(
        {"messages": [HumanMessage(content="Write the final report now following the requirements exactly.")]},
    )

    messages = out.get("messages", [])
    if not messages:
        raise ValueError("No messages returned from final report agent")

    last_message = messages[-1]
    # Use .text property which automatically extracts text from string or list content
    if hasattr(last_message, "text"):
        return last_message.text
    # Fallback for dict messages
    if isinstance(last_message, dict):
        content = last_message.get("content", "")
        return str(content) if content else ""
    raise ValueError(f"Unexpected message type: {type(last_message)}")


async def write_final_report_and_update_state(state: WorkerAgentState, final_text: str) -> Dict[str, Any]:
    """
    Writes final report to filesystem and returns overwrite updates:
      - final_report: FileReference
      - file_refs: append final report ref (as delta)
      - research_notes: append note (as delta)
    """
    workspace_root = state.get("workspace_root", "")
    plan = state["agent_instance_plan"]
    agent_type = str(getattr(plan, "agent_type", state.get("agent_type", "")))
    instance_id = getattr(plan, "instance_id", "unknown")

    mission_id = state.get("mission_id", "unknown")
    sub_stage_id = getattr(plan, "sub_stage_id", None) or getattr(plan, "substage_id", "unknown")
    uuid_str = str(uuid.uuid4())

    if not workspace_root:
        raise ValueError("workspace_root is required to write final report")

    root_parts = _workspace_root_components(workspace_root)
    filename = f"final_report_{mission_id}_{sub_stage_id}_{uuid_str}.txt"

    filepath = await write_file(*root_parts, filename, content=final_text)
    relative_path = _relative_to_base(filepath)

    ref = FileReference(
        file_path=relative_path,
        agent_type=agent_type,
        description=(
            f"FINAL synthesized report for {agent_type} instance {instance_id}. "
            f"Synthesizes all checkpoint reports from this agent instance."
        ),
        source=instance_id,
    )

    note = f"Wrote final report: {relative_path}"

    return {
        "final_report": ref,
        "file_refs": [ref],
        "research_notes": [note],
    }


async def finalize_agent_instance_after_agent(state: WorkerAgentState, runtime) -> Dict[str, Any] | None:
    file_refs: List[FileReference] = state.get("file_refs", []) or []
    if not file_refs:
        logger.warning("🏁 after_agent: no file_refs found; skipping final report synthesis")
        return {"research_notes": ["WARNING: Agent completed without producing any checkpoint files. No final report generated."]}

    logger.info("🏁 after_agent: generating final synthesized report (gpt_5)")
    try:
        final_text = await generate_final_report_text(state)
        updates = await write_final_report_and_update_state(state, final_text)
        logger.info(f"✅ after_agent: final report written at {updates['final_report'].file_path}")
        return updates
    except Exception as e:
        logger.exception("❌ after_agent: failed to generate final report")
        return {"research_notes": [f"ERROR: Failed to generate final report: {str(e)}"]}


FINALIZE_AFTER_AGENT: Dict[str, Callable[[WorkerAgentState, Any], Any]] = {
    "BusinessIdentityAndLeadershipAgent": finalize_agent_instance_after_agent,
    "PersonBioAndAffiliationsAgent": finalize_agent_instance_after_agent,
    "EcosystemMapperAgent": finalize_agent_instance_after_agent,
    "ProductSpecAgent": finalize_agent_instance_after_agent,
    "CaseStudyHarvestAgent": finalize_agent_instance_after_agent,
}


# -----------------------------------------------------------------------------
# Dynamic prompt: INITIAL on first model call, REMINDER thereafter
# -----------------------------------------------------------------------------

@dynamic_prompt
def worker_dynamic_prompt(request: ModelRequest) -> str:
    """
    This MUST provide the system prompt the model sees.

    Correct behavior:
    - First model call: return the INITIAL prompt (big system prompt).
    - Later calls: return the REMINDER prompt (state-aware, includes ledger/telemetry/missing_fields/etc).

    We deliberately do NOT inject the full initial prompt as a HumanMessage, because the system prompt
    is the right channel + avoids the “only saw the small HumanMessage” failure mode.
    """
    s: WorkerAgentState = request.state
    plan = s["agent_instance_plan"]
    agent_type = str(getattr(plan, "agent_type", s.get("agent_type", "")))

    if s.get("_initial_prompt_sent") is True:
        fn = REMINDER_PROMPT_BUILDERS.get(agent_type, build_reminder_prompt)
        return fn(s)

    fn = INITIAL_PROMPT_BUILDERS.get(agent_type, build_initial_prompt)
    return fn(s)


@after_model
def latch_initial_prompt_after_first_model(state: WorkerAgentState, runtime) -> Optional[Dict[str, Any]]:
    """
    Flip latch after the first model call so subsequent calls use reminder prompt.
    """
    if state.get("_initial_prompt_sent") is False:
        return {"_initial_prompt_sent": True}
    return None


@after_agent
async def finalize_worker_after_agent(state: WorkerAgentState, runtime) -> Dict[str, Any] | None:
    plan = state["agent_instance_plan"]
    agent_type = str(getattr(plan, "agent_type", state.get("agent_type", "")))
    fn = FINALIZE_AFTER_AGENT.get(agent_type)
    if fn is None:
        logger.warning(f"No finalize function for agent_type={agent_type}, skipping")
        return None
    return await fn(state, runtime)


# -----------------------------------------------------------------------------
# Build worker agent
# -----------------------------------------------------------------------------

def build_worker_agent(
    *,
    tools: List[BaseTool],
    agent_type: AgentType,
    model: BaseChatModel = DEFAULT_MODEL,
    store: BaseStore | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    extra_middleware: List[AgentMiddleware] | None = None,
):
    middleware: List[AgentMiddleware] = [
        worker_dynamic_prompt,
        latch_initial_prompt_after_first_model,
        summarizer,
        finalize_worker_after_agent,
    ]
    if extra_middleware:
        middleware = [*middleware, *extra_middleware]

    return create_agent(
        name=f"{agent_type}",
        model=model,
        tools=tools,
        middleware=middleware,
        state_schema=WorkerAgentState,
        store=store,
        checkpointer=checkpointer,
    )


# -----------------------------------------------------------------------------
# Run worker once
# -----------------------------------------------------------------------------

async def run_worker_once(
    *,
    agent_graph: CompiledStateGraph[WorkerAgentState, Any, Any, Any],
    agent_instance_plan: AgentInstancePlanWithSources,
    workspace_root: str,
    agent_type: AgentType,
    mission_id: str,
    stage_id: str,
    substage_id: str,
    substage_name: str = "",
    config: RunnableConfig,
) -> Dict[str, Any]:
    """
    Single invocation entrypoint for a worker.
    The agent itself may do many tool calls internally.
    """

    objective = ""
    success_criteria: List[str] = []
    sub_objectives: List[str] = []

    if agent_instance_plan.objectives:
        objective = agent_instance_plan.objectives[0].objective
        success_criteria = list(agent_instance_plan.objectives[0].success_criteria or [])
        sub_objectives = list(agent_instance_plan.objectives[0].sub_objectives or [])

    seed_context = {
        "slice": agent_instance_plan.slice,
        "starter_sources": agent_instance_plan.starter_sources or [],
        "starter_sources_by_category": _group_sources(agent_instance_plan.starter_sources),
        "objective": objective,
        "success_criteria": success_criteria,
        "sub_objectives": sub_objectives,
        "requires_artifacts": agent_instance_plan.requires_artifacts or [],
        "produces_artifacts": agent_instance_plan.produces_artifacts or [],
        "notes": agent_instance_plan.notes,
    }

    # IMPORTANT:
    # - We keep the initial messages minimal.
    # - The FULL initial instructions come from worker_dynamic_prompt (system prompt) on the first model call.
    init_state: WorkerAgentState = {
        "messages": [HumanMessage(content="Begin. Follow the system instructions exactly.")],
        "agent_instance_plan": agent_instance_plan,
        "workspace_root": workspace_root,
        "agent_type": agent_type,
        "mission_id": mission_id,
        "stage_id": stage_id,
        "sub_stage_id": substage_id,
        "sub_stage_name": substage_name,
        "objective": objective,
        "seed_context": seed_context,
        "file_refs": [],
        "thoughts": [],
        "research_notes": [],
        "final_report": None,
        "_initial_prompt_sent": False,

        # telemetry/control-plane defaults (match your updated WorkerAgentState)
        "steps_taken": 0,
        "checkpoint_count": 0,
        "tool_counts": {},
        "missing_fields": [],
        "visited_urls": [],
        # reminder convenience
        "last_checkpoint_path": "",
    }

    return await agent_graph.ainvoke(init_state, config)


# =============================================================================
# Test script for single agent instance
# =============================================================================

if __name__ == "__main__":
    import asyncio
    from research_agent.structured_outputs.research_plans_outputs import AgentInstancePlanWithSources
    from research_agent.utils.research_tools_map import RESEARCH_TOOLS_MAP
    from research_agent.utils.default_tools_by_agent_type import FULL_ENTITIES_BASIC_DEFAULT_TOOL_MAP
    from research_agent.tools.utils.agent_workspace_root_helpers import workspace_root_for

    FIRST_AGENT_INSTANCE_JSON = {
        "instance_id": "BusinessIdentityAndLeadershipAgent:S1:S1.1:single",
        "agent_type": "BusinessIdentityAndLeadershipAgent",
        "stage_id": "S1",
        "sub_stage_id": "S1.1",
        "slice": None,
        "objectives": [
            {
                "objective": "Compile authoritative entity biography and corporate identity about One Thousand Roads the biotech product company",
                "sub_objectives": [
                    "Identify canonical domain(s) and official product/catalog pages",
                    "Extract About/Founders content and corporate timeline",
                    "Produce a high-level operating posture summary",
                    "About One Thousand Roads the biotech product company",
                ],
                "success_criteria": [
                    "EntityBiography artifact with canonicalName, domains, and top official pages",
                    "HighLevelTimeline covering founding and product launches (when available)",
                    "OperatingPostureSummary describing product focus and market claims",
                    "About One Thousand Roads the biotech product company",
                ],
            }
        ],
        "starter_sources": [
            {"url": "https://www.onethousandroads.com/", "category": "official_home", "title": None, "notes": None, "language": "en"},
            {"url": "https://www.onethousandroads.com/pages/about-us", "category": "official_leadership", "title": None, "notes": None, "language": "en"},
            {"url": "https://www.onethousandroads.com/pages/shop", "category": "official_products", "title": None, "notes": None, "language": "en"},
            {"url": "https://www.onethousandroads.com/pages/ewot-research", "category": "official_research", "title": None, "notes": None, "language": "en"},
            {"url": "https://help.onethousandroads.com/", "category": "official_help_center", "title": None, "notes": None, "language": "en"},
            {"url": "https://www.onethousandroads.com/pages/product-warranty", "category": "official_docs_manuals", "title": None, "notes": None, "language": "en"},
        ],
        "starter_inputs": "One Thousand Roads the biotech product company with base domain:  https://www.onethousandroads.com/",
        "requires_artifacts": ["seed_business_name"],
        "produces_artifacts": ["EntityBiography", "OperatingPostureSummary", "HighLevelTimeline", "ProductList"],
        "notes": "Single instance to establish canonical company-level identity from official pages.",
    }

    def _select_tools(tool_names: List[str]) -> List[Any]:
        tools = []
        for name in tool_names:
            tool = RESEARCH_TOOLS_MAP.get(name)
            if tool is not None:
                tools.append(tool)
        return tools

    def tools_for_agent_type(tool_map: dict[str, list[str]], agent_type: str) -> List[Any]:
        tool_names = tool_map.get(agent_type, []) or []
        return _select_tools(tool_names)

    async def test_single_agent():
        instance_plan = AgentInstancePlanWithSources.model_validate(FIRST_AGENT_INSTANCE_JSON)

        mission_id = "mission_onethousandroads_001"
        stage_id = instance_plan.stage_id
        sub_stage_id = instance_plan.sub_stage_id
        agent_type = instance_plan.agent_type
        instance_id = instance_plan.instance_id

        workspace_root = workspace_root_for(
            mission_id,
            stage_id,
            f"{sub_stage_id}_test",
            f"{agent_type}_{instance_id}",
        )

        tools = tools_for_agent_type(FULL_ENTITIES_BASIC_DEFAULT_TOOL_MAP, agent_type)
        logger.info(f"Loaded {len(tools)} tools for {agent_type}")

        agent_graph = build_worker_agent(
            tools=tools,
            agent_type=agent_type,
            store=None,
            checkpointer=None,
        )

        config: RunnableConfig = {
            "configurable": {
                "thread_id": f"test__{instance_id}",
                "mission_id": mission_id,
                "stage_id": stage_id,
                "sub_stage_id": sub_stage_id,
                "instance_id": instance_id,
            }
        }

        logger.info(f"🚀 Starting test run for {agent_type} instance: {instance_id}")
        logger.info(f"   Workspace: {workspace_root}")

        result = await run_worker_once(
            agent_graph=agent_graph,
            agent_instance_plan=instance_plan,
            workspace_root=workspace_root,
            agent_type=agent_type,
            mission_id=mission_id,
            stage_id=stage_id,
            substage_id=sub_stage_id,
            substage_name="Organization Identity & Structure",
            config=config,
        )

        logger.info("✅ Agent run completed successfully")
        logger.info(f"   File refs: {len(result.get('file_refs', []))}")
        logger.info(f"   Research notes: {len(result.get('research_notes', []))}")
        if result.get("final_report"):
            logger.info(f"   Final report: {result['final_report']}")
        return result

    asyncio.run(test_single_agent())
