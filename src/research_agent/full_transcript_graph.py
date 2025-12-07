import os
import sys
import asyncio
import json
from uuid import uuid4
from pathlib import Path
from typing import Optional, List, Dict, Any, TypedDict, cast  
from langchain_core.prompts import PromptTemplate 

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI 
from langgraph.store.postgres.aio import AsyncPostgresStore 
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, START, END 
from langgraph.graph.state import CompiledStateGraph 
from langchain_core.runnables import RunnableConfig   
from graphql_client.async_base_client import AsyncBaseClient   
from urllib.parse import urlparse     
from research_agent.research_subgraph import research_subgraph_builder, DirectionResearchResult, ResearchState   
from research_agent.prompts.research_directions_prompts import RESEARCH_DIRECTIONS_SYSTEM_PROMPT, RESEARCH_DIRECTIONS_USER_PROMPT 
from research_agent.retrieval.async_mongo_client import get_episode, EpisodeDoc 
from research_agent.retrieval.async_s3_client import get_transcript_text_from_s3_url 

import aiofiles

# Windows-specific: psycopg requires SelectorEventLoop, not ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from research_agent.output_models import (
    TranscriptSummaryOutput, 
    ResearchDirectionOutput, 
    ResearchDirection, 
    GuestInfoModel,
    ExtractedEntityBase,
    SummaryOnlyOutput,
) 
from research_agent.prompts.prompts import (
    SUMMARY_SYSTEM_PROMPT, 
    summary_only_prompt,
    GUEST_EXTRACTION_SYSTEM_PROMPT,
    guest_extraction_prompt,
    summary_prompt,  # kept for backwards compatibility
)


# -----------------------------------------------------------------------------
# Environment & Paths
# -----------------------------------------------------------------------------

load_dotenv()   



graphql_auth_token = os.getenv("GRAPHQL_AUTH_TOKEN")
graphql_url = os.getenv("GRAPHQL_LOCAL_URL")  # e.g., "http://localhost:4000/graphql" 

tavily_api_key = os.getenv("TAVILY_API_KEY")
firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY") 

ncbi_api_key = os.getenv("NCBI_API_KEY") 


# Load in Langsmith Versioned Prompts here  


# Convert HTTP URL to WebSocket URL
parsed = urlparse(graphql_url)
ws_url = f"ws://{parsed.netloc}{parsed.path}"  # e.g., "ws://localhost:4000/graphql"

async_graphql_client = AsyncBaseClient(
    url=graphql_url,
    ws_url=ws_url,  # Add this for WebSocket subscriptions
    headers={"Authorization": f"Bearer {graphql_auth_token}"},
    ws_headers={"Authorization": f"Bearer {graphql_auth_token}"},  # Auth for WebSocket too
)

# Adjust this if your layout is different:
# Assuming: project_root/dev_env/... and this file in src/research_agent/ 

# Conceptually we want to 
PROJECT_ROOT = Path(__file__).resolve().parents[2]  

PARENT_DIR = Path(__file__).resolve().parent   
DATA_DIR = PARENT_DIR / "dev_env" / "data"
OUTPUT_DIR = PARENT_DIR / "dev_env" / "summary_graph_outputs"

TRANSCRIPT_FILE = DATA_DIR / "full_transcript_two.txt"
WEBPAGE_SUMMARY_FILE = DATA_DIR / "webpage_summary_two.md"

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")




# -----------------------------------------------------------------------------
# LangChain Models
# -----------------------------------------------------------------------------

summary_model = ChatOpenAI(
    model="gpt-5-nano",
    reasoning_effort="medium",
    temperature=0.0,
    output_version="responses/v1",
    max_retries=2,
)

web_search_model = ChatOpenAI(
    model="gpt-5-nano",
    temperature=0.0,
    output_version="responses/v1",
    max_retries=2,
) 

general_model = ChatOpenAI(
    model="gpt-5-nano",
    temperature=0.0,
    output_version="responses/v1",
    max_retries=2,
) 

