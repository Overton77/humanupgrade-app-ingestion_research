# Human-in-the-Loop Implementation Plan for Research Plan Approval

## Overview
Implement real-time Human-in-the-Loop (HITL) approval workflow for the `create_research_plan` tool using LangChain's `HumanInTheLoopMiddleware` with WebSocket-based real-time notifications to the frontend.

## Architecture Overview

### Current State
- Backend: FastAPI with LangChain `create_agent` (CompiledStateGraph)
- Streaming: Server-Sent Events (SSE) for agent responses
- Persistence: PostgreSQL (LangGraph checkpointing) + MongoDB (thread storage)
- Frontend: React/Next.js with SSE connection

### Target State
- Add `HumanInTheLoopMiddleware` to coordinator agent
- Detect interrupts during agent streaming
- Send interrupt notifications via **WebSocket** for bidirectional communication
- Display approval UI on frontend with full plan details
- Collect user decision (approve/edit/reject)
- Resume agent execution with decision
- Continue streaming response

---

## Implementation Phases

### Phase 1: Backend - Add HITL Middleware to Agent

#### 1.1 Update Coordinator Agent Service
**File**: `ingestion/src/research_agent/services/coordinator_agent.py`

**Changes**:
```python
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.memory import InMemorySaver  # Already using Postgres

# Add middleware to agent creation
agent = create_agent(
    model=model_with_builtin,
    tools=coordinator_tools,
    system_prompt=COORDINATOR_SYSTEM_PROMPT,
    state_schema=CoordinatorAgentState,
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                # Require approval for research plan creation
                "create_research_plan": {
                    "allowed_decisions": ["approve", "edit", "reject"],
                    "description": lambda action: (
                        f"Research Plan: {action['arguments'].get('mission_title', 'Untitled')}\n\n"
                        f"The coordinator has created a research plan and requires your approval "
                        f"before proceeding."
                    )
                },
                # Other tools auto-approved (no interrupt)
                "search_web": False,
                "extract_from_urls": False,
                "map_website": False,
                "search_wikipedia": False,
                "get_research_plan": False,
                "list_research_plans": False,
            },
            description_prefix="Tool execution requires approval",
        ),
    ],
    store=store,
    checkpointer=checkpointer,  # Required for interrupts
)
```

**Key Points**:
- Only `create_research_plan` triggers interrupt
- All three decision types allowed: approve, edit, reject
- Custom description function to show plan title
- Checkpointer already configured (Postgres)

---

### Phase 2: Backend - WebSocket Route for HITL

#### 2.1 Create WebSocket Route
**New File**: `ingestion/src/research_agent/api/coordinator/routes/hitl_websocket.py`

**Purpose**: Handle bidirectional WebSocket communication for HITL interrupts

**Endpoints**:
```
WS /api/coordinator/threads/{thread_id}/hitl
```

**Flow**:
1. Client connects to WebSocket when sending a message
2. Backend streams agent response as usual
3. When interrupt occurs, send interrupt event with full details
4. Wait for client decision via WebSocket
5. Resume agent with decision
6. Continue streaming

**Schema**:
```python
# WebSocket message types (client -> server)
{
    "type": "decision",
    "decisions": [
        {
            "type": "approve",  # or "edit", "reject"
            # For edit:
            "edited_action": {
                "name": "create_research_plan",
                "args": {...}
            },
            # For reject:
            "message": "Reason for rejection..."
        }
    ]
}

# WebSocket message types (server -> client)
{
    "type": "interrupt",
    "interrupt_data": {
        "action_requests": [...],
        "review_configs": [...]
    }
}

{
    "type": "content",
    "content": "text chunk..."
}

{
    "type": "done"
}

{
    "type": "error",
    "error": "error message"
}
```

---

#### 2.2 Update Streaming Logic
**File**: `ingestion/src/research_agent/api/coordinator/routes/threads.py`

**Current**: Uses SSE for streaming
**Change**: Add WebSocket support alongside SSE (or migrate entirely to WebSocket)

**Options**:
1. **Hybrid Approach** (Recommended):
   - Keep SSE for simple streaming (backward compatible)
   - Add WebSocket route specifically for conversations that might need HITL
   - Client chooses which to use based on context

2. **WebSocket-Only Approach**:
   - Replace SSE with WebSocket entirely
   - Better for bidirectional communication
   - More complex client implementation

**Recommended: Hybrid Approach**

---

### Phase 3: Backend - Interrupt Detection and Handling

