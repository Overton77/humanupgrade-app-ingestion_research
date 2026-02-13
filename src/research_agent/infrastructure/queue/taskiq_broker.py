"""
Taskiq broker setup for distributed task execution.

Uses:
- RabbitMQ (AioPikaBroker) for task distribution
- Redis (RedisAsyncResultBackend) for result storage
"""
import os
from dotenv import load_dotenv
from taskiq_aio_pika import AioPikaBroker
from taskiq_redis import RedisAsyncResultBackend

load_dotenv(override=True)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Result TTL: 1 hour
RESULT_TTL_SECONDS = 3600

broker = AioPikaBroker(RABBITMQ_URL).with_result_backend(
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
