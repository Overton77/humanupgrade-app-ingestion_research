import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import redis.asyncio as redis


RUNNABLE_STREAM = os.getenv("RUNNABLE_STREAM", "mission:runnable")
EVENTS_STREAM = os.getenv("EVENTS_STREAM", "mission:events")
CONSUMER_GROUP = os.getenv("CONSUMER_GROUP", "workers")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", f"worker-{uuid.uuid4().hex[:6]}")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Controls how long XREADGROUP blocks (ms) and how many messages to pull at once
XREAD_BLOCK_MS = int(os.getenv("XREAD_BLOCK_MS", "5000"))
XREAD_COUNT = int(os.getenv("XREAD_COUNT", "10"))

# Concurrency inside the worker process (async tasks at once)
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "5"))


# Helper 

def to_str(x: Any) -> Any:
    if isinstance(x, (bytes, bytearray)):
        return x.decode()
    return x

@dataclass(frozen=True)
class RunnableTask:
    task_id: str
    mission_id: str
    task_type: str
    payload: Dict[str, Any]
    created_at_ms: int


def now_ms() -> int:
    return int(time.time() * 1000)


async def ensure_consumer_group(r: redis.Redis) -> None:
    """
    Ensure the consumer group exists for the runnable stream.
    MKSTREAM creates the stream if missing.
    """
    try:
        await r.xgroup_create(
            name=RUNNABLE_STREAM,
            groupname=CONSUMER_GROUP,
            id="0",  # start from beginning (safe for dev)
            mkstream=True,
        )
        print(f"[setup] created consumer group '{CONSUMER_GROUP}' on stream '{RUNNABLE_STREAM}'")
    except Exception as e:
        # BUSYGROUP means it already exists
        if "BUSYGROUP" in str(e):
            print(f"[setup] consumer group '{CONSUMER_GROUP}' already exists")
        else:
            raise


async def publish_event(
    r: redis.Redis,
    mission_id: str,
    task_id: str,
    event_type: str,
    data: Optional[Dict[str, Any]] = None,
) -> str:
    safe_data = {k: to_str(v) for k, v in (data or {}).items()}

    event = {
        "mission_id": mission_id,
        "task_id": task_id,
        "event_type": event_type,
        "ts_ms": str(now_ms()),
        "data": json.dumps(safe_data),
    }
    event_id = await r.xadd(EVENTS_STREAM, event)
    return event_id


# --------------------------
# Hard-coded "workflow" logic
# --------------------------
async def run_hardcoded_workflow(task: RunnableTask) -> Dict[str, Any]:
    """
    This simulates a stage/substage/subagent task execution.
    Replace this later with your LangGraph node executor.
    """
    if task.task_type == "HELLO_WORLD":
        name = task.payload.get("name", "world")
        await asyncio.sleep(0.2)
        return {"message": f"Hello, {name}!", "task_id": task.task_id}

    if task.task_type == "FAN_OUT":
        # Example: pretend this step "discovers" new work (we won't enqueue it yet)
        await asyncio.sleep(0.4)
        n = int(task.payload.get("n", 3))
        return {"spawn_suggestions": [f"child-{i}" for i in range(n)]}

    if task.task_type == "SLOW_IO":
        # Simulate external calls
        delay = float(task.payload.get("delay", 1.0))
        await asyncio.sleep(delay)
        return {"slept_seconds": delay}

    raise ValueError(f"Unknown task_type: {task.task_type}")


# --------------------------
# Worker implementation
# --------------------------
async def handle_message(
    r: redis.Redis,
    message_id: str,
    fields: Dict[bytes, bytes],
    sem: asyncio.Semaphore,
) -> None:
    """
    Process a single runnable message and ACK it on success.
    """
    async with sem:
        # Decode fields from Redis (bytes -> str)
        decoded: Dict[str, str] = {k.decode(): v.decode() for k, v in fields.items()}

        # Parse runnable task
        task = RunnableTask(
            task_id=decoded["task_id"],
            mission_id=decoded["mission_id"],
            task_type=decoded["task_type"],
            payload=json.loads(decoded.get("payload", "{}")),
            created_at_ms=int(decoded.get("created_at_ms", "0") or "0"),
        )

        try:
            await publish_event(r, task.mission_id, task.task_id, "TASK_STARTED", {"message_id": message_id})
            result = await run_hardcoded_workflow(task)
            await publish_event(r, task.mission_id, task.task_id, "TASK_SUCCEEDED", {"result": result})

            # ACK runnable message
            await r.xack(RUNNABLE_STREAM, CONSUMER_GROUP, message_id)
            await publish_event(r, task.mission_id, task.task_id, "TASK_ACKED", {"message_id": message_id})

            print(f"[worker:{CONSUMER_NAME}] ✅ {task.task_type} task_id={task.task_id} acked={message_id}")
        except Exception as e:
            # Do NOT ACK on failure -> stays pending; can be retried/reclaimed later
            await publish_event(
                r,
                task.mission_id,
                task.task_id,
                "TASK_FAILED",
                {"error": repr(e), "message_id": message_id},
            )
            print(f"[worker:{CONSUMER_NAME}] ❌ task_id={task.task_id} error={e!r} (NOT acked)")


