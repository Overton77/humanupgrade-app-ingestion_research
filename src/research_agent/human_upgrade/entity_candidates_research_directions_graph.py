"""
Candidate and Research Directions Graph for Entity Intel 
"""

from langgraph.graph import StateGraph, START, END   
from langgraph.graph.state import CompiledStateGraph 
from datetime import datetime

from typing_extensions import TypedDict
from typing import  Dict, Any, List

from langchain.agents import create_agent  
from dotenv import load_dotenv 
from langchain.agents.structured_output import ProviderStrategy 
from langchain.agents.middleware import SummarizationMiddleware
from research_agent.human_upgrade.structured_outputs.research_direction_outputs import ( 
    EntityBundlesListOutputA,
    EntityBundlesListFinal,
    compile_bundles_list, 
    EntityBundleDirectionsFinal,
) 
from research_agent.human_upgrade.structured_outputs.candidates_outputs import ( 
 
    CandidateSourcesConnected,
    OfficialStarterSources,
    SeedExtraction,
    DomainCatalogSet,
)   
from langchain_core.runnables import RunnableConfig
from langchain.tools import BaseTool 

from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.utils.artifacts import save_json_artifact, save_text_artifact 
from research_agent.human_upgrade.prompts.seed_prompts import PROMPT_OUTPUT_A_SEED_EXTRACTION
from research_agent.human_upgrade.prompts.candidates_prompts import ( 
    PROMPT_OUTPUT_A2_CONNECTED_CANDIDATE_SOURCES, PROMPT_NODE_A_OFFICIAL_STARTER_SOURCES, PROMPT_NODE_B_DOMAIN_CATALOGS 
    )
from research_agent.human_upgrade.prompts.research_directions_prompts import PROMPT_OUTPUT_A3_ENTITY_RESEARCH_DIRECTIONS
from research_agent.clients.langsmith_client import pull_prompt_from_langsmith 
from research_agent.human_upgrade.tools.web_search_tools import (
    wiki_tool, 
    tavily_map_validation, 
    tavily_search_validation,
    tavily_extract_validation, 
    
) 

from research_agent.human_upgrade.utils.formatting import format_seed_extraction_for_prompt, format_connected_candidates_for_prompt 
from research_agent.human_upgrade.intel_mongo_nodes import ( 
    persist_candidates_node, 
    persist_research_plans_node,
    persist_domain_catalogs_node,
)

from research_agent.human_upgrade.base_models import gpt_4_1, gpt_5_mini, gpt_5_nano, gpt_5  
from research_agent.human_upgrade.persistence.checkpointer_and_store import get_persistence
import os 

load_dotenv() 

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") 

openai_search_tool: Dict[str, str] = {"type": "web_search"}  



pull_prompt_names: Dict[str, str] = { 
    "seed_extraction_prompt": "seed_extraction_prompt", 
    "connected_candidate_sources_prompt": "connected_candidate_sources_prompt",
    "research_directions_prompt": "research_directions_prompt",
}


class EntityIntelCandidateAndResearchDirectionsState(TypedDict, total=False):
    """State for a single entity candidate and research directions."""
    # Core tool-loop plumbing
    llm_calls: int
    tool_calls: int

    # Episode context
    episode: Dict[str, Any]

    # Existing outputs
    seed_extraction: SeedExtraction
    candidate_sources: CandidateSourcesConnected
    research_directions: EntityBundlesListFinal

    # ----------------------------
    # NEW: Intel orchestration
    # ----------------------------

    # Stable per-run identifiers (set once, reused across nodes)
    intel_run_id: str
    intel_pipeline_version: str

    # Outputs from persist_candidates_node
    candidate_entity_ids: List[str]          # candidateEntityId values inserted for this run
    dedupe_group_map: Dict[str, str]         # entityKey -> dedupeGroupId

    # Outputs from persist_research_plans_node
    research_plan_ids: List[str]    
    
    official_starter_sources: OfficialStarterSources          
    domain_catalogs: DomainCatalogSet  
    domain_catalog_set_id: str
    domain_catalog_extracted_at: datetime | str 

    error: str

    steps_taken: int
    



VALIDATION_TOOLS: List[BaseTool] = [
    wiki_tool,
    tavily_search_validation,
    tavily_extract_validation,
    tavily_map_validation,
]


