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
from langgraph.graph.state import CompiledStateGraph 
from langchain.tools import BaseTool 
from langgraph.prebuilt import ToolNode 
from typing_extensions import TypedDict, Annotated  
from typing import List, Dict, Any, Optional, Sequence, Literal, Union
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, ToolMessage, AnyMessage, AIMessage
from langchain_openai import ChatOpenAI  
from pydantic import BaseModel, Field  
import operator   
from langchain.agents import create_agent  
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


from research_agent.human_upgrade.structured_outputs.todos import ( 
    TodoList,
    TodoListOutput,
    convert_output_to_state,
)   

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
    get_direction_synthesis_prompt
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
)
from research_agent.human_upgrade.tools.todo_list_tools import (
  todo_update,
  todo_read,
  todo_get_next,
) 

from research_agent.human_upgrade.tools.web_search_tools import (
    wiki_tool,
    tavily_search_research,
    tavily_extract_research,
    tavily_map_research,   
 
    
) 

from research_agent.agent_tools.filesystem_tools import read_file, write_file as fs_write_file 


from research_agent.human_upgrade.base_models import gpt_4_1, gpt_5_mini, gpt_5_nano, gpt_5

load_dotenv() 


# ========================================================================
# STATE DEFINITIONS
# ========================================================================

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


class EntityIntelResearchDirectionState(TypedDict, total=False): 
    messages: Annotated[Sequence[BaseMessage], operator.add]   
    todo_list: TodoList   
    bundle_id: str 
    plan: Dict[str, Any]  
    run_id: str 
    episode: Dict[str, Any]
    llm_calls: int 
    tool_calls: int 
    steps_taken: int  
    max_steps: int
    file_refs: Annotated[List[FileReference], operator.add]  
    citations: Annotated[List[TavilyCitation], operator.add]          # URLs / DOIs  
    research_notes: Annotated[List[str], operator.add]     # human-readable notes from each step 
    final_report: FileReference

    direction_type: Literal["GUEST", "BUSINESS", "PRODUCT", "COMPOUND", "PLATFORM"] 



# ========================================================================
# GRAPH BUILDERS (to be compiled at end)
# ========================================================================

research_parent_graph_builder: StateGraph = StateGraph(EntityIntelResearchParentState) 
research_subgraph_builder: StateGraph = StateGraph(EntityIntelResearchBundleState) 
research_direction_graph_builder: StateGraph = StateGraph(EntityIntelResearchDirectionState)


# ========================================================================
# TOOL DEFINITIONS
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
]



TODO_TOOLS: List[BaseTool] = [
    todo_update,
    todo_read,
    todo_get_next,
]  


