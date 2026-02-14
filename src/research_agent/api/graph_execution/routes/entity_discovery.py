"""
Entity discovery graph execution endpoints.
"""
import json
import uuid
import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
import redis.asyncio as redis

from research_agent.api.common.dependencies import get_redis
from research_agent.api.common.responses import TaskResponse, ErrorResponse
from research_agent.api.graph_execution.schemas.entity_discovery import (
    EntityDiscoveryRequest,
    EntityDiscoveryResponse,
)
from research_agent.api.graph_execution.websockets.connection_manager import manager
from research_agent.api.tasks.graph_tasks import run_entity_discovery_graph
from research_agent.infrastructure.storage.redis.client import get_streams_manager
from research_agent.infrastructure.storage.redis.streams_manager import StreamAddress
from research_agent.infrastructure.storage.redis.event_registry import (
    GROUP_GRAPH,
    CHANNEL_ENTITY_DISCOVERY,
    EVENT_TYPE_START,
    EVENT_TYPE_COMPLETE,
    EVENT_TYPE_ERROR,
)

router = APIRouter(prefix="/entity-discovery", tags=["entity-discovery"])


@router.post(
    "/execute",
    response_model=TaskResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def execute_entity_discovery(
    request: EntityDiscoveryRequest,
    r: redis.Redis = Depends(get_redis),
) -> TaskResponse:
    """
    Execute entity discovery graph asynchronously.
    
    Returns a task ID and run ID for tracking progress via WebSocket.
    
    **Workflow:**
    1. Enqueue graph execution task to RabbitMQ via Taskiq
    2. Return task_id + run_id immediately
    3. Client connects to WebSocket `/ws/entity-discovery/{run_id}` for progress
    """
    # Generate IDs
    run_id = str(uuid.uuid4())
    thread_id = request.thread_id or f"thread_{run_id}"
    checkpoint_ns = request.checkpoint_ns or f"ns_{run_id}"
    
    try:
        # Enqueue task
        print(f"[api] Enqueuing entity discovery task for run_id={run_id}")
        task = await run_entity_discovery_graph.kiq(
            query=request.query,
            starter_sources=request.starter_sources,
            starter_content=request.starter_content,
            run_id=run_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
        )
        print(f"[api] ✅ Task enqueued: task_id={task.task_id}, run_id={run_id}")
        
        return TaskResponse(
            task_id=task.task_id,
            run_id=run_id,
            status="pending",
            message=f"Entity discovery graph enqueued. Connect to WebSocket /ws/entity-discovery/{run_id} for progress.",
        )
    
    except Exception as e:
        print(f"[api] ❌ Failed to enqueue task: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue task: {str(e)}",
        )


@router.websocket("/ws/{run_id}")
async def websocket_entity_discovery_progress(
    websocket: WebSocket,
    run_id: str,
):
    """
    WebSocket endpoint for streaming entity discovery progress.
    
    Streams ALL event types (lifecycle + progress) for the given run_id.
    
    **Message Format:**
    ```json
    {
        "id": "1234567890-0",
        "event_type": "start" | "complete" | "error" | "initialized" | ...,
        "group": "graph",
        "channel": "entity_discovery",
        "key": "<run_id>",
        "data": { ... validated against Pydantic models },
        "meta": { ... },
        "ts": 1234567890.123
    }
    ```
    
    **Lifecycle Event Types:**
    - `start`: Graph execution started (EntityCandidateRunStart)
    - `complete`: Graph execution completed (EntityCandidateRunComplete)
    - `error`: Graph execution failed (EntityCandidateRunError)
    
    **Progress Event Types:**
    - `initialized`: Graph state initialized (EntityCandidateRunInitialized)
    - `seeds_complete`: Seed entities processed (EntityCandidateRunSeedsComplete)
    - `official_sources_complete`: Official sources processed (EntityCandidateRunOfficialSourcesComplete)
    - `domain_catalogs_complete`: Domain catalogs processed (EntityCandidateRunDomainCatalogsComplete)
    - `slice_started`: Processing slice started (EntityCandidateRunSliceStarted)
    - `slice_complete`: Processing slice completed (EntityCandidateRunSliceComplete)
    - `merge_complete`: Entity merge completed (EntityCandidateRunMergeComplete)
    - `persistence_complete`: Database persistence completed (EntityCandidateRunPersistenceComplete)
    
    **Client-Side Filtering:**
    The client can choose to filter events by event_type if only specific events are needed.
    """
    await manager.connect(websocket, run_id)
    
    # Get streams manager
    streams_manager = await get_streams_manager()
    
    # Create stream address for this run
    addr = StreamAddress(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        key=run_id,
    )
    
    try:
        # Send initial connection confirmation
        await manager.send_personal_message(
            json.dumps({
                "event_type": "connected",
                "group": GROUP_GRAPH,
                "channel": CHANNEL_ENTITY_DISCOVERY,
                "key": run_id,
                "data": {"run_id": run_id, "message": "Connected to progress stream"},
            }),
            websocket,
        )
        
        last_id = "0"  # Start from beginning
        
        # Poll Redis Streams for progress updates
        while True:
            # Read events using the manager
            events = await streams_manager.read(
                addr,
                last_id=last_id,
                block_ms=2000,
                count=10,
            )
            
            for event in events:
                # Send validated event to WebSocket
                await manager.send_personal_message(
                    event.model_dump_json(),
                    websocket,
                )
                
                last_id = event.id or last_id
                
                # If graph completed or errored, close connection
                if event.event_type in [EVENT_TYPE_COMPLETE, EVENT_TYPE_ERROR]:
                    await asyncio.sleep(0.5)  # Give client time to receive
                    break
            
            # Check if graph finished
            if events and any(e.event_type in [EVENT_TYPE_COMPLETE, EVENT_TYPE_ERROR] for e in events):
                break
    
    except WebSocketDisconnect:
        await manager.disconnect(websocket, run_id)
    
    except Exception as e:
        # Send error and close
        try:
            await manager.send_personal_message(
                json.dumps({
                    "event_type": "ws_error",
                    "group": GROUP_GRAPH,
                    "channel": CHANNEL_ENTITY_DISCOVERY,
                    "key": run_id,
                    "data": {"error": str(e)},
                }),
                websocket,
            )
        except Exception:
            pass
        
        await manager.disconnect(websocket, run_id)
    
    finally:
        await manager.disconnect(websocket, run_id)


@router.get("/status/{run_id}")
async def get_run_status(
    run_id: str,
) -> Dict[str, Any]:
    """
    Get current status of a graph run by reading Redis Stream.
    
    Returns the latest progress events with validated data models.
    """
    # Get streams manager
    streams_manager = await get_streams_manager()
    
    # Create stream address for this run
    addr = StreamAddress(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        key=run_id,
    )
    
    # Read all events (non-blocking)
    events = await streams_manager.read(
        addr,
        last_id="0",
        block_ms=0,  # Non-blocking
        count=100,
    )
    
    if not events:
        raise HTTPException(status_code=404, detail=f"No progress found for run_id: {run_id}")
    
    # Extract latest status
    latest = events[-1]
    
    return {
        "run_id": run_id,
        "latest_event": latest.event_type,
        "latest_data": latest.data,
        "total_events": len(events),
        "events": [event.model_dump() for event in events],
    }
