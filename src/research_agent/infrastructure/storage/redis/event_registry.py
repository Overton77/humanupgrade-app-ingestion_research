"""
Redis Streams event registry and router setup.

This module defines the event routing structure for the application:
- Group: High-level category (e.g., "graph")
- Channel: Specific subsystem (e.g., "entity_discovery")
- Event Type: Specific event (e.g., "start", "complete", "error")
- Data Model: Pydantic model for validation
- Handlers: Functions to process events
"""
from typing import List, Optional

from research_agent.infrastructure.storage.redis.streams_manager import EventRouter, Handler
from research_agent.infrastructure.storage.redis.entity_candidate_run_events import (
    # Lifecycle events
    EntityCandidateRunStart,
    EntityCandidateRunComplete,
    EntityCandidateRunError,
    # Progress events
    EntityCandidateRunInitialized,
    EntityCandidateRunSeedsComplete,
    EntityCandidateRunOfficialSourcesComplete,
    EntityCandidateRunDomainCatalogsComplete,
    EntityCandidateRunSliceStarted,
    EntityCandidateRunSliceComplete,
    EntityCandidateRunMergeComplete,
    EntityCandidateRunPersistenceComplete,
)


# Event naming constants
GROUP_GRAPH = "graph"
CHANNEL_ENTITY_DISCOVERY = "entity_discovery"

# Lifecycle events
EVENT_TYPE_START = "start"
EVENT_TYPE_COMPLETE = "complete"
EVENT_TYPE_ERROR = "error"

# Progress events
EVENT_TYPE_INITIALIZED = "initialized"
EVENT_TYPE_SEEDS_COMPLETE = "seeds_complete"
EVENT_TYPE_OFFICIAL_SOURCES_COMPLETE = "official_sources_complete"
EVENT_TYPE_DOMAIN_CATALOGS_COMPLETE = "domain_catalogs_complete"
EVENT_TYPE_SLICE_STARTED = "slice_started"
EVENT_TYPE_SLICE_COMPLETE = "slice_complete"
EVENT_TYPE_MERGE_COMPLETE = "merge_complete"
EVENT_TYPE_PERSISTENCE_COMPLETE = "persistence_complete"


def create_event_router(
    additional_handlers: Optional[dict] = None
) -> EventRouter:
    """
    Create and configure the event router with all event types and their models.
    
    Args:
        additional_handlers: Optional dict mapping (group, channel, event_type) tuples
                           to lists of handlers. Use this to register custom handlers
                           without modifying this file.
    
    Returns:
        Configured EventRouter instance
    
    Example:
        >>> router = create_event_router()
        >>> # Or with custom handlers
        >>> async def my_handler(event: StreamEvent):
        ...     print(f"Received: {event.event_type}")
        >>> 
        >>> handlers = {
        ...     ("graph", "entity_discovery", "complete"): [my_handler]
        ... }
        >>> router = create_event_router(additional_handlers=handlers)
    """
    router = EventRouter()
    
    # =========================================================================
    # Entity Discovery - Lifecycle Events
    # =========================================================================
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_START,
        data_model=EntityCandidateRunStart,
        handlers=[],
    )
    
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_COMPLETE,
        data_model=EntityCandidateRunComplete,
        handlers=[],
    )
    
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_ERROR,
        data_model=EntityCandidateRunError,
        handlers=[],
    )
    
    # =========================================================================
    # Entity Discovery - Progress Events
    # =========================================================================
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_INITIALIZED,
        data_model=EntityCandidateRunInitialized,
        handlers=[],
    )
    
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_SEEDS_COMPLETE,
        data_model=EntityCandidateRunSeedsComplete,
        handlers=[],
    )
    
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_OFFICIAL_SOURCES_COMPLETE,
        data_model=EntityCandidateRunOfficialSourcesComplete,
        handlers=[],
    )
    
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_DOMAIN_CATALOGS_COMPLETE,
        data_model=EntityCandidateRunDomainCatalogsComplete,
        handlers=[],
    )
    
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_SLICE_STARTED,
        data_model=EntityCandidateRunSliceStarted,
        handlers=[],
    )
    
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_SLICE_COMPLETE,
        data_model=EntityCandidateRunSliceComplete,
        handlers=[],
    )
    
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_MERGE_COMPLETE,
        data_model=EntityCandidateRunMergeComplete,
        handlers=[],
    )
    
    router.register(
        group=GROUP_GRAPH,
        channel=CHANNEL_ENTITY_DISCOVERY,
        event_type=EVENT_TYPE_PERSISTENCE_COMPLETE,
        data_model=EntityCandidateRunPersistenceComplete,
        handlers=[],
    )
    
    # Add any additional handlers provided
    if additional_handlers:
        for (group, channel, event_type), handlers in additional_handlers.items():
            for handler in handlers:
                router.add_handler(
                    group=group,
                    channel=channel,
                    event_type=event_type,
                    handler=handler,
                )
    
    return router
