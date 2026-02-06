from __future__ import annotations

from typing import Any, Dict, Optional, Annotated, List, Union, Callable 
import operator 
from typing_extensions import NotRequired 
from langchain.chat_models import BaseChatModel
from langgraph.store.base import BaseStore
from langgraph.checkpoint.base import BaseCheckpointSaver 
from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import before_agent, dynamic_prompt
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig  
from research_agent.agent_tools.file_system_functions import (
    write_file,
    BASE_DIR,
    read_file_from_mongo_path,
)
from research_agent.human_upgrade.structured_outputs.research_plans_outputs import ( 
    StageMode, 
    AgentType,  
    SubStagePlan,  
    AgentInstancePlanWithSources,  
    Objective, 
    SliceSpec, 
) 
from research_agent.human_upgrade.structured_outputs.file_outputs import ( 
    FileReference 
) 
from langchain.agents.middleware import ( 
    SummarizationMiddleware,   
    AgentMiddleware,
    dynamic_prompt, 
    ModelRequest,  
    before_agent,
    before_model,
    after_model, 
    after_agent, 
)  
from research_agent.human_upgrade.prompts.summary_middleware_prompts import SUMMARY_PROMPT  
from research_agent.human_upgrade.base_models import gpt_5_mini, gpt_5_nano, gpt_5, gpt_4_1
import uuid 
# Default model for worker agents
DEFAULT_MODEL = gpt_5_mini   
from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.tools.utils.agent_workspace_root_helpers import (
    _workspace_root_components,
    _relative_to_base,
    _concat_agent_files,
) 
from research_agent.human_upgrade.graphs.state.agent_instance_state import WorkerAgentState

from research_agent.human_upgrade.prompts.sub_agent_prompt_builders import (  
    INITIAL_PROMPT_BUILDERS, 
    REMINDER_PROMPT_BUILDERS,  
    build_initial_prompt_generic, 
    build_reminder_prompt_generic,
)
from research_agent.human_upgrade.prompts.sub_agent_final_synthesis_prompt_builders import (
    build_final_synthesis_prompt_generic,  
    FINAL_SYNTHESIS_PROMPT_BUILDERS,
)
""" 
AgentInstancePlanWithSources: 
{
    "instance_id": "string",
    "agent_type": "AgentType",
    "stage_id": "string",
    "sub_stage_id": "string",
    "slice": SliceSpec,
    "objectives": [Objective], 
    "starter_sources": [CuratedSource],
    "requires_artifacts": ["string", "..."],
    "produces_artifacts": ["string", "..."],
    "notes": "string" OR null
}


"""

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




async def generate_final_report_text(state: WorkerAgentState) -> str:
    """
    Uses gpt_5 to synthesize a final report from all checkpoint files.
    Returns plain-text report (does NOT write to filesystem).
    """
    plan = state["agent_instance_plan"]
    agent_type = str(getattr(plan, "agent_type", state.get("agent_type", "")))
    file_refs: List[FileReference] = state.get("file_refs", []) or []

    # Concatenate all checkpoint files with metadata 
    # TODO: Make sure read_file inside of _concnat_agent_files works properly with the file path passed in 
    concatenated = await _concat_agent_files(file_refs)
    
    # Get objective text
    objective = ""
    if plan.objectives:
        objective = plan.objectives[0].objective
    else:
        objective = state.get("objective", "Complete the assigned objective.")

    # Get agent-type-specific synthesis prompt builder
    prompt_builder = FINAL_SYNTHESIS_PROMPT_BUILDERS.get(
        agent_type,
        build_final_synthesis_prompt_generic,
    )
    
    # Build the system prompt
    system_prompt = prompt_builder(objective, concatenated, plan)

    # Create agent for final report generation
    final_report_agent = create_agent(
        model=gpt_5,
        system_prompt=system_prompt,
        tools=[], 
        middleware=[],
    )

    # The model already has the inputs in the system prompt.
    # The user message is simply the instruction to produce the report.
    out = await final_report_agent.ainvoke(
        {"messages": [HumanMessage(content="Write the final report now following the requirements exactly.")]},
    ) 

    # Extract text from the response
    # create_agent returns a dict with 'messages' key; last message has the content
    messages = out.get("messages", [])
    if not messages:
        raise ValueError("No messages returned from final report agent")
    
    last_message = messages[-1]
    if hasattr(last_message, "content"):
        return last_message.content
    elif isinstance(last_message, dict):
        return last_message.get("content", "")
    else:
        raise ValueError(f"Unexpected message type: {type(last_message)}") 




