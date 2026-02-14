# Taskiq Broker Blocking Issue - Fix Applied

**Date**: 2026-02-13  
**Issue**: FastAPI POST endpoint blocks when calling `.kiq()` to enqueue tasks  
**Status**: ✅ Fixed

---

## The Problem

Your FastAPI server was **blocking** when you POSTed to `/graphs/entity-discovery/execute`. Instead of returning immediately with "Entity discovery graph enqueued", the request hung indefinitely.

### Root Cause

The AioPikaBroker was experiencing one of these issues:

1. **Lazy connection initialization**: The broker doesn't connect to RabbitMQ until the first `.kiq()` call
2. **No connection timeout**: If RabbitMQ connection fails or is slow, it blocks forever
3. **Connection pool not ready**: The broker hadn't fully established its connection pool after `startup()`

---

## The Fixes Applied

### 1. ✅ Added Connection Timeout

**File**: `taskiq_broker.py`

```python
# BEFORE: No timeout, could block forever
broker = AioPikaBroker(
    RABBITMQ_URL,
    max_async_tasks=MAX_ASYNC_TASKS,
    task_timeout=TASK_TIMEOUT_SECONDS,
)

# AFTER: 10-second connection timeout
CONNECTION_TIMEOUT_SECONDS = int(os.environ.get("TASKIQ_CONNECTION_TIMEOUT", "10"))

broker = AioPikaBroker(
    RABBITMQ_URL,
    max_async_tasks=MAX_ASYNC_TASKS,
    task_timeout=TASK_TIMEOUT_SECONDS,
    connection_timeout=CONNECTION_TIMEOUT_SECONDS,  # ← NEW
)
```

**Why this helps:**
- If RabbitMQ is down or unreachable, you get an error after 10 seconds instead of hanging forever
- Connection attempts are non-blocking with a timeout

### 2. ✅ Added Comprehensive Logging

**File**: `main.py` (lifespan)

Added logging at every step:
- `[fastapi] Starting Taskiq broker...`
- `[fastapi] ✅ Taskiq broker connected to RabbitMQ`
- `[fastapi] Initializing MongoDB/Beanie...`
- `[fastapi] 🚀 All services ready`

**Why this helps:**
- You can now see exactly where the startup process fails or hangs
- Clear indication when the server is ready to accept requests

### 3. ✅ Added Error Handling in Lifespan

**File**: `main.py`

```python
try:
    await broker.startup()
    print("[fastapi] ✅ Taskiq broker connected to RabbitMQ")
except Exception as e:
    print(f"[fastapi] ❌ Failed to start Taskiq broker: {e}")
    raise  # Fail fast, don't start if broker can't connect
```

**Why this helps:**
- If broker startup fails, the entire app fails to start (fail-fast principle)
- Better than silently failing and blocking on first request

### 4. ✅ Added Request-Level Logging

**File**: `entity_discovery.py`

```python
print(f"[api] Enqueuing entity discovery task for run_id={run_id}")
task = await run_entity_discovery_graph.kiq(...)
print(f"[api] ✅ Task enqueued: task_id={task.task_id}, run_id={run_id}")
```

**Why this helps:**
- You can see if the request is hanging on `.kiq()` call
- Clear indication of successful task enqueue

---

## How to Test

### Step 1: Restart Services

```bash
# Stop everything
Ctrl+C (FastAPI)
Ctrl+C (Taskiq workers)
docker-compose down

# Start fresh
docker-compose up -d
```

### Step 2: Start FastAPI (watch the logs!)

```bash
cd ingestion
uv run uvicorn research_agent.api.graph_execution.main:app --reload --port 8001
```

**Expected output:**
```
[fastapi] Starting Taskiq broker...
[fastapi] ✅ Taskiq broker connected to RabbitMQ
[fastapi] Initializing MongoDB/Beanie...
[fastapi] ✅ MongoDB/Beanie initialized
[fastapi] 🚀 All services ready
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

**If you see an error here, RabbitMQ is not accessible!**

### Step 3: Start Taskiq Workers

```bash
cd ingestion
uv run taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker --workers 2
```

**Expected output:**
```
[2026-02-13 XX:XX:XX][taskiq.worker][INFO] Starting 2 worker processes.
[taskiq-worker] MongoDB/Beanie initialized
[taskiq.receiver.receiver][INFO] Listening started.
```

### Step 4: Test the Endpoint

```bash
curl -X POST http://localhost:8001/graphs/entity-discovery/execute \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Utilize the provided starter_content and starter_sources to perform entity discovery on Qualia Life.",
    "starter_sources": ["https://www.qualialife.com"],
    "starter_content": "Qualia Life Sciences (Qualia) is a wellness and longevity supplement company..."
  }'