#### 3.1 Update Message Streaming Function
**File**: `ingestion/src/research_agent/api/coordinator/routes/threads.py`

**Current Flow**:
```python
async for chunk in agent.astream({"messages": messages}, stream_mode="messages", config=config):
    # Stream content
```

**New Flow**:
```python
# Option 1: Check state for interrupt during streaming
async for chunk in agent.astream({"messages": messages}, stream_mode="messages", config=config):
    # Stream content as before
    pass

# After streaming completes, check for interrupt
final_state = await agent.aget_state(config)
if final_state.next and "__interrupt__" in final_state.values:
    # Handle interrupt
    interrupt_data = final_state.values["__interrupt__"]
    # Send interrupt notification
    await send_interrupt_to_websocket(thread_id, interrupt_data)
    # Wait for decision from WebSocket
    decision = await wait_for_decision(thread_id, timeout=300)  # 5 min timeout
    # Resume agent
    result = await agent.ainvoke(
        Command(resume={"decisions": decision}),
        config=config
    )
```

**Option 2: Use astream with updates mode**:
```python
async for chunk in agent.astream(
    {"messages": messages}, 
    stream_mode=["messages", "updates"],  # Get both messages and state updates
    config=config
):
    mode, data = chunk
    if mode == "updates" and "__interrupt__" in data:
        # Handle interrupt immediately
        ...
```

---

### Phase 4: Backend - WebSocket Manager

#### 4.1 Create WebSocket Connection Manager
**New File**: `ingestion/src/research_agent/api/coordinator/websocket_manager.py`

**Purpose**: Manage WebSocket connections for real-time HITL notifications

```python
from fastapi import WebSocket
from typing import Dict, Optional
import asyncio

class HITLWebSocketManager:
    """Manages WebSocket connections for HITL notifications."""
    
    def __init__(self):
        # thread_id -> WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}
        # thread_id -> decision future (for waiting)
        self.pending_decisions: Dict[str, asyncio.Future] = {}
    
    async def connect(self, thread_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[thread_id] = websocket
    
    def disconnect(self, thread_id: str):
        self.active_connections.pop(thread_id, None)
        # Cancel pending decision if exists
        if thread_id in self.pending_decisions:
            future = self.pending_decisions.pop(thread_id)
            if not future.done():
                future.cancel()
    
    async def send_interrupt(self, thread_id: str, interrupt_data: dict):
        """Send interrupt notification to client."""
        if thread_id in self.active_connections:
            ws = self.active_connections[thread_id]
            await ws.send_json({
                "type": "interrupt",
                "interrupt_data": interrupt_data,
            })
    
    async def wait_for_decision(self, thread_id: str, timeout: float = 300) -> dict:
        """Wait for user decision with timeout."""
        future = asyncio.Future()
        self.pending_decisions[thread_id] = future
        try:
            decision = await asyncio.wait_for(future, timeout=timeout)
            return decision
        except asyncio.TimeoutError:
            # Auto-reject after timeout
            return {"decisions": [{"type": "reject", "message": "Timeout - no decision received"}]}
        finally:
            self.pending_decisions.pop(thread_id, None)
    
    def submit_decision(self, thread_id: str, decision: dict):
        """Submit user decision to resume agent."""
        if thread_id in self.pending_decisions:
            future = self.pending_decisions[thread_id]
            if not future.done():
                future.set_result(decision)

# Global manager instance
hitl_manager = HITLWebSocketManager()
```

---

### Phase 5: Backend - WebSocket Endpoint Implementation

#### 5.1 WebSocket Endpoint
**File**: `ingestion/src/research_agent/api/coordinator/routes/hitl_websocket.py`

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from research_agent.api.coordinator.websocket_manager import hitl_manager
from research_agent.services.coordinator_agent import get_coordinator_agent
from research_agent.models.mongo.threads import ConversationThreadDoc
from langgraph.types import Command

router = APIRouter(prefix="/api/coordinator/threads", tags=["coordinator-hitl"])

@router.websocket("/{thread_id}/hitl")
async def hitl_websocket(websocket: WebSocket, thread_id: str):
    """WebSocket endpoint for HITL-enabled conversations.
    
    Handles bidirectional communication for:
    - Streaming agent responses
    - Interrupt notifications
    - User decisions (approve/edit/reject)
    """
    # Verify thread exists
    thread = await ConversationThreadDoc.find_one(
        ConversationThreadDoc.thread_id == thread_id
    )
    if not thread:
        await websocket.close(code=1008, reason="Thread not found")
        return
    
    # Connect
    await hitl_manager.connect(thread_id, websocket)
    
    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "send_message":
                # User sent a new message - stream agent response
                user_message = data.get("content")
                await thread.add_message("user", user_message)
                
                # Stream response (with interrupt handling)
                await stream_with_hitl(websocket, thread)
            
            elif message_type == "decision":
                # User submitted HITL decision
                decisions = data.get("decisions")
                hitl_manager.submit_decision(thread_id, {"decisions": decisions})
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "error": f"Unknown message type: {message_type}"
                })
    
    except WebSocketDisconnect:
        hitl_manager.disconnect(thread_id)
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })
        hitl_manager.disconnect(thread_id)


async def stream_with_hitl(websocket: WebSocket, thread: ConversationThreadDoc):
    """Stream agent response with HITL interrupt handling."""
    agent = get_coordinator_agent()
    config = {"configurable": {"thread_id": thread.thread_id}}
    messages = await thread.get_langchain_messages()
    
    # Send thinking event
    await websocket.send_json({"type": "thinking"})
    
    full_response = ""
    
    # Stream agent response
    async for chunk in agent.astream(
        {"messages": messages},
        stream_mode="messages",
        config=config,
    ):
        if isinstance(chunk, tuple):
            message, metadata = chunk
        else:
            message = chunk
        
        # Stream content
        if hasattr(message, 'content') and message.content:
            content_text = extract_content_text(message.content)
            if content_text:
                full_response += content_text
                await websocket.send_json({
                    "type": "content",
                    "content": content_text
                })
    
    # Check for interrupt
    final_state = await agent.aget_state(config)
    if final_state.next and len(final_state.next) > 0:
        # Check for __interrupt__ in state values
        interrupt_data = final_state.values.get("__interrupt__")
        if interrupt_data:
            # Send interrupt notification
            await hitl_manager.send_interrupt(thread.thread_id, interrupt_data)
            
            # Wait for user decision
            await websocket.send_json({
                "type": "waiting_for_decision",
                "message": "Waiting for your approval..."
            })
            
            decision = await hitl_manager.wait_for_decision(thread.thread_id)
            
            # Resume agent with decision
            await websocket.send_json({
                "type": "resuming",
                "message": "Resuming with your decision..."
            })
            
            # Resume and continue streaming
            async for chunk in agent.astream(
                Command(resume=decision),
                stream_mode="messages",
                config=config,
            ):
                if isinstance(chunk, tuple):
                    message, metadata = chunk
                else:
                    message = chunk
                
                if hasattr(message, 'content') and message.content:
                    content_text = extract_content_text(message.content)
                    if content_text:
                        full_response += content_text
                        await websocket.send_json({
                            "type": "content",
                            "content": content_text
                        })
    
    # Save response
    if full_response:
        await thread.add_message("assistant", full_response)
    
    # Sync from LangGraph
    final_state = await agent.aget_state(config)
    if final_state and final_state.values.get("messages"):
        await thread.sync_from_langgraph_state(
            final_state.values["messages"],
            replace=True
        )
    
    # Done
    await websocket.send_json({"type": "done"})


def extract_content_text(content) -> str:
    """Extract text from message content."""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text = ""
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text += item.get("text", "")
            elif isinstance(item, str):
                text += item
        return text
    return str(content)
```

---

### Phase 6: Backend - API Router Registration

#### 6.1 Register WebSocket Router
**File**: `ingestion/src/research_agent/api/main.py`

```python
from research_agent.api.coordinator.routes import hitl_websocket

# Add to router registration
app.include_router(hitl_websocket.router)
```

---

### Phase 7: Frontend - WebSocket Client

#### 7.1 Create WebSocket Hook
**New File**: `research_client/src/hooks/use-hitl-websocket.ts`

```typescript
import { useEffect, useRef, useState, useCallback } from 'react';

export interface HITLInterrupt {
  action_requests: Array<{
    name: string;
    arguments: Record<string, any>;
    description: string;
  }>;
  review_configs: Array<{
    action_name: string;
    allowed_decisions: string[];
  }>;
}

export interface Decision {
  type: 'approve' | 'edit' | 'reject';
  edited_action?: {
    name: string;
    args: Record<string, any>;
  };
  message?: string;
}

