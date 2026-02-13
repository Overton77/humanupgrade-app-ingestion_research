"""
Health check endpoints.
"""
from fastapi import APIRouter, Depends
import redis.asyncio as redis

from research_agent.api.common.dependencies import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(r: redis.Redis = Depends(get_redis)):
    """
    Readiness check - verifies Redis connection.
    """
    try:
        await r.ping()
        return {"status": "ready", "redis": "connected"}
    except Exception as e:
        return {"status": "not_ready", "redis": "disconnected", "error": str(e)}