openai_search_tool = {"type": "web_search"}  # passed into create_agent tools 




class TranscriptGraph(TypedDict, total=False):
    episode_meta: Dict[str, Any]
    webpage_summary: str
    full_transcript: str 
    initial_transcript_output: TranscriptSummaryOutput  
    research_directions: List[ResearchDirection]

    # outputs of the per-direction subgraphs
    direction_results: List[DirectionResearchResult]
    direction_structured_outputs: List[ExtractedEntityBase]

   


# -----------------------------------------------------------------------------
# Filesystem Helpers
# -----------------------------------------------------------------------------

async def write_summary_outputs_without_docs(
    summary_output: TranscriptSummaryOutput,
    output_dir: Path,
    episode_number: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / f"episode_{episode_number}_summary.txt"
    guest_path = output_dir / f"episode_{episode_number}_guest.json"

    async with aiofiles.open(summary_path, "w", encoding="utf-8") as f:
        await f.write(summary_output.summary)

    async with aiofiles.open(guest_path, "w", encoding="utf-8") as f:
        await f.write(summary_output.guest_information.model_dump_json(indent=2))

    print(f"Finished writing summary outputs for episode {episode_number}")




# -----------------------------------------------------------------------------
# Graph Nodes
# -----------------------------------------------------------------------------

async def summarize_transcript(state: TranscriptGraph) -> TranscriptGraph:
    """
    Run summary and guest extraction in parallel, then combine results.
    
    This splits the work into two focused agents:
    1. Summary agent - focuses only on producing the episode summary
    2. Guest agent - focuses only on extracting guest information
    
    Both run concurrently and their outputs are combined into TranscriptSummaryOutput.
    """
    webpage_summary = state.get("webpage_summary")
    full_transcript = state.get("full_transcript")

    if not webpage_summary or not full_transcript:
        raise Exception("webpage_summary and full_transcript are required for this graph")

    # Format prompts for both agents
    formatted_summary_prompt = summary_only_prompt.format(
        webpage_summary=webpage_summary,
        full_transcript=full_transcript,
    )
    
    formatted_guest_prompt = guest_extraction_prompt.format(
        webpage_summary=webpage_summary,
    )

    # Create both agents with their respective output formats
    summary_agent = create_agent(
        summary_model,
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        response_format=SummaryOnlyOutput,
    )
    
    guest_agent = create_agent(
        summary_model,
        system_prompt=GUEST_EXTRACTION_SYSTEM_PROMPT,
        response_format=GuestInfoModel,
    )

    # Run both agents in parallel
    summary_task = summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": formatted_summary_prompt}]}
    )
    guest_task = guest_agent.ainvoke(
        {"messages": [{"role": "user", "content": formatted_guest_prompt}]}
    )
    
    # Await both concurrently
    summary_response, guest_response = await asyncio.gather(summary_task, guest_task)

    # Extract structured responses
    summary_output: SummaryOnlyOutput = summary_response["structured_response"]
    guest_output: GuestInfoModel = guest_response["structured_response"]

    # Combine into the final TranscriptSummaryOutput
    transcript_output = TranscriptSummaryOutput(
        summary=summary_output.summary,
        guest_information=guest_output,
    )

    # Write outputs to disk
    episode_number = state["episode_meta"]["episode_number"]
    await write_summary_outputs_without_docs(
        summary_output=transcript_output,
        output_dir=OUTPUT_DIR,
        episode_number=episode_number,
    )

    # Return partial state update (LangGraph merges this into the state)
    return {"initial_transcript_output": transcript_output} 



