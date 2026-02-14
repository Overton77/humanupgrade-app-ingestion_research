# Research Agent API - Quick Start Guide

## Prerequisites

1. **Python 3.12+** with `uv` package manager
2. **Redis** (via Docker)
3. **RabbitMQ** (via Docker)
4. **MongoDB** running locally or via Docker
5. **PostgreSQL** running locally (for LangGraph checkpointing)

## Start Services

### 1. Start Redis & RabbitMQ (Docker)

```bash
cd ingestion

# Start Redis and RabbitMQ using docker-compose
docker-compose up -d

# Verify services are running
docker-compose ps
```

This starts:
- **Redis** on `localhost:6379` (for progress streaming)
- **RabbitMQ** on `localhost:5672` (task queue) and `localhost:15672` (management UI)

### 2. Verify Local Services

Ensure these are running locally:

```bash
# PostgreSQL (should be running locally)
psql -U your_user -d research_db -c "SELECT 1;"

# MongoDB (if running locally)
mongosh --eval "db.adminCommand('ping')"
```

Or start MongoDB via Docker if needed:
```bash
docker run -d --name mongo -p 27017:27017 mongo:7
```

## Environment Setup

Create `.env` in the `ingestion/` directory:

```bash
# ingestion/.env

# RabbitMQ (Docker)
RABBITMQ_URL=amqp://taskiq:taskiq@localhost:5672/

# Redis (Docker)
REDIS_URL=redis://localhost:6379/0

# MongoDB (Local or Docker)
MONGO_URI=mongodb://localhost:27017
MONGO_BIOTECH_DB_NAME=biotech_research_db

# PostgreSQL (Local - for LangGraph checkpointing)
POSTGRES_URI=postgresql+asyncpg://your_user:your_password@localhost:5432/research_db

# OpenAI
OPENAI_API_KEY=sk-your-api-key-here

# Tavily (for web search)
TAVILY_API_KEY=tvly-your-api-key-here

# Taskiq Worker Configuration (Optional)
TASKIQ_MAX_ASYNC_TASKS=8        # Concurrent async tasks per worker (default: 8)
TASKIQ_TASK_TIMEOUT=1800        # Task timeout in seconds (default: 1800 = 30 min)
```

## Install Dependencies

```bash
cd ingestion

# Install with uv (recommended)
uv sync

# Or install with pip
pip install -e .
```

## Start the System

### Terminal 1: FastAPI Server

```bash
cd ingestion

# Using uv (recommended)
uv run uvicorn research_agent.api.graph_execution.main:app --reload --port 8001 --host 0.0.0.0

# Or using the script
uv run python -m research_agent.scripts.run_graph_api
```

Expected output:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
[taskiq-worker] MongoDB/Beanie initialized
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

### Terminal 2: Taskiq Worker

```bash
cd ingestion

# Using uv with taskiq CLI (recommended)
uv run taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker --workers 2

# Or using the script
uv run python -m research_agent.scripts.run_taskiq_worker
```

**Worker Configuration:**
- `--workers N`: Number of worker processes (default: 2)
- Each worker handles `TASKIQ_MAX_ASYNC_TASKS` concurrent async tasks (default: 8)
- Total concurrency: `workers × max_async_tasks` (e.g., 2 × 8 = 16 concurrent tasks)

Expected output:
```
[2026-02-13 14:27:41,633][taskiq.worker][INFO   ][MainProcess] Pid of a main process: 4712
[2026-02-13 14:27:41,633][taskiq.worker][INFO   ][MainProcess] Starting 2 worker processes.
[2026-02-13 14:27:41,644][taskiq.process-manager][INFO   ][MainProcess] Started process worker-0 with pid 24952
[2026-02-13 14:27:41,654][taskiq.process-manager][INFO   ][MainProcess] Started process worker-1 with pid 14072
[taskiq-worker] MongoDB/Beanie initialized
[2026-02-13 14:27:42,756][taskiq.receiver.receiver][INFO   ][worker-0] Listening started.
[2026-02-13 14:27:42,756][taskiq.receiver.receiver][INFO   ][worker-1] Listening started.
```

