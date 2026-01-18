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

from langchain.chat_models import BaseChatModel
from langgraph.graph import StateGraph, START, END     
from langgraph.types import Command 
from langgraph.graph.state import CompiledStateGraph 
from langchain.tools import BaseTool 
from langgraph.prebuilt import ToolNode 
from typing_extensions import TypedDict, Annotated  
from typing import List, Dict, Any, Optional, Sequence, Literal, Union
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, ToolMessage, AnyMessage, AIMessage
from langchain_openai import ChatOpenAI  
from pydantic import BaseModel, Field  
import operator   
from langchain.agents import create_agent, AgentState  
from datetime import datetime 
from dotenv import load_dotenv 
from langchain.agents.structured_output import ProviderStrategy 
from research_agent.human_upgrade.structured_outputs.enums_literals import DirectionType
from research_agent.human_upgrade.structured_outputs.research_direction_outputs import ( 
    EntityBundlesListFinal,
    EntityBundleDirectionsFinal,
    GuestDirectionOutputFinal,
    BusinessDirectionOutputFinal,
    ProductsDirectionOutputFinal,
    CompoundsDirectionOutputFinal,
    PlatformsDirectionOutputFinal,
    StarterSource,
    GuestFieldEnum,
    BusinessFieldEnum,
    ProductFieldEnum,
    CompoundFieldEnum,
    PlatformFieldEnum,
) 

from research_agent.human_upgrade.tools.think_tool import think_tool 
from research_agent.human_upgrade.prompts.research_prompt_builders import ( 
    _recent_file_refs,
    get_initial_research_prompt,
    get_reminder_research_prompt,
) 
from research_agent.human_upgrade.utils.formatting import _concat_direction_files

   

from research_agent.human_upgrade.structured_outputs.file_outputs import ( 
    FileReference,
)  
from datetime import datetime, timezone 

from research_agent.human_upgrade.structured_outputs.sources_and_search_summary_outputs import TavilyCitation

from research_agent.human_upgrade.prompts.todo_prompts import todo_generation_prompt
from research_agent.human_upgrade.prompts.research_prompts import (
    get_main_research_prompt,
    get_reminder_research_prompt,
)
from research_agent.human_upgrade.prompts.synthesis_prompts import (
    get_direction_synthesis_prompt,
    _final_report_system_prompt,
)


from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.utils.artifacts import save_json_artifact, save_text_artifact

from research_agent.clients.langsmith_client import pull_prompt_from_langsmith 
from research_agent.human_upgrade.tools.file_system_tools import (
     agent_write_file,
     agent_read_file,
     agent_edit_file,
     agent_delete_file,
     agent_list_directory, 
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
from research_agent.human_upgrade.prompts.synthesis_prompts import (
    get_direction_synthesis_prompt
)

from research_agent.agent_tools.filesystem_tools import read_file, write_file as fs_write_file  
from pathlib import Path 


from research_agent.human_upgrade.base_models import gpt_4_1, gpt_5_mini, gpt_5_nano, gpt_5 

from langchain.agents.middleware import ( 
    SummarizationMiddleware,   
    AgentMiddleware,
    dynamic_prompt, 
    ModelRequest,  
    before_agent, 
    after_agent, 
) 



load_dotenv() 


# ========================================================================
# STATE DEFINITIONS
# ========================================================================


RESEARCH_FILESYSTEM_TOOLS: List[BaseTool] = [
    agent_write_file,
    agent_read_file,
    agent_edit_file,
    agent_delete_file,
 
] 

ALL_FILESYSTEM_TOOLS: List[BaseTool] = [   
    agent_write_file,
    agent_read_file,
    agent_edit_file,
    agent_delete_file,

    agent_list_directory,
    agent_search_files,
    agent_list_outputs,
]







class EntityIntelResearchParentState(TypedDict, total=False):
    episode: Dict[str, Any]
    bundles: EntityBundlesListFinal

    bundle_index: int
    completed_bundle_ids: List[str]

    # optional rollups
    file_refs: Annotated[List[FileReference], operator.add]   
    structured_outputs: Annotated[List[BaseModel], operator.add] 

    final_reports: Annotated[List[FileReference], operator.add]




class EntityIntelResearchBundleState(TypedDict, total=False):  
    episode: Dict[str, Any] 
    bundle: EntityBundleDirectionsFinal  


    bundle_id: str  

    direction_queue: List[Literal["GUEST", "BUSINESS", "PRODUCT", "COMPOUND", "PLATFORM"]]  

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

    # --- final output (overwrite) ---
    # keep as overwrite (default behavior). If you want to be strict, make it Optional[FileReference].
    final_report: Optional[Union[FileReference, str]]

    # --- convenience state for prompting/debug ---
    # overwrite each time
    last_file_event: Optional[LastFileEvent]

    # accumulated snapshots; tools can return a list delta and it will append.
    # NOTE: if you prefer overwrite instead of append, do NOT Annotate this.
    workspace_files: Annotated[List[WorkspaceFile], operator.add]



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
        tools=[],  # no tools: pure synthesis
        middleware=[],
    )

    # The model already has the inputs in the system prompt.
    # The user message is simply the instruction to produce the report.
    out = await final_report_agent.ainvoke(
        {"messages": [HumanMessage(content="Write the final report now following the requirements exactly.")]},
    ) 

    return out.text 




def _scoped_final_report_filename(state: DirectionAgentState) -> str:
    """
    Matches your workspace scheme:
      agent_files_current/<bundle_id>/<direction_type>/<run_id>/
    We store file_path relative to BASE_DIR (agent_files_current),
    consistent with your agent_write_file tool.
    """
    bundle_id = state["bundle_id"]
    direction_type = state["direction_type"]
    run_id = state["run_id"]
    return str(Path(bundle_id) / direction_type / run_id / "final_report.txt")

async def write_final_report_and_update_state(state: DirectionAgentState, final_text: str) -> Dict[str, Any]:
    """
    Writes final report to filesystem and returns overwrite updates:
      - final_report: FileReference
      - file_refs: append final report ref (as delta)
      - research_notes: append note (as delta)
    """
    final_path = _scoped_final_report_filename(state)
    await fs_write_file(final_path, final_text)

    ref = FileReference(
        file_path=final_path,
        description=(
            f"FINAL synthesized report for direction={state['direction_type']} "
            f"bundle_id={state['bundle_id']} run_id={state['run_id']}. "
            "Synthesizes all checkpoint reports and explicitly covers requiredFields."
        ),
        bundle_id=state["bundle_id"],
        entity_key=f"final_{state['direction_type'].lower()}",
    )

    note = f"Wrote final report: {final_path}"

    return {
        "final_report": ref,          # overwrite
        "file_refs": [ref],           # list delta (for operator.add reducer)
        "research_notes": [note],     # list delta (for operator.add reducer)
    }


# ============================================================
# AFTER_AGENT middleware hook: generate + write final report
# ============================================================

@after_agent(state_schema=DirectionAgentState, name="FinalizeDirectionReport")
async def finalize_direction_report_after_agent(state: DirectionAgentState, runtime) -> DirectionAgentState:
    """
    Runs once per direction-agent invocation, after the agent completes its loop.
    Generates a final synthesized report (gpt_5), writes it to the scoped workspace,
    and updates state.final_report + file_refs + research_notes.
    """
    logger.info("🏁 after_agent: generating final synthesized report (gpt_5)")

    # If you want to skip when no files exist:
    file_refs: List[FileReference] = state.get("file_refs", []) or []
    if not file_refs:
        logger.warning("after_agent: no file_refs found; skipping final report generation")
        return {"research_notes": ["Skipped final report: no checkpoint files were produced."]}

    final_text = await generate_final_report_text(state)
    updates = await write_final_report_and_update_state(state, final_text)

    logger.info(f"✅ after_agent: final report written at {updates['final_report'].file_path}")
    return updates




