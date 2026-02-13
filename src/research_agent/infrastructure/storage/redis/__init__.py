"""Redis client and utilities."""

from .client import get_redis_client, close_redis_client, get_streams_manager
from .streams_manager import RedisStreamsManager, StreamAddress, StreamEvent, EventRouter
from .event_registry import (
    create_event_router,
    GROUP_GRAPH,
    CHANNEL_ENTITY_DISCOVERY,
    EVENT_TYPE_START,
    EVENT_TYPE_COMPLETE,
    EVENT_TYPE_ERROR,
)

__all__ = [
    # Client functions
    "get_redis_client",
    "close_redis_client",
    "get_streams_manager",
    # Streams manager classes
    "RedisStreamsManager",
    "StreamAddress",
    "StreamEvent",
    "EventRouter",
    # Event registry
    "create_event_router",
    # Constants
    "GROUP_GRAPH",
    "CHANNEL_ENTITY_DISCOVERY",
    "EVENT_TYPE_START",
    "EVENT_TYPE_COMPLETE",
    "EVENT_TYPE_ERROR",
]