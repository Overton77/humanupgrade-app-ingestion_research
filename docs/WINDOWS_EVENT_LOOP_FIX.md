# Windows Event Loop Fix for Psycopg

## Problem

On Windows, Python's default event loop is `ProactorEventLoop`, which is incompatible with `psycopg` (the async PostgreSQL driver). When running async operations with psycopg, you'll get this error:

```
psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode. 
Please use a compatible event loop, for instance by running 'asyncio.run(..., 
loop_factory=asyncio.SelectorEventLoop(selectors.SelectSelector()))'
```

This error occurs when:
- Running the Taskiq worker (`taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker`)
- The worker executes tasks that use LangGraph persistence (PostgreSQL via psycopg)
- The event loop is already created as ProactorEventLoop before our code runs

## Solution

The fix is implemented at **package initialization** level in `research_agent/__init__.py`. This ensures the event loop policy is set to `WindowsSelectorEventLoopPolicy` **before** any event loops are created.

### Implementation Details

1. **Primary Fix**: `research_agent/__init__.py`
   - Sets `asyncio.WindowsSelectorEventLoopPolicy()` when the package is imported
   - This is the FIRST thing that happens when any code imports `research_agent`
   - Works for CLI, scripts, and direct imports

2. **Defense in Depth**: `research_agent/infrastructure/queue/taskiq_broker.py`
   - Also calls the event loop fix function
   - Provides redundancy in case the package __init__ is somehow bypassed

3. **Utility Function**: `research_agent/utils/windows_event_loop_fix.py`
   - Contains the reusable `ensure_selector_event_loop_on_windows()` function
   - Can be used in other entry points if needed

## How to Verify the Fix

### Option 1: Run the Tests

```bash
# From the ingestion directory
uv run pytest tests/test_windows_event_loop_fix.py -v
```

All tests should pass on Windows.

### Option 2: Manual Verification

```python
import sys
import asyncio
import research_agent  # This triggers the fix

# Check the policy
policy = asyncio.get_event_loop_policy()
print(f"Event loop policy: {type(policy).__name__}")
# Should print: WindowsSelectorEventLoopPolicy (on Windows)

# Check the event loop
loop = asyncio.new_event_loop()
print(f"Event loop type: {type(loop).__name__}")
loop.close()
# Should print: SelectorEventLoop (on Windows)
```

### Option 3: Check Worker Execution

1. **Stop** your existing Taskiq worker (Ctrl+C)
2. **Restart** the worker:
   ```bash
   cd ingestion
   uv run taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker --workers 2
   ```
3. **Submit a task** that uses PostgreSQL (e.g., entity discovery)
4. **Check the worker logs** - you should NO LONGER see the psycopg error

## Important Notes

### Restart Required

After applying this fix, you **MUST restart** all running processes:
- ✅ **Restart the Taskiq worker**
- ✅ **Restart the FastAPI server** (if running)
- ✅ **Restart any other Python processes** using the research_agent package

### Why Package __init__.py?

Setting the event loop policy in `__init__.py` ensures it runs:
- ✅ Before the Taskiq CLI creates the event loop
- ✅ Before FastAPI creates the event loop
- ✅ Before any manual scripts run
- ✅ No matter how the package is imported

### Cross-Platform Compatibility

The fix only applies on Windows (`sys.platform.startswith("win")`). Other platforms (Linux, macOS) are not affected and will use their default event loop policies.

## Troubleshooting

### Still Getting the Error?

1. **Did you restart?** - The fix won't apply to already-running processes
2. **Check imports** - Make sure code imports from `research_agent` package (not isolated modules)
3. **Verify the fix** - Run the tests or manual verification above
4. **Check multiple workers** - If you have multiple worker terminals, restart ALL of them

### Other Event Loop Issues?

If you're creating event loops manually elsewhere in the code, make sure to:
```python
import asyncio
loop = asyncio.SelectorEventLoop()  # Explicit SelectorEventLoop
asyncio.set_event_loop(loop)
```

Or use:
```python
import asyncio
from research_agent.utils.windows_event_loop_fix import ensure_selector_event_loop_on_windows

ensure_selector_event_loop_on_windows()
loop = asyncio.new_event_loop()  # Will be SelectorEventLoop on Windows
```

## Related Files

- `research_agent/__init__.py` - Primary fix location
- `research_agent/utils/windows_event_loop_fix.py` - Utility function
- `research_agent/infrastructure/queue/taskiq_broker.py` - Secondary fix (defense in depth)
- `research_agent/scripts/run_taskiq_worker.py` - Worker script (also has fix for direct execution)
- `tests/test_windows_event_loop_fix.py` - Test suite

## References

- [Psycopg Documentation - Async Operations](https://www.psycopg.org/psycopg3/docs/advanced/async.html)
- [Python asyncio - Event Loop](https://docs.python.org/3/library/asyncio-eventloop.html)
- [Python asyncio - Windows Specific](https://docs.python.org/3/library/asyncio-platforms.html#asyncio-windows-subprocess)