@before_agent(state_schema=DirectionAgentState)
def init_prompt_latch(state: DirectionAgentState, runtime) -> Command:
    """
    Runs once per agent invocation (one full agent loop).
    Initialize latch so the first model call gets the full prompt.
    """
    return Command(update={"_initial_prompt_sent": False})


@dynamic_prompt
def biotech_direction_dynamic_prompt(request: ModelRequest) -> str:
    """
    - First model call: emit full prompt and flip latch to True
    - Later model calls: emit reminder prompt
    """
    s = request.runtime.state

    bundle_id: str = s["bundle_id"]
    run_id: str = s["run_id"]
    direction_type: str = s["direction_type"]
    plan: Dict[str, Any] = s["plan"]

    # Optional: display only
    steps_taken: int = int(s.get("steps_taken", 0) or 0)
    entity_context: str = s.get("entity_context", "")
    max_web_tool_calls_hint: int = int(s.get("max_web_tool_calls_hint", 18) or 18)

    # First model call of this agent invocation
    if s.get("_initial_prompt_sent") is False:
        s["_initial_prompt_sent"] = True
        return get_initial_research_prompt(
            bundle_id=bundle_id,
            run_id=run_id,
            direction_type=direction_type,
            plan=plan,
            entity_context=entity_context,
            max_web_tool_calls_hint=max_web_tool_calls_hint,
        )

    # Subsequent calls
    recent_files_block = _recent_file_refs(s, limit=10)
    return get_reminder_research_prompt(
        bundle_id=bundle_id,
        run_id=run_id,
        direction_type=direction_type,
        plan=plan,
        recent_files_block=recent_files_block,
        steps_taken=steps_taken,
    )

summarizer = SummarizationMiddleware(
    model=gpt_5_mini,                
    trigger=[("tokens", 220_000), ("messages", 120)],
    keep=("messages", 20),
    summary_prompt=SUMMARY_PROMPT,
    trim_tokens_to_summarize=20_000,          
) 

direction_agent_middlewares: List[AgentMiddleware] = [ 

    init_prompt_latch, 
     summarizer,
    biotech_direction_dynamic_prompt,
   
    finalize_direction_report_after_agent, 
    
] 


ALL_RESEARCH_TOOLS: List[BaseTool] = [
    wiki_tool,
    tavily_search_research,
    tavily_extract_research,
    tavily_map_research,
] + RESEARCH_FILESYSTEM_TOOLS 

def create_direction_agent(name: str, model: BaseChatModel,  
tools: List[BaseTool], state_schema: DirectionAgentState, middleware: List[AgentMiddleware]) -> CompiledStateGraph: 


    """
    Create a direction agent with the given model, tools, state schema, and middleware.
    """ 

    agent: CompiledStateGraph = create_agent( 
        model=model, 
        tools=tools, 
        state_schema=state_schema, 
        middleware=middleware,  
        name=name,
    ) 

    return agent  




research_parent_graph_builder: StateGraph = StateGraph(EntityIntelResearchParentState) 
research_subgraph_builder: StateGraph = StateGraph(EntityIntelResearchBundleState) 



# ========================================================================
# PARENT GRAPH - BundlesParentGraph
# ========================================================================
# Orchestrates research across multiple entity bundles

async def load_bundles_node(
    state: EntityIntelResearchParentState
) -> EntityIntelResearchParentState:
    bundles_list: EntityBundlesListFinal | None = state.get("bundles")
    if bundles_list is None:
        raise ValueError("ParentGraph requires state['bundles'] (EntityBundlesListFinal)")

    n: int = len(bundles_list.bundles)
    logger.info(f"🧭 BundlesParentGraph loaded {n} bundles")

    return {
        "bundle_index": 0,
        "completed_bundle_ids": [],
    } 


def has_next_bundle(
    state: EntityIntelResearchParentState,
) -> Literal["run_bundle", "done"]:
    bundles_list: EntityBundlesListFinal | None = state.get("bundles")
    if bundles_list is None:
        return "done"
    idx: int = state.get("bundle_index", 0)
    return "run_bundle" if idx < len(bundles_list.bundles) else "done" 