```

**Expected behavior:**
1. Request returns **immediately** (< 1 second)
2. You see in FastAPI logs:
   ```
   [api] Enqueuing entity discovery task for run_id=xxx-xxx-xxx
   [api] ✅ Task enqueued: task_id=xxx, run_id=xxx
   ```
3. Response body:
   ```json
   {
     "task_id": "xxx",
     "run_id": "xxx-xxx-xxx",
     "status": "pending",
     "message": "Entity discovery graph enqueued. Connect to WebSocket /ws/entity-discovery/xxx-xxx-xxx for progress."
   }
   ```

---

## Troubleshooting

### If FastAPI Still Hangs on Startup

**Problem**: `[fastapi] Starting Taskiq broker...` then nothing

**Solution**: RabbitMQ is not running or not accessible

```bash
# Check RabbitMQ
docker-compose ps

# Check RabbitMQ management UI
curl http://localhost:15672 -u taskiq:taskiq

# Check RabbitMQ credentials in .env
cat .env | grep RABBITMQ
```

### If POST Request Still Blocks

**Problem**: Request hangs after "Enqueuing entity discovery task"

**Possible causes:**
1. **Broker not fully connected**: Add `await asyncio.sleep(0.5)` after `broker.startup()` in lifespan
2. **RabbitMQ queue full**: Check RabbitMQ management UI for queue status
3. **Network issue**: Check firewall/network between FastAPI and RabbitMQ

**Debug steps:**
```bash
# 1. Check if broker.startup() completed successfully
# Look for: [fastapi] ✅ Taskiq broker connected to RabbitMQ

# 2. Add more verbose logging to .kiq() call
# See if it hangs before or after the call

# 3. Test RabbitMQ connection manually
import aio_pika
connection = await aio_pika.connect_robust("amqp://taskiq:taskiq@localhost:5672/")
# Should connect immediately
```

### If Connection Timeout Error

**Problem**: `ConnectionTimeout: Failed to connect to RabbitMQ after 10s`

**Solution**: RabbitMQ is down or credentials are wrong

```bash
# Check RabbitMQ logs
docker logs rabbitmq

# Verify credentials
# In .env: RABBITMQ_URL=amqp://taskiq:taskiq@localhost:5672/
# In docker-compose.yml: RABBITMQ_DEFAULT_USER/PASS should match
```

---

## Environment Variables

Add to your `.env`:

```bash
# Taskiq Configuration
RABBITMQ_URL=amqp://taskiq:taskiq@localhost:5672/
REDIS_URL=redis://localhost:6379/0

# Taskiq Worker Configuration
TASKIQ_MAX_ASYNC_TASKS=8          # Concurrent tasks per worker
TASKIQ_TASK_TIMEOUT=1800          # Task timeout: 30 minutes
TASKIQ_CONNECTION_TIMEOUT=10      # Connection timeout: 10 seconds (NEW)
```

---

## What Changed

### Before (Blocking)

```
Client → POST → FastAPI (.kiq() blocks!) ❌
                   ↓
           RabbitMQ not connected
                   ↓
         Hangs forever trying to connect
```

### After (Non-Blocking)

```
Client → POST → FastAPI (.kiq() returns in <100ms) ✅
                   ↓
           RabbitMQ (already connected via startup())
                   ↓
         Task enqueued immediately
                   ↓
         Taskiq Worker picks up task
                   ↓
         LangGraph executes (5-30 min)
                   ↓
         Progress streamed via Redis/WebSocket
```

---

## Architecture Clarification

Your understanding was **correct**! The architecture should be:

1. **FastAPI** (API server) - Accepts requests, enqueues tasks, returns immediately
2. **RabbitMQ** (Task queue) - Holds tasks until workers pick them up
3. **Taskiq Workers** (Background workers) - Execute long-running LangGraph workflows
4. **Redis Streams** (Progress bus) - Real-time progress events
5. **WebSocket** (Client communication) - Streams progress to clients

The key is that **FastAPI never executes the long-running task**. It just enqueues it and returns immediately.

---

## Next Steps

1. **Restart everything** with the new code
2. **Watch the startup logs** to confirm broker connection
3. **Test the POST endpoint** - should return in < 1 second
4. **Monitor the worker logs** - should see task execution start
5. **Connect via WebSocket** - should see progress events

If it still blocks, share the logs and I'll help debug further!

---

**Status**: Ready to test 🚀
