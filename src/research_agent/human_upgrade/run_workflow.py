from dotenv import load_dotenv 
import logging
from research_agent.common.logging_utils import configure_logging
from langchain_core.runnables import RunnableConfig 
import sys  
from typing import Literal  
from datetime import datetime  
import uuid 
import asyncio
import selectors
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
    make_bundle_research_graph,
  
)    

from research_agent.retrieval.async_mongo_client import _humanupgrade_db 
from research_agent.human_upgrade.entity_candidates_research_directions_graph import  make_entity_research_directions_graph 
from research_agent.human_upgrade.utils.graph_namespaces import make_thread_id_from_episode_url, base_config, with_checkpoint_ns, ns_direction, ns_bundle, NS_DIRECTIONS, NS_PARENT
from research_agent.common.artifacts import save_json_artifact
from research_agent.human_upgrade.utils.graph_state import dump_graph_state_history, dump_full_workflow_histories 
from research_agent.human_upgrade.utils.state_serializer import _jsonable, sanitize_mongo_document   
from research_agent.retrieval.intel_mongo_helpers import (
    find_plans,
    set_plan_status,
)

from research_agent.human_upgrade.structured_outputs.research_direction_outputs import (
    EntityBundleDirectionsFinal,
)




load_dotenv() 

def make_selector_loop():
    return asyncio.SelectorEventLoop(selectors.SelectSelector()) 


DELIM = "__"

def _thread_id_for_plan(
    *,
    episode_url: str,
    plan_id: str,
    thread_mode: Literal["episode", "plan"],
) -> str:
    base = make_thread_id_from_episode_url(episode_url)
    if thread_mode == "episode":
        return base
    # plan-scoped (avoid ":" — use DELIM)
    return f"{base}{DELIM}plan{DELIM}{plan_id}"


def _directions_cfg(*, cfg_base: RunnableConfig) -> RunnableConfig:
    return with_checkpoint_ns(cfg_base, NS_DIRECTIONS)


def _bundle_cfg(*, cfg_base: RunnableConfig, bundle_id: str) -> RunnableConfig:
    return with_checkpoint_ns(cfg_base, ns_bundle(bundle_id))


async def _bundle_from_plan_doc(plan_doc: Dict[str, Any]) -> EntityBundleDirectionsFinal:
    directions = plan_doc.get("directions")
    if not directions:
        raise ValueError(f"planId={plan_doc.get('planId')} missing directions")
    return EntityBundleDirectionsFinal.model_validate(directions)


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

test_run_episode = "https://daveasprey.com/1301-ewot/"



