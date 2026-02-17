# HITL Deadlock Fix - WebSocket Message Handling

## 🐛 The Bug

The HITL workflow was experiencing a **deadlock** that caused decision timeouts after 5 minutes, even when users clicked "Approve" in the UI.

### Timeline of the Deadlock:

```
1. User sends message via WebSocket
   ↓
2. Backend calls: await stream_with_hitl(websocket, thread)
   ↓
3. Agent streams response, then hits interrupt
   ↓
4. Backend calls: await hitl_manager.wait_for_decision(thread_id, timeout=300)
   ⚠️  WEBSOCKET MESSAGE LOOP IS NOW BLOCKED!
   ↓
5. User clicks "Approve" in UI
   ↓
6. Frontend sends: {type: "decision", decisions: [...]}
   ↓
7. ❌ Backend CANNOT receive the message!
      (The WebSocket handler is stuck waiting in step 4)
   ↓
8. After 5 minutes → Timeout → Auto-reject
```

### Root Cause

The WebSocket endpoint has a message loop:

```python
while True:
    data = await websocket.receive_json()
    message_type = data.get("type")
    
    if message_type == "send_message":
        await stream_with_hitl(websocket, thread)  # ← BLOCKS HERE
    
    elif message_type == "decision":
        hitl_manager.submit_decision(...)  # ← CAN'T REACH THIS
```

When `stream_with_hitl()` is awaited, it internally calls `await wait_for_decision()`, which blocks the entire WebSocket handler. The handler cannot process the next message (the decision) because it's stuck waiting.

This is a classic **async deadlock**: the code waits for an event that requires the same execution context to process.

---

## ✅ The Fix

Run `stream_with_hitl()` as a **background task** using `asyncio.create_task()`, allowing the WebSocket message loop to continue receiving messages.

### Code Changes

#### Before (Blocking):
```python
if message_type == "send_message":
    await stream_with_hitl(websocket, thread)  # ← Blocks entire loop
```

#### After (Non-blocking):
```python
# Initialize before loop
streaming_task = None

# In message handler
if message_type == "send_message":
    # Run in background so we can continue receiving messages
    streaming_task = asyncio.create_task(stream_with_hitl(websocket, thread))
```

### Complete Fix

**File**: `ingestion/src/research_agent/api/coordinator/routes/hitl_websocket.py`

**Changes**:

1. **Added import**:
   ```python
   import asyncio
   ```

2. **Track streaming task**:
   ```python
   streaming_task = None  # Initialize before try block
   ```

3. **Run stream as background task**:
   ```python
   if message_type == "send_message":
       # Check if already streaming
       if streaming_task and not streaming_task.done():
           await websocket.send_json({
               "type": "error",
               "error": "Already streaming a response"
           })
           continue
       
       # Run in background
       streaming_task = asyncio.create_task(stream_with_hitl(websocket, thread))
   ```

4. **Added logging for decision submission**:
   ```python
   elif message_type == "decision":
       logger.info(f"Submitting decision for thread {thread_id}: {decisions}")
       hitl_manager.submit_decision(thread_id, {"decisions": decisions})
   ```

5. **Cleanup on disconnect**:
   ```python
   except WebSocketDisconnect:
       # Cancel streaming task if running
       if streaming_task and not streaming_task.done():
           streaming_task.cancel()
       hitl_manager.disconnect(thread_id)
   ```

---

## 🧪 Testing

### Expected Behavior After Fix:

```
1. User sends message via WebSocket
   ↓
2. Backend starts: asyncio.create_task(stream_with_hitl(...))
   ✅ WEBSOCKET MESSAGE LOOP CONTINUES RUNNING!
   ↓
3. Agent streams response in background task
   ↓
4. Background task calls: await wait_for_decision()
   ↓
5. User clicks "Approve" in UI (within 5 minutes)
   ↓
6. Frontend sends: {type: "decision", decisions: [...]}
   ↓
7. ✅ Backend receives and processes the message!
      (The message loop is NOT blocked)
   ↓
8. Backend calls: hitl_manager.submit_decision(...)
   ↓
9. The Future in wait_for_decision() is resolved
   ↓
10. Background task resumes agent execution
   ↓
11. Research plan tool executes with approval
   ↓
12. ✅ Success!
```

### What to Look For in Logs:

