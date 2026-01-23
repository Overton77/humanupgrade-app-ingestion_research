from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig 

import asyncio
from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.utils.state_serializer import sanitize_mongo_document

from research_agent.human_upgrade.structured_outputs.research_direction_outputs import (
    EntityBundleDirectionsFinal,
)

from research_agent.retrieval.async_mongo_client import get_episode  # your existing function
from research_agent.retrieval.async_mongo_client import _humanupgrade_db  # optional default

from research_agent.retrieval.intel_mongo_helpers import (
    find_plan_by_id,
    find_plans,
    claim_next_plan,
    set_plan_status,
    mark_plan_execution_meta,
)

# ✅ Use graph_namespaces.py as source of truth
from research_agent.human_upgrade.utils.graph_namespaces import (
    base_config,
    with_checkpoint_ns,
    ns_bundle,
    plan_thread_id,
) 


# Import your graph factory
from research_agent.human_upgrade.entity_research_graphs import make_bundle_research_graph

from research_agent.common.artifacts import save_json_artifact
def _bundle_cfg(*, cfg_base: RunnableConfig, bundle_id: str) -> RunnableConfig:
    return with_checkpoint_ns(cfg_base, ns_bundle(bundle_id))


async def build_bundle_from_plan_doc(plan_doc: Dict[str, Any]) -> EntityBundleDirectionsFinal:
    directions = plan_doc.get("directions")
    if not directions:
        raise ValueError(f"planId={plan_doc.get('planId')} missing directions")

    # Stored dict matches this schema.
    return EntityBundleDirectionsFinal.model_validate(directions)


async def run_research_plan_bundle(
    *,
    plan_doc: Dict[str, Any],
    db=_humanupgrade_db,
    user_id: str = "dev",
    max_web_tool_calls_hint: int = 18,
) -> Dict[str, Any]:
    """
    Runs ONE plan doc through BundleResearchSubGraph.
    Updates plan status + writes execution metadata back to mongo.
    """
    plan_id = plan_doc["planId"]
    episode_url = plan_doc.get("episodeUrl") or "unknown"

    # 1) build bundle from plan
    bundle_obj = await build_bundle_from_plan_doc(plan_doc) 

    print(f"bundle_obj: {bundle_obj}")
    bundle_id = bundle_obj.bundleId

    # 2) load episode
    episode = await get_episode(episode_page_url=episode_url)
    if not episode:
        raise ValueError(f"Episode not found for planId={plan_id} url={episode_url}")

    episode_sanitized = sanitize_mongo_document(episode)

    # 3) mark running
    await set_plan_status(db=db, plan_id=plan_id, status="running")

    # 4) create cfg + graph (✅ uses graph_namespaces.plan_thread_id, DELIM-safe)
    thread_id = plan_thread_id(episode_url=episode_url, plan_id=plan_id)
    cfg_base = base_config(thread_id=thread_id, user_id=user_id)
    cfg_bundle = _bundle_cfg(cfg_base=cfg_base, bundle_id=bundle_id)

    bundle_graph = await make_bundle_research_graph(cfg_bundle)

    # 5) bundle state
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
        "max_web_tool_calls_hint": max_web_tool_calls_hint,
    }

    try:
        out = await bundle_graph.ainvoke(bundle_state, cfg_bundle) 

    except Exception as e:
        await set_plan_status(db=db, plan_id=plan_id, status="failed", error=str(e))
        raise

    # 6) mark complete + persist metadata
    await set_plan_status(db=db, plan_id=plan_id, status="complete")

    execution = {
        "executionRunId": str(uuid.uuid4()),
        "threadId": thread_id,
        "bundleId": bundle_id,
        "completedAt": str(plan_doc.get("updatedAt") or ""),
        "finalReports": [
            fr.model_dump() if hasattr(fr, "model_dump") else fr
            for fr in (out.get("final_reports") or [])
        ],
        "fileRefs": [
            fr.model_dump() if hasattr(fr, "model_dump") else fr
            for fr in (out.get("file_refs") or [])
        ],
    }
    await mark_plan_execution_meta(db=db, plan_id=plan_id, execution=execution)

    logger.info("✅ Plan executed planId=%s bundleId=%s", plan_id, bundle_id)  

    await save_json_artifact(out, "newest_research_outputs", f"{bundle_id}{str(uuid.uuid4())}", "bundle_research_output", suffix=episode_url.replace("/", "_")[:30])
    return out


async def run_plan_by_id(
    *,
    plan_id: str,
    db=_humanupgrade_db,
    user_id: str = "dev",
) -> Dict[str, Any]:
    plan = await find_plan_by_id(db=db, plan_id=plan_id)
    if not plan:
        raise ValueError(f"Plan not found: {plan_id}")
    return await run_research_plan_bundle(plan_doc=plan, db=db, user_id=user_id)


async def run_plans_for_episode(
    *,
    episode_url: str,
    status: str = "draft",
    limit: int = 25,
    db=_humanupgrade_db,
    user_id: str = "dev",
) -> List[Dict[str, Any]]:
    """
    Finds plans by episodeUrl and runs them sequentially.
    """
    plans = await find_plans(
        db=db,
        episode_url=episode_url,
        status=status,
        limit=limit,
        sort_newest=False,
    )

    results: List[Dict[str, Any]] = []
    for p in plans:
        results.append(await run_research_plan_bundle(plan_doc=p, db=db, user_id=user_id))

    return results


async def run_next_n_claimed_plans(
    *,
    n: int = 10,
    pipeline_version: Optional[str] = None,
    db=_humanupgrade_db,
    user_id: str = "dev",
) -> int:
    """
    Claims next draft plans and runs them.
    Great for batching: run your candidate workflow over many episodes,
    then run this to execute research.

    Returns: number of SUCCESSFULLY completed plans.
    """
    succeeded = 0

    for _ in range(int(n)):
        plan = await claim_next_plan(db=db, pipeline_version=pipeline_version)
        if not plan:
            return succeeded

        try:
            await run_research_plan_bundle(plan_doc=plan, db=db, user_id=user_id)
            succeeded += 1
        except Exception:
            # status already set to failed
            logger.exception("❌ Plan failed planId=%s", plan.get("planId"))
            # do NOT increment succeeded

    return succeeded 
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


if __name__ == "__main__":
    async def main_run(): 
        results = await run_plans_for_episode( 
            episode_url="https://daveasprey.com/1353-vinia-bioharvest/",
            status="draft",
            limit=25,
            db=_humanupgrade_db,
            user_id="dev",
        ) 

        print(f"results: {results}") 

    asyncio.run(main_run())