async def write_final_report_and_update_state(state: WorkerAgentState, final_text: str) -> Dict[str, Any]:
    """
    Writes final report to filesystem and returns overwrite updates:
      - final_report: FileReference
      - file_refs: append final report ref (as delta)
      - research_notes: append note (as delta)
    
    Uses the write_file API with path components from workspace_root.
    """
    workspace_root = state.get("workspace_root", "")
    plan = state["agent_instance_plan"]
    agent_type = str(getattr(plan, "agent_type", state.get("agent_type", "")))
    instance_id = getattr(plan, "instance_id", "unknown") 

    # mission_id is not on the plan, get it from state
    mission_id = state.get("mission_id", "unknown")
    sub_stage_id = getattr(plan, "sub_stage_id", None) or getattr(plan, "substage_id", "unknown")  
    uuid = uuid.uuid4() 
    
    if not workspace_root:
        raise ValueError("workspace_root is required to write final report")
    
    # Build path components from workspace_root
    root_parts = _workspace_root_components(workspace_root)
    filename = f"final_report_{mission_id}_{sub_stage_id}_{uuid}.txt"
    
    # Write using write_file API with path components
    filepath = await write_file(
        *root_parts,
        filename,
        content=final_text
    )
    
    # Get relative path for state storage (forward slashes for cross-platform)
    relative_path = _relative_to_base(filepath)

    # Create FileReference with new structure
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
        "final_report": ref,          # overwrite
        "file_refs": [ref],           # list delta (for operator.add reducer)
        "research_notes": [note],     # list delta (for operator.add reducer)
    }




@after_agent
async def finalize_agent_instance_after_agent(state: WorkerAgentState, runtime) -> Dict[str, Any] | None:
    """
    Runs once per worker agent invocation, after the agent completes its loop.
    Generates a final synthesized report (gpt_5), writes it to the scoped workspace,
    and updates state.final_report + file_refs + research_notes.
    
    Note: @after_agent receives (state, runtime) parameters. State is the first param,
    runtime is the second. Returns a dict with state updates or None.
    """
    file_refs: List[FileReference] = state.get("file_refs", []) or []
    
    # If no checkpoint files exist, skip synthesis to save GPT-5 credits
    if not file_refs:
        logger.warning("🏁 after_agent: no file_refs found; skipping final report synthesis")
        return {"research_notes": ["WARNING: Agent completed without producing any checkpoint files. No final report generated."]}
    
    # Generate and write final report
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



@before_agent(state_schema=WorkerAgentState)
def init_worker_state(state: WorkerAgentState, runtime) -> Optional[Dict[str, Any]]:
    """
    Runs once per agent invocation.
    - sets the initial prompt latch
    - ensures accumulators exist (optional; reducers handle missing, but helps debugging)
    """
    updates: Dict[str, Any] = {}
    if state.get("_initial_prompt_sent") is None:
        updates["_initial_prompt_sent"] = False
    return updates or None


@dynamic_prompt
def worker_dynamic_prompt(request: ModelRequest) -> str:
    s: WorkerAgentState = request.state
    plan = s["agent_instance_plan"]
    agent_type = plan.agent_type

    if s.get("_initial_prompt_sent") is False:
        fn = INITIAL_PROMPT_BUILDERS.get(agent_type, build_initial_prompt_generic)
        return fn(s)

    fn = REMINDER_PROMPT_BUILDERS.get(agent_type, build_reminder_prompt_generic)
    return fn(s)


@after_model
def latch_initial_prompt_after_first_model(state: WorkerAgentState, runtime) -> Optional[Dict[str, Any]]:
    """
    Flip latch after the first model call so future calls use reminder prompt.
    """
    if state.get("_initial_prompt_sent") is False:
        return {"_initial_prompt_sent": True}
    return None


@after_agent
async def finalize_worker_after_agent(state: WorkerAgentState, runtime) -> Dict[str, Any] | None:
    plan = state["agent_instance_plan"]
    fn = FINALIZE_AFTER_AGENT.get(plan.agent_type)
    if fn is None:
        logger.warning(f"No finalize function for agent_type={plan.agent_type}, skipping")
        return None
    return await fn(state, runtime)


def build_worker_agent(
    *,
    tools: list, 
    agent_type: AgentType, 
    model: BaseChatModel = DEFAULT_MODEL, 
    store: BaseStore | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    extra_middleware: List[AgentMiddleware] | None = None,
):
    """
    Build a compiled worker agent (LangGraph-under-the-hood) with:
      - state schema
      - middleware (init, prompt, latch, finalize)
      - tools
      - optional store/checkpointer
    """
    middleware: List[AgentMiddleware] = [
        init_worker_state,
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


async def run_worker_once(
    *,
    agent_graph,
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
    # Extract objective from plan
    objective = ""
    if agent_instance_plan.objectives:
        objective = agent_instance_plan.objectives[0].objective
    
    # Build seed_context from plan
    seed_context = {
        "slice": agent_instance_plan.slice,
        "starter_sources": agent_instance_plan.starter_sources or [],
        "requires_artifacts": agent_instance_plan.requires_artifacts or [],
        "produces_artifacts": agent_instance_plan.produces_artifacts or [],
        "notes": agent_instance_plan.notes,
    }
    
    init_state: WorkerAgentState = {
        "messages": [],
        "agent_instance_plan": agent_instance_plan, 
        "workspace_root": workspace_root, 
        "agent_type": agent_type,
        "mission_id": mission_id,
        "stage_id": stage_id,
        "sub_stage_id": substage_id,
        "sub_stage_name": substage_name,
        "objective": objective,
        "seed_context": seed_context,
        # reducers: it's fine to omit these, but initializing helps inspection
        "file_refs": [],
        "thoughts": [],
        "research_notes": [],
        "final_report": None,
    }
    return await agent_graph.ainvoke(init_state, config)