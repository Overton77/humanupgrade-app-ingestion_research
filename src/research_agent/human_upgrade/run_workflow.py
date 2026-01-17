from dotenv import load_dotenv 
import logging
from research_agent.common.logging_utils import configure_logging

# Configure logging FIRST, before importing anything that uses the logger
# Using root logger (None) so all child loggers inherit the configuration
configure_logging(
    level=logging.INFO,
    logger_name=None,  # Root logger - all child loggers will inherit
)

from typing import Dict, List, Any, Optional  
from research_agent.human_upgrade.logger import logger  
from research_agent.retrieval.async_mongo_client import get_episode 
from research_agent.human_upgrade.entity_research_graphs import (
    BundlesParentGraph,
  
)  

from research_agent.human_upgrade.entity_candidates_research_directions_graph import  entity_research_directions_subgraph

from research_agent.common.artifacts import save_json_artifact




load_dotenv() 




# ============================================================================
# EPISODE URLS
# ============================================================================

# EPISODE_URLS: List[str] = [
#     "https://daveasprey.com/1303-nayan-patel/",
#     "https://daveasprey.com/1302-nathan-bryan/",
#     "https://daveasprey.com/1301-ewot/",
#     "https://daveasprey.com/1296-qualia-greg-kelly/",
#     "https://daveasprey.com/1295-ben-azadi/",
#     "https://daveasprey.com/1293-darin-olien/",
#     "https://daveasprey.com/1292-amitay-eshel-young-goose/",
#     "https://daveasprey.com/1291-mte-jeff-boyd/",
#     "https://daveasprey.com/1289-josh-axe/",
#     "https://daveasprey.com/1330-energybits/",
#     "https://daveasprey.com/1327-jim-murphy/",
#     "https://daveasprey.com/1323-sulforaphane-curcumin-and-new-glp-1-drugs-biohacking-for-longevity/",
#     "https://daveasprey.com/1315-stemregen/",
#     "https://daveasprey.com/1311-biolongevity-labs/",
#     "https://daveasprey.com/1352-roxiva/",
#     "https://daveasprey.com/1353-vinia-bioharvest/",
# ]

EPISODE_URLS= [  
        "https://daveasprey.com/1303-nayan-patel/",
    "https://daveasprey.com/1302-nathan-bryan/",
    "https://daveasprey.com/1301-ewot/",
    "https://daveasprey.com/1296-qualia-greg-kelly/",
    "https://daveasprey.com/1295-ben-azadi/",
    "https://daveasprey.com/1330-energybits/",
    "https://daveasprey.com/1311-biolongevity-labs/",
    "https://daveasprey.com/1352-roxiva/",
    "https://daveasprey.com/1353-vinia-bioharvest/",

]  

test_run_episode = "https://daveasprey.com/1296-qualia-greg-kelly/"



async def run_research_agent_workflow(entity_intel_subgraph, episode_url: str):
    episode = await get_episode(episode_page_url=episode_url)
    if not episode:
        logger.error(f"❌ Episode not found: {episode_url}")
        return

    # Ensure these exist so seed_extraction doesn't explode if missing
    # (Your seed node expects episode["webPageSummary"] and episode["episodePageUrl"])

    initial_state: Dict[str, Any] = {
        "llm_calls": 0,
        "tool_calls": 0,
        "steps_taken": 0,

        # Episode context
        "episode": episode,

   
    }

    final_state_directions_state = await entity_research_directions_subgraph.ainvoke(initial_state)

    # Quick visibility:
    seed_extraction = final_state_directions_state.get("seed_extraction")  
    candidate_sources = final_state_directions_state.get("candidate_sources")
    research_directions = final_state_directions_state.get("research_directions")   

    # Iterate over research directions. 

    parent_graph_state = { 
        "episode": episode, 
        "bundles": research_directions, 
        "llm_calls": 0, 
        "tool_calls": 0, 
        "steps_taken": 0, 
        "messages": [], 
        "file_refs": [], 
    }  

    parent_final_state = await BundlesParentGraph.ainvoke(parent_graph_state)   

    # Convert Pydantic models to dicts for JSON serialization
    final_reports_data = [fr.model_dump() if hasattr(fr, 'model_dump') else fr for fr in parent_final_state.get("final_reports", [])]
    file_refs_data = [fr.model_dump() if hasattr(fr, 'model_dump') else fr for fr in parent_final_state.get("file_refs", [])]

    await save_json_artifact(final_reports_data, "test_run", "parent_final_reports", suffix=episode_url.replace("/", "_")[:30])   
    await save_json_artifact(file_refs_data, "test_run", "parent_file_refs", suffix=episode_url.replace("/", "_")[:30])   

    

    final_state = { 
        "seed_extraction": seed_extraction,
        "candidate_sources": candidate_sources,
        "research_directions": research_directions,
        "parent_final_state": parent_final_state, 
    } 







    logger.info("✅ Graph run complete")
  

  
    return final_state



if __name__ == "__main__":
    import asyncio
    # asyncio.run(run_all_then_save())   

    final_state = asyncio.run(run_research_agent_workflow(entity_research_directions_subgraph, test_run_episode)) 

 


