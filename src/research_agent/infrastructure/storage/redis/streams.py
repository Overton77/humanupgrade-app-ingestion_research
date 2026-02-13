"""
Redis Streams utilities for graph progress updates.

Stream naming convention:
- graph:progress:{run_id} - Progress updates for a specific graph run
"""
import json
from typing import Any, Dict, Optional
import redis.asyncio as redis


async def publish_progress(
    r: redis.Redis,
    run_id: str,
    event_type: str,
    data: Dict[str, Any],
) -> str:
    """
    Publish a progress event to Redis Stream.
    
    Args:
        r: Redis client
        run_id: Unique run identifier
        event_type: Event type (e.g., "node_start", "node_complete", "graph_complete")
        data: Event payload
    
    Returns:
        Message ID from Redis XADD
    """
    stream_name = f"graph:progress:{run_id}"
    
    message = {
        "event_type": event_type,
        "data": json.dumps(data, default=str),
    }
    
    message_id = await r.xadd(stream_name, message)
    
    # Set TTL on stream (24 hours)
    await r.expire(stream_name, 86400)
    
    return message_id


async def subscribe_progress(
    r: redis.Redis,
    run_id: str,
    last_id: str = "0",
    block_ms: int = 5000,
    count: int = 100,
) -> list:
    """
    Subscribe to progress updates for a graph run.
    
    Args:
        r: Redis client
        run_id: Unique run identifier
        last_id: Last message ID received (use "0" for all, "$" for new only)
        block_ms: Milliseconds to block waiting for messages
        count: Maximum messages to return
    
    Returns:
        List of messages
    """
    stream_name = f"graph:progress:{run_id}"
    
    streams = {stream_name: last_id}
    
    # XREAD with BLOCK
    result = await r.xread(streams, count=count, block=block_ms)
    
    if not result:
        return []
    
    # result format: [(stream_name, [(msg_id, msg_dict), ...])]
    messages = []
    for _stream, msgs in result:
        for msg_id, msg_dict in msgs:
            event_type = msg_dict.get("event_type", "unknown")
            data_str = msg_dict.get("data", "{}")
            data = json.loads(data_str)
            
            messages.append({
                "id": msg_id,
                "event_type": event_type,
                "data": data,
            })
    
    return messages