## Test the API

### 1. Health Check

```bash
curl http://localhost:8001/health
```

Expected response:
```json
{"status": "ok"}
```

### 2. Readiness Check

```bash
curl http://localhost:8001/ready
```

Expected response:
```json
{
  "status": "ready",
  "redis": "connected"
}
```

### 3. Execute Entity Discovery Graph

```bash
curl -X POST http://localhost:8001/graphs/entity-discovery/execute \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Research Ozempic for diabetes treatment",
    "starter_sources": ["https://www.novonordisk.com"],
    "starter_content": "Ozempic is a GLP-1 agonist medication developed by Novo Nordisk"
  }'
```

Expected response:
```json
{
  "task_id": "abc123-def456-...",
  "run_id": "uuid-run-id",
  "status": "pending",
  "message": "Entity discovery graph enqueued. Connect to WebSocket /ws/entity-discovery/uuid-run-id for progress."
}
```

**Save the `run_id` for the next step!**

### 4. Stream Progress (WebSocket)

#### Using `websocat` (command-line WebSocket client)

```bash
# Install websocat first: https://github.com/vi/websocat
# Windows: Download from releases
# macOS: brew install websocat
# Linux: cargo install websocat

websocat ws://localhost:8001/graphs/entity-discovery/ws/{run_id}
```

#### Using Python

```python
import asyncio
import websockets
import json

async def stream_progress(run_id: str):
    uri = f"ws://localhost:8001/graphs/entity-discovery/ws/{run_id}"
    
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")
        
        while True:
            try:
                message = await websocket.recv()
                event = json.loads(message)
                
                print(f"\n[{event['event_type']}]")
                print(json.dumps(event['data'], indent=2))
                
                # Stop if graph completed or errored
                if event['event_type'] in ['complete', 'error']:
                    print("\nGraph finished!")
                    break
                    
            except websockets.exceptions.ConnectionClosed:
                print("Connection closed")
                break

# Run
asyncio.run(stream_progress("your-run-id-here"))
```

#### Using JavaScript (Browser)

```javascript
const runId = 'your-run-id-here';
const ws = new WebSocket(`ws://localhost:8001/graphs/entity-discovery/ws/${runId}`);