export function useHITLWebSocket(threadId: string) {
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [interrupt, setInterrupt] = useState<HITLInterrupt | null>(null);
  const [streamedContent, setStreamedContent] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Connect to WebSocket
  useEffect(() => {
    const websocket = new WebSocket(
      `ws://localhost:8000/api/coordinator/threads/${threadId}/hitl`
    );

    websocket.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
    };

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      switch (data.type) {
        case 'thinking':
          setStreaming(true);
          setStreamedContent('');
          break;
        
        case 'content':
          setStreamedContent(prev => prev + data.content);
          break;
        
        case 'interrupt':
          // Received interrupt - show approval UI
          setInterrupt(data.interrupt_data);
          setStreaming(false);
          break;
        
        case 'waiting_for_decision':
          // Agent is waiting for decision
          break;
        
        case 'resuming':
          // Agent is resuming after decision
          setInterrupt(null);
          setStreaming(true);
          break;
        
        case 'done':
          setStreaming(false);
          break;
        
        case 'error':
          setError(data.error);
          setStreaming(false);
          break;
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setError('WebSocket connection error');
    };

    websocket.onclose = () => {
      console.log('WebSocket disconnected');
      setConnected(false);
    };

    setWs(websocket);

    return () => {
      websocket.close();
    };
  }, [threadId]);

  // Send message
  const sendMessage = useCallback((content: string) => {
    if (ws && connected) {
      ws.send(JSON.stringify({
        type: 'send_message',
        content,
      }));
    }
  }, [ws, connected]);

  // Submit decision
  const submitDecision = useCallback((decisions: Decision[]) => {
    if (ws && connected) {
      ws.send(JSON.stringify({
        type: 'decision',
        decisions,
      }));
    }
  }, [ws, connected]);

  return {
    connected,
    streaming,
    interrupt,
    streamedContent,
    error,
    sendMessage,
    submitDecision,
  };
}
```

---

#### 7.2 Create Research Plan Approval Component
**New File**: `research_client/src/components/hitl/research-plan-approval.tsx`

```typescript
'use client';

import { HITLInterrupt, Decision } from '@/hooks/use-hitl-websocket';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { CheckCircle, XCircle, Edit } from 'lucide-react';

interface ResearchPlanApprovalProps {
  interrupt: HITLInterrupt;
  onDecision: (decisions: Decision[]) => void;
}

