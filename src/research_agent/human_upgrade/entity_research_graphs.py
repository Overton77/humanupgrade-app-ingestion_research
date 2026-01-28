"""
Entity Intelligence Research Graphs - Three-Tier Architecture

This module implements a hierarchical LangGraph system for entity research:

1. BundlesParentGraph (Top Level)
   - Orchestrates research across multiple entity bundles
   - Iterates through bundle list and invokes BundleResearchSubGraph for each

2. BundleResearchSubGraph (Middle Level)
   - Handles research for a single bundle (e.g., one podcast episode)
   - Iterates through research directions (GUEST, BUSINESS, PRODUCT, COMPOUND, PLATFORM)
   - Invokes ResearchDirectionSubGraph for each direction

3. ResearchDirectionSubGraph (Leaf Level)
   - Performs actual research for one direction (e.g., GUEST research)
   - Generates todos, uses LLM + tools loop, synthesizes final report
   - Uses ToolNode for tool execution (web search, file operations, todo management)

Graph Compilation Order:
   ResearchDirectionSubGraph → BundleResearchSubGraph → BundlesParentGraph
   (innermost first, then middle, then outermost)
"""


from langgraph.graph import StateGraph, START, END   
from langgraph.store.base import BaseStore
from langgraph.checkpoint.base import BaseCheckpointSaver 
from langchain_core.runnables import RunnableConfig

from research_agent.human_upgrade.persistence.checkpointer_and_store import get_persistence   

from langgraph.graph.state import CompiledStateGraph 
from langchain.tools import BaseTool 
from typing_extensions import TypedDict, Annotated  
from typing import List, Dict, Any, Optional, Literal, Union
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, ToolMessage, AnyMessage, AIMessage
from pydantic import BaseModel, Field  
import operator   
from langchain.agents import create_agent, AgentState  
from datetime import datetime 
from dotenv import load_dotenv 
from langchain.agents.structured_output import ProviderStrategy 
from research_agent.human_upgrade.structured_outputs.enums_literals import DirectionType
from research_agent.human_upgrade.structured_outputs.research_direction_outputs import EntityBundleDirectionsFinal
 

from research_agent.human_upgrade.tools.think_tool import think_tool 
from research_agent.human_upgrade.prompts.research_prompt_builders import ( 
    _recent_file_refs,
    _recent_thought,
    get_initial_research_prompt,
    get_reminder_research_prompt,
) 
from research_agent.human_upgrade.utils.formatting import _concat_direction_files
from research_agent.agent_tools.file_system_functions import (
        write_file,
        sanitize_path_component,
        BASE_DIR,
    )
   

from research_agent.human_upgrade.structured_outputs.file_outputs import ( 
    FileReference
)  


from research_agent.human_upgrade.prompts.synthesis_prompts import _final_report_system_prompt


from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.utils.artifacts import save_json_artifact, save_text_artifact

from research_agent.clients.langsmith_client import pull_prompt_from_langsmith 
from research_agent.human_upgrade.tools.file_system_tools import (
     agent_write_file,
     agent_edit_file,
     agent_delete_file,
  
     agent_search_files,
     agent_list_outputs,
)


from research_agent.human_upgrade.tools.web_search_tools import (
    wiki_tool,
    tavily_search_research,
    tavily_extract_research,
    tavily_map_research,   
 
    
)  
from research_agent.human_upgrade.prompts.summary_middleware_prompts import SUMMARY_PROMPT 


from research_agent.agent_tools.file_system_functions import read_file, write_file as fs_write_file  
from pathlib import Path  
from research_agent.human_upgrade.utils.graph_namespaces import with_checkpoint_ns, ns_direction, ns_bundle 
import json
import asyncio 
from research_agent.retrieval.async_mongo_client import _humanupgrade_db 


from research_agent.human_upgrade.base_models import gpt_4_1, gpt_5_mini, gpt_5_nano, gpt_5 

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



load_dotenv() 


