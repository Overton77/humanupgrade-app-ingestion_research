"""
Taskiq tasks for graph execution.

These tasks run graphs in background workers.
"""
import uuid
from typing import Any, Dict
import redis.asyncio as redis

from research_agent.infrastructure.queue.taskiq_broker import broker
from research_agent.infrastructure.storage.redis.client import get_streams_manager
from research_agent.infrastructure.storage.redis.streams_manager import StreamAddress
from research_agent.infrastructure.storage.redis.event_registry import (
    GROUP_GRAPH,
    CHANNEL_ENTITY_DISCOVERY,
    EVENT_TYPE_START,
    EVENT_TYPE_COMPLETE,
    EVENT_TYPE_ERROR,
)


@broker.task
async def run_entity_discovery_graph(
    query: str,
    starter_sources: list[str],
    starter_content: str,
    run_id: str,
    thread_id: str,
    checkpoint_ns: str,
) -> Dict[str, Any]:
    """
    Execute entity discovery graph.
    
    Args:
        query: Research query
        starter_sources: Starting URLs/domains
        starter_content: Starter context
        run_id: Unique run identifier for progress tracking
        thread_id: LangGraph thread ID
        checkpoint_ns: LangGraph checkpoint namespace
    
    Returns:
        Graph output with candidate sources
    """
    # Import here to avoid circular dependencies
    from research_agent.graphs.entity_candidates_connected_graph import (
        make_entity_intel_connected_candidates_and_sources_graph
    )
    
    # Get streams manager (handles validation and routing)
    manager = await get_streams_manager()
    
    # Create stream address for this run
    addr = StreamAddress(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        key=run_id,
    )
    
    try:
        # Publish start event (validated against EntityCandidateRunStart model)
        await manager.publish(
            addr,
            event_type=EVENT_TYPE_START,
            data={
                "query": query,
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
            },
        )
        
        # Build graph with checkpointing config
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
            }
        }
        
        graph = await make_entity_intel_connected_candidates_and_sources_graph(config)
        
        # Run graph (pass run_id as intel_run_id so all events use the same stream key)
        result = await graph.ainvoke(
            {
                "query": query,
                "starter_sources": starter_sources,
                "starter_content": starter_content,
                "intel_run_id": run_id,  # Critical: ensures progress events use same stream key
            },
            config=config,
        )
        
        # Extract output (now available via OutputState)
        candidate_sources = result.get("candidate_sources")
        intel_run_id = result.get("intel_run_id", run_id)  # Fallback to input run_id if not in output
        pipeline_version = result.get("intel_pipeline_version", "v1")
        
        # Extract entity counts from result (now available via OutputState)
        candidate_entity_ids = result.get("candidate_entity_ids")
        entity_count_val = len(candidate_entity_ids) if candidate_entity_ids else None
        dedupe_group_map = result.get("dedupe_group_map", {})
        dedupe_group_count_val = len(set(dedupe_group_map.values())) if dedupe_group_map else None
        
        # Publish completion event (validated against EntityCandidateRunComplete model)
        await manager.publish(
            addr,
            event_type=EVENT_TYPE_COMPLETE,
            data={
                "intel_run_id": intel_run_id,
                "pipeline_version": pipeline_version,
                "has_candidates": candidate_sources is not None,
                "entity_count": entity_count_val,
                "dedupe_group_count": dedupe_group_count_val,
            },
        )
        
        return {
            "run_id": run_id,
            "candidate_sources": candidate_sources.model_dump() if hasattr(candidate_sources, "model_dump") else candidate_sources,
            "intel_run_id": intel_run_id,
            "pipeline_version": pipeline_version,
        }
    
    except Exception as e:
        # Publish error event (validated against EntityCandidateRunError model)
        await manager.publish(
            addr,
            event_type=EVENT_TYPE_ERROR,
            data={
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise
