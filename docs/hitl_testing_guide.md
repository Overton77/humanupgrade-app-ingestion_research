# HITL Backend Testing Guide

## Quick Start Testing with WebSocket Client

### Prerequisites
```bash
# Start the backend server
cd ingestion
poetry run uvicorn research_agent.api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Testing with Python WebSocket Client

### Install WebSocket Client
```bash
pip install websocket-client
```

### Test Script

```python
#!/usr/bin/env python3
"""Test script for HITL WebSocket endpoint."""

import websocket
import json
import time
import threading

# Configuration
THREAD_ID = "test-thread-123"  # Replace with actual thread ID
WS_URL = f"ws://localhost:8000/api/coordinator/threads/{THREAD_ID}/hitl"

def on_message(ws, message):
    """Handle incoming WebSocket messages."""
    data = json.loads(message)
    msg_type = data.get("type")
    
    print(f"\n[RECEIVED] Type: {msg_type}")
    
    if msg_type == "thinking":
        print("  → Agent is thinking...")
    
    elif msg_type == "content":
        print(f"  → Content: {data.get('content')}")
    
    elif msg_type == "interrupt":
        print("  → 🚨 INTERRUPT DETECTED!")
        interrupt_data = data.get("interrupt_data")
        action = interrupt_data["action_requests"][0]
        print(f"  → Tool: {action['name']}")
        print(f"  → Description: {action['description']}")
        print(f"  → Arguments: {json.dumps(action['arguments'], indent=2)[:200]}...")
        
        # Auto-approve for testing (you can change this to "edit" or "reject")
        decision_type = input("\n  Enter decision (approve/edit/reject): ").strip().lower()
        
        if decision_type == "approve":
            decision = {
                "type": "decision",
                "decisions": [{"type": "approve"}]
            }
        elif decision_type == "reject":
            reason = input("  Enter rejection reason: ")
            decision = {
                "type": "decision",
                "decisions": [{
                    "type": "reject",
                    "message": reason
                }]
            }
        elif decision_type == "edit":
            print("  → Edit mode: Provide modified arguments as JSON")
            # For simplicity, just approve for now
            decision = {
                "type": "decision",
                "decisions": [{"type": "approve"}]
            }
        else:
            print(f"  → Unknown decision type, defaulting to approve")
            decision = {
                "type": "decision",
                "decisions": [{"type": "approve"}]
            }
        
        print(f"  → Sending decision: {decision['decisions'][0]['type']}")
        ws.send(json.dumps(decision))
    
    elif msg_type == "waiting_for_decision":
        print(f"  → {data.get('message')}")
    
    elif msg_type == "resuming":
        print(f"  → {data.get('message')}")
    
    elif msg_type == "done":
        print("  → ✅ Response complete!")
    
    elif msg_type == "error":
        print(f"  → ❌ Error: {data.get('error')}")

def on_error(ws, error):
    """Handle WebSocket errors."""
    print(f"\n[ERROR] {error}")

def on_close(ws, close_status_code, close_msg):
    """Handle WebSocket close."""
    print(f"\n[CLOSED] Status: {close_status_code}, Message: {close_msg}")

def on_open(ws):
    """Handle WebSocket open."""
    print(f"[CONNECTED] WebSocket connected to {WS_URL}")
    
    # Send a message after connection
    def send_test_message():
        time.sleep(1)
        message = {
            "type": "send_message",
            "content": "Create a research plan to analyze Tesla's battery technology and compare it with competitors like BYD and CATL. Budget: $50, Priority: balanced"
        }
        print(f"\n[SENDING] {message['content']}")
        ws.send(json.dumps(message))
    
    # Start message sending in a separate thread
    threading.Thread(target=send_test_message).start()

if __name__ == "__main__":
    print("=" * 80)
    print("HITL WebSocket Test Client")
    print("=" * 80)
    
    # Create WebSocket connection
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    # Run forever
    ws.run_forever()
```

### Save and Run
```bash
# Save as test_hitl_websocket.py
python test_hitl_websocket.py
```

---

## Testing with Browser WebSocket

### JavaScript Console Test

1. Open browser to `http://localhost:8000/docs`
2. Open Developer Console (F12)
3. Run this JavaScript:

```javascript
// Replace with actual thread ID
const threadId = "test-thread-123";
const ws = new WebSocket(`ws://localhost:8000/api/coordinator/threads/${threadId}/hitl`);

