import os
import sys
import asyncio
import json
from uuid import uuid4
from pathlib import Path
from typing import Optional, List, Dict, Any, TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, START 
from langgraph.graph.state import CompiledStateGraph  
from langchain_core.runnables import RunnableConfig  

import aiofiles

# Windows-specific: psycopg requires SelectorEventLoop, not ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from research_agent.output_models import TranscriptSummaryOutput
from research_agent.prompts import summary_prompt, SUMMARY_SYSTEM_PROMPT


# -----------------------------------------------------------------------------
# Environment & Paths
# -----------------------------------------------------------------------------

load_dotenv()  

# Adjust this if your layout is different:
# Assuming: project_root/dev_env/... and this file in src/research_agent/
PROJECT_ROOT = Path(__file__).resolve().parents[2]  

PARENT_DIR = Path(__file__).resolve().parent   
DATA_DIR = PARENT_DIR / "dev_env" / "data"
OUTPUT_DIR = PARENT_DIR / "dev_env" / "summary_graph_outputs"

TRANSCRIPT_FILE = DATA_DIR / "full_transcript_two.txt"
WEBPAGE_SUMMARY_FILE = DATA_DIR / "webpage_summary_two.md"

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")


# -----------------------------------------------------------------------------
# Models for Web Search Output
# -----------------------------------------------------------------------------

class ProductSearchOutput(BaseModel):
    product_name: str = Field(..., description="The name of the product")
    product_overview: str = Field(..., description="A concise overview of the product")
    product_ingredients: List[str] = Field(..., description="The ingredients of the product")
    product_price: Optional[float] = Field(
        default=None,
        description="The price of the product",
    )
    product_url: Optional[str] = Field(
        default=None,
        description="The URL of the product",
    )


class BusinessSearchOutput(BaseModel):
    business_name: str = Field(..., description="The name of the business")
    business_overview: str = Field(..., description="A concise overview of the business")
    products: List[ProductSearchOutput] = Field(
        ...,
        description="The products of the business",
    )


class WebSearchOutput(BaseModel):
    guest_name: str = Field(..., description="The name of the guest")
    guest_overview: str = Field(..., description="A concise overview of the guest")
    business: BusinessSearchOutput = Field(
        ...,
        description="The business of the guest",
    )
    research_complete: bool = Field(
        ...,
        description="Whether the research is complete",
    )


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

openai_search_tool = {"type": "web_search"}  # passed into create_agent tools


# -----------------------------------------------------------------------------
# Guest Search Prompt Template
# -----------------------------------------------------------------------------

GUEST_SEARCH_PROMPT = """
Your task is to gather accurate, up-to-date information about the following guest who appeared on 
The Human Upgrade podcast with Dave Asprey.

Guest Name:
{guest_name}

Guest Description:
{guest_description}

Guest Company or Affiliation:
{guest_company}

Guest Product or Offering:
{guest_product_affiliation}

Your job is to:
1. Conduct thorough web research using your available web search tool.
2. Validate the guest’s identity, background, profession, and reputation.
3. Identify their primary business, company, or organization.
4. Identify the products, programs, supplements, or technologies associated with them.
5. Collect concise but complete information suitable for a biotech knowledge system focused on 
   human longevity, performance, and excellence.
6. When you have gathered enough information to confidently populate:
   - guest_name
   - guest_overview
   - business (name, overview, product details)
   - product specifics (ingredients, pricing, URLs, etc.)
   then set the `research_complete` flag to True.

If more information is still needed, set `research_complete` to False and request additional refinement or 
additional search passes.

Ensure every response is factual, verifiable, and grounded in real web data.
"""


# -----------------------------------------------------------------------------
# Graph State Definition
# -----------------------------------------------------------------------------

class TranscriptGraph(TypedDict, total=False):
    episode_meta: Dict[str, Any]
    webpage_summary: str
    full_transcript: str

    # From summarize_transcript
    initial_transcript_output: TranscriptSummaryOutput

    # From guest_research
    guest_research_result: WebSearchOutput
    guest_research_history: List[WebSearchOutput]


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


async def write_guest_research_outputs(
    web_output: WebSearchOutput,
    history: List[WebSearchOutput],
    output_dir: Path,
    episode_number: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    research_path = output_dir / f"episode_{episode_number}_guest_research.json"
    history_path = output_dir / f"episode_{episode_number}_guest_research_history.json"

    async with aiofiles.open(research_path, "w", encoding="utf-8") as f:
        await f.write(web_output.model_dump_json(indent=2))

    async with aiofiles.open(history_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(
            [item.model_dump() for item in history],
            indent=2
        ))

    print(f"Finished writing guest research outputs for episode {episode_number}")


# -----------------------------------------------------------------------------
# Graph Nodes
# -----------------------------------------------------------------------------

async def summarize_transcript(state: TranscriptGraph) -> TranscriptGraph:
    summary_agent = create_agent(
        summary_model,
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        response_format=TranscriptSummaryOutput,
    )

    webpage_summary = state.get("webpage_summary")
    full_transcript = state.get("full_transcript")

    if not webpage_summary or not full_transcript:
        raise RuntimeError("webpage_summary and full_transcript are required for this graph")

    formatted_summary_prompt = summary_prompt.format(
        webpage_summary=webpage_summary,
        full_transcript=full_transcript,
    )

    summary_agent_response = await summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": formatted_summary_prompt}]}
    )

    transcript_output: TranscriptSummaryOutput = summary_agent_response["structured_response"]

    episode_number = state["episode_meta"]["episode_number"]
    await write_summary_outputs_without_docs(
        summary_output=transcript_output,
        output_dir=OUTPUT_DIR,
        episode_number=episode_number,
    )

    # Return partial state update (LangGraph merges this into the state)
    return {"initial_transcript_output": transcript_output}