OFFICIAL_STARTER_TOOLS = [
    tavily_search_validation,
    tavily_extract_validation,  
    wiki_tool,                 
]

DOMAIN_CATALOG_TOOLS = [
    tavily_map_validation,
    tavily_extract_validation,  
] 

CONNECTED_TOOLS = [
        wiki_tool,
        tavily_search_validation,  # fallback only 
        tavily_extract_validation,  # primary
        # tavily_map_validation,    # intentionally omitted in Node C
    ]

async def seed_extraction_node(state: EntityIntelCandidateAndResearchDirectionsState) -> EntityIntelCandidateAndResearchDirectionsState:  
    episode: Dict[str, Any] = state.get("episode", {})
    webpage_summary: str = episode.get("webPageSummary") 
    episode_url: str = episode.get("episodePageUrl")
    
    if not webpage_summary:
        raise ValueError("episode.webPageSummary is required")
    if not episode_url:
        raise ValueError("episode.episodePageUrl is required")
    
    logger.info(f"🌱 Starting seed extraction for episode: {episode_url[:80]}...")   

    seed_extraction_prompt: str = PROMPT_OUTPUT_A_SEED_EXTRACTION.format(
        episode_url=episode_url,
        webpage_summary=webpage_summary,
    )  

    seed_extraction_agent: CompiledStateGraph = create_agent(   
     
        gpt_5_mini,   
        tools=[openai_search_tool], 
        response_format=ProviderStrategy(SeedExtraction),  
           name="seed_extraction_agent",
    ) 

    response = await seed_extraction_agent.ainvoke( 
        {"messages": [{"role": "user", "content": seed_extraction_prompt}]} 
    ) 

    seed_extraction_output: SeedExtraction = response["structured_response"]
    
    logger.info(
        "✅ Seed extraction complete: guests=%s businesses=%s products=%s compounds=%s",
        len(seed_extraction_output.guest_candidates) if seed_extraction_output.guest_candidates else 0,
        len(seed_extraction_output.business_candidates) if seed_extraction_output.business_candidates else 0,
        len(seed_extraction_output.product_candidates) if seed_extraction_output.product_candidates else 0,
        len(seed_extraction_output.compound_candidates) if seed_extraction_output.compound_candidates else 0,
    )

    return { 
        "seed_extraction": seed_extraction_output,
    }  




async def official_sources_node(
    state: EntityIntelCandidateAndResearchDirectionsState,
) -> EntityIntelCandidateAndResearchDirectionsState:
    seed_extraction: SeedExtraction | None = state.get("seed_extraction")
    if seed_extraction is None:
        raise ValueError("seed_extraction is required")

    episode: Dict[str, Any] = state.get("episode", {})
    episode_url: str = episode.get("episodePageUrl", "unknown")

    formatted_fields: Dict[str, str] = format_seed_extraction_for_prompt(seed_extraction)

    prompt = PROMPT_NODE_A_OFFICIAL_STARTER_SOURCES.format(
        episode_url=episode_url,
        guest_candidates=formatted_fields["guest_candidates"],
        business_candidates=formatted_fields["business_candidates"],
        product_candidates=formatted_fields["product_candidates"],
    )

    agent = create_agent(
        gpt_5_mini,
        tools=OFFICIAL_STARTER_TOOLS,
        response_format=ProviderStrategy(OfficialStarterSources),
        name="official_sources_agent",
    )

    response = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    official_sources: OfficialStarterSources = response["structured_response"]

    await save_json_artifact(
        official_sources.model_dump(),
        "test_run",
        "official_starter_sources",
        suffix=episode_url.replace("/", "_")[:30],
    )

    return {"official_starter_sources": official_sources}