async def worker_loop() -> None:
    r = redis.from_url(REDIS_URL, decode_responses=False)
    await ensure_consumer_group(r)

    sem = asyncio.Semaphore(WORKER_CONCURRENCY)

    print(
        f"[worker:{CONSUMER_NAME}] listening on stream='{RUNNABLE_STREAM}' group='{CONSUMER_GROUP}' "
        f"events='{EVENTS_STREAM}' concurrency={WORKER_CONCURRENCY}"
    )

    try:
        while True:
            # XREADGROUP returns: [(stream_name, [(message_id, {field: value, ...}), ...]) ...]
            resp = await r.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={RUNNABLE_STREAM: ">"},
                count=XREAD_COUNT,
                block=XREAD_BLOCK_MS,
            )

            if not resp:
                continue

            # Flatten and spawn tasks
            for _stream_name, messages in resp:
                for message_id, fields in messages:
                    # fire-and-forget within concurrency guard
                    asyncio.create_task(handle_message(r, message_id, fields, sem))

    finally:
        await r.aclose()


# --------------------------
# Producer / test sender
# --------------------------
async def produce_test_tasks() -> None:
    r = redis.from_url(REDIS_URL, decode_responses=False)

    mission_id = f"mission-{uuid.uuid4().hex[:8]}"

    tasks = [
        {
            "task_id": f"task-{uuid.uuid4().hex[:8]}",
            "mission_id": mission_id,
            "task_type": "HELLO_WORLD",
            "payload": {"name": "Human Upgrade"},
        },
        {
            "task_id": f"task-{uuid.uuid4().hex[:8]}",
            "mission_id": mission_id,
            "task_type": "SLOW_IO",
            "payload": {"delay": 0.8},
        },
        {
            "task_id": f"task-{uuid.uuid4().hex[:8]}",
            "mission_id": mission_id,
            "task_type": "FAN_OUT",
            "payload": {"n": 5},
        },
    ]

    for t in tasks:
        msg = {
            "task_id": t["task_id"],
            "mission_id": t["mission_id"],
            "task_type": t["task_type"],
            "payload": json.dumps(t["payload"]),
            "created_at_ms": str(now_ms()),
        }
        message_id = await r.xadd(RUNNABLE_STREAM, msg)
        print(f"[producer] enqueued {t['task_type']} task_id={t['task_id']} message_id={message_id}")

        # Also emit an event that it was enqueued (optional)
        await publish_event(r, t["mission_id"], t["task_id"], "TASK_ENQUEUED", {"message_id": message_id})

    await r.aclose()
    print(f"[producer] done. mission_id={mission_id}")


async def tail_events(seconds: float = 5.0) -> None:
    """
    Simple event tailer for quick verification.
    Uses XREAD (not groups) starting from '$' (new events only).
    """
    r = redis.from_url(REDIS_URL, decode_responses=True)
    start_id = "$"
    deadline = time.time() + seconds
    print(f"[tail] tailing events for {seconds:.1f}s from '{EVENTS_STREAM}'...")
    while time.time() < deadline:
        resp = await r.xread({EVENTS_STREAM: start_id}, block=1000, count=50)
        if not resp:
            continue
        for _stream, msgs in resp:
            for mid, fields in msgs:
                start_id = mid
                print(f"[event] {mid} {fields.get('event_type')} task_id={fields.get('task_id')} data={fields.get('data')}")
    await r.aclose()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Redis Streams runnable worker + test producer")
    parser.add_argument("mode", choices=["worker", "produce", "tail"], help="Run worker, produce test tasks, or tail events")
    parser.add_argument("--tail-seconds", type=float, default=5.0)
    args = parser.parse_args()

    if args.mode == "worker":
        asyncio.run(worker_loop())
    elif args.mode == "produce":
        asyncio.run(produce_test_tasks())
    elif args.mode == "tail":
        asyncio.run(tail_events(args.tail_seconds))


if __name__ == "__main__":
    main()