# ========================================================================
# STATE DEFINITIONS
# ========================================================================

RESEARCH_FILESYSTEM_TOOLS: List[BaseTool] = [
    agent_write_file,
    agent_edit_file, 
 
] 

ALL_FILESYSTEM_TOOLS: List[BaseTool] = [   
    agent_write_file,
    # agent_read_file,  # REMOVED: for now 
    # agent_edit_file,  # REMOVED: for now 
    agent_delete_file,
    agent_search_files,
    agent_list_outputs,
]




class EntityIntelResearchBundleState(TypedDict, total=False):  
    episode: Dict[str, Any] 
    bundle: EntityBundleDirectionsFinal  


    bundle_id: str  

    direction_queue: List[Literal["GUEST", "BUSINESS", "PRODUCT", "COMPOUND"]]  

    direction_index: int 

    file_refs: Annotated[List[FileReference], operator.add]   

    structured_outputs: Annotated[List[BaseModel], operator.add] 
    final_reports: Annotated[List[FileReference], operator.add]




class LastFileEvent(TypedDict, total=False):
    """
    Overwrite-only event metadata about the most recent file operation.
    (We intentionally overwrite this each time.)
    """
    op: Literal["write", "edit", "delete", "read", "list", "search"]
    file_path: str
    description: str
    entity_key: str
    timestamp: str
    # optional previews
    find_text_preview: str
    pattern: str
    subdir: str


class WorkspaceFile(TypedDict, total=False):
    """
    A lightweight snapshot of files/dirs in this agent's workspace root.
    """
    name: str
    path: str               # path relative to BASE_DIR (agent_files_current)
    is_dir: bool
    size: Optional[int]



FieldStatus = Literal["todo", "in_progress", "done", "not_found"]

class RequiredFieldEntry(TypedDict, total=False):
    status: FieldStatus
    evidence_files: List[str]   # file paths
    notes: str                  # 1-2 lines

class CurrentFocus(TypedDict, total=False):
    entity: str
    field: str

class ContextIndex(TypedDict, total=False):
    latest_checkpoint: str
    key_files: List[str]


class DirectionAgentState(AgentState):
    # --- identity / plan ---
    direction_type: DirectionType
    bundle_id: str
    run_id: str
    plan: Dict[str, Any]           # {"chosen": {...}, "required_fields": [...]}
    episode: Dict[str, Any]

    # --- counters / progress ---
    steps_taken: int

    # --- accumulators (reducers) ---
    # append list deltas returned by tools/nodes
    file_refs: Annotated[List[FileReference], operator.add]
    research_notes: Annotated[List[str], operator.add]
    thoughts: Annotated[List[str], operator.add]  # Agent reflections from think_tool

    # --- final output (overwrite) ---
    # keep as overwrite (default behavior). If you want to be strict, make it Optional[FileReference].
    final_report: Optional[Union[FileReference, str]]

    # --- convenience state for prompting/debug ---
    # overwrite each time
    last_file_event: Optional[LastFileEvent]

    # accumulated snapshots; tools can return a list delta and it will append.
    # NOTE: if you prefer overwrite instead of append, do NOT Annotate this.
    workspace_files: Annotated[List[WorkspaceFile], operator.add] 

    required_fields_status: Dict[str, RequiredFieldEntry]   # key = requiredField string
    open_questions: List[str]
    current_focus: CurrentFocus
    context_index: ContextIndex
    last_plan: str  # compact plan string to inject (optional but handy)



async def generate_final_report_text(state: DirectionAgentState) -> str:
    """
    Uses gpt_5 to synthesize a final report from all checkpoint files.
    Returns plain-text report (does NOT write to filesystem).
    """
    plan = state["plan"]
    file_refs: List[FileReference] = state.get("file_refs", []) or []

    concatenated = await _concat_direction_files(file_refs)

    system_prompt = _final_report_system_prompt(
        direction_type=state["direction_type"],
        bundle_id=state["bundle_id"],
        run_id=state["run_id"],
        plan=plan,
        concatenated_files_block=concatenated,
    )

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