ws.onopen = () => {
  console.log('Connected to progress stream');
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(`[${msg.event_type}]`, msg.data);
  
  if (msg.event_type === 'complete') {
    console.log('✅ Graph completed successfully!');
    ws.close();
  } else if (msg.event_type === 'error') {
    console.error('❌ Graph failed:', msg.data);
    ws.close();
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected from progress stream');
};
```

### 5. Check Status (HTTP polling alternative)

```bash
curl http://localhost:8001/graphs/entity-discovery/status/{run_id}
```

Expected response:
```json
{
  "run_id": "uuid-run-id",
  "latest_event": "complete",
  "latest_data": {
    "intel_run_id": "run_xyz789",
    "pipeline_version": "v1",
    "has_candidates": true
  },
  "total_events": 3,
  "events": [
    {
      "id": "1234567890-0",
      "event_type": "start",
      "data": { ... }
    },
    {
      "id": "1234567891-0",
      "event_type": "complete",
      "data": { ... }
    }
  ]
}
```

## Expected Progress Events

### 1. Connected
```json
{
  "event_type": "connected",
  "data": {
    "run_id": "...",
    "message": "Connected to progress stream"
  }
}
```

### 2. Graph Start
```json
{
  "event_type": "start",
  "data": {
    "query": "Research Ozempic for diabetes treatment",
    "thread_id": "thread_...",
    "checkpoint_ns": "ns_..."
  }
}
```

### 3. Graph Complete (Success)
```json
{
  "event_type": "complete",
  "data": {
    "intel_run_id": "run_...",
    "pipeline_version": "v1",
    "has_candidates": true
  }
}
```

### 4. Graph Error (Failure)
```json
{
  "event_type": "error",
  "data": {
    "error": "Connection timeout after 30s",
    "error_type": "TimeoutError"
  }
}
```

## API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Troubleshooting

### "Connection refused" errors

**Problem**: Can't connect to Redis/RabbitMQ/MongoDB/PostgreSQL

**Solution**:
```bash
# Check Docker services
docker-compose ps

# Check Redis
docker exec -it redis redis-cli ping  # Should return "PONG"

# Check RabbitMQ
curl http://localhost:15672  # Management UI (taskiq/taskiq)

# Check MongoDB (if local)
mongosh --eval "db.adminCommand('ping')"

# Check PostgreSQL (if local)
psql -U your_user -d research_db -c "SELECT 1;"
```

### Worker not picking up tasks

**Problem**: Tasks enqueued but worker not executing them

**Solution**:
1. Check RabbitMQ connection in worker logs
2. Verify broker URL in `.env`
3. Ensure tasks are imported in `taskiq_broker.py`
4. Check RabbitMQ queues: http://localhost:15672/#/queues (taskiq/taskiq)
5. Verify MongoDB/Beanie initialization in worker logs

### WebSocket immediately closes

**Problem**: WebSocket connects then immediately disconnects

**Solution**:
1. Verify `run_id` is correct
2. Check if graph execution started (worker running?)
3. Look at worker logs for errors
4. Check Redis streams: `docker exec -it redis redis-cli XREAD COUNT 10 STREAMS graph:entity_discovery:{run_id} 0`

### Graph execution hangs

**Problem**: Graph starts but never completes

**Solution**:
1. Check MongoDB connection and Beanie initialization
2. Verify OpenAI API key
3. Check Tavily API key (for web search)
4. Look at worker logs for errors
5. Check LangGraph checkpointer (PostgreSQL connection)
6. Increase task timeout: `TASKIQ_TASK_TIMEOUT=3600` (60 minutes)

### Import errors

**Problem**: `ModuleNotFoundError` when starting services

**Solution**:
```bash
# Reinstall dependencies
cd ingestion
uv sync

# Or with pip
pip install -e .
```

## Performance Tuning

### Taskiq Worker Concurrency

For IO-bound tasks (API calls, DB queries), increase concurrency:

```bash
# In .env
TASKIQ_MAX_ASYNC_TASKS=16    # More concurrent tasks per worker

# Start workers with more processes
uv run taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker --workers 4
```

**Recommended settings:**
- **Light load**: 2 workers × 8 tasks = 16 concurrent
- **Medium load**: 4 workers × 12 tasks = 48 concurrent
- **Heavy load**: 8 workers × 16 tasks = 128 concurrent

### Task Timeout

For long-running graphs, increase timeout:

```bash
# In .env
TASKIQ_TASK_TIMEOUT=3600    # 60 minutes
```

## Monitoring

### RabbitMQ Management UI

http://localhost:15672 (taskiq/taskiq)

- View queues
- Monitor task throughput
- Check connection status

### Redis CLI

```bash
# List all streams
docker exec -it redis redis-cli KEYS "graph:*"

# Read messages from a stream
docker exec -it redis redis-cli XREAD COUNT 10 STREAMS graph:entity_discovery:{run_id} 0

# Get stream length
docker exec -it redis redis-cli XLEN graph:entity_discovery:{run_id}
```

### Taskiq Worker Logs

Watch worker logs for task execution:

```
INFO: Received task: run_entity_discovery_graph
INFO: Executing task...
INFO: Task completed successfully
```

## Next Steps

1. **Add more graphs**: Follow the same pattern for other graphs
2. **Add authentication**: Implement JWT auth middleware
3. **Add monitoring**: Prometheus metrics, structured logging
4. **Add retries**: Configure Taskiq retry policies
5. **Add WebSocket auth**: Secure WebSocket connections
6. **Scale workers**: Run multiple worker processes across machines

## Support

- API README: `ingestion/src/research_agent/api/README.md`
- Full docs: `ingestion/src/research_agent/.cursor/AGENTS.md`
- Codebase plan: `ingestion/src/research_agent/.cursor/CODEBASE_ORGANIZATION_PLAN.md`
