"""
Shared FastAPI dependencies.
"""
from typing import AsyncGenerator
import redis.asyncio as redis
from research_agent.infrastructure.storage.redis.client import get_redis_client


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """Dependency to get Redis client."""
    r = await get_redis_client()
    try:
        yield r
    finally:
        # Don't close here, it's a singleton
        pass
