from __future__ import annotations

from typing import Any, Dict, List
from langchain_core.runnables import RunnableConfig

from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.utils.state_serializer import snapshot_to_dict
from research_agent.human_upgrade.utils.artifacts import save_json_artifact
from research_agent.human_upgrade.utils.graph_namespaces import (
    with_checkpoint_ns,
    NS_DIRECTIONS,
    NS_PARENT,
    ns_bundle,
    ns_direction,
)

def _safe_suffix(s: str, max_len: int = 80) -> str:
    # filesystem-friendly
    s = s.replace("/", "_").replace("\\", "_").replace(":", "_")
    return s[:max_len]

def _get_bundles(research_directions: Any) -> List[Any]:
    """
    Works if research_directions is:
    - Pydantic model with .bundles
    - dict with "bundles"
    - None
    """
    if research_directions is None:
        return []
    if isinstance(research_directions, dict):
        return research_directions.get("bundles", []) or []
    return getattr(research_directions, "bundles", []) or []


async def dump_graph_state_history(
    *,
    graph,
    config: RunnableConfig,
    run_dir: str,
    artifact_name: str,
    suffix: str,
) -> None:
    """
    Fetch history (reverse chronological), serialize, and write to filesystem via save_json_artifact.
    """
    try:
        states = list(graph.get_state_history(config))  # newest -> oldest
    except Exception:
        logger.exception(
            "Failed to get_state_history artifact_name=%s suffix=%s configurable=%s",
            artifact_name,
            suffix,
            (config or {}).get("configurable", {}),
        )
        raise

    payload = [snapshot_to_dict(s) for s in states]

    await save_json_artifact(
        payload,
        run_dir,
        artifact_name,
        suffix=_safe_suffix(suffix),
    )


async def dump_full_workflow_histories(
    *,
    directions_graph,
    parent_graph,
    cfg_base: RunnableConfig,
    episode_url: str,
    research_directions,
) -> None:
    """
    Dumps state histories for:
      - directions graph
      - parent graph
      - per-bundle histories
      - per-direction histories
    """
    suffix = _safe_suffix(episode_url)

    # 1) Directions graph history
    await dump_graph_state_history(
        graph=directions_graph,
        config=with_checkpoint_ns(cfg_base, NS_DIRECTIONS),
        run_dir="test_run",
        artifact_name="state_history_directions_graph",
        suffix=suffix,
    )

    # 2) Parent graph history
    await dump_graph_state_history(
        graph=parent_graph,
        config=with_checkpoint_ns(cfg_base, NS_PARENT),
        run_dir="test_run",
        artifact_name="state_history_parent_graph",
        suffix=suffix,
    )

    # 3) Bundle + Direction histories
    try:
        bundles = _get_bundles(research_directions)

        for b in bundles:
            # bundle could be dict or pydantic
            bundle_id = b.get("bundleId") if isinstance(b, dict) else getattr(b, "bundleId", None)
            if not bundle_id:
                logger.warning("Skipping bundle with missing bundleId. bundle=%s", type(b).__name__)
                continue

            bundle_suffix = _safe_suffix(f"{suffix}__{bundle_id}")

            # Bundle history
            await dump_graph_state_history(
                graph=parent_graph,
                config=with_checkpoint_ns(cfg_base, ns_bundle(bundle_id)),
                run_dir="test_run",
                artifact_name="state_history_bundle",
                suffix=bundle_suffix,
            )

            # Direction queue (match your deterministic logic)
            direction_queue = ["GUEST"]
            business = b.get("businessDirection") if isinstance(b, dict) else getattr(b, "businessDirection", None)
            products = b.get("productsDirection") if isinstance(b, dict) else getattr(b, "productsDirection", None)
            compounds = b.get("compoundsDirection") if isinstance(b, dict) else getattr(b, "compoundsDirection", None)
            platforms = b.get("platformsDirection") if isinstance(b, dict) else getattr(b, "platformsDirection", None)

            if business is not None:
                direction_queue.append("BUSINESS")
            if products is not None:
                direction_queue.append("PRODUCT")
            if compounds is not None:
                direction_queue.append("COMPOUND")
            if platforms is not None:
                direction_queue.append("PLATFORM")

            for direction_type in direction_queue:
                await dump_graph_state_history(
                    graph=parent_graph,
                    config=with_checkpoint_ns(cfg_base, ns_direction(bundle_id, direction_type)),
                    run_dir="test_run",
                    artifact_name="state_history_direction",
                    suffix=_safe_suffix(f"{suffix}__{bundle_id}__{direction_type}"),
                )

    except Exception:
        logger.exception("Failed dumping bundle/direction histories (continuing).")