export function ResearchPlanApproval({ 
  interrupt, 
  onDecision 
}: ResearchPlanApprovalProps) {
  const [editMode, setEditMode] = useState(false);
  const [editedPlan, setEditedPlan] = useState<any>(null);
  const [rejectMessage, setRejectMessage] = useState('');

  if (!interrupt || !interrupt.action_requests?.[0]) {
    return null;
  }

  const action = interrupt.action_requests[0];
  const reviewConfig = interrupt.review_configs[0];
  const planArgs = action.arguments;

  const handleApprove = () => {
    onDecision([{ type: 'approve' }]);
  };

  const handleReject = () => {
    if (!rejectMessage.trim()) {
      alert('Please provide a reason for rejection');
      return;
    }
    onDecision([{
      type: 'reject',
      message: rejectMessage,
    }]);
  };

  const handleEdit = () => {
    if (!editedPlan) {
      alert('Please make changes to the plan');
      return;
    }
    onDecision([{
      type: 'edit',
      edited_action: {
        name: 'create_research_plan',
        args: editedPlan,
      },
    }]);
  };

  return (
    <Card className="p-6 border-2 border-amber-500 bg-amber-50 dark:bg-amber-950/20">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-xl font-bold text-amber-900 dark:text-amber-100">
              Research Plan Approval Required
            </h3>
            <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
              {action.description}
            </p>
          </div>
        </div>

        {/* Plan Details */}
        <div className="bg-white dark:bg-zinc-900 rounded-lg p-4 space-y-3">
          <div>
            <span className="font-semibold">Title:</span> {planArgs.mission_title}
          </div>
          <div>
            <span className="font-semibold">Description:</span> {planArgs.mission_description}
          </div>
          <div>
            <span className="font-semibold">Target Entities:</span>{' '}
            {planArgs.target_entities?.join(', ')}
          </div>
          <div>
            <span className="font-semibold">Budget:</span> $
            {planArgs.max_budget_usd || 'No limit'} | Priority: {planArgs.priority}
          </div>
          <div>
            <span className="font-semibold">Estimated Cost:</span>{' '}
            {planArgs.estimated_total_cost || 'TBD'}
          </div>
          <div>
            <span className="font-semibold">Estimated Duration:</span>{' '}
            {planArgs.estimated_total_duration || 'TBD'}
          </div>
          
          {/* Show stages summary */}
          <div>
            <span className="font-semibold">Stages:</span>
            <div className="mt-2 space-y-2">
              {JSON.parse(planArgs.stages || '[]').map((stage: any, idx: number) => (
                <div key={idx} className="ml-4">
                  <div className="font-medium">{stage.name}</div>
                  <div className="text-sm text-zinc-600 dark:text-zinc-400">
                    {stage.substages?.length} substages
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Edit Mode */}
        {editMode && (
          <div className="space-y-2">
            <label className="block text-sm font-medium">
              Edit Plan (JSON format)
            </label>
            <textarea
              className="w-full h-64 p-3 border rounded-lg font-mono text-sm"
              defaultValue={JSON.stringify(planArgs, null, 2)}
              onChange={(e) => {
                try {
                  setEditedPlan(JSON.parse(e.target.value));
                } catch {
                  // Invalid JSON
                }
              }}
            />
          </div>
        )}

        {/* Reject Mode */}
        {rejectMessage !== null && !editMode && (
          <div className="space-y-2">
            <label className="block text-sm font-medium">
              Reason for rejection
            </label>
            <textarea
              className="w-full h-24 p-3 border rounded-lg"
              placeholder="Explain why you're rejecting this plan..."
              value={rejectMessage}
              onChange={(e) => setRejectMessage(e.target.value)}
            />
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          {reviewConfig.allowed_decisions.includes('approve') && !editMode && (
            <Button
              onClick={handleApprove}
              className="flex-1 bg-green-600 hover:bg-green-700"
            >
              <CheckCircle className="w-4 h-4 mr-2" />
              Approve Plan
            </Button>
          )}
          
          {reviewConfig.allowed_decisions.includes('edit') && (
            <Button
              onClick={() => {
                if (editMode) {
                  handleEdit();
                } else {
                  setEditMode(true);
                  setEditedPlan(planArgs);
                }
              }}
              className="flex-1 bg-blue-600 hover:bg-blue-700"
            >
              <Edit className="w-4 h-4 mr-2" />
              {editMode ? 'Submit Edits' : 'Edit Plan'}
            </Button>
          )}
          
          {reviewConfig.allowed_decisions.includes('reject') && !editMode && (
            <Button
              onClick={handleReject}
              className="flex-1 bg-red-600 hover:bg-red-700"
            >
              <XCircle className="w-4 h-4 mr-2" />
              Reject Plan
            </Button>
          )}
          
          {editMode && (
            <Button
              onClick={() => {
                setEditMode(false);
                setEditedPlan(null);
              }}
              variant="outline"
            >
              Cancel Edit
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
```

---

#### 7.3 Update Chat Interface
**File**: `research_client/src/components/chat/chat-interface.tsx`

```typescript
'use client';

import { useHITLWebSocket } from '@/hooks/use-hitl-websocket';
import { ResearchPlanApproval } from '@/components/hitl/research-plan-approval';
import { useEffect, useRef } from 'react';

export function ChatInterface({ threadId }: { threadId: string }) {
  const {
    connected,
    streaming,
    interrupt,
    streamedContent,
    error,
    sendMessage,
    submitDecision,
  } = useHITLWebSocket(threadId);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [streamedContent, interrupt]);

  const handleSendMessage = (content: string) => {
    sendMessage(content);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* ... existing message rendering ... */}
        
        {/* Streaming content */}
        {streaming && streamedContent && (
          <div className="bg-white dark:bg-zinc-900 rounded-lg p-4">
            <div className="prose dark:prose-invert">
              {streamedContent}
            </div>
          </div>
        )}

        {/* HITL Interrupt - Approval UI */}
        {interrupt && (
          <ResearchPlanApproval
            interrupt={interrupt}
            onDecision={submitDecision}
          />
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-50 dark:bg-red-950/20 border border-red-500 rounded-lg p-4">
            <p className="text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t p-4">
        <MessageInput
          onSend={handleSendMessage}
          disabled={!connected || streaming || !!interrupt}
        />
        {!connected && (
          <p className="text-sm text-zinc-500 mt-2">Connecting...</p>
        )}
        {interrupt && (
          <p className="text-sm text-amber-600 dark:text-amber-400 mt-2">
            ⚠️ Waiting for your approval before continuing...
          </p>
        )}
      </div>
    </div>
  );
}
```

---

### Phase 8: Testing & Validation

#### 8.1 Test Scenarios
1. **Happy Path - Approve**:
   - User asks to create research plan
   - Agent proposes plan
   - Interrupt fires, frontend shows approval UI
   - User clicks "Approve"
   - Agent continues and confirms plan created

2. **Edit Path**:
   - User asks to create research plan
   - Agent proposes plan
   - User clicks "Edit", modifies budget/stages
   - Agent creates plan with edits

3. **Reject Path**:
   - User asks to create research plan
   - Agent proposes plan
   - User clicks "Reject" with feedback
   - Agent receives feedback, proposes revised plan

4. **Timeout Handling**:
   - Interrupt fires
   - User doesn't respond within timeout (5 min)
   - System auto-rejects with timeout message

5. **Connection Loss**:
   - WebSocket disconnects during approval
   - System handles gracefully, can reconnect

---

## Database Schema Changes

### MongoDB - Thread Documents
**File**: `ingestion/src/research_agent/models/mongo/threads/docs/conversation_threads.py`

**Optional Enhancement**: Track HITL events in thread history
```python
class HITLEvent(BaseModel):
    """Record of a HITL interrupt event."""
    timestamp: datetime
    action_name: str
    arguments: dict
    decision_type: str  # approve, edit, reject
    decision_details: Optional[dict] = None
    user_message: Optional[str] = None

# Add to ConversationThreadDoc
hitl_events: List[HITLEvent] = Field(default_factory=list)
```

---

## Configuration & Environment Variables

### Backend
```bash
# .env
HITL_DECISION_TIMEOUT_SECONDS=300  # 5 minutes
```

### Frontend
```bash
# .env.local
NEXT_PUBLIC_API_WS_URL=ws://localhost:8000
```

---

## Security Considerations

1. **Authentication**: Verify user owns thread before accepting decisions
2. **Timeout**: Prevent indefinite waits with configurable timeout
3. **Validation**: Validate edited plans before resuming agent
4. **Rate Limiting**: Prevent abuse of WebSocket connections
5. **Audit Trail**: Log all HITL decisions for compliance

---

## Performance Considerations

1. **WebSocket Connections**: Limit concurrent connections per user
2. **State Persistence**: LangGraph checkpointer handles state efficiently
3. **Message History**: Large message histories may slow down agent
4. **Timeout Management**: Clean up stale connections and pending decisions

---

## Rollout Strategy

### Phase 1: Backend Only (1-2 days)
- Implement middleware and interrupt detection
- Test with API clients (Postman, curl)
- Verify interrupt/resume flow

### Phase 2: WebSocket Infrastructure (1-2 days)
- Implement WebSocket routes and manager
- Test bidirectional communication
- Load testing

### Phase 3: Frontend Integration (2-3 days)
- Implement WebSocket hook
- Create approval UI component
- Integrate with chat interface

### Phase 4: Testing & Polish (1-2 days)
- End-to-end testing
- Error handling
- UX refinements

**Total Estimated Time**: 5-9 days

---

## Alternative Approaches Considered

### 1. HTTP Polling
**Pros**: Simpler implementation, no WebSocket complexity
**Cons**: Higher latency, more server load, poor UX
**Verdict**: ❌ Not recommended

### 2. SSE + HTTP POST
**Pros**: Keep existing SSE, add POST endpoint for decisions
**Cons**: Not truly bidirectional, more complex flow
**Verdict**: ⚠️ Acceptable fallback if WebSocket issues arise

### 3. Redis Pub/Sub
**Pros**: Scalable across multiple backend instances
**Cons**: Additional complexity, overkill for single instance
**Verdict**: 💡 Consider for future horizontal scaling

---

## Success Criteria

1. ✅ Interrupt fires when `create_research_plan` is called
2. ✅ Frontend receives interrupt notification within 100ms
3. ✅ User can approve/edit/reject plan via UI
4. ✅ Agent resumes correctly with decision
5. ✅ All HITL events are logged in database
6. ✅ Timeout handling works correctly
7. ✅ No data loss if connection drops
8. ✅ System handles multiple concurrent users

---

## Future Enhancements

1. **Mobile Support**: Push notifications for HITL events
2. **Team Collaboration**: Multiple reviewers for plan approval
3. **Approval Templates**: Quick-approve common plan patterns
4. **Analytics Dashboard**: Track approval rates, reasons for rejection
5. **Smart Timeouts**: Dynamic timeouts based on plan complexity

---

## References

- [LangChain HITL Documentation](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [LangChain Middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in#human-in-the-loop)
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