ALL_RESEARCH_TOOLS: List[BaseTool] = [
    wiki_tool,
    tavily_search_research,
    tavily_extract_research,
    tavily_map_research,
] + RESEARCH_FILESYSTEM_TOOLS + TODO_TOOLS


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
    direction_state: EntityIntelResearchDirectionState = {
        "direction_type": direction_type,
        "messages": [], 
        "todo_list": None, 
        "llm_calls": 0,
        "tool_calls": 0,
        "steps_taken": 0,
        "max_steps": 30,  # Configurable max steps per direction
        "file_refs": [],
        "citations": [],
        "research_notes": [], 
        "final_report": None, 
        "plan": plan,
        "run_id": run_id,
        "bundle_id": bundle_id,
        "episode": state.get("episode", {}),
    }

    # Invoke the real DirectionResearchSubGraph
    out = await ResearchDirectionSubGraph.ainvoke(direction_state)

    # Merge results (file_refs/messages) back up to bundle state
    merged_file_refs: List[FileReference] = out.get("file_refs", [])
    merged_messages: List[BaseMessage] = out.get("messages", [])
    merged_notes: List[str] = out.get("research_notes", []) 
    final_report: FileReference | None = out.get("final_report", None)
    
    steps: int = out.get("steps_taken", 0)
    llm_calls: int = out.get("llm_calls", 0)
    tool_calls: int = out.get("tool_calls", 0)
    logger.info(f"   ✓ Direction {direction_type} complete: {len(merged_file_refs)} files, {steps} steps, {llm_calls} LLM calls, {tool_calls} tool calls") 

    if merged_notes:
        logger.info(f"    Notes: {merged_notes[-1]}")

    # final_reports is Annotated[List[FileReference], operator.add] - must return list
    final_reports_list: List[FileReference] = [final_report] if final_report else []

    return {
        "file_refs": merged_file_refs,
        "messages": merged_messages, 
        "final_reports": final_reports_list, 
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


# ========================================================================
# DIRECTION SUBGRAPH - ResearchDirectionSubGraph
# ========================================================================
# Performs actual research for one direction using LLM + tools loop

async def generate_todos_node(state: EntityIntelResearchDirectionState) -> EntityIntelResearchDirectionState: 
    """
    Generate a TodoList for this research direction using structured LLM output.
    Extracts objective, entity names, starter sources from the plan.
    """
    plan: Dict[str, Any] = state.get("plan", {})
    direction_type: DirectionType = state.get("direction_type")
    bundle_id: str = state.get("bundle_id", "unknown")
    episode: Dict[str, Any] = state.get("episode", {})
    
    # Extract chosen direction (the LLM's output)
    chosen: Union[GuestDirectionOutputFinal, BusinessDirectionOutputFinal, ProductsDirectionOutputFinal, CompoundsDirectionOutputFinal, PlatformsDirectionOutputFinal] = plan.get('chosen', {})
    
    # Extract relevant episode context
    episode_context: str = f"Episode: {episode.get('title', 'N/A')}"
    if episode.get("guest_name"):
        episode_context += f" | Guest: {episode.get('guest_name')}"
    
    # Extract objective
    objective: str = chosen.get('objective', f'Complete research for {direction_type}')
    
    # Extract entity names based on direction type
    entity_names: List[str] = []
    if direction_type == "GUEST":
        entity_names = [chosen.get('guestCanonicalName', 'Unknown Guest')]
    elif direction_type == "BUSINESS":
        entity_names = chosen.get('businessNames', ['Unknown Business'])
    elif direction_type == "PRODUCT":
        entity_names = chosen.get('productNames', ['Unknown Product'])
    elif direction_type == "COMPOUND":
        entity_names = chosen.get('compoundNames', ['Unknown Compound'])
    elif direction_type == "PLATFORM":
        entity_names = chosen.get('platformNames', ['Unknown Platform'])
    
    entity_names_str: str = ", ".join(entity_names) if entity_names else "Unknown Entity"
    
    # Extract starter sources
    starter_sources: List[StarterSource] = chosen.get('starterSources', [])
    if starter_sources:
        sources_str: str = "\n".join([
            f"- {s.get('url', 'N/A')} ({s.get('sourceType', 'UNKNOWN')}) - {s.get('reason', 'No reason provided')}"
            for s in starter_sources
        ])
    else:
        sources_str: str = "No specific starter sources provided. Use general web search."
    
    # Extract required fields and create summary
    required_fields: List[Union[GuestFieldEnum, BusinessFieldEnum, ProductFieldEnum, CompoundFieldEnum, PlatformFieldEnum]] = plan.get('required_fields', [])
    # Convert enum values to readable strings if needed
    required_fields_list: List[str] = [str(f.value) if hasattr(f, 'value') else str(f) for f in required_fields]
    required_fields_summary: str = ", ".join(required_fields_list[:10])  # Limit to first 10 for readability
    if len(required_fields_list) > 10:
        required_fields_summary += f" (and {len(required_fields_list) - 10} more)"
    
    # Format the todo generation prompt
    todo_prompt_formatted: str = todo_generation_prompt.format(
        bundle_id=bundle_id,
        direction_type=direction_type,
        episode_context=episode_context,
        objective=objective,
        entity_names=entity_names_str,
        starter_sources=sources_str,
        required_fields_summary=required_fields_summary
    )
    
    logger.info(f"🧠 Generating TodoList for {direction_type} in bundle {bundle_id}")
    
    todo_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        response_format=ProviderStrategy(TodoListOutput), 
        name="todo_list_generation_agent",
    )
    
    response = await todo_agent.ainvoke(
        {"messages": [{"role": "user", "content": todo_prompt_formatted}]}
    )
    
    # Get minimal LLM output
    todo_list_output: TodoListOutput = response["structured_response"]
    
    # Convert to full TodoList with temporal data and counts
    todo_list_final: TodoList = convert_output_to_state(todo_list_output) 

    await save_json_artifact(
        todo_list_final.model_dump(),
        bundle_id,
        "todo_list",
        suffix=f"{direction_type}_{datetime.now(timezone.utc).isoformat()}",
    )
    
    logger.info(f"✅ Generated {todo_list_final.totalTodos} todos for {direction_type}")
    
    return {
        "todo_list": todo_list_final,
        "llm_calls": state.get("llm_calls", 0) + 1,
    }  


