# Research Agent API

FastAPI-based API layer for executing research graphs with real-time progress streaming.

## Architecture

```
┌─────────────┐      HTTP POST       ┌──────────────────┐
│   Client    │ ──────────────────▶  │  FastAPI Server  │
│             │                      │  (Graph Exec)    │
└─────────────┘                      └──────────────────┘
       │                                      │
       │                                      │ Enqueue Task
       │                                      ▼
       │                              ┌──────────────────┐
       │                              │   RabbitMQ       │
       │                              │   (Taskiq)       │
       │                              └──────────────────┘
       │                                      │
       │                                      │ Consume Task
       │                                      ▼
       │                              ┌──────────────────┐
       │                              │  Taskiq Worker   │
       │                              │  (Run Graph)     │
       │                              └──────────────────┘
       │                                      │
       │                                      │ Publish Progress
       │                                      ▼
       │                              ┌──────────────────┐
       │   WebSocket Subscribe        │  Redis Streams   │
       │ ◀────────────────────────────│  (Progress)      │
       │                              └──────────────────┘
       │
       ▼
  Progress Updates
  (Real-time)
```

## Quick Start

### 1. Start Required Services

```bash
# Redis (for progress streaming)
docker run -d --name redis -p 6379:6379 redis:7-alpine

# RabbitMQ (for task queue)
docker run -d --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  rabbitmq:3-management
```

### 2. Start API Server

```bash
# Terminal 1: FastAPI Graph Execution API
cd ingestion
python -m research_agent.scripts.run_graph_api

# Or with uvicorn directly
uvicorn research_agent.api.graph_execution.main:app --reload --port 8001
```

### 3. Start Taskiq Worker

```bash
# Terminal 2: Taskiq worker
cd ingestion
taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker

# Or with the script
python -m research_agent.scripts.run_taskiq_worker
```

### 4. Test the API

#### Execute Entity Discovery Graph

```bash
curl -X POST http://localhost:8001/graphs/entity-discovery/execute \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Research Ozempic for diabetes treatment",
    "starter_sources": ["https://www.novonordisk.com"],
    "starter_content": "Ozempic is a GLP-1 agonist medication"
  }'
```

Response:
```json
{
  "task_id": "abc123...",
  "run_id": "def456...",
  "status": "pending",
  "message": "Entity discovery graph enqueued. Connect to WebSocket /ws/entity-discovery/def456... for progress."
}
```

#### Stream Progress via WebSocket

```javascript
// JavaScript client
const ws = new WebSocket('ws://localhost:8001/graphs/entity-discovery/ws/{run_id}');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log('Progress:', msg);
  
  // msg.event_type: "connected" | "graph_start" | "node_start" | "node_complete" | "graph_complete" | "graph_error"
};
```

#### Check Status (HTTP polling alternative)

```bash
curl http://localhost:8001/graphs/entity-discovery/status/{run_id}
```

## API Endpoints

### Graph Execution

- **POST** `/graphs/entity-discovery/execute`
  - Execute entity discovery graph
  - Returns: `task_id`, `run_id`
  - Body: `EntityDiscoveryRequest`

- **WS** `/graphs/entity-discovery/ws/{run_id}`
  - Real-time progress streaming
  - Events: `connected`, `graph_start`, `graph_complete`, `graph_error`

- **GET** `/graphs/entity-discovery/status/{run_id}`
  - Get current status and all events for a run

### Health

- **GET** `/health` - Basic health check
- **GET** `/ready` - Readiness check (Redis connectivity)

## Request Schema

```python
class EntityDiscoveryRequest(BaseModel):
    query: str                    # Required: research query
    starter_sources: List[str]    # Optional: starting URLs
    starter_content: str          # Optional: starter context
    thread_id: Optional[str]      # Optional: LangGraph thread ID
    checkpoint_ns: Optional[str]  # Optional: checkpoint namespace
```

## WebSocket Event Types

### Connected
```json
{
  "event_type": "connected",
  "data": {
    "run_id": "abc123...",
    "message": "Connected to progress stream"
  }
}
```

### Graph Start
```json
{
  "event_type": "graph_start",
  "data": {
    "query": "Research Ozempic...",
    "thread_id": "thread_abc123",
    "checkpoint_ns": "ns_abc123"
  }
}
```

### Graph Complete
```json
{
  "event_type": "graph_complete",
  "data": {
    "intel_run_id": "run_xyz789",
    "pipeline_version": "v1",
    "has_candidates": true
  }
}
```

### Graph Error
```json
{
  "event_type": "graph_error",
  "data": {
    "error": "Connection timeout",
    "error_type": "TimeoutError"
  }
}
```

## Environment Variables

```bash
# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Redis
REDIS_URL=redis://localhost:6379/0

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_BIOTECH_DB_NAME=biotech_research_db

# PostgreSQL (for LangGraph checkpointing)
POSTGRES_URI=postgresql+asyncpg://user:pass@localhost:5432/research_db

# OpenAI
OPENAI_API_KEY=sk-...
```

## Development

### Install Dependencies

```bash
cd ingestion
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/api/
```

### Interactive API Docs

- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

## Adding Progress Updates to Graph Nodes

To publish progress from within graph nodes:

```python
# In your graph node
from research_agent.infrastructure.storage.redis.client import get_redis_client
from research_agent.infrastructure.storage.redis.streams import publish_progress

async def my_graph_node(state: MyState) -> MyState:
    r = await get_redis_client()
    run_id = state.get("run_id")  # Pass run_id through state
    
    # Publish node start
    await publish_progress(
        r,
        run_id,
        "node_start",
        {"node": "my_node", "status": "starting"},
    )
    
    # Do work...
    result = await do_work()
    
    # Publish node complete
    await publish_progress(
        r,
        run_id,
        "node_complete",
        {"node": "my_node", "status": "complete", "result_summary": "..."},
    )
    
    return {"result": result}
```

## Troubleshooting

### Worker not consuming tasks

1. Check RabbitMQ is running: `curl http://localhost:15672` (guest/guest)
2. Verify broker connection in worker logs
3. Ensure tasks are imported: check `taskiq_broker.py` imports

### WebSocket not receiving messages

1. Check Redis is running: `redis-cli ping`
2. Verify stream exists: `redis-cli XREAD COUNT 10 STREAMS graph:progress:{run_id} 0`
3. Check worker is publishing: look for `publish_progress` calls in worker logs

### Graph execution fails

1. Check MongoDB connection
2. Verify Beanie initialization
3. Check LangGraph checkpointer (PostgreSQL)
4. Review worker logs for exceptions

## Next Steps

1. Add authentication/authorization
2. Implement rate limiting
3. Add metrics/monitoring (Prometheus)
4. Add structured logging
5. Implement retry logic for failed tasks
6. Add task priority queues
7. Implement graceful shutdown for workers
