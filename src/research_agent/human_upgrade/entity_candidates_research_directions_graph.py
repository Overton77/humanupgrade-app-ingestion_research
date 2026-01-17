"""
Candidate and Research Directions Graph for Entity Intel 
"""

from langgraph.graph import StateGraph, START, END   
from langgraph.graph.state import CompiledStateGraph

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
   SeedExtraction,
)  
from langchain.tools import BaseTool 

from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.utils.artifacts import save_json_artifact, save_text_artifact 
from research_agent.human_upgrade.prompts.seed_prompts import PROMPT_OUTPUT_A_SEED_EXTRACTION
from research_agent.human_upgrade.prompts.candidates_prompts import PROMPT_OUTPUT_A2_CONNECTED_CANDIDATE_SOURCES
from research_agent.human_upgrade.prompts.research_directions_prompts import PROMPT_OUTPUT_A3_ENTITY_RESEARCH_DIRECTIONS
from research_agent.clients.langsmith_client import pull_prompt_from_langsmith 
from research_agent.human_upgrade.tools.web_search_tools import (
    wiki_tool, 
    tavily_map_validation, 
    tavily_search_validation,
    tavily_extract_validation, 
    
) 

from research_agent.human_upgrade.utils.formatting import format_seed_extraction_for_prompt, format_connected_candidates_for_prompt

from research_agent.human_upgrade.base_models import gpt_4_1, gpt_5_mini, gpt_5_nano, gpt_5 
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
    llm_calls: int # if needed 
    tool_calls: int  # if needed 

    # Episode context
    episode: Dict[str, Any] 

    
  
    seed_extraction: SeedExtraction 
    candidate_sources: CandidateSourcesConnected 
    research_directions: EntityBundlesListFinal 
    
    steps_taken: int  # if needed 
    



VALIDATION_TOOLS: List[BaseTool] = [
    wiki_tool,
    tavily_search_validation,
    tavily_extract_validation,
    tavily_map_validation,
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
        "✅ Seed extraction complete: guests=%s businesses=%s products=%s compounds=%s platforms=%s",
        len(seed_extraction_output.guest_candidates) if seed_extraction_output.guest_candidates else 0,
        len(seed_extraction_output.business_candidates) if seed_extraction_output.business_candidates else 0,
        len(seed_extraction_output.product_candidates) if seed_extraction_output.product_candidates else 0,
        len(seed_extraction_output.compound_candidates) if seed_extraction_output.compound_candidates else 0,
        len(seed_extraction_output.platform_candidates) if seed_extraction_output.platform_candidates else 0,
    )

    return { 
        "seed_extraction": seed_extraction_output,
    }  


async def candidate_sources_node(state: EntityIntelCandidateAndResearchDirectionsState) -> EntityIntelCandidateAndResearchDirectionsState:
    seed_extraction: SeedExtraction = state.get("seed_extraction")
    if seed_extraction is None:
        logger.error("❌ seed_extraction is None in candidate_sources_node")
        raise ValueError("seed_extraction is required but was not found in state")

    episode_url: str = (state.get("episode") or {}).get("episodePageUrl", "unknown")

    logger.info(
        "📋 Processing candidate sources: guests=%s businesses=%s products=%s",
        len(seed_extraction.guest_candidates),
        len(seed_extraction.business_candidates),
        len(seed_extraction.product_candidates),
    )

    formatted_fields: Dict[str, str] = format_seed_extraction_for_prompt(seed_extraction)

    candidate_sources_prompt: str = PROMPT_OUTPUT_A2_CONNECTED_CANDIDATE_SOURCES.format(
        episode_url=episode_url,
        guest_candidates=formatted_fields["guest_candidates"],
        business_candidates=formatted_fields["business_candidates"],
        product_candidates=formatted_fields["product_candidates"],
        platform_candidates=formatted_fields["platform_candidates"],
        compound_candidates=formatted_fields["compound_candidates"],
        evidence_claim_hooks=formatted_fields["evidence_claim_hooks"],
        notes=formatted_fields["notes"],
    )

    candidate_sources_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        tools=VALIDATION_TOOLS,
        response_format=ProviderStrategy(CandidateSourcesConnected),
        middleware=[
            SummarizationMiddleware(
                model="gpt-4.1",
                trigger=("tokens", 300000),
                keep=("messages", 20),
            )
        ],
        name="candidate_sources_agent",
    )

    response = await candidate_sources_agent.ainvoke(
        {"messages": [{"role": "user", "content": candidate_sources_prompt}]}
    )

    candidate_sources_output: CandidateSourcesConnected = response["structured_response"]

    logger.info("✅ Candidate sources complete: connected_bundles=%s", len(candidate_sources_output.connected))

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

    # Return partial state update (LangGraph merges it)
    return {
        "candidate_sources": candidate_sources_output,
    }


async def generate_research_directions_node(state: EntityIntelCandidateAndResearchDirectionsState) -> EntityIntelCandidateAndResearchDirectionsState:
    """
    Generate structured research directions from connected candidate sources.
    
    Step 1: LLM generates EntityBundlesListOutputA (objectives + starter sources for each bundle)
    Step 2: We compile to EntityBundlesListFinal (add deterministic required fields)
    """
    candidate_sources: CandidateSourcesConnected = state.get("candidate_sources")
    if candidate_sources is None:
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

entity_research_directions_subgraph_builder: StateGraph = StateGraph(EntityIntelCandidateAndResearchDirectionsState)



entity_research_directions_subgraph_builder.add_node("seed_extraction", seed_extraction_node)
entity_research_directions_subgraph_builder.add_node("candidate_sources", candidate_sources_node)
entity_research_directions_subgraph_builder.add_node("generate_research_directions", generate_research_directions_node)

entity_research_directions_subgraph_builder.set_entry_point("seed_extraction") 

entity_research_directions_subgraph_builder.add_edge("seed_extraction", "candidate_sources")
entity_research_directions_subgraph_builder.add_edge("candidate_sources", "generate_research_directions")
entity_research_directions_subgraph_builder.add_edge("generate_research_directions", END)


entity_research_directions_subgraph: CompiledStateGraph = entity_research_directions_subgraph_builder.compile()