async def domain_catalogs_node(
    state: EntityIntelCandidateAndResearchDirectionsState,
) -> EntityIntelCandidateAndResearchDirectionsState:
    official_sources: OfficialStarterSources | None = state.get("official_starter_sources")
    if official_sources is None:
        raise ValueError("official_starter_sources is required for domain_catalogs_node")

    episode: Dict[str, Any] = state.get("episode", {})
    episode_url: str = episode.get("episodePageUrl", "unknown")

    prompt = PROMPT_NODE_B_DOMAIN_CATALOGS.format(
        episode_url=episode_url,
        official_starter_sources_json=official_sources.model_dump_json(indent=2),
    )

    agent = create_agent(
        gpt_5_mini,
        tools=DOMAIN_CATALOG_TOOLS,
        response_format=ProviderStrategy(DomainCatalogSet),
        name="domain_catalogs_agent",
    )

    response = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    domain_catalogs: DomainCatalogSet = response["structured_response"]

    await save_json_artifact(
        domain_catalogs.model_dump(),
        "test_run",
        "domain_catalogs",
        suffix=episode_url.replace("/", "_")[:30],
    )

    return {"domain_catalogs": domain_catalogs}


async def candidate_sources_node(
    state: EntityIntelCandidateAndResearchDirectionsState,
) -> EntityIntelCandidateAndResearchDirectionsState:
    seed_extraction: SeedExtraction | None = state.get("seed_extraction")
    if seed_extraction is None:
        logger.error("❌ seed_extraction is None in candidate_sources_node")
        raise ValueError("seed_extraction is required but was not found in state")

    official_starter_sources: OfficialStarterSources | None = state.get("official_starter_sources")
    if official_starter_sources is None:
        logger.error("❌ official_starter_sources is None in candidate_sources_node")
        raise ValueError("official_starter_sources is required but was not found in state")

    domain_catalogs: DomainCatalogSet | None = state.get("domain_catalogs")
    if domain_catalogs is None:
        logger.error("❌ domain_catalogs is None in candidate_sources_node")
        raise ValueError("domain_catalogs is required but was not found in state")

    episode: Dict[str, Any] = state.get("episode", {})
    episode_url: str = episode.get("episodePageUrl", "unknown")

    logger.info(
        "📋 Candidate sources (Node C): guests=%s businesses=%s products=%s | domains=%s catalogs=%s",
        len(seed_extraction.guest_candidates),
        len(seed_extraction.business_candidates),
        len(seed_extraction.product_candidates),
        len(official_starter_sources.domainTargets or []),
        len(domain_catalogs.catalogs or []),
    )

    # Keep this: it provides readable seed context and helps with disambiguation
    formatted_fields: Dict[str, str] = format_seed_extraction_for_prompt(seed_extraction)

    # Inject Node A + Node B artifacts into Node C prompt.
    # These make Node C "mostly deterministic": prioritize extract from known pages.
    candidate_sources_prompt: str = PROMPT_OUTPUT_A2_CONNECTED_CANDIDATE_SOURCES.format(
        episode_url=episode_url,
        guest_candidates=formatted_fields["guest_candidates"],
        business_candidates=formatted_fields["business_candidates"],
        product_candidates=formatted_fields["product_candidates"],
        compound_candidates=formatted_fields["compound_candidates"],
        evidence_claim_hooks=formatted_fields["evidence_claim_hooks"],
        notes=formatted_fields["notes"],

        official_starter_sources_json=official_starter_sources.model_dump_json(indent=2),
        domain_catalogs_json=domain_catalogs.model_dump_json(indent=2),
    )

   


    candidate_sources_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        tools=CONNECTED_TOOLS,
        response_format=ProviderStrategy(CandidateSourcesConnected),
        # middleware=[
        #     SummarizationMiddleware(
        #         model="gpt-4.1",
        #         trigger=("tokens", 170000),
        #         keep=("messages", 20),
        #     )
        # ],
        name="candidate_sources_agent",
    )

    response = await candidate_sources_agent.ainvoke(
        {"messages": [{"role": "user", "content": candidate_sources_prompt}]}
    )

    candidate_sources_output: CandidateSourcesConnected = response["structured_response"]

    logger.info(
        "✅ Candidate sources complete: connected_bundles=%s",
        len(candidate_sources_output.connected),
    )

    try:
        await save_json_artifact(
            candidate_sources_output.model_dump(),
            "test_run",
            "candidate_sources_connected",
            suffix=episode_url.replace("/", "_")[:30],
        )
    except Exception as e:
        return {
            "candidate_sources": candidate_sources_output,
            "error": str(e),
        }

    return {"candidate_sources": candidate_sources_output}