# Inside of the tools we have to do something with messages at the checkpointing level 


async def perform_direction_research_node(state: EntityIntelResearchDirectionState) -> EntityIntelResearchDirectionState: 
    """
    Main research loop node: calls the LLM with tools to work on todos.
    Uses llm_calls counter to determine whether to use full or reminder prompt.
    """
    todo_list: TodoList = state.get("todo_list")
    messages: List[BaseMessage] = state.get("messages", [])
    run_id: str = state.get("run_id", "unknown")
    direction_type: DirectionType = state.get("direction_type", "UNKNOWN")
    plan: Dict[str, Any] = state.get("plan", {})
    episode: Dict[str, Any] = state.get("episode", {})
    bundle_id: str = state.get("bundle_id", "unknown")
    steps_taken: int = state.get("steps_taken", 0)
    llm_calls: int = state.get("llm_calls", 0)
    
    # Build todo summary
    todo_summary: str = "\n".join([
        f"- [{t.status.upper()}] {t.id}: {t.description} (Priority: {t.priority or 'MEDIUM'})" 
        for t in (todo_list.todos if todo_list else [])
    ]) if todo_list else "No todos available"
    
    # Add completion counts
    if todo_list:
        todo_summary: str = f"""Total: {todo_list.totalTodos} | Completed: {todo_list.completedCount} | In Progress: {todo_list.inProgressCount} | Pending: {todo_list.pendingCount}

{todo_summary}"""
    
    # Build entity context
    entity_name: str = plan.get('chosen', {}).get('entityName', 'Unknown Entity')
    entity_context: str = f"{entity_name}"
    if episode.get('title'):
        entity_context += f" (Episode: {episode.get('title')})"
    
    # Determine which prompt to use based on llm_calls
    # First call (llm_calls == 0 after increment in generate_todos): use MAIN prompt
    # Subsequent calls: use REMINDER prompt
    if llm_calls <= 1:
        # First research call - use comprehensive prompt
        max_steps: int = state.get("max_steps", 30)
        research_prompt: str = get_main_research_prompt(
            bundle_id=bundle_id,
            direction_type=direction_type,
            plan=plan,
            todo_summary=todo_summary,
            entity_context=entity_context,
            max_steps=max_steps
        )
        logger.info(f"🔬 Research INITIAL call for {direction_type} (run_id={run_id})")
    else:
        # Subsequent calls - use reminder prompt
        tool_calls_count: int = state.get("tool_calls", 0)
        research_prompt: str = get_reminder_research_prompt( 
            bundle_id=bundle_id,
            direction_type=direction_type,
            todo_summary=todo_summary,
            steps_taken=steps_taken,
            llm_calls=llm_calls,
            tool_calls=tool_calls_count
        )
        logger.info(f"🔬 Research step {steps_taken + 1} for {direction_type} (llm_calls={llm_calls}, run_id={run_id})")
    
    model_with_research_tools: BaseChatModel = gpt_5_mini.bind_tools(ALL_RESEARCH_TOOLS)
    
    # Handle message history correctly
    if not messages:
        # First call: store the initial prompt and response in state
        messages_to_send: List[BaseMessage] = [HumanMessage(content=research_prompt)]
        response_message = await model_with_research_tools.ainvoke(messages_to_send)
        
        # Log if model wants to call tools
        response_tool_calls = getattr(response_message, "tool_calls", []) or []
        if response_tool_calls:
            tool_names = [tc.get("name", "unknown") for tc in response_tool_calls]
            logger.info(f"   → LLM requesting {len(response_tool_calls)} tool(s): {', '.join(tool_names[:3])}{'...' if len(tool_names) > 3 else ''}")
        
        # Return both prompt and response to store in state
        return {
            "messages": [HumanMessage(content=research_prompt), response_message],
            "llm_calls": llm_calls + 1,
        }
    else:
        # Subsequent calls: prepend ephemeral reminder prompt, but only return response
        # This keeps the reminder out of state (it's dynamic) while maintaining conversation history
        messages_to_send: List[BaseMessage] = [HumanMessage(content=research_prompt)] + messages
        response_message = await model_with_research_tools.ainvoke(messages_to_send)
        
        # Log if model wants to call tools
        response_tool_calls = getattr(response_message, "tool_calls", []) or []
        if response_tool_calls:
            tool_names = [tc.get("name", "unknown") for tc in response_tool_calls]
            logger.info(f"   → LLM requesting {len(response_tool_calls)} tool(s): {', '.join(tool_names[:3])}{'...' if len(tool_names) > 3 else ''}")
        
        # Only return the response (reminder prompt is ephemeral, not stored)
        return {
            "messages": [response_message],
            "llm_calls": llm_calls + 1,
        }




