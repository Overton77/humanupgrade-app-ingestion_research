# HITL WebSocket Implementation - Fixes & Architecture Summary

## Issues Fixed

### 1. **Lambda Signature Error** ✅ FIXED
**Error**: `TypeError: initialize_coordinator_agent.<locals>.<lambda>() takes 1 positional argument but 3 were given`

**Root Cause**: The `description` callable in `HumanInTheLoopMiddleware` configuration was accepting 1 parameter (`action`) but LangChain's HITL middleware calls it with 3 parameters: `(tool_call, state, runtime)`.

**Fix Location**: `ingestion/src/research_agent/services/coordinator_agent.py` line 167

**Before**:
```python
"description": lambda action: (
    f"Research Plan: {action['arguments'].get('mission_title', 'Untitled')}\n\n"
    ...
)
```

**After**:
```python
"description": lambda tool_call, state, runtime: (
    f"Research Plan: {tool_call.get('arguments', {}).get('mission_title', 'Untitled')}\n\n"
    ...
)
```

---

### 2. **Interrupt Data Not Found** ⚙️ ENHANCED

**Issue**: After the agent stream completed, the interrupt data wasn't being detected, causing the frontend to stall.

**Enhancements Made**:

#### A. **Multi-location Interrupt Detection**
The interrupt data can be in different locations depending on LangGraph's internal state:
- First check: `final_state.values.get("__interrupt__")`
- Fallback check: `final_state.tasks[*].interrupts[*].value`

```python
# Look for __interrupt__ in state values first
interrupt_data = final_state.values.get("__interrupt__")

# If not in values, check tasks for interrupts
if not interrupt_data and final_state.tasks:
    for task in final_state.tasks:
        if hasattr(task, 'interrupts') and task.interrupts:
            interrupt_data = task.interrupts[0].value if task.interrupts else None
            break
```

#### B. **Proper Interrupt Object Unwrapping**
HITL middleware returns interrupts as a list of `Interrupt` objects with a `value` field:

```python
if isinstance(interrupt_data, list) and len(interrupt_data) > 0:
    first_interrupt = interrupt_data[0]
    if hasattr(first_interrupt, 'value'):
        interrupt_payload = first_interrupt.value
    else:
        interrupt_payload = first_interrupt
else:
    interrupt_payload = interrupt_data
```

#### C. **Pydantic Model Serialization**
Added `serialize_interrupt_data()` function to handle:
- Pydantic models (`.model_dump()`)
- Nested lists and dicts
- Objects with `__dict__`
- Primitive types

```python
def serialize_interrupt_data(data):
    """Serialize interrupt data to JSON-compatible format."""
    if isinstance(data, BaseModel):
        return data.model_dump()
    # ... handles lists, dicts, objects, primitives
```

#### D. **Enhanced Logging**
Added comprehensive logging at each step:
- Interrupt data raw format
- State tasks structure
- State values keys
- Serialized payload

This will help diagnose exactly where the interrupt data is and what format it's in.

---

## Architecture Clarification

### Two Separate Endpoints

Your application now has **two different endpoints** for conversations:

#### 1. **Legacy POST Endpoint** (No HITL)
**Endpoint**: `POST /api/coordinator/threads/{thread_id}/messages`

**Protocol**: Server-Sent Events (SSE)

**Features**:
- ✅ Streaming responses
- ✅ Multimodal messages (text + attachments)
- ❌ **NO** Human-in-the-Loop support

**Use When**:
- You don't need approval workflows
- Client prefers SSE over WebSockets
- Simple streaming conversations

**Example**:
```typescript
const response = await fetch(`/api/coordinator/threads/${threadId}/messages`, {
  method: 'POST',
  body: JSON.stringify({ content: 'Hello' }),
  headers: { 'Content-Type': 'application/json' }
});

// Read SSE stream
const reader = response.body.getReader();
// ... process events
```

---

#### 2. **WebSocket Endpoint** (WITH HITL) ⭐
**Endpoint**: `WS /api/coordinator/threads/{thread_id}/hitl`

**Protocol**: WebSocket (bidirectional)

**Features**:
- ✅ Streaming responses
- ✅ Human-in-the-Loop interrupts
- ✅ Research plan approval workflow
- ✅ Real-time decision submission

**Use When**:
- You need HITL approval workflows
- Research plan creation and approval
- Real-time bidirectional communication

**Message Flow**:

**Client → Server**:
```json
// Send message
{"type": "send_message", "content": "Create a research plan..."}

// Submit decision
{"type": "decision", "decisions": [{"type": "approve"}]}
```