async def finalize_parent_node(
    state: EntityIntelResearchParentState
) -> EntityIntelResearchParentState:
    done: List[str] = state.get("completed_bundle_ids", [])
    logger.info(f"✅ BundlesParentGraph complete. bundles_done={len(done)}")
    return {}


async def run_bundle_node(
    state: EntityIntelResearchParentState
) -> EntityIntelResearchParentState:
    bundles_list: EntityBundlesListFinal | None = state.get("bundles")
    if bundles_list is None:
        raise ValueError("Missing bundles")

    idx: int = state.get("bundle_index", 0)
    bundle: EntityBundleDirectionsFinal = bundles_list.bundles[idx]
    bundle_id: str = bundle.bundleId

    logger.info(f"📦 ParentGraph invoking BundleResearchSubGraph {idx+1}/{len(bundles_list.bundles)}: {bundle_id}")

    # Invoke the bundle subgraph
    bundle_state: EntityIntelResearchBundleState = {
        "episode": state.get("episode", {}),
        "bundle": bundle,
        "bundle_id": bundle_id,
        "direction_queue": [],
        "direction_index": 0,
        "messages": [],
        "file_refs": [],
        "structured_outputs": [],
        "final_reports": [],
        "llm_calls": state.get("llm_calls", 0),
        "tool_calls": state.get("tool_calls", 0),
        "steps_taken": state.get("steps_taken", 0),
    }

    bundle_out = await BundleResearchSubGraph.ainvoke(bundle_state)

    # Roll up bundle completion
    completed = list(state.get("completed_bundle_ids", []))
    completed.append(bundle_id)

    # Merge file refs upward
    merged_file_refs: List[FileReference] = bundle_out.get("file_refs", [])

    return {
        "bundle_index": idx + 1,
        "completed_bundle_ids": completed,
        "file_refs": merged_file_refs, 
        "final_reports": bundle_out.get("final_reports", []),
        # optional: merge counters if you want
        "llm_calls": bundle_out.get("llm_calls", state.get("llm_calls", 0)),
        "tool_calls": bundle_out.get("tool_calls", state.get("tool_calls", 0)),
        "steps_taken": bundle_out.get("steps_taken", state.get("steps_taken", 0)),
        "messages": bundle_out.get("messages", []),
    } 


# -----------------------------
# Parent Graph - Wire up nodes and edges
# -----------------------------

research_parent_graph_builder.add_node("load_bundles", load_bundles_node)
research_parent_graph_builder.add_node("run_bundle", run_bundle_node)
research_parent_graph_builder.add_node("finalize_parent", finalize_parent_node)

research_parent_graph_builder.set_entry_point("load_bundles")

research_parent_graph_builder.add_conditional_edges(
    "load_bundles",
    has_next_bundle,
    {
        "run_bundle": "run_bundle",
        "done": "finalize_parent",
    },
)

# After each bundle, loop again
research_parent_graph_builder.add_conditional_edges(
    "run_bundle",
    has_next_bundle,
    {
        "run_bundle": "run_bundle",
        "done": "finalize_parent",
    },
)

research_parent_graph_builder.add_edge("finalize_parent", END)


# ========================================================================
# BUNDLE SUBGRAPH - BundleResearchSubGraph
# ========================================================================
# Handles research for a single bundle, iterating through research directions




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
    if bundle.platformsDirection is not None:
        queue.append("PLATFORM")

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

    if direction_type == "PLATFORM":
        if bundle.platformsDirection is None:
            raise ValueError("bundle.platformsDirection is None but direction_type=PLATFORM")
        return {
            "chosen": bundle.platformsDirection.chosenDirection.model_dump(),
            "required_fields": [f.value for f in bundle.platformsDirection.requiredFields],
        }


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


