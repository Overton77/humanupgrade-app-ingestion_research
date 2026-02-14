"""
Taskiq broker setup for distributed task execution.

Uses:
- RabbitMQ (AioPikaBroker) for task distribution
- Redis (RedisAsyncResultBackend) for result storage

Configuration for long-running IO-bound tasks (LangGraph workflows):
- max_async_tasks: Controls concurrent async tasks per worker process
- worker_count: Number of worker processes (set via CLI)

Windows Event Loop Fix:
-----------------------
The event loop policy is set in research_agent/__init__.py (package root).
This ensures SelectorEventLoop is used instead of ProactorEventLoop,
which is required for psycopg (async PostgreSQL driver) on Windows.
"""
# Ensure event loop policy is set (defense in depth)
from research_agent.utils.windows_event_loop_fix import ensure_selector_event_loop_on_windows
ensure_selector_event_loop_on_windows()

import os
from dotenv import load_dotenv
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import RedisAsyncResultBackend 
from taskiq import TaskiqEvents, TaskiqState 

load_dotenv(override=True)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://taskiq:taskiq@127.0.0.1:5672/")
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

# Result TTL: 1 hour
RESULT_TTL_SECONDS = 3600

# Concurrency: How many async tasks can run concurrently per worker process
# For IO-bound tasks (API calls, DB queries), higher is better
# Recommended: 5-10 for LangGraph workflows with external API calls
MAX_ASYNC_TASKS = int(os.environ.get("TASKIQ_MAX_ASYNC_TASKS", "8"))

# Task timeout: Maximum time a task can run before being killed
# LangGraph workflows can take 5-30 minutes depending on complexity
TASK_TIMEOUT_SECONDS = int(os.environ.get("TASKIQ_TASK_TIMEOUT", "1800"))  # 30 minutes

# Connection timeout: Prevent broker from hanging on connection attempts
CONNECTION_TIMEOUT_SECONDS = int(os.environ.get("TASKIQ_CONNECTION_TIMEOUT", "10"))

broker = AioPikaBroker(
    RABBITMQ_URL,
    max_async_tasks=MAX_ASYNC_TASKS,  # Concurrent async tasks per worker
    task_timeout=TASK_TIMEOUT_SECONDS,  # Task execution timeout
    # CRITICAL: Set connection timeout to prevent blocking
    connection_timeout=CONNECTION_TIMEOUT_SECONDS,
).with_result_backend(
    RedisAsyncResultBackend(
        redis_url=REDIS_URL,
        result_ex_time=RESULT_TTL_SECONDS,
    )
)

# Import tasks to ensure they're registered with the broker
# This must be done after broker is defined to avoid circular imports
try:
    import research_agent.api.tasks.graph_tasks  # noqa: F401
except ImportError:
    # Tasks may not be defined yet during initial setup
    pass


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def init_worker_dependencies(state: TaskiqState) -> None:
    from research_agent.infrastructure.storage.mongo.base_client import mongo_client
    from research_agent.infrastructure.storage.mongo.biotech_research_db_beanie import init_beanie_biotech_db

    print("[taskiq-worker] 🔄 WORKER_STARTUP: initializing MongoDB/Beanie...")
    await init_beanie_biotech_db(mongo_client)
    print("[taskiq-worker] ✅ MongoDB/Beanie initialized")

@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def cleanup_worker_dependencies(state: TaskiqState) -> None:
    from research_agent.infrastructure.storage.mongo.base_client import mongo_client

    print("[taskiq-worker] 🔄 WORKER_SHUTDOWN: closing MongoDB client...")
    await mongo_client.close()  # Logs say Coroutine was not awaited if I use sync 
    print("[taskiq-worker] ✅ MongoDB client closed")