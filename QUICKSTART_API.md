# Research Agent API - Quick Start Guide

## Prerequisites

1. **Python 3.11+** with dependencies installed
2. **Redis** running on localhost:6379
3. **RabbitMQ** running on localhost:5672
4. **MongoDB** running on localhost:27017
5. **PostgreSQL** running (for LangGraph checkpointing)

## Start Services (Docker)

```bash
# Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# RabbitMQ (with management UI)
docker run -d --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=guest \
  -e RABBITMQ_DEFAULT_PASS=guest \
  rabbitmq:3-management

# MongoDB
docker run -d --name mongo -p 27017:27017 mongo:7

# PostgreSQL (for LangGraph)
docker run -d --name postgres \
  -p 5432:5432 \
  -e POSTGRES_USER=research \
  -e POSTGRES_PASSWORD=research \
  -e POSTGRES_DB=research_db \
  postgres:16-alpine
```

## Environment Setup

Create `.env` in the `ingestion/` directory:

```bash
# ingestion/.env

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Redis
REDIS_URL=redis://localhost:6379/0

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_BIOTECH_DB_NAME=biotech_research_db

# PostgreSQL (for LangGraph checkpointing)
POSTGRES_URI=postgresql+asyncpg://research:research@localhost:5432/research_db

# OpenAI
OPENAI_API_KEY=sk-your-api-key-here

# Tavily (for web search)
TAVILY_API_KEY=tvly-your-api-key-here
```

## Start the System

### Terminal 1: FastAPI Server

```bash
cd ingestion

# Option 1: Using the script
python -m research_agent.scripts.run_graph_api

# Option 2: Using uvicorn directly
uvicorn research_agent.api.graph_execution.main:app --reload --port 8001 --host 0.0.0.0
```

Expected output:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
```

### Terminal 2: Taskiq Worker

```bash
cd ingestion

# Option 1: Using taskiq CLI (recommended)
taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker

# Option 2: Using the script
python -m research_agent.scripts.run_taskiq_worker
```

Expected output:
```
Starting Taskiq worker...
Broker: <AioPikaBroker ...>
Waiting for tasks...
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
# Install websocat first: brew install websocat (or download from GitHub)

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
                if event['event_type'] in ['graph_complete', 'graph_error']:
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
  
  if (msg.event_type === 'graph_complete') {
    console.log('✅ Graph completed successfully!');
    ws.close();
  } else if (msg.event_type === 'graph_error') {
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
  "latest_event": "graph_complete",
  "latest_data": {
    "intel_run_id": "run_xyz789",
    "pipeline_version": "v1",
    "has_candidates": true
  },
  "total_events": 3,
  "events": [
    {
      "id": "1234567890-0",
      "event_type": "graph_start",
      "data": { ... }
    },
    {
      "id": "1234567891-0",
      "event_type": "graph_complete",
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
  "event_type": "graph_start",
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
  "event_type": "graph_complete",
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
  "event_type": "graph_error",
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

**Problem**: Can't connect to Redis/RabbitMQ/MongoDB

**Solution**:
```bash
# Check if services are running
docker ps

# Check Redis
redis-cli ping  # Should return "PONG"

# Check RabbitMQ
curl http://localhost:15672  # Management UI (guest/guest)

# Check MongoDB
mongosh  # Should connect
```

### Worker not picking up tasks

**Problem**: Tasks enqueued but worker not executing them

**Solution**:
1. Check RabbitMQ connection in worker logs
2. Verify broker URL in `.env`
3. Ensure tasks are imported in `taskiq_broker.py`
4. Check RabbitMQ queues: http://localhost:15672/#/queues

### WebSocket immediately closes

**Problem**: WebSocket connects then immediately disconnects

**Solution**:
1. Verify `run_id` is correct
2. Check if graph execution started (worker running?)
3. Look at worker logs for errors
4. Check Redis streams: `redis-cli XREAD COUNT 10 STREAMS graph:progress:{run_id} 0`

### Graph execution hangs

**Problem**: Graph starts but never completes

**Solution**:
1. Check MongoDB connection
2. Verify Beanie initialization
3. Check OpenAI API key
4. Look at worker logs for errors
5. Check LangGraph checkpointer (PostgreSQL connection)

### Import errors after removing `human_upgrade/`

**Problem**: `ModuleNotFoundError` for `human_upgrade` modules

**Solution**:
The graph still imports from `human_upgrade/`. Update imports in:
- `ingestion/src/research_agent/graphs/entity_candidates_connected_graph.py`

Change:
```python
from research_agent.human_upgrade.base_models import gpt_5_mini
```

To:
```python
from research_agent.infrastructure.llm.model_registry import gpt_5_mini
```

(Repeat for all `human_upgrade` imports)

## Monitoring

### RabbitMQ Management UI

http://localhost:15672 (guest/guest)

- View queues
- Monitor task throughput
- Check connection status

### Redis CLI

```bash
# List all streams
redis-cli KEYS "graph:progress:*"

# Read messages from a stream
redis-cli XREAD COUNT 10 STREAMS graph:progress:{run_id} 0

# Get stream length
redis-cli XLEN graph:progress:{run_id}
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
6. **Scale workers**: Run multiple worker processes

## Support

- API README: `ingestion/src/research_agent/api/README.md`
- Full docs: `ingestion/src/research_agent/.cursor/AGENTS.md`
- Codebase plan: `ingestion/src/research_agent/.cursor/CODEBASE_ORGANIZATION_PLAN.md`