async def run_entity_intel_directions_only(
    episode_url: str,
    *,
    user_id: str = "dev",
    pipeline_version: str = "entity-intel-v1",
    intel_run_id: Optional[str] = None,
    save_state_artifacts: bool = True,
    dump_history: bool = True,
) -> Dict[str, Any]:
    """
    Runs ONLY the Candidate + Research Directions graph (directions_graph),
    including Mongo persistence nodes (candidate_runs/entities/dedupe_groups/research_plans).

    Returns final state so you can inspect run_id, plan_ids, etc.
    """
    episode = await get_episode(episode_page_url=episode_url)
    if not episode:
        logger.error("❌ Episode not found: %s", episode_url)
        return {}

    episode_sanitized = sanitize_mongo_document(episode)
    thread_id = make_thread_id_from_episode_url(episode_url)

    cfg_base = base_config(thread_id=thread_id, user_id=user_id)
    cfg_directions = with_checkpoint_ns(cfg_base, NS_DIRECTIONS)

    # IMPORTANT: set intel_run_id once here so persistence nodes share it
    run_id = intel_run_id or str(uuid.uuid4())

    initial_state: Dict[str, Any] = {
        "llm_calls": 0,
        "tool_calls": 0,
        "steps_taken": 0,
        "episode": episode_sanitized,
        "intel_run_id": run_id,
        "intel_pipeline_version": pipeline_version,
    }

    directions_graph = await make_entity_research_directions_graph(cfg_directions)

    final_state = await directions_graph.ainvoke(initial_state, cfg_directions)

    # Helpful values to log / return
    research_directions = final_state.get("research_directions")
    plan_ids = final_state.get("research_plan_ids") or []
    candidate_entity_ids = final_state.get("candidate_entity_ids") or []
    dedupe_group_map = final_state.get("dedupe_group_map") or {}

    logger.info(
        "✅ Directions-only complete. thread_id=%s run_id=%s plans=%s entities=%s dedupe_groups=%s",
        thread_id,
        run_id,
        len(plan_ids),
        len(candidate_entity_ids),
        len(set(dedupe_group_map.values())) if dedupe_group_map else 0,
    )

    if save_state_artifacts:
        suffix = episode_url.replace("/", "_")[:30] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")

        if research_directions is not None:
            # directions is a pydantic model in your code; dump safely
            rd_dump = research_directions.model_dump() if hasattr(research_directions, "model_dump") else research_directions
            await save_json_artifact(rd_dump, "newest_research_outputs", "test_run", "research_directions_final", suffix=suffix)

        await save_json_artifact(_jsonable(final_state), "newest_research_outputs", "test_run", "final_state_directions_graph", suffix=suffix)

    if dump_history:
        # if you want full state history for this graph alone
        try:
            await dump_graph_state_history(
                graph=directions_graph,
                config=cfg_directions,
                run_dir="test_run",
                artifact_name="directions_graph_history",
                suffix=episode_url.replace("/", "_")[:30],
            )
        except Exception as e:
            logger.warning("⚠️ Failed to dump directions graph history: %s", e)

    return {
        "thread_id": thread_id,
        "intel_run_id": run_id,
        "directions_final_state": final_state,
    } 



async def run_full_entity_intel_workflow(
    episode_url: str,
    *,
    user_id: str = "dev",
    pipeline_version: str = "entity-intel-v1",
    intel_run_id: Optional[str] = None,
    # thread behavior
    thread_mode: Literal["episode", "plan"] = "episode",
    # plan selection
    plan_status_to_run: str = "draft",
    limit_plans: int = 50,
    # artifacts
    save_state_artifacts: bool = True,
) -> Dict[str, Any]:
    """
    Full workflow:
      A) run directions graph (seed -> connected sources -> compile directions -> persist intel collections)
      B) query intel_research_plans for this episode
      C) run bundle research graph per plan (bundle = plan.directions)
    """

    # -----------------------
    # Load episode once
    # -----------------------
    episode = await get_episode(episode_page_url=episode_url)
    if not episode:
        logger.error("❌ Episode not found: %s", episode_url)
        return {}

    episode_sanitized = sanitize_mongo_document(episode)

    # -----------------------
    # DIRECTIONS GRAPH
    # -----------------------
    # Thread id policy:
    # - In episode mode: directions + research share same thread_id
    # - In plan mode: directions stays episode thread; plans get their own thread
    episode_thread_id = make_thread_id_from_episode_url(episode_url)

    cfg_base_episode = base_config(thread_id=episode_thread_id, user_id=user_id)
    cfg_directions = _directions_cfg(cfg_base=cfg_base_episode)

    run_id = intel_run_id or str(uuid.uuid4())

    initial_state: Dict[str, Any] = {
        "llm_calls": 0,
        "tool_calls": 0,
        "steps_taken": 0,
        "episode": episode_sanitized,
        "intel_run_id": run_id,
        "intel_pipeline_version": pipeline_version,
    }

    directions_graph = await make_entity_research_directions_graph(cfg_directions)
    directions_final_state = await directions_graph.ainvoke(initial_state, cfg_directions)

    plan_ids_created = directions_final_state.get("research_plan_ids") or []
    logger.info(
        "✅ Directions graph complete. episode_thread=%s run_id=%s plans_created=%s",
        episode_thread_id,
        run_id,
        len(plan_ids_created),
    )

    # -----------------------
    # FIND PLANS FOR EPISODE
    # -----------------------
    plans = await find_plans(
        db=_humanupgrade_db,
        episode_url=episode_url,
        status=plan_status_to_run,
        pipeline_version=pipeline_version,
        limit=limit_plans,
        sort_newest=False,
    )

    if not plans:
        logger.warning("⚠️ No plans found to run. episode=%s status=%s", episode_url, plan_status_to_run)
        return {
            "episode_url": episode_url,
            "thread_id": episode_thread_id,
            "intel_run_id": run_id,
            "directions_final_state": directions_final_state,
            "plans_ran": 0,
            "plan_ids": [],
        }

    # -----------------------
    # RUN EACH PLAN (BUNDLE GRAPH)
    # -----------------------
    plan_results: List[Dict[str, Any]] = []

    for plan_doc in plans:
        plan_id = plan_doc["planId"]
        bundle_obj = await _bundle_from_plan_doc(plan_doc)
        bundle_id = bundle_obj.bundleId

        # choose thread id based on mode
        thread_id_for_this_plan = _thread_id_for_plan(
            episode_url=episode_url,
            plan_id=plan_id,
            thread_mode=thread_mode,
        )

        cfg_base_plan = base_config(thread_id=thread_id_for_this_plan, user_id=user_id)
        cfg_bundle = _bundle_cfg(cfg_base=cfg_base_plan, bundle_id=bundle_id)

        bundle_graph = await make_bundle_research_graph(cfg_bundle)

        # Mark running (optional but helpful)
        await set_plan_status(db=_humanupgrade_db, plan_id=plan_id, status="running")

        bundle_state: Dict[str, Any] = {
            "episode": episode_sanitized,
            "bundle": bundle_obj,
            "bundle_id": bundle_id,
            "direction_queue": [],
            "direction_index": 0,
            "messages": [],
            "file_refs": [],
            "structured_outputs": [],
            "final_reports": [],
            "llm_calls": 0,
            "tool_calls": 0,
            "steps_taken": 0,
        }

        try:
            out = await bundle_graph.ainvoke(bundle_state, cfg_bundle)
            await set_plan_status(db=_humanupgrade_db, plan_id=plan_id, status="complete")
        except Exception as e:
            await set_plan_status(db=_humanupgrade_db, plan_id=plan_id, status="failed", error=str(e))
            raise

        plan_results.append(
            {
                "planId": plan_id,
                "bundleId": bundle_id,
                "threadId": thread_id_for_this_plan,
                "final_reports": out.get("final_reports", []) or [],
                "file_refs": out.get("file_refs", []) or [],
            }
        )

        logger.info("✅ Plan complete planId=%s bundleId=%s thread=%s", plan_id, bundle_id, thread_id_for_this_plan)

    # -----------------------
    # ARTIFACTS
    # -----------------------
    if save_state_artifacts:
        suffix = episode_url.replace("/", "_")[:30] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        await save_json_artifact(_jsonable(directions_final_state), "newest_research_outputs", "test_run", "final_state_directions_graph", suffix=suffix)

        # Save a compact run summary
        summary = {
            "episodeUrl": episode_url,
            "episodeThreadId": episode_thread_id,
            "threadMode": thread_mode,
            "intelRunId": run_id,
            "plansCreated": plan_ids_created,
            "plansRan": [r["planId"] for r in plan_results],
        }
        await save_json_artifact(summary, "newest_research_outputs", "test_run", "workflow_summary", suffix=suffix)

    return {
        "episode_url": episode_url,
        "episode_thread_id": episode_thread_id,
        "thread_mode": thread_mode,
        "intel_run_id": run_id,
        "directions_final_state": directions_final_state,
        "plans_ran": len(plan_results),
        "plan_results": plan_results,
    }

if __name__ == "__main__":
 

    final_state = asyncio.run(run_entity_intel_directions_only(test_run_episode), loop_factory=make_selector_loop)  

 


