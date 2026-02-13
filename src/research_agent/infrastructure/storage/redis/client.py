"""
Redis client for caching and pub/sub.
"""
import os
from typing import Optional
import redis.asyncio as redis
from dotenv import load_dotenv

from research_agent.infrastructure.storage.redis.streams_manager import RedisStreamsManager
from research_agent.infrastructure.storage.redis.event_registry import create_event_router

load_dotenv()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

_redis_client: Optional[redis.Redis] = None
_streams_manager: Optional[RedisStreamsManager] = None


async def get_redis_client() -> redis.Redis:
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


async def get_streams_manager() -> RedisStreamsManager:
    """
    Get or create Redis Streams Manager with configured event router.
    
    This manager handles:
    - Type-safe event publishing
    - Event validation with Pydantic models
    - Event routing and handling
    - Automatic stream TTL and maxlen management
    
    Returns:
        Configured RedisStreamsManager instance
    """
    global _streams_manager
    if _streams_manager is None:
        r = await get_redis_client()
        router = create_event_router()
        _streams_manager = RedisStreamsManager(
            r,
            router=router,
            ttl_seconds=86400,  # 24 hours
            maxlen=2000,  # Keep last 2000 events per stream
        )
    return _streams_manager


async def close_redis_client() -> None:
    """Close Redis client and reset manager."""
    global _redis_client, _streams_manager
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        _streams_manager = None  # Reset manager when client closes