async def write_final_report_and_update_state(state: DirectionAgentState, final_text: str) -> Dict[str, Any]:
    """
    Writes final report to filesystem and returns overwrite updates:
      - final_report: FileReference
      - file_refs: append final report ref (as delta)
      - research_notes: append note (as delta)
    
    Uses the new write_file API with path components + keyword argument.
    """

    
    # Get and sanitize path components
    bundle_id = sanitize_path_component(state["bundle_id"])
    direction_type = sanitize_path_component(state["direction_type"])
    run_id = sanitize_path_component(state["run_id"])
    filename = "final_report.txt"
    
    # Write using new API: components + keyword argument
    filepath = await write_file(
        bundle_id,
        direction_type,
        run_id,
        filename,
        content=final_text
    )
    
    # Get relative path for state storage
    relative_path = str(filepath.relative_to(BASE_DIR))

    ref = FileReference(
        file_path=relative_path,
        description=(
            f"FINAL synthesized report for direction={state['direction_type']} "
            f"bundle_id={state['bundle_id']} run_id={state['run_id']}. "
            "Synthesizes all checkpoint reports and explicitly covers requiredFields."
        ),
        bundle_id=state["bundle_id"],
        entity_key=f"final_{state['direction_type'].lower()}",
    )

    note = f"Wrote final report: {relative_path}"

    return {
        "final_report": ref,          # overwrite
        "file_refs": [ref],           # list delta (for operator.add reducer)
        "research_notes": [note],     # list delta (for operator.add reducer)
    }


@before_agent
def init_run_state(state: DirectionAgentState, runtime) -> Optional[Dict[str, Any]]:
    """
    Runs once per agent invocation (one full agent loop).
    - Initializes the prompt latch for this invocation
    - Initializes the research ledger only if missing (so checkpoint resume doesn't reset it)
    """
    updates: Dict[str, Any] = {"_initial_prompt_sent": False}

    if not state.get("required_fields_status"):
        plan = state.get("plan") or {}
        req = list(plan.get("required_fields") or [])

        updates.update(
            {
                "required_fields_status": {
                    f: {"status": "todo", "evidence_files": [], "notes": ""} for f in req
                },
                "open_questions": [],
                "current_focus": {"entity": "", "field": ""},
                "context_index": {"latest_checkpoint": "", "key_files": []},
                "last_plan": "",
            }
        )

    return updates if updates else None

@after_agent
async def finalize_direction_report_after_agent(state: DirectionAgentState, runtime) -> Dict[str, Any] | None:
    """
    Runs once per direction-agent invocation, after the agent completes its loop.
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

 

# REMOVED: Manual truncation replaced by SummarizationMiddleware
# The SummarizationMiddleware automatically handles message history management
# and properly preserves tool call/response pairs, which is critical for OpenAI API

@after_model
def latch_initial_prompt_after_first_model(state: DirectionAgentState, runtime) -> Optional[Dict[str, Any]]:
    """
    Flip the latch after the first model call of this invocation.
    This is robust: state updates returned here are persisted by the agent runtime/checkpointer.
    """
    if state.get("_initial_prompt_sent") is False:
        return {"_initial_prompt_sent": True}
    return None



@dynamic_prompt
def biotech_direction_dynamic_prompt(request: ModelRequest) -> str:
    s = request.state

    bundle_id: str = s["bundle_id"]
    run_id: str = s["run_id"]
    direction_type: str = s["direction_type"]
    plan: Dict[str, Any] = s["plan"]

    steps_taken: int = int(s.get("steps_taken", 0) or 0)
    entity_context: str = s.get("entity_context", "")
    max_web_tool_calls_hint: int = int(s.get("max_web_tool_calls_hint", 18) or 18)

    if s.get("_initial_prompt_sent") is False:
        return get_initial_research_prompt(
            bundle_id=bundle_id,
            run_id=run_id,
            direction_type=direction_type,
            plan=plan,
            entity_context=entity_context,
            max_web_tool_calls_hint=max_web_tool_calls_hint,
        )


    return get_reminder_research_prompt(
        bundle_id=bundle_id,
        run_id=run_id,
        direction_type=direction_type,
        plan=plan,
        state=s,
        steps_taken=steps_taken,
    )
summarizer = SummarizationMiddleware(
    model=gpt_5_mini,
    # Trigger summarization when we reach 75% of gpt-5-mini's 40k token context (30k tokens)
    # This gives us a comfortable buffer before hitting the limit
    trigger=[("tokens", 30_000)],
    # After summarization, keep the most recent 15k tokens of conversation
    # This leaves ~15k tokens for the summary + new messages before next trigger
    keep=("tokens", 15_000),
    # Use our custom research-focused summary prompt
    summary_prompt=SUMMARY_PROMPT,
    # When creating the summary, trim input to 12k tokens to stay well under gpt-5-mini's limits
    # (Summary input should be < model context / 2 to allow room for summary output)
    trim_tokens_to_summarize=12_000,
) 
direction_agent_middlewares = [
    init_run_state,                    # sets _initial_prompt_sent=False at invocation start
    summarizer,                        # Manages message history with smart summarization
    biotech_direction_dynamic_prompt,  # chooses initial vs reminder based on latch
    latch_initial_prompt_after_first_model,  # flips latch after first model call
    finalize_direction_report_after_agent,
]

ALL_RESEARCH_TOOLS: List[BaseTool] = [
    wiki_tool,
    tavily_search_research,
    tavily_extract_research,
    tavily_map_research, 
    think_tool, 
] + RESEARCH_FILESYSTEM_TOOLS 







def build_direction_agent(
    *,
    store: BaseStore,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    return create_agent(
        name="direction_agent",
        model=gpt_5_mini,
        tools=ALL_RESEARCH_TOOLS,
        state_schema=DirectionAgentState,
        middleware=direction_agent_middlewares,
        checkpointer=checkpointer,
        store=store,
    )



DirectionAgent: CompiledStateGraph = create_agent(
    name="direction_agent",
    model=gpt_5_mini,
    tools=ALL_RESEARCH_TOOLS,
    state_schema=DirectionAgentState,
    middleware=direction_agent_middlewares,
)

def build_direction_queue(bundle: EntityBundleDirectionsFinal) -> List[DirectionType]:
    """
    Deterministic ordering within a bundle.
    Guest always exists; other directions optional.
    """
    queue: List[DirectionType] = ["GUEST"]

    if bundle.businessDirection is not None:
        queue.append("BUSINESS")
    if bundle.productsDirection is not None:
        queue.append("PRODUCT")
    if bundle.compoundsDirection is not None:
        queue.append("COMPOUND")
   

    return queue


def select_direction_plan(bundle: EntityBundleDirectionsFinal, direction_type: DirectionType) -> Dict[str, Any]:
    """
    Returns a uniform shape of {chosen: ..., required_fields: ...}
    regardless of direction type.
    """
    if direction_type == "GUEST":
        return {
            "chosen": bundle.guestDirection.chosenDirection.model_dump(),
            "required_fields": [f.value for f in bundle.guestDirection.requiredFields],
        }

    if direction_type == "BUSINESS":
        if bundle.businessDirection is None:
            raise ValueError("bundle.businessDirection is None but direction_type=BUSINESS")
        return {
            "chosen": bundle.businessDirection.chosenDirection.model_dump(),
            "required_fields": [f.value for f in bundle.businessDirection.requiredFields],
        }

    if direction_type == "PRODUCT":
        if bundle.productsDirection is None:
            raise ValueError("bundle.productsDirection is None but direction_type=PRODUCT")
        return {
            "chosen": bundle.productsDirection.chosenDirection.model_dump(),
            "required_fields": [f.value for f in bundle.productsDirection.requiredFields],
        }

    if direction_type == "COMPOUND":
        if bundle.compoundsDirection is None:
            raise ValueError("bundle.compoundsDirection is None but direction_type=COMPOUND")
        return {
            "chosen": bundle.compoundsDirection.chosenDirection.model_dump(),
            "required_fields": [f.value for f in bundle.compoundsDirection.requiredFields],
        }

 


# Add Human In The Loop Here. Can be in init_bundle or another node 
# Retrieve memory / call db to see what is currently had on the entities in the bundle 
# add an interrupt from langgraph and I will respond with confirmation or denial to continue with the research 

async def init_bundle_research_node(
    state: EntityIntelResearchBundleState,
) -> EntityIntelResearchBundleState:
    bundle: EntityBundleDirectionsFinal | None = state.get("bundle")
    if bundle is None:
        raise ValueError("BundleResearchSubGraph requires state['bundle']")

    bundle_id: str = state.get("bundle_id") or bundle.bundleId
    queue: List[DirectionType] = build_direction_queue(bundle)

    logger.info(f"📦 BundleResearchSubGraph init bundle={bundle_id} queue={queue}")

    return {
        "bundle_id": bundle_id,
        "direction_queue": queue,
        "direction_index": 0,
    }


def has_next_direction(
    state: EntityIntelResearchBundleState,
) -> Literal["run_direction", "done"]:
    queue: List[DirectionType] = state.get("direction_queue", [])
    idx: int = state.get("direction_index", 0)
    return "run_direction" if idx < len(queue) else "done"




async def advance_direction_index_node(
    state: EntityIntelResearchBundleState,
) -> EntityIntelResearchBundleState:
    idx: int = state.get("direction_index", 0)
    return {"direction_index": idx + 1}


async def finalize_bundle_research_node(
    state: EntityIntelResearchBundleState,
) -> EntityIntelResearchBundleState:
    logger.info(f"🏁 BundleResearchSubGraph complete bundle={state.get('bundle_id')}")
    return {}



async def make_bundle_research_graph(config: RunnableConfig) -> CompiledStateGraph:
    store, checkpointer = await get_persistence()

    # Build the agent graph *with* persistence
    direction_agent = build_direction_agent(store=store, checkpointer=checkpointer)

    # --- Bundle Subgraph builder ---
    bundle_builder: StateGraph = StateGraph(EntityIntelResearchBundleState)

    async def run_direction_node(
        state: EntityIntelResearchBundleState,
        config: RunnableConfig,
    ) -> EntityIntelResearchBundleState:
        """
        Selects the next direction in the bundle and invokes DirectionAgent.
        Includes logging and defensive error handling.
        """
        bundle: EntityBundleDirectionsFinal | None = state.get("bundle")
        if bundle is None:
            logger.error("❌ run_direction_node: missing state['bundle']")
            raise ValueError("Missing bundle in BundleResearchSubGraph state")

        bundle_id: str = state.get("bundle_id") or bundle.bundleId
        queue: List[DirectionType] = state.get("direction_queue", [])
        idx: int = int(state.get("direction_index", 0) or 0)

        if not queue:
            logger.error("❌ run_direction_node: empty direction_queue bundle_id=%s", bundle_id)
            raise ValueError("direction_queue is empty")

        if idx >= len(queue):
            logger.error(
                "❌ run_direction_node: direction_index out of range bundle_id=%s idx=%s len(queue)=%s queue=%s",
                bundle_id, idx, len(queue), queue
            )
            raise ValueError("direction_index out of range")

        direction_type: DirectionType = queue[idx]
        try:
            plan: Dict[str, Any] = select_direction_plan(bundle, direction_type)
        except Exception as e:
            logger.exception(
                "❌ run_direction_node: failed to select plan bundle_id=%s direction=%s",
                bundle_id, direction_type
            )
            raise

    
        run_id: str = sanitize_path_component(f"{bundle_id}_{direction_type}")

        logger.info(
            "➡️  Bundle %s: running direction %s/%s %s",
            bundle_id, idx + 1, len(queue), direction_type
        )

        direction_state: DirectionAgentState = {
            "direction_type": direction_type,
            "bundle_id": bundle_id,
            "run_id": run_id,
            "plan": plan,
            "episode": state.get("episode", {}),

            "steps_taken": 0,

            "file_refs": [],
            "research_notes": [],
            "thoughts": [],

            "final_report": None,
            "last_file_event": None,

            "workspace_files": [],
            "messages": [],
            "required_fields_status": {},
            "open_questions": [],
            "current_focus": {"entity": "", "field": ""},
            "context_index": {"latest_checkpoint": "", "key_files": []},
            "last_plan": "",
        } 

        dir_cfg = with_checkpoint_ns(config, ns_direction(bundle_id, direction_type))

        # Log initial state for debugging
        logger.info(
            "📝 Invoking DirectionAgent with initial state: messages=%s, steps_taken=%s",
            len(direction_state.get("messages", [])),
            direction_state.get("steps_taken")
        )

        try:
            out: Dict[str, Any] = await direction_agent.ainvoke(direction_state, dir_cfg)
            
            # Log what the agent produced
            logger.info(
                "📊 DirectionAgent completed: messages=%s, steps_taken=%s, file_refs=%s, thoughts=%s",
                len(out.get("messages", [])),
                out.get("steps_taken"),
                len(out.get("file_refs", [])),
                len(out.get("thoughts", []))
            )
        except Exception as e:
            # Don’t swallow the error; log with context and re-raise so the checkpoint shows failure at this node.
            logger.exception(
                "❌ DirectionAgent failed bundle_id=%s direction=%s run_id=%s",
                bundle_id, direction_type, run_id
            )
            raise

        merged_file_refs: List[FileReference] = out.get("file_refs", []) or []
        merged_notes: List[str] = out.get("research_notes", []) or []
        final_report = out.get("final_report", None)

        steps: int = int(out.get("steps_taken", 0) or 0)
        logger.info(
            "   ✓ Direction %s complete: %s files, %s steps",
            direction_type, len(merged_file_refs), steps
        )

        if merged_notes:
            logger.info("    Notes: %s", merged_notes[-1])

        final_reports_list: List[FileReference] = []
        if isinstance(final_report, FileReference):
            final_reports_list = [final_report]
        elif final_report is not None and not isinstance(final_report, (FileReference, str)):
            # Just a helpful log if something unexpected shows up
            logger.warning(
                "run_direction_node: unexpected final_report type=%s bundle_id=%s direction=%s",
                type(final_report).__name__, bundle_id, direction_type
            )

        return {
            "file_refs": merged_file_refs,
            "final_reports": final_reports_list,
            # If you want to bubble notes upward, uncomment:
            # "research_notes": merged_notes,
        }

    # (add your other bundle nodes / edges exactly as you already have)
    bundle_builder.add_node("init_bundle", init_bundle_research_node)
    bundle_builder.add_node("run_direction", run_direction_node)
    bundle_builder.add_node("advance_direction", advance_direction_index_node)
    bundle_builder.add_node("finalize_bundle", finalize_bundle_research_node)
    bundle_builder.set_entry_point("init_bundle")
    bundle_builder.add_conditional_edges("init_bundle", has_next_direction, {"run_direction": "run_direction", "done": "finalize_bundle"})
    bundle_builder.add_edge("run_direction", "advance_direction")
    bundle_builder.add_conditional_edges("advance_direction", has_next_direction, {"run_direction": "run_direction", "done": "finalize_bundle"})
    bundle_builder.add_edge("finalize_bundle", END)

    # Option A (recommended here): bundle uses SAME saver, but its own internal memory
    # This matches the official “subgraph has its own memory” pattern. :contentReference[oaicite:4]{index=4}
    BundleResearchSubGraph = bundle_builder.compile(
        checkpointer=checkpointer,
        store=store,
    ) 

    return BundleResearchSubGraph  

  