ws.onopen = () => {
    console.log("✅ Connected");
    
    // Send a test message
    ws.send(JSON.stringify({
        type: "send_message",
        content: "Create a research plan for analyzing OpenAI's GPT-4 competitors"
    }));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`📨 [${data.type}]`, data);
    
    if (data.type === "interrupt") {
        console.log("🚨 INTERRUPT DETECTED!");
        console.log("Action:", data.interrupt_data.action_requests[0]);
        
        // Auto-approve
        ws.send(JSON.stringify({
            type: "decision",
            decisions: [{ type: "approve" }]
        }));
    }
};

ws.onerror = (error) => {
    console.error("❌ Error:", error);
};

ws.onclose = () => {
    console.log("👋 Disconnected");
};
```

---

## Testing with Postman

### 1. Create Thread (HTTP)
```
POST http://localhost:8000/api/coordinator/threads
Content-Type: application/json

{
    "initial_message": "Hello"
}
```

**Response**: Copy the `thread_id`

### 2. Connect WebSocket (Postman WebSocket)
1. New → WebSocket Request
2. URL: `ws://localhost:8000/api/coordinator/threads/{thread_id}/hitl`
3. Connect

### 3. Send Message
```json
{
    "type": "send_message",
    "content": "Create a research plan to analyze Tesla vs BYD battery technology"
}
```

### 4. Wait for Interrupt
You'll receive:
```json
{
    "type": "interrupt",
    "interrupt_data": {
        "action_requests": [...],
        "review_configs": [...]
    }
}
```

### 5. Send Decision
**Approve**:
```json
{
    "type": "decision",
    "decisions": [
        { "type": "approve" }
    ]
}
```

**Reject**:
```json
{
    "type": "decision",
    "decisions": [
        {
            "type": "reject",
            "message": "Please revise the budget"
        }
    ]
}
```

**Edit**:
```json
{
    "type": "decision",
    "decisions": [
        {
            "type": "edit",
            "edited_action": {
                "name": "create_research_plan",
                "args": {
                    "mission_title": "Modified Title",
                    "mission_description": "Modified description",
                    ...
                }
            }
        }
    ]
}
```

---

## Expected Flow

1. **Connect**: WebSocket connection established
2. **Send Message**: Client sends research request
3. **Thinking**: Server sends `{"type": "thinking"}`
4. **Content Streaming**: Multiple `{"type": "content", "content": "..."}` messages
5. **Interrupt**: `{"type": "interrupt", "interrupt_data": {...}}`
6. **Waiting**: `{"type": "waiting_for_decision"}`
7. **Client Decision**: Client sends decision
8. **Resuming**: `{"type": "resuming"}`
9. **More Content**: Continued streaming after approval
10. **Done**: `{"type": "done"}`

---

## Common Issues & Solutions

### Issue: "Thread not found"
**Solution**: Create a thread first using POST `/api/coordinator/threads`

### Issue: Connection refused
**Solution**: Ensure backend server is running on port 8000

### Issue: No interrupt fires
**Solution**: Make sure you're asking to create a research plan. Try:
```
"Create a research plan for analyzing XYZ"
```

### Issue: Timeout after 5 minutes
**Solution**: Submit decision within 5 minutes, or adjust timeout in `websocket_manager.py`

---

## Logging

Check backend logs for detailed information:
```
[api] WebSocket connected for thread <thread_id>
[api] Starting agent stream for thread <thread_id>
[api] Interrupt detected for thread <thread_id>
[api] Decision received for thread <thread_id>: approve
[api] Agent resumed and completed for thread <thread_id>
```

---

## Next Steps

Once backend testing is successful:
1. Proceed to frontend integration (Phase 7)
2. Implement React WebSocket hook
3. Create approval UI component
4. Test end-to-end flow

---

## Troubleshooting Commands

### Check if server is running
```bash
curl http://localhost:8000/health
```

### Check available endpoints
```bash
curl http://localhost:8000/
```

### View API docs
```
http://localhost:8000/docs
```

---

## Test Checklist

- [ ] WebSocket connection establishes successfully
- [ ] Send message via WebSocket
- [ ] Agent streams response
- [ ] Interrupt fires when research plan is created
- [ ] Interrupt data includes plan details
- [ ] Submit "approve" decision
- [ ] Agent resumes and completes
- [ ] Submit "reject" decision with message
- [ ] Agent receives feedback correctly
- [ ] Test timeout (wait 5+ minutes without decision)
- [ ] Test connection loss (close WebSocket during approval)
- [ ] Test multiple concurrent threads

**Once all tests pass, backend is ready for frontend integration! 🚀**