research_tools_prebuilt_node: ToolNode = ToolNode(ALL_RESEARCH_TOOLS)


async def research_tools_node(
    state: EntityIntelResearchDirectionState,
) -> EntityIntelResearchDirectionState:
    """
    Execute tool calls requested by the last AI message via ToolNode.

    Assumes StateGraph-style inputs/outputs:
      - input:  {"messages": [...] , ...}
      - output: {"messages": [ToolMessage, ...]}
    """
    messages: List[BaseMessage] = state.get("messages") or []
    if not messages:
        return {"messages": []}

    last_message: BaseMessage = messages[-1]
    tool_calls: List[Dict[str, Any]] | List[ToolMessage] = getattr(last_message, "tool_calls", None) or []
    if not tool_calls:
        return {"messages": []}

    direction_type: DirectionType | str = state.get("direction_type", "UNKNOWN")

    tool_names: List[str] = [tc.get("name", "unknown") for tc in tool_calls]
    tool_ids: List[str] = [tc.get("id", "no-id") for tc in tool_calls]
    logger.info(
        f"🔧 [{direction_type}] Executing {len(tool_calls)} tool call(s): "
        f"{', '.join(tool_names[:3])}{'...' if len(tool_names) > 3 else ''}"
    )
    logger.debug(f"   Tool call IDs: {tool_ids[:3]}{'...' if len(tool_ids) > 3 else ''}")

    # ToolNode can return either a dict with {"messages": [...]} or a list directly
    result = await research_tools_prebuilt_node.ainvoke(state)
    
    # Handle both return types (dict or list)
    if isinstance(result, dict):
        tool_messages: List[ToolMessage] = result.get("messages", [])
    elif isinstance(result, list):
        tool_messages: List[ToolMessage] = result
    else:
        logger.error(f"Unexpected result type from ToolNode: {type(result)}")
        tool_messages: List[ToolMessage] = []
    
    logger.info(f"   ✓ Tool execution complete: {len(tool_messages)} result message(s)")
    for i, msg in enumerate(tool_messages[:3]):
        if hasattr(msg, "name") and hasattr(msg, "content"):
            content = str(msg.content)
            preview = content[:100] + "..." if len(content) > 100 else content
            logger.debug(f"      [{i+1}] {msg.name}: {preview}")

    # Decide what you want tool_calls to mean:
    # Option A (recommended): count tool CALLS executed (matches "total tool calls executed")
    total_tool_calls: int = state.get("tool_calls", 0) + len(tool_calls)

    # Return only the delta; your messages reducer will append these ToolMessages
    return {
        "messages": tool_messages,
        "tool_calls": total_tool_calls,
    }