```
[INFO] Starting agent stream for thread <id>
[INFO] Agent stream completed for thread <id>
[INFO] Interrupt detected for thread <id>
[INFO] Interrupt payload (serialized): {...}
[INFO] Sent interrupt notification for thread <id>
[INFO] Waiting for decision on thread <id> (timeout: 300s)

← User clicks "Approve" in UI →

[INFO] Submitting decision for thread <id>: [{'type': 'approve'}]  ← NEW LOG
[INFO] Decision submitted for thread <id>
[INFO] Received decision for thread <id>: approve
[INFO] Agent resumed and completed for thread <id>
```

### Test Steps:

1. **Start backend** (restart to load the fix)
2. **Open frontend** and connect to a thread
3. **Send message**: "Create a research plan for Anthropic"
4. **Wait for interrupt** (~15 seconds)
5. **Verify UI shows** Research Plan Approval component
6. **Click "Approve"** (or Edit/Reject)
7. **Verify logs** show decision submission
8. **Verify agent resumes** and completes

---

## 📊 Architecture Diagram

### Before (Deadlock):

```
┌─────────────────────────────────────┐
│   WebSocket Message Loop            │
│                                     │
│   while True:                       │
│       msg = await receive()         │
│       if msg.type == "send":        │
│           await stream_with_hitl()  │ ← BLOCKED
│             └─> await wait_for_decision() ← WAITING
│                                     │
│       elif msg.type == "decision":  │ ← NEVER REACHED
│           submit_decision()         │
└─────────────────────────────────────┘
```

### After (Fixed):

```
┌─────────────────────────────────────┐
│   WebSocket Message Loop            │
│                                     │
│   while True:                       │
│       msg = await receive()         │ ← CONTINUES RUNNING
│       if msg.type == "send":        │
│           create_task(stream...)    │ ← NON-BLOCKING
│                                     │
│       elif msg.type == "decision":  │ ← REACHABLE!
│           submit_decision()         │ ← RESOLVES FUTURE
└─────────────────────────────────────┘
                │
                │ spawns
                ↓
┌─────────────────────────────────────┐
│   Background Task                   │
│                                     │
│   stream_with_hitl():               │
│       stream response...            │
│       await wait_for_decision()     │ ← WAITS IN BACKGROUND
│       (Future gets resolved)        │ ← FROM MAIN LOOP
│       resume agent...               │
└─────────────────────────────────────┘
```

---

## 🔑 Key Insights

### Why This Pattern Works:

1. **Asyncio Tasks**: `asyncio.create_task()` allows concurrent execution without blocking
2. **Futures**: `wait_for_decision()` uses `asyncio.Future`, which can be resolved from any task
3. **Message Loop**: The main loop remains free to process messages
4. **Cross-task Communication**: The main loop can call `submit_decision()` which resolves the Future that the background task is waiting on

### Benefits:

- ✅ No blocking
- ✅ Proper async/await patterns
- ✅ Handles multiple concurrent operations
- ✅ Clean error handling and cancellation
- ✅ User decisions work as expected

---

## 🚀 Next Steps

After verifying the fix:

1. **Remove excessive debug logging** (lines 188-190 in `hitl_websocket.py`)
2. **Add error handling** for background task exceptions
3. **Consider timeout handling** for streaming tasks
4. **Write integration tests** for HITL workflows
5. **Document WebSocket API** contract for frontend developers

---

## 📚 Related Files Modified

- `ingestion/src/research_agent/api/coordinator/routes/hitl_websocket.py`
  - Added `asyncio` import
  - Changed `await stream_with_hitl()` to `asyncio.create_task()`
  - Added streaming task tracking and cleanup
  - Added decision submission logging

---

## 🎓 Lessons Learned

### Async Deadlock Anti-pattern:

```python
# ❌ BAD: Blocking the message loop
while True:
    msg = await receive()
    if msg.type == "action":
        await do_something_that_waits_for_another_message()
```

### Correct Pattern:

```python
# ✅ GOOD: Non-blocking message loop
while True:
    msg = await receive()
    if msg.type == "action":
        asyncio.create_task(do_something_that_waits_for_another_message())
```

---

## 🔍 Debugging Tips

If timeouts still occur, check:

1. **Frontend actually sends decision**: Check browser console for `[WebSocket] Submitting decision: approve`
2. **WebSocket connection**: Ensure `connected: true` in UI
3. **Backend receives message**: Look for `Submitting decision for thread` in logs
4. **Future gets resolved**: Look for `Decision submitted for thread` in logs

---

**Fix Date**: February 16, 2026  
**Impact**: Critical - Enables HITL workflow to function correctly  
**Testing Status**: Ready for testing