**Server → Client**:
```json
// Agent thinking
{"type": "thinking"}

// Streaming content
{"type": "content", "content": "Here is the plan..."}

// Interrupt (tool needs approval)
{
  "type": "interrupt",
  "interrupt_data": {
    "action_requests": [{"name": "create_research_plan", "arguments": {...}}],
    "review_configs": [{"action_name": "create_research_plan", "allowed_decisions": ["approve", "edit", "reject"]}]
  }
}

// Waiting for decision
{"type": "waiting_for_decision", "message": "Waiting for your approval..."}

// Resuming after decision
{"type": "resuming", "message": "Resuming with your decision..."}

// Complete
{"type": "done"}

// Error
{"type": "error", "error": "..."}
```

---

## Current Integration (Frontend)

Your `chat-interface.tsx` is correctly using the **WebSocket endpoint**:

```tsx
const {
  connected,
  streaming,
  interrupt,           // HITL interrupt data
  streamedContent,
  error: wsError,
  waitingForDecision,  // Waiting for user approval
  sendMessage,         // Send user message via WS
  submitDecision,      // Submit HITL decision via WS
  reconnect,
} = useHITLWebSocket(threadId);
```

The `ResearchPlanApproval` component handles the HITL UI when `interrupt` is set.

---

## Testing Instructions

### 1. **Restart the Backend**
The server auto-reloaded during your last test. Restart it cleanly:

```bash
cd ingestion
# Stop any running instances
# Start fresh
python -m research_agent.api.main
# or
uvicorn research_agent.api.main:app --reload --port 8001
```

### 2. **Test HITL Workflow**

1. **Open the frontend** and create/open a thread
2. **Send a message** asking for a research plan:
   ```
   "Create a research plan to analyze Anthropic as a company"
   ```
3. **Watch the logs** - You should see:
   ```
   [INFO] Starting agent stream for thread <id>
   [INFO] Agent stream completed for thread <id>
   [INFO] Checking for interrupt in thread <id>, next nodes: (...)
   [INFO] Interrupt data: <data>
   [INFO] Final state tasks: <tasks>
   [INFO] Final state values keys: [...]
   [INFO] Interrupt payload (serialized): {...}
   [INFO] Sent interrupt notification for thread <id>
   ```
4. **Frontend should show**: Research plan approval UI
5. **Approve/Edit/Reject** the plan
6. **Watch the agent resume** and complete

### 3. **Check the Logs**

Look for these specific log lines to diagnose:

```python
logger.info(f"Interrupt data: {interrupt_data}")          # Raw interrupt data
logger.info(f"Final state tasks: {final_state.tasks}")    # Tasks structure
logger.info(f"Final state values keys: {list(final_state.values.keys())}")  # State keys
logger.info(f"Interrupt payload (serialized): {serialized_payload}")  # Final payload sent
```

**If still failing**, share these logs and we can adjust the interrupt detection logic.

---

## What Changed

### Files Modified:

1. **`ingestion/src/research_agent/services/coordinator_agent.py`**
   - Fixed lambda signature for HITL middleware description

2. **`ingestion/src/research_agent/api/coordinator/routes/hitl_websocket.py`**
   - Enhanced interrupt detection (check multiple locations)
   - Added Interrupt object unwrapping
   - Added `serialize_interrupt_data()` helper
   - Added comprehensive logging

3. **`ingestion/src/research_agent/api/coordinator/routes/threads.py`**
   - Added documentation clarifying POST endpoint doesn't support HITL

### Files NOT Changed (Working Correctly):

- `research_client/src/hooks/use-hitl-websocket.ts` ✅
- `research_client/src/components/chat/chat-interface.tsx` ✅
- `research_client/src/components/hitl/research-plan-approval.tsx` ✅
- `ingestion/src/research_agent/api/coordinator/websocket_manager.py` ✅

---

## Next Steps

1. **Test** the HITL workflow with the fixes
2. **Share the logs** if still encountering issues
3. Once working, we can:
   - Remove excessive debug logging
   - Add error handling improvements
   - Write tests for HITL workflows
   - Document the HITL API contract

---

## LangChain HITL Documentation

Reference: https://docs.langchain.com/oss/python/langchain/human-in-the-loop

Key concepts:
- Interrupts pause execution until human decision
- Requires checkpointing (Postgres in your case)
- Resume with `Command(resume={"decisions": [...]})`
- Three decision types: `approve`, `edit`, `reject`