async def generate_research_directions_node(state: EntityIntelCandidateAndResearchDirectionsState) -> EntityIntelCandidateAndResearchDirectionsState:
    """
    Generate structured research directions from connected candidate sources.
    
    Step 1: LLM generates EntityBundlesListOutputA (objectives + starter sources for each bundle)
    Step 2: We compile to EntityBundlesListFinal (add deterministic required fields)
    """
    candidate_sources: CandidateSourcesConnected = state.get("candidate_sources", CandidateSourcesConnected(connected=[]))
    if not candidate_sources.connected:
        logger.error("❌ candidate_sources is None in research_directions_node")
        raise ValueError("candidate_sources is required but was not found in state")

    episode: Dict[str, Any] = state.get("episode", {})
    episode_url: str = episode.get("episodePageUrl", "unknown")
    
    logger.info(
        "🎯 Generating research directions for %s connected bundles",
        len(candidate_sources.connected)
    )

    # Format connected candidates for the prompt
    formatted_bundles: str = format_connected_candidates_for_prompt(candidate_sources)

    research_directions_prompt: str = PROMPT_OUTPUT_A3_ENTITY_RESEARCH_DIRECTIONS.format(
        connected_bundles=formatted_bundles,
    )

    
    research_directions_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        response_format=ProviderStrategy(EntityBundlesListOutputA), 
        name="research_directions_agent",
    )

    response = await research_directions_agent.ainvoke(
        {"messages": [{"role": "user", "content": research_directions_prompt}]}
    )

    bundles_list_output_a: EntityBundlesListOutputA = response["structured_response"]  



    logger.info(
        "✅ LLM OutputA complete: %s bundles with objectives and starter sources",
        len(bundles_list_output_a.bundles),
    ) 

    compiled_bundles_list: EntityBundlesListFinal = compile_bundles_list(bundles_list_output_a) 

    await save_json_artifact(
        compiled_bundles_list.model_dump(),
        "test_run",
        "research_directions_compiled_bundles_list",
        suffix=episode_url.replace("/", "_")[:30] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    
    logger.info(
        "✅ Research directions complete: %s bundles compiled with required fields",
        len(compiled_bundles_list.bundles)
    )

    return {
        "research_directions": compiled_bundles_list,
    }


# ============================================================================
# BUILD SUBGRAPH
# ============================================================================

def build_entity_research_directions_builder() -> StateGraph:
    builder: StateGraph = StateGraph(EntityIntelCandidateAndResearchDirectionsState)

    builder.add_node("seed_extraction", seed_extraction_node)
    builder.add_node("candidate_sources", candidate_sources_node) 
    builder.add_node("official_sources", official_sources_node)
    builder.add_node("domain_catalogs", domain_catalogs_node)
    builder.add_node("persist_domain_catalogs", persist_domain_catalogs_node)
    builder.add_node("generate_research_directions", generate_research_directions_node)
    builder.add_node("persist_candidates", persist_candidates_node)
    builder.add_node("persist_research_plans", persist_research_plans_node)
    builder.set_entry_point("seed_extraction")
    builder.add_edge("seed_extraction", "official_sources") 
    builder.add_edge("official_sources", "domain_catalogs") 
    builder.add_edge("domain_catalogs", "persist_domain_catalogs") 

    builder.add_edge("persist_domain_catalogs", "candidate_sources")
    builder.add_edge("candidate_sources", "persist_candidates")  
    builder.add_edge("candidate_sources", "generate_research_directions") 
    builder.add_edge("generate_research_directions", "persist_research_plans")
    builder.add_edge("generate_research_directions", END)

    return builder



async def make_entity_research_directions_graph(config: RunnableConfig) -> CompiledStateGraph:
    """
    Graph factory for LangSmith Studio / LangGraph CLI.
    Called per run; we reuse process-wide store/checkpointer.
    """
    store, checkpointer = await get_persistence()

    # IMPORTANT: checkpoint namespace is provided at runtime via config["configurable"]["checkpoint_ns"]
    # so compile once with the saver; per-run separation happens via config.
    graph: CompiledStateGraph = build_entity_research_directions_builder().compile(
        checkpointer=checkpointer,
        store=store,
    )
    return graph