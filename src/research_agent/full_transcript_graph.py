import os
import sys
import asyncio
import json
from uuid import uuid4
from pathlib import Path
from typing import (Optional, Union, Tuple, List, Dict, Any, TypedDict, 
 Iterable, Literal, Mapping, AsyncIterator, cast) 
from contextlib import asynccontextmanager    
import operator 
from typing_extensions import Annotated 
from langchain_core.prompts import PromptTemplate  
from langgraph.checkpoint.base import BaseCheckpointSaver

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI 
from langgraph.store.postgres.aio import AsyncPostgresStore  
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver 
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, START, END 
from langgraph.graph.state import CompiledStateGraph 
from langchain_core.runnables import RunnableConfig    
from langgraph.store.base import BaseStore 
from graphql_client.async_base_client import AsyncBaseClient   
from urllib.parse import urlparse     
from research_agent.entity_intel_subgraph import entity_intel_subgraph_builder, EntityIntelResearchState    
from research_agent.evidence_research_subgraph import evidence_research_subgraph_builder, EvidenceResearchState    
from research_agent.prompts.research_directions_prompts import RESEARCH_DIRECTIONS_SYSTEM_PROMPT, RESEARCH_DIRECTIONS_USER_PROMPT 
from research_agent.retrieval.async_mongo_client import get_episode, EpisodeDoc 
from research_agent.retrieval.async_s3_client import get_transcript_text_from_s3_url  
from research_agent.common.artifacts import save_json_artifact, save_text_artifact   
from research_agent.common.logging_utils import configure_logging     
from copy import deepcopy 
from pprint import pprint 
import logging 

from langmem import create_memory_store_manager

import aiofiles

# Windows-specific: psycopg requires SelectorEventLoop, not ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from research_agent.output_models import (
    TranscriptSummaryOutput, 
    ResearchDirectionOutput, 
    ResearchDirection, 
    GuestInfoModel,
    SummaryAndAttributionOutput,
    AttributionQuote,
    ResearchDirectionType, 
    EntitiesIntelResearchResult,   
    ResearchEntities 
)   



from research_agent.graph_states.evidence_research_subgraph import EvidenceResearchResult
from research_agent.prompts.prompts import (
    SUMMARY_SYSTEM_PROMPT, 
    summary_only_prompt,
    GUEST_EXTRACTION_SYSTEM_PROMPT,
    guest_extraction_prompt,
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

pg_password = os.getenv("POSTGRES_PASSWORD")  
pg_db_name = os.getenv("POSTGRES_DB")   
pg_url = f"postgresql://postgres:{pg_password}@localhost:5432/{pg_db_name}"

DEFAULT_MEMORY_NAMESPACE: Tuple[str, str] = ("memories", "transcript_graph")
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
    model="gpt-5",
    reasoning_effort="medium",
    temperature=0.0,
    output_version="responses/v1",
    max_retries=2,
) 