MAX_RESEARCH_LOOPS = 5


async def guest_research(state: TranscriptGraph) -> TranscriptGraph:
    transcript_output = state.get("initial_transcript_output")
    if not transcript_output:
        raise RuntimeError("initial_transcript_output is required for guest research")

    guest_name = transcript_output.guest_information.name
    guest_description = transcript_output.guest_information.description
    guest_company = (
        transcript_output.guest_information.company
        if transcript_output.guest_information.company
        else "No company provided. Web search should take this into account."
    )
    guest_product_affiliation = (
        transcript_output.guest_information.product
        if transcript_output.guest_information.product
        else "No product provided. Web search should take this into account."
    )

    guest_search_prompt_template = PromptTemplate.from_template(GUEST_SEARCH_PROMPT).format(
        guest_name=guest_name,
        guest_description=guest_description,
        guest_company=guest_company,
        guest_product_affiliation=guest_product_affiliation,
    )

    WEB_SEARCH_SYSTEM_PROMPT = """
    You are a critical piece in the research process for a biotech information system built in collaboration 
    with Dave Asprey. Currently the organization is enriching the knowledge base that contains each of the guests 
    that have come on the show with Dave Asprey. Utilize your web search tool to find up to date information about 
    the guest, their business, business affiliations and those business products. When you have found all of the 
    information you need ensure you respond with the research_complete flag set to True.
    """

    web_search_agent = create_agent(
        web_search_model,
        system_prompt=WEB_SEARCH_SYSTEM_PROMPT,
        response_format=WebSearchOutput,
        tools=[openai_search_tool],
    )

    messages: List[Dict[str, str]] = [
        {"role": "user", "content": guest_search_prompt_template}
    ]

    all_structured_responses: List[WebSearchOutput] = []

    for _ in range(MAX_RESEARCH_LOOPS):
        response = await web_search_agent.ainvoke({"messages": messages})

        messages = response["messages"]
        structured_response: WebSearchOutput = response["structured_response"]
        all_structured_responses.append(structured_response)

        if structured_response.research_complete:
            episode_number = state["episode_meta"]["episode_number"]
            await write_guest_research_outputs(
                web_output=structured_response,
                history=all_structured_responses,
                output_dir=OUTPUT_DIR,
                episode_number=episode_number,
            )
            return {
                "guest_research_result": structured_response,
                "guest_research_history": all_structured_responses,
            }

    # If never marked complete, still save what we have
    if all_structured_responses:
        episode_number = state["episode_meta"]["episode_number"]
        await write_guest_research_outputs(
            web_output=all_structured_responses[-1],
            history=all_structured_responses,
            output_dir=OUTPUT_DIR,
            episode_number=episode_number,
        )

    return {
        "guest_research_result": all_structured_responses[-1] if all_structured_responses else None,
        "guest_research_history": all_structured_responses,
    }

# -----------------------------------------------------------------------------
# Build the Graph
# -----------------------------------------------------------------------------

graph = StateGraph(TranscriptGraph)

graph.add_node("summarize_transcript", summarize_transcript)
graph.add_node("guest_research", guest_research)

graph.add_edge(START, "summarize_transcript")
graph.add_edge("summarize_transcript", "guest_research") 

# Compile without checkpointer for langgraph dev server compatibility
# The dev server will inject its own in-memory checkpointer
app: CompiledStateGraph = graph.compile()   


initial_state: TranscriptGraph = {
    "episode_meta": {
        "episode_number": 1303,
    },
    "webpage_summary": WEBPAGE_SUMMARY_FILE.read_text(encoding="utf-8"),
    "full_transcript": TRANSCRIPT_FILE.read_text(encoding="utf-8"),
} 





# -----------------------------------------------------------------------------
# Main: run the graph, persist checkpoints, pretty-print final state
# -----------------------------------------------------------------------------

async def main() -> None:   
    # Import here to avoid module-level async context manager issues
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from pprint import pprint
    
    pg_password = os.getenv("POSTGRES_PASSWORD")  
    pg_db_name = os.getenv("POSTGRES_DB")   
    pg_url = f"postgresql://postgres:{pg_password}@localhost:5432/{pg_db_name}"
    
    # Use AsyncPostgresSaver as an async context manager
    async with AsyncPostgresSaver.from_conn_string(pg_url) as checkpointer:
        await checkpointer.setup()
        
        # Recompile the graph with the checkpointer for persistence
        app_with_checkpointer = graph.compile(checkpointer=checkpointer)

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
        state_path = OUTPUT_DIR / "final_state.json"

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
    asyncio.run(main())  
    # print(TRANSCRIPT_FILE.read_text())