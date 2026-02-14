# Windows Taskiq Worker Setup Guide

## 🔴 The Problem

Psycopg (async PostgreSQL driver) is **incompatible with Windows ProactorEventLoop**. When running the Taskiq worker via CLI, the event loop is created **before** Python can import our package-level fix, causing this error:

```
psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode.
Please use a compatible event loop, for instance by running 'asyncio.run(...,
loop_factory=asyncio.SelectorEventLoop(selectors.SelectSelector()))'
```

## ✅ Three Solutions (Pick One)

### **Solution 1: Use sitecustomize.py (RECOMMENDED)**

This is the most reliable solution. Python automatically imports `sitecustomize.py` **before anything else**, ensuring the event loop policy is set before Taskiq creates its workers.

#### Setup

1. **The file `sitecustomize.py` is already created** in the `ingestion/` directory

2. **Run the worker with PYTHONPATH set**:

```bash
# Windows CMD
cd ingestion
set PYTHONPATH=%CD%
uv run taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker --workers 2
```

Or use the provided batch script:

```bash
cd ingestion
start_worker.bat
```

#### Verification

When the worker starts, you should see:
```
[sitecustomize] ✅ Windows SelectorEventLoop policy set (for psycopg compatibility)
```

This confirms the fix is working!

---

### **Solution 2: Use the Python Wrapper Script**

This script wraps the Taskiq CLI and automatically sets up PYTHONPATH for sitecustomize.py.

#### Usage

```bash
cd ingestion
uv run python -m research_agent.scripts.run_taskiq_worker --workers 2
```

The wrapper will:
- Set PYTHONPATH to include `sitecustomize.py`
- Configure environment variables
- Launch the taskiq worker with proper settings

---

### **Solution 3: Set PYTHONPATH Globally**

If you want to use the standard Taskiq CLI without any wrappers:

#### Windows CMD

```bash
cd ingestion
set PYTHONPATH=%CD%
set TASKIQ_MAX_ASYNC_TASKS=8

# Now run taskiq normally
uv run taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker --workers 2
```

#### PowerShell

```powershell
cd ingestion
$env:PYTHONPATH = (Get-Location).Path
$env:TASKIQ_MAX_ASYNC_TASKS = "8"

# Now run taskiq normally
uv run taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker --workers 2
```

---

## 🧪 Testing the Fix

After starting the worker with any of the above methods:

1. **Check the worker logs** - Look for:
   ```
   [sitecustomize] ✅ Windows SelectorEventLoop policy set
   ```

2. **Submit a test task**:
   ```bash
   curl -X POST http://localhost:8001/graphs/entity-discovery/execute \
     -H "Content-Type: application/json" \
     -d "{\"query\": \"Test\", \"starter_sources\": [\"https://example.com\"], \"starter_content\": \"Test\"}"
   ```

3. **Verify no psycopg errors** - The worker logs should NOT show:
   ```
   psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop'
   ```

---

## 🔍 How It Works

### The Event Loop Problem

1. **ProactorEventLoop** (Windows default) - Fast, but incompatible with psycopg
2. **SelectorEventLoop** - Compatible with psycopg, but needs explicit configuration

### The Fix Mechanism

```
sitecustomize.py (runs FIRST)
    ↓
Sets WindowsSelectorEventLoopPolicy
    ↓
Taskiq CLI starts
    ↓
Creates event loop (now SelectorEventLoop)
    ↓
Imports research_agent package
    ↓
Psycopg operations work! ✅
```

### Defense in Depth

The fix is implemented at multiple levels:

1. **`sitecustomize.py`** - Runs before anything (most reliable)
2. **`research_agent/__init__.py`** - Package-level fix (backup)
3. **`taskiq_broker.py`** - Module-level fix (tertiary backup)
4. **Worker startup hook** - Final check (verification)

---

## 📝 Troubleshooting

### ❌ Still Getting the ProactorEventLoop Error?

**Check PYTHONPATH**:
```bash
# Windows CMD
echo %PYTHONPATH%

# PowerShell
echo $env:PYTHONPATH

# Should include: C:\Users\...\humanupgradeapp\ingestion
```

**Check sitecustomize.py is being loaded**:
```bash
cd ingestion
uv run python -c "import sys; print('sitecustomize' in sys.modules)"
# Should print: True
```

**Verify event loop policy manually**:
```bash
cd ingestion
set PYTHONPATH=%CD%
uv run python -c "import asyncio; print(asyncio.get_event_loop_policy().__class__.__name__)"
# Should print: WindowsSelectorEventLoopPolicy
```

### ❌ Worker Not Receiving Tasks?

This is a separate issue from the event loop. Check:

1. **RabbitMQ is running**:
   ```bash
   curl http://localhost:15672
   ```

2. **Worker is connected**:
   Look for "Connected to RabbitMQ" in worker logs

3. **Task is being enqueued**:
   Check FastAPI logs for "Task enqueued" messages

4. **Worker is not hanging**:
   Try restarting both the worker and FastAPI server

---

## 📂 Related Files

- `ingestion/sitecustomize.py` - **Main fix** (auto-imported by Python)
- `ingestion/start_worker.bat` - **Convenience script** for Windows
- `ingestion/src/research_agent/__init__.py` - Package-level fix (backup)
- `ingestion/src/research_agent/scripts/run_taskiq_worker.py` - Python wrapper script
- `ingestion/src/research_agent/infrastructure/queue/taskiq_broker.py` - Broker setup
- `ingestion/docs/WINDOWS_EVENT_LOOP_FIX.md` - Detailed technical documentation

---

## 🚀 Quick Start (Recommended Path)

**Step 1**: Start the FastAPI server
```bash
cd ingestion
uv run uvicorn research_agent.api.graph_execution.main:app --reload --port 8001 --host 0.0.0.0
```

**Step 2**: Start the Taskiq worker (NEW WINDOW)
```bash
cd ingestion
start_worker.bat
```
Or manually:
```bash
cd ingestion
set PYTHONPATH=%CD%
uv run taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker --workers 2
```

**Step 3**: Submit a test task
```bash
curl -X POST http://localhost:8001/graphs/entity-discovery/execute \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"Test\", \"starter_sources\": [\"https://example.com\"], \"starter_content\": \"Test\"}"
```

**Step 4**: Check both terminals - you should see task execution without errors! 🎉

---

## 💡 Key Takeaways

1. **Use `sitecustomize.py`** - It's the most reliable solution for Windows
2. **Set PYTHONPATH** - Must include the `ingestion/` directory  
3. **Use `start_worker.bat`** - Simplest way to start the worker correctly
4. **Verify the fix** - Look for the sitecustomize success message in logs

If you're still having issues, check the troubleshooting section or review the detailed technical docs in `WINDOWS_EVENT_LOOP_FIX.md`.