guest_extraction_model = ChatOpenAI(
    model="gpt-4.1",
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


DirectionResearchResult = Union[EvidenceResearchResult, EntitiesIntelResearchResult] 

class TranscriptGraph(TypedDict, total=False):
    # Core episode context
    episode_meta: Dict[str, Any]
    webpage_summary: str
    full_transcript: str
    initial_transcript_output: TranscriptSummaryOutput
    attribution_quotes: List[AttributionQuote]
    research_directions: List[ResearchDirection]

    evidence_direction_results: Annotated[
        List[EvidenceResearchResult],
        operator.add
    ]

    # Entity-intel-only direction-level results
    entity_direction_results: Annotated[
        List[EntitiesIntelResearchResult],
        operator.add
    ]

    # Evidence-only structured outputs (e.g., EvidenceItem, progress snapshots, etc.)
    evidence_structured_outputs: Annotated[
        List[BaseModel],   # or List[EvidenceItem] if you want to be strict
        operator.add
    ]

    # Entity-intel-only structured outputs (e.g., ExtractedEntityBase)
    entity_structured_outputs: Annotated[
        List[BaseModel],   # or List[ExtractedEntityBase] if you want to be strict
        operator.add
    ]

    # Combined direction-level results across ALL directions
    direction_results: Annotated[
        List[DirectionResearchResult],  # Union[EvidenceResearchResult, EntitiesIntelResearchResult]
        operator.add
    ]

    # Combined structured outputs across ALL directions
    direction_structured_outputs: Annotated[
        List[BaseModel],
        operator.add
    ]


# -----------------------------------------------------------------------------
# Filesystem Helpers
# -----------------------------------------------------------------------------
GRAPH_SNAPSHOT_OUTPUT_DIR = PARENT_DIR / "dev_env" / "graph_snapshots"

async def dump_final_state_snapshot(
    app: CompiledStateGraph,
    config: RunnableConfig,
    *,
    thread_id: str,
) -> str:
    """
    Get the final StateSnapshot from LangGraph for this config
    and dump its .values (full state) to disk as JSON.
    """
    # Use LangGraph API to inspect state
    snapshot = await app.aget_state(config)  # or app.get_state(config) in sync code
    final_values: dict[str, Any] = snapshot.values

    # Use your artifact utilities to save it
    # We treat episode_id like the "direction_id" directory bucket
    return await save_json_artifact(
        data=final_values,
        base_dir=GRAPH_SNAPSHOT_OUTPUT_DIR,
        direction_id=thread_id,
        artifact_type="final_state",
        suffix=str(uuid4())[:8],  # optional, just to distinguish runs
    )

async def write_summary_outputs_without_docs(
    summary_output: TranscriptSummaryOutput,
    output_dir: Path,
    episode_number: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / f"episode_{uuid4()}-{episode_number}_summary.txt"
    guest_path = output_dir / f"episode_{uuid4()}-{episode_number}_guest.json"

    async with aiofiles.open(summary_path, "w", encoding="utf-8") as f:
        await f.write(summary_output.summary)

    async with aiofiles.open(guest_path, "w", encoding="utf-8") as f:
        await f.write(summary_output.guest_information.model_dump_json(indent=2))

    print(f"Finished writing summary outputs for episode {episode_number}")


def with_checkpoint_ns(
    config: RunnableConfig,
    checkpoint_ns: str,
) -> RunnableConfig:
    """Copy the parent config and override checkpoint_ns."""
    cfg = deepcopy(config) if config is not None else {}
    configurable = dict(cfg.get("configurable") or {})
    configurable["checkpoint_ns"] = checkpoint_ns
    cfg["configurable"] = configurable
    return cfg

def select_subgraph_for_direction(
    direction: ResearchDirection,
) -> Literal["evidence", "entity"]:
    """
    Decide which compiled subgraph to use for this ResearchDirection.
    """
    dt = direction.direction_type

    if dt in {
        ResearchDirectionType.CLAIM_VALIDATION,
        ResearchDirectionType.MECHANISM_EXPLANATION,
        ResearchDirectionType.RISK_BENEFIT_PROFILE,
        ResearchDirectionType.COMPARATIVE_EFFECTIVENESS,
    }:
        return "evidence"

    if dt == ResearchDirectionType.ENTITIES_DUE_DILIGENCE:
        return "entity"

    # Fallback: treat unknown types as evidence-oriented
    return "evidence" 

MAX_PARALLEL_DIRECTIONS=2   

evidence_research_graph = ["research_graph"] 
entity_intel_graph = ["entity_intel_graph"]  


# Wrong  

def create_initial_subgraph_state( 
    subgraph_type: Literal["evidence", "entity"], 
    direction: ResearchDirection,
    episode_context: str, 
):  


    if subgraph_type == "entity": 
        return EntityIntelResearchState( 
            messages=[], 
            llm_calls=0, 
            tool_calls=0, 
            direction=direction,
            episode_context=episode_context,
            research_notes=[],
            citations=[],
            file_refs=[],
            steps_taken=0,
            structured_outputs=[], 
            result=None, 
        ) 
    else: 
        return EvidenceResearchState( 
            messages=[], 
            llm_calls=0, 
            tool_calls=0, 
            direction=direction,
            episode_context=episode_context,
            research_notes=[], 
            evidence_items=[],
            citations=[],
            file_refs=[], 
            steps_taken=0, 
            summaries_written=0,
            claim_validation_progress=[],
            mechanism_explanation_progress=[],
            risk_benefit_progress=[],
            comparative_progress=[],
            structured_outputs=[], 
            result=None, 
        )


class SingleDirectionRunResult(TypedDict):
    kind: Literal["evidence", "entity"]
    direction: ResearchDirection
    result: DirectionResearchResult | None   
    structured_outputs: List[BaseModel]      


async def run_single_direction(
    direction: ResearchDirection,
    episode_context: str,
    semaphore: asyncio.Semaphore,
    evidence_subgraph_app: CompiledStateGraph, 
    entity_intel_subgraph_app: CompiledStateGraph,  
    config: RunnableConfig,
) -> SingleDirectionRunResult:
    """
    Run the appropriate subgraph (evidence or entity) for a single ResearchDirection.

    The compiled subgraphs are passed in so we don't rely on globals and can
    ensure they share the same checkpointer/store as the parent.
    """
    async with semaphore:
        subgraph_kind = select_subgraph_for_direction(direction)

        if subgraph_kind == "evidence":
            subgraph = evidence_subgraph_app
            initial_child_state: EvidenceResearchState = create_initial_subgraph_state(
                subgraph_type="evidence",
                direction=direction,
                episode_context=episode_context,
            ) 

            sub_config = with_checkpoint_ns(config, "evidence_subgraph")

            child_final = cast(
                EvidenceResearchState,
                await subgraph.ainvoke(initial_child_state, config=sub_config),
            )

        else:
            subgraph = entity_intel_subgraph_app
            initial_child_state: EntityIntelResearchState = create_initial_subgraph_state(
                subgraph_type="entity",
                direction=direction,
                episode_context=episode_context,
            )

            sub_config = with_checkpoint_ns(config, "entity_intel_subgraph")

            child_final = cast(
                EntityIntelResearchState,
                await subgraph.ainvoke(initial_child_state, config=sub_config),
            )

        # Extract result (may be None if the graph never set it)
        result: DirectionResearchResult | None = None
        if "result" in child_final and child_final["result"] is not None:
            result = child_final["result"]  # type: ignore[assignment]

        # Extract any structured outputs accumulated along the way
        structured_outputs: List[BaseModel] = []
        if "structured_outputs" in child_final and child_final["structured_outputs"]:
            structured_outputs = list(child_final["structured_outputs"])  # type: ignore[list-item]

        return SingleDirectionRunResult(
            kind=subgraph_kind,
            direction=direction,
            result=result,
            structured_outputs=structured_outputs,
        )
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
  
    
    formatted_guest_prompt = guest_extraction_prompt.format(
        webpage_summary=webpage_summary,
    )

    # Create both agents with their respective output formats
    summary_agent = create_agent(
        summary_model,
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        response_format=SummaryAndAttributionOutput,
    )
    
    guest_agent = create_agent(
        guest_extraction_model,
        system_prompt=GUEST_EXTRACTION_SYSTEM_PROMPT,
        response_format=GuestInfoModel,
    )  

    guest_response = await guest_agent.ainvoke(
        {"messages": [{"role": "user", "content": formatted_guest_prompt}]}
    ) 

    guest_output: GuestInfoModel = guest_response["structured_response"] 

    formatted_summary_prompt = summary_only_prompt.format(
        webpage_summary=webpage_summary,
        full_transcript=full_transcript,
        guest_name=guest_output.name,
        guest_description=guest_output.description,
        guest_company=guest_output.company or "(not specified)",
        guest_product=guest_output.product or "(not specified)",
    )

   
    summary_response = await summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": formatted_summary_prompt}]}
    ) 

    summary_output: SummaryAndAttributionOutput = summary_response["structured_response"]
   
    
    
    

    # Extract structured responses
    summary_output: SummaryAndAttributionOutput = summary_response["structured_response"]
    guest_output: GuestInfoModel = guest_response["structured_response"]

    # Combine into the final TranscriptSummaryOutput
    transcript_output = TranscriptSummaryOutput(
        summary=summary_output.summary,
        guest_information=summary_output.enhanced_guest_information,
        attribution_quotes=summary_output.attribution_quotes,
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
    guest_product = guest_info.product if len(guest_info.product)  else "(not specified)"  

    attribution_quotes = initial_output.attribution_quotes   

    attribution_quotes_text = "\n".join([f" Speaker: {quote.speaker} - Quote: {quote.statement} -Paraphrased Statement: {quote.statement} - Verbatim: {quote.verbatim}" for quote in attribution_quotes])




    # Build the user instructions
    user_instructions = RESEARCH_DIRECTIONS_USER_PROMPT.format(
        episode_summary=episode_summary, 
        retrieved_memories="",  
        guest_name=guest_name,
        guest_description=guest_description,
        guest_company=guest_company if guest_company is not None else "(not specified)",
        guest_product="\n".join([product for product in guest_product]) if guest_product is not None else "(not specified)",
        expertise_areas="\n".join([area for area in guest_info.expertise_areas]) if guest_info.expertise_areas is not None else "(not specified)",
        motivation_or_origin_story=guest_info.motivation_or_origin_story if guest_info.motivation_or_origin_story is not None else "(not specified)",
        notable_health_history=guest_info.notable_health_history if guest_info.notable_health_history is not None else "(not specified)",
        key_contributions="\n".join([contribution for contribution in guest_info.key_contributions]) if guest_info.key_contributions is not None else "(not specified)",
        attribution_quotes=attribution_quotes_text,
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


def compile_subgraphs(
    checkpointer: BaseCheckpointSaver,
    store: BaseStore,  
) -> tuple[CompiledStateGraph, CompiledStateGraph]:
    evidence_subgraph_app = evidence_research_subgraph_builder.compile(
        checkpointer=checkpointer,
        store=store, 
        
    )
    entity_intel_subgraph_app = entity_intel_subgraph_builder.compile(
        checkpointer=checkpointer,
        store=store,
        
    )
    return evidence_subgraph_app, entity_intel_subgraph_app


async def run_research_directions(
    state: TranscriptGraph,
    config: RunnableConfig,
    *,
    store: BaseStore,
    evidence_subgraph_app: CompiledStateGraph,
    entity_intel_subgraph_app: CompiledStateGraph,
) -> TranscriptGraph:
    """
    For each ResearchDirection in the episode, run the appropriate subgraph
    (evidence or entity) and aggregate results.

    All directions are processed in parallel with bounded concurrency.
    The compiled subgraphs are passed in via closure when the node is added
    to the graph (not stored in state).
    """
    directions: List[ResearchDirection] = state.get("research_directions", []) or []
    if not directions:
        return {
            "evidence_direction_results": [],
            "entity_direction_results": [],
            "evidence_structured_outputs": [],
            "entity_structured_outputs": [],
            "direction_results": [],
            "direction_structured_outputs": [],
        }

    episode_context = ""
    if state.get("initial_transcript_output") is not None:
        episode_context = getattr(state["initial_transcript_output"], "summary", "") or ""

    semaphore = asyncio.Semaphore(MAX_PARALLEL_DIRECTIONS)

    tasks = [
        run_single_direction(
            direction=direction,
            episode_context=episode_context,
            semaphore=semaphore,
            evidence_subgraph_app=evidence_subgraph_app,
            entity_intel_subgraph_app=entity_intel_subgraph_app,
            config=config,
        )
        for direction in directions
    ]

    # Run all directions concurrently (bounded by semaphore)
    results: list[SingleDirectionRunResult] = await asyncio.gather(*tasks)

    # Subgraph-specific buckets
    evidence_direction_results: list[EvidenceResearchResult] = []
    entity_direction_results: list[EntitiesIntelResearchResult] = []

    evidence_structured_outputs: list[BaseModel] = []
    entity_structured_outputs: list[ResearchEntities] = []

    # Optional combined views if you still want them
    all_direction_results: list[EvidenceResearchResult | EntitiesIntelResearchResult] = []
    all_structured_outputs: list[BaseModel] = []

    for r in results:
        kind = r["kind"]
        result = r["result"]
        structured = r["structured_outputs"]

        # Combined
        if result is not None:
            all_direction_results.append(result)
        if structured:
            all_structured_outputs.extend(structured)

        # Subgraph-specific
        if kind == "evidence":
            if result is not None:
                evidence_direction_results.append(
                    cast(EvidenceResearchResult, result)
                )
            if structured:
                evidence_structured_outputs.extend(structured)
        else:  # "entity"
            if result is not None:
                entity_direction_results.append(
                    cast(EntitiesIntelResearchResult, result)
                )
            if structured:
                entity_structured_outputs.extend(
                    cast(list[ResearchEntities], structured)
                )

    return {
        # Subgraph-specific
        "evidence_direction_results": evidence_direction_results,
        "entity_direction_results": entity_direction_results,
        "evidence_structured_outputs": evidence_structured_outputs,
        "entity_structured_outputs": entity_structured_outputs,
        # Optional combined views
        "direction_results": all_direction_results,
        "direction_structured_outputs": all_structured_outputs,
    }



graph = StateGraph(TranscriptGraph)

def build_transcript_graph(
    evidence_subgraph_app: CompiledStateGraph,
    entity_intel_subgraph_app: CompiledStateGraph,
) -> StateGraph:
    """
    Build the parent transcript graph, closing over the compiled
    evidence/entity subgraphs in the run_research_directions node.
    """
    

    graph.add_node("summarize_transcript", summarize_transcript)
    graph.add_node("generate_research_directions", generate_research_directions)

    # Wrap run_research_directions so it can see the compiled subgraphs
    async def run_research_directions_node(
        state: TranscriptGraph,
        config: RunnableConfig,
        *,
        store: BaseStore,
    ) -> TranscriptGraph:
        return await run_research_directions(
            state,
            config,
            store=store,
            evidence_subgraph_app=evidence_subgraph_app,
            entity_intel_subgraph_app=entity_intel_subgraph_app,
        )

    graph.add_node("run_research_directions", run_research_directions_node)

    graph.add_edge(START, "summarize_transcript")
    graph.add_edge("summarize_transcript", "generate_research_directions")
    graph.add_edge("generate_research_directions", "run_research_directions")
    graph.add_edge("run_research_directions", END)

    return graph



def create_memory_agent(
    store: BaseStore,
    namespace: Iterable[str] = DEFAULT_MEMORY_NAMESPACE,
):
    """
    Create a LangMem memory manager bound to the given BaseStore.

    - `store`: the shared BaseStore instance (e.g., AsyncPostgresStore).
    - `namespace`: hierarchical namespace used to partition memory entries,
      e.g. ("memories", "transcript_graph") or ("memories", "guest_history").
    """
    namespace_tuple = tuple(namespace)

    manager = create_memory_store_manager(
        "openai:gpt-5-nano",   
        namespace=namespace_tuple,       
        store=store,                 
        enable_inserts=True,
        enable_deletes=True,
    )
    return manager



DEFAULT_INDEX_CONFIG: Mapping[str, object] = {
    "dims": 1536,
    "embed": "openai:text-embedding-3-small",
}


@asynccontextmanager
async def postgres_checkpointer(pg_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    """
    Async context manager that yields a fully set-up AsyncPostgresSaver
    configured as a LangGraph checkpointer.
    """
    async with AsyncPostgresSaver.from_conn_string(pg_url) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
        # cleanup handled by __aexit__ of AsyncPostgresSaver


@asynccontextmanager
async def postgres_store(
    pg_url: str,
    index: Mapping[str, object] | None = None,
) -> AsyncIterator[BaseStore]:
    """
    Async context manager that yields a fully set-up AsyncPostgresStore
    wrapped as a LangMem BaseStore.
    """
    async with AsyncPostgresStore.from_conn_string(
        pg_url,
        index=index or DEFAULT_INDEX_CONFIG,
    ) as store:
        await store.setup()
        yield store

# -----------------------------------------------------------------------------
# Main: run the graph, persist checkpoints, pretty-print final state
# -----------------------------------------------------------------------------

async def run_transcript_graph_for_episode(episode_page_url: str) -> None:
    """
    Run the full transcript graph pipeline for a single episode:
    - Load episode metadata + transcript
    - Initialize state
    - Create checkpointer + shared store
    - Compile parent graph and subgraphs with shared persistence
    - Attach compiled subgraphs (and memory manager if desired) to state
    - Invoke the parent graph and write final state to disk.
    """
    # Fetch episode and context
    episode_doc: EpisodeDoc = await get_episode(episode_page_url=episode_page_url)

    episode_meta = {
        "episode_number": episode_doc.get("episodeNumber") or "Unknown",
        "episode_page_url": episode_doc.get("episodePageUrl") or "Unknown",
        "episode_transcript_url": episode_doc.get("episodeTranscriptUrl") or "Unknown",
    }

    full_transcript = await get_transcript_text_from_s3_url(
        episode_doc["s3TranscriptUrl"]
    )

    webpage_summary = episode_doc.get("webPageSummary")

    initial_state: TranscriptGraph = {
        "episode_meta": episode_meta,
        "webpage_summary": webpage_summary,
        "full_transcript": full_transcript,
    }

    # Use AsyncPostgresSaver as an async context manager
    async with postgres_checkpointer(pg_url) as checkpointer, \
               postgres_store(pg_url) as store: 

        # Use Memory manager inside nodes 
       

        parent_graph_config = { 
            "configurable": {
                "thread_id": str(uuid4()),
                "checkpoint_ns": "transcript_graph",
                "episode_id": episode_meta["episode_page_url"],
            }
        }   

        evidence_subgraph_app, entity_intel_subgraph_app = compile_subgraphs(
            checkpointer=checkpointer,
            store=store,
        ) 

        graph = build_transcript_graph(
            evidence_subgraph_app=evidence_subgraph_app,
            entity_intel_subgraph_app=entity_intel_subgraph_app,
        )

        # Compile parent graph with checkpointer + store
        parent_app = graph.compile(
            checkpointer=checkpointer,
            store=store,
        )

      
      

        # Single final result (no streaming)
        final_state: TranscriptGraph = await parent_app.ainvoke(initial_state, parent_graph_config)  

        snapshot_path = await dump_final_state_snapshot(
            app=parent_app,
            config=parent_graph_config,
            thread_id=parent_graph_config["configurable"]["thread_id"],
        )  

        return final_state 

    


if __name__ == "__main__": 
    import argparse 
    configure_logging( 
        level=logging.INFO, 
        log_dir="transcript_graph_logs"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode_page_url", type=str, required=True)
    args = parser.parse_args()
    episode_page_url = args.episode_page_url
    asyncio.run(run_transcript_graph_for_episode(episode_page_url))  
    # print(TRANSCRIPT_FILE.read_text())