async def run_direction_node(
    state: EntityIntelResearchBundleState,
) -> EntityIntelResearchBundleState:
    """
    Selects the next direction in the bundle and invokes DirectionResearchSubGraph (placeholder).
    """
    bundle: EntityBundleDirectionsFinal | None = state.get("bundle")
    if bundle is None:
        raise ValueError("Missing bundle in BundleResearchSubGraph state")

    bundle_id: str = state.get("bundle_id") or bundle.bundleId
    queue: List[DirectionType] = state.get("direction_queue", [])
    idx: int = state.get("direction_index", 0)

    if idx >= len(queue):
        raise ValueError("direction_index out of range")

    direction_type: DirectionType = queue[idx]
    plan: Dict[str, Any] = select_direction_plan(bundle, direction_type)

    # Stable run_id per direction invocation
    run_id: str = f"{bundle_id}:{direction_type}"

    logger.info(f"➡️  Bundle {bundle_id}: running direction {idx+1}/{len(queue)} {direction_type}")

    # Build the direction subgraph state
    direction_state: DirectionAgentState = {
        "direction_type": direction_type,
        "bundle_id": bundle_id,
        "run_id": run_id,
        "plan": plan,
        "episode": state.get("episode", {}),

        "steps_taken": 0,

        # reducers (operator.add) expect list deltas
        "file_refs": [],
        "research_notes": [],

        # overwrite fields
        "final_report": None,
        "last_file_event": None,

        # If you are using workspace_files as an accumulator, start empty
        "workspace_files": [],

        # AgentState base
        "messages": [],
    }  

    DirectionAgent: CompiledStateGraph = create_direction_agent( 
        name=f"{direction_type}_direction_agent",
        model=gpt_5_mini,
        tools=ALL_RESEARCH_TOOLS,
        state_schema=DirectionAgentState,
        middleware=direction_agent_middlewares,
    )

    # Invoke the real DirectionResearchSubGraph
    out: Dict[str, Any] = await DirectionAgent.ainvoke(direction_state)

    merged_file_refs: List[FileReference] = out.get("file_refs", []) or []
    merged_notes: List[str] = out.get("research_notes", []) or []

    # After-agent finalizer should set this (FileReference OR str depending on your type)
    final_report = out.get("final_report", None)

    steps: int = int(out.get("steps_taken", 0) or 0)
    logger.info(
        f"   ✓ Direction {direction_type} complete: "
        f"{len(merged_file_refs)} files, {steps} steps"
    )

    if merged_notes:
        logger.info(f"    Notes: {merged_notes[-1]}")

    # Parent state has Annotated[List[FileReference], operator.add] so return LIST delta
    final_reports_list: List[FileReference] = []
    if isinstance(final_report, FileReference):
        final_reports_list = [final_report]
    # If your after-agent stored a string (path), you can optionally normalize here:
    # elif isinstance(final_report, str) and final_report:
    #     final_reports_list = [FileReference(file_path=final_report, description="Final report", bundle_id=bundle_id, entity_key=f"final_{direction_type.lower()}")]

    return {
        "file_refs": merged_file_refs,
        "final_reports": final_reports_list,
        # optionally bubble notes up if you want:
        # "structured_outputs": [],  # unchanged here 
        # merged_messages
    }


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


# -----------------------------
# Bundle Subgraph - Wire up nodes and edges
# -----------------------------

research_subgraph_builder.add_node("init_bundle", init_bundle_research_node)
research_subgraph_builder.add_node("run_direction", run_direction_node)
research_subgraph_builder.add_node("advance_direction", advance_direction_index_node)
research_subgraph_builder.add_node("finalize_bundle", finalize_bundle_research_node)

research_subgraph_builder.set_entry_point("init_bundle")

research_subgraph_builder.add_conditional_edges(
    "init_bundle",
    has_next_direction,
    {"run_direction": "run_direction", "done": "finalize_bundle"},
)

research_subgraph_builder.add_edge("run_direction", "advance_direction")

research_subgraph_builder.add_conditional_edges(
    "advance_direction",
    has_next_direction,
    {"run_direction": "run_direction", "done": "finalize_bundle"},
)

research_subgraph_builder.add_edge("finalize_bundle", END)



BundleResearchSubGraph: CompiledStateGraph = research_subgraph_builder.compile()
BundlesParentGraph: CompiledStateGraph = research_parent_graph_builder.compile()