async def generate_research_directions(state: TranscriptGraph) -> TranscriptGraph:
    """
    Use the initial transcript summary + guest information to propose
    a set of ResearchDirection objects for downstream research.

    Guarantees:
    - At least one direction is centered on the guest as a person
      (and their company/product when available).
    """
    initial_output = state.get("initial_transcript_output")
    if initial_output is None:
        raise Exception(
            "Missing 'initial_transcript_output' in state; cannot generate research directions."
        )

    # Typed: TranscriptSummaryOutput
    episode_summary: str = initial_output.summary
    guest_info: GuestInfoModel = initial_output.guest_information

    guest_name = guest_info.name
    guest_description = guest_info.description
    guest_company = guest_info.company or "(not specified)"
    guest_product = guest_info.product or "(not specified)"

    # Build the user instructions
    user_instructions = RESEARCH_DIRECTIONS_USER_PROMPT.format(
        episode_summary=episode_summary,
        guest_name=guest_name,
        guest_description=guest_description,
        guest_company=guest_company,
        guest_product=guest_product,
    )

    # Create the agent that returns ResearchDirectionOutput
    research_directions_agent = create_agent(
        general_model,
        system_prompt=RESEARCH_DIRECTIONS_SYSTEM_PROMPT,
        response_format=ResearchDirectionOutput,
    )

    # Call the agent with system + user messages
    research_directions_response = await research_directions_agent.ainvoke(
        {
            "messages": [
                {"role": "user", "content": user_instructions},
            ]
        }
    )

    research_directions_output: ResearchDirectionOutput = (
        research_directions_response["structured_response"]
    )

    return {
        "research_directions": research_directions_output.research_directions,
    }




research_subgraph: "CompiledStateGraph" = research_subgraph_builder.compile() 

async def run_research_directions(state: TranscriptGraph) -> TranscriptGraph:
    """
    For each ResearchDirection in the episode, run the research_subgraph and
    aggregate the results back onto the TranscriptGraph state.
    """
    directions: List[ResearchDirection] = state.get("research_directions", []) or []

    if not directions:
        # Nothing to do; return state unchanged
        return {
            "direction_results": [],
            "direction_structured_outputs": [],
        }

    episode_context = ""
    if state.get("initial_transcript_output") is not None:
        # whatever your summary field is called:
        episode_context = getattr(
            state["initial_transcript_output"], "summary", ""
        ) or ""

    all_direction_results: List[DirectionResearchResult] = []
    all_structured_outputs: List[ExtractedEntityBase] = []

    # Run subgraph once per direction (sequentially).
    # You can later add bounded concurrency here with asyncio.gather if needed.
    for direction in directions:
        initial_child_state: ResearchState = {
            "messages": [],
            "llm_calls": 0,
            "tool_calls": 0,
            "direction": direction,
            "episode_context": episode_context,
            "research_notes": [],
            "citations": [],
            "file_refs": [],  # For file-based context offloading
            "steps_taken": 0,
            "structured_outputs": [],
        }

        child_final: ResearchState = cast(
            ResearchState,
            await research_subgraph.ainvoke(initial_child_state),
        )

        # pull out the master result for this direction
        if "result" in child_final and child_final["result"] is not None:
            all_direction_results.append(child_final["result"])

        # merge any entities created
        if "structured_outputs" in child_final and child_final["structured_outputs"]:
            all_structured_outputs.extend(child_final["structured_outputs"])

    return {
        "direction_results": all_direction_results,
        "direction_structured_outputs": all_structured_outputs,
    }



# Guest Output should go to subgraph with wikipedia tool in addition to firecrawl and tavily or just go to another node in this graph 
# for guest output 
# Or guest output is part of Research Directions 

# -----------------------------------------------------------------------------
# Build the Graph
# -----------------------------------------------------------------------------

graph = StateGraph(TranscriptGraph)

graph.add_node("summarize_transcript", summarize_transcript) 
graph.add_node("generate_research_directions", generate_research_directions)  
graph.add_node("run_research_directions", run_research_directions)   



graph.add_edge(START, "summarize_transcript") 
graph.add_edge("summarize_transcript", "generate_research_directions")   
graph.add_edge("generate_research_directions", "run_research_directions")    

graph.add_edge("run_research_directions", END)  

# Generates a List of Research Directions how map out the subgraph or whatever operation strategy 

# Compile without checkpointer for langgraph dev server compatibility
# The dev server will inject its own in-memory checkpointer
app: CompiledStateGraph = graph.compile()   


# initial_state: TranscriptGraph = {
#     "episode_meta": {
#         "episode_number": 1303,
#     },
#     "webpage_summary": WEBPAGE_SUMMARY_FILE.read_text(encoding="utf-8"),
#     "full_transcript": TRANSCRIPT_FILE.read_text(encoding="utf-8"),
# } 





# -----------------------------------------------------------------------------
# Main: run the graph, persist checkpoints, pretty-print final state
# -----------------------------------------------------------------------------

async def one_full_transcript_graph_run(episode_page_url: str) -> None:    
    # Import here to avoid module-level async context manager issues
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from pprint import pprint  

    episode_doc: EpisodeDoc = await get_episode(episode_page_url=episode_page_url)  

    episode_meta = { 
        "episode_number": episode_doc["episodeNumber"] if episode_doc["episodeNumber"] is not None else "Unknown", 
        "episode_page_url": episode_doc["episodePageUrl"] if episode_doc["episodePageUrl"] is not None else "Unknown", 
        "episode_transcript_url": episode_doc["episodeTranscriptUrl"] if episode_doc["episodeTranscriptUrl"] is not None else "Unknown", 
    }  

    full_transcript = await get_transcript_text_from_s3_url(episode_doc["s3TranscriptUrl"]) 

    webpage_summary = episode_doc.get("webPageSummary")    

    initial_state: TranscriptGraph = {
        "episode_meta": episode_meta,
        "webpage_summary": webpage_summary,
        "full_transcript": full_transcript,
    }

    
    pg_password = os.getenv("POSTGRES_PASSWORD")  
    pg_db_name = os.getenv("POSTGRES_DB")   
    pg_url = f"postgresql://postgres:{pg_password}@localhost:5432/{pg_db_name}"
    
    # Use AsyncPostgresSaver as an async context manager
    async with ( AsyncPostgresSaver.from_conn_string(pg_url) as checkpointer, 
                 AsyncPostgresStore.from_conn_string(pg_url) as store,
    
    ):
        await checkpointer.setup()
        await store.setup()
        
        # Recompile the graph with the checkpointer for persistence
        app_with_checkpointer = graph.compile(checkpointer=checkpointer, store=store)

        config = {
            "configurable": {
                "thread_id": str(uuid4()),
                "checkpoint_ns": "transcript_graph",
            }
        } 

        # Single final result (no streaming)
        final_state: TranscriptGraph = await app_with_checkpointer.ainvoke(initial_state, config)

        # Pretty-print to console
        print("\n=== FINAL GRAPH STATE ===")
        pprint(final_state)

        # Also save full state to disk for inspection
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True) 

        final_state_id = str(uuid4())
        state_path = OUTPUT_DIR / f"final_state_{final_state_id}.json"

        # Convert Pydantic models to dicts before dumping
        serializable_state: Dict[str, Any] = dict(final_state)

        if "initial_transcript_output" in serializable_state:
            serializable_state["initial_transcript_output"] = (
                serializable_state["initial_transcript_output"].model_dump()
            )

        if "guest_research_result" in serializable_state and serializable_state["guest_research_result"] is not None:
            serializable_state["guest_research_result"] = (
                serializable_state["guest_research_result"].model_dump()
            )

        if "guest_research_history" in serializable_state and serializable_state["guest_research_history"]:
            serializable_state["guest_research_history"] = [
                item.model_dump() for item in serializable_state["guest_research_history"]
            ]

        async with aiofiles.open(state_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(serializable_state, indent=2))

        print(f"\nFinal state written to: {state_path}")


if __name__ == "__main__":
    asyncio.run(one_full_transcript_graph_run("https://daveasprey.com/james-baber-toxic-mold-hidden-dangers-198/"))  
    # print(TRANSCRIPT_FILE.read_text())