def should_continue_research(state: EntityIntelResearchDirectionState) -> Literal["research_tools_node", "perform_research", "finalize_research"]:
    """
    Determine next step in research loop:
    - If there are tool calls -> execute them
    - If max steps reached -> finalize
    - If all todos complete -> finalize
    - Otherwise -> continue research
    """
    messages: List[BaseMessage] = state.get("messages", [])
    if not messages:
        return "finalize_research"
    
    last_message: BaseMessage = messages[-1]
    tool_calls: List[Dict[str, Any]] | List[ToolMessage] = getattr(last_message, "tool_calls", []) or []
    
    # If model wants to call tools, execute them
    if tool_calls:
        return "research_tools_node"
    
    # Check if we've hit max steps
    max_steps: int = state.get("max_steps", 30)
    steps_taken: int = state.get("steps_taken", 0)
    if steps_taken >= max_steps:
        logger.warning(f"⚠️  Max steps ({max_steps}) reached, finalizing research")
        return "finalize_research"
    
    # Check if all todos are complete
    todo_list: TodoList = state.get("todo_list")
    if todo_list and todo_list.completedCount == todo_list.totalTodos and todo_list.totalTodos > 0:
        logger.info(f"✅ All todos complete ({todo_list.completedCount}/{todo_list.totalTodos}), finalizing")
        return "finalize_research"
    
    # Continue research
    return "perform_research"  



async def finalize_research_node(state: EntityIntelResearchDirectionState) -> EntityIntelResearchDirectionState:
    """
    Finalize the research for this direction by synthesizing all file_refs into a final report.
    
    Strategy:
    1. Group file_refs by entity_key
    2. Read all files for each entity
    3. Use LLM to synthesize into ONE final report per entity
    4. Save final report(s) and add to structured_outputs
    """
    direction_type: DirectionType | str = state.get("direction_type")
    run_id: str = state.get("run_id", "unknown")
    bundle_id: str = state.get("bundle_id", "unknown")
    todo_list: TodoList = state.get("todo_list")
    steps_taken: int = state.get("steps_taken", 0)
    llm_calls: int = state.get("llm_calls", 0)
    tool_calls: int = state.get("tool_calls", 0)
    file_refs: List[FileReference] = state.get("file_refs", [])
    citations: List[TavilyCitation] = state.get("citations", [])
    plan: Dict[str, Any] = state.get("plan", {})
    
    logger.info(f"""
🏁 Finalizing Research: {direction_type} (run_id={run_id})
   Steps: {steps_taken} | LLM Calls: {llm_calls} | Tool Calls: {tool_calls}
   Files Created: {len(file_refs)} | Citations: {len(citations)}
   Todos: {todo_list.completedCount if todo_list else 0}/{todo_list.totalTodos if todo_list else 0} completed
""")
    
    # If no files were created, just log and return
    if not file_refs:
        logger.warning(f"⚠️  No files created for {direction_type}, skipping synthesis")
        return {
            "research_notes": [f"Completed {direction_type} with no file outputs"],
        }
    
    # Group file_refs by entity_key
    files_by_entity: Dict[str, List[FileReference]] = {}
    for file_ref in file_refs:
        entity_key: str = file_ref.entity_key or "unknown_entity"
        if entity_key not in files_by_entity:
            files_by_entity[entity_key] = []
        files_by_entity[entity_key].append(file_ref)
    
    logger.info(f"📁 Grouped {len(file_refs)} files into {len(files_by_entity)} entities")
    
    # Read all files and create content string for synthesis
    files_content_parts: List[str] = []
    for entity_key, refs in files_by_entity.items():
        files_content_parts.append(f"\n## Entity: {entity_key}\n")
        for ref in refs:
            try:
                content = await read_file(ref.file_path)
                files_content_parts.append(f"""
        ### File: {ref.file_path}
        Description: {ref.description or 'N/A'}
            Content:
            {content}
            ---
            """)
            except FileNotFoundError:
                logger.warning(f"File not found: {ref.file_path}")
            except Exception as e:
                logger.error(f"Error reading {ref.file_path}: {e}")
    
    files_content: str = "\n".join(files_content_parts)
    
    # Extract objective and required fields from plan
    objective: str = plan.get('chosen', {}).get('objective', f'Complete research for {direction_type}')
    required_fields: List[Union[GuestFieldEnum, BusinessFieldEnum, ProductFieldEnum, CompoundFieldEnum, PlatformFieldEnum]] = plan.get('required_fields', [])
    entity_names: List[str] = list(files_by_entity.keys())
    
    # Generate direction-specific synthesis prompt
    synthesis_prompt: str = get_direction_synthesis_prompt(
        direction_type=direction_type,
        objective=objective,
        entity_names=entity_names,
        files_content=files_content,
        required_fields=required_fields
    )
    
    logger.info(f"🧠 Synthesizing final report for {direction_type}")
    
    # Call LLM for synthesis
    synthesis_model: BaseChatModel = gpt_5
    synthesis_response = await synthesis_model.ainvoke([
        HumanMessage(content=synthesis_prompt)
    ])
    
    # Get the synthesized report content
    final_report_narrative: str = synthesis_response.text
    
    # Build complete report with metadata header
   
    current_date: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    metadata_header: str = f"""---
RESEARCH REPORT METADATA
Direction: {direction_type}
Bundle ID: {bundle_id}
Run ID: {run_id}
Research Date: {current_date}
Objective: {objective}
Entities Researched: {', '.join(entity_names)}
Files Synthesized: {len(file_refs)}
Required Fields: {', '.join(required_fields)}
Research Quality:
  - Steps Taken: {steps_taken}
  - LLM Calls: {llm_calls}
  - Tool Calls: {tool_calls}
  - Total Sources: {len(citations)}
  - Todos Completed: {todo_list.completedCount if todo_list else 0}/{todo_list.totalTodos if todo_list else 0}
---

"""
    
    final_report_content: str = metadata_header + final_report_narrative
    
    # Save final report as markdown
    final_report_filename: str = f"final_report_{direction_type.lower()}_{bundle_id}.md"
    final_report_ref: FileReference = FileReference(
        file_path=final_report_filename,
        description=f"Final synthesized {direction_type} report for {', '.join(entity_names)}",
        bundle_id=bundle_id,
        entity_key=f"synthesis_{direction_type.lower()}"
    )
    
    try:
        await fs_write_file(final_report_filename, final_report_content)
        logger.info(f"✅ Final report saved: {final_report_filename} ({len(final_report_content)} chars)")
    except Exception as e:
        logger.error(f"❌ Failed to save final report: {e}")
    
    summary_note = f"Synthesized {len(files_by_entity)} entities into final {direction_type} report"
    
    return {
        "research_notes": [summary_note],
        "file_refs": [final_report_ref],
        "llm_calls": llm_calls + 1,
        "final_report": final_report_ref,
    }


# -----------------------------
# Direction Subgraph - Wire up nodes and edges
# -----------------------------

research_direction_graph_builder.add_node("generate_todos", generate_todos_node)
research_direction_graph_builder.add_node("perform_research", perform_direction_research_node)
research_direction_graph_builder.add_node("research_tools_node", research_tools_node)
research_direction_graph_builder.add_node("finalize_research", finalize_research_node)

research_direction_graph_builder.set_entry_point("generate_todos")

# After generating todos, start research
research_direction_graph_builder.add_edge("generate_todos", "perform_research")

# After research node, check if we should continue, execute tools, or finalize
research_direction_graph_builder.add_conditional_edges(
    "perform_research",
    should_continue_research,
    {
        "research_tools_node": "research_tools_node",
        "perform_research": "perform_research",
        "finalize_research": "finalize_research",
    },
)

# After executing tools, go back to research node
research_direction_graph_builder.add_edge("research_tools_node", "perform_research")

# After finalization, end
research_direction_graph_builder.add_edge("finalize_research", END)


# ========================================================================
# COMPILE ALL GRAPHS - Must be done after all nodes and edges are added
# ========================================================================

# Compile in order: innermost subgraph first, then middle, then parent
ResearchDirectionSubGraph: CompiledStateGraph = research_direction_graph_builder.compile()
BundleResearchSubGraph: CompiledStateGraph = research_subgraph_builder.compile()
BundlesParentGraph: CompiledStateGraph = research_parent_graph_builder.compile()