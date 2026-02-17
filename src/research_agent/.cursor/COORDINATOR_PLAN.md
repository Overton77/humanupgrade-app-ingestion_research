# Coordinator Agent Implementation Plan

> **Goal**: Get a streaming, conversational Coordinator Agent working with web search tools, accessible from a Next.js frontend. Human-in-the-loop and Research Plan Tool will be added in Phase 2.

> **Note**: While this plan focuses on the Coordinator Agent, the MongoDB models (`ConversationThreadDoc`, `MessageDoc`) are **general-purpose** and can be reused for any conversational agent or chat interface. Thread identity is based on `thread_id`, with optional `agent_type` filtering.

---

## Phase 1: Basic Conversational Agent with Web Search

### Overview

Build a working end-to-end system where:
1. User starts/resumes conversations in Next.js app
2. FastAPI backend runs LangChain `create_agent` with web search tools
3. Agent responses stream back to the client in real-time
4. Conversations persist in MongoDB

**Technology Stack:**
- **Backend**: FastAPI + LangChain `create_agent` + Beanie (MongoDB ODM)
- **Frontend**: Next.js 15 + TypeScript + Tailwind + shadcn/ui
- **Streaming**: Server-Sent Events (SSE) via FastAPI StreamingResponse
- **Agent**: LangChain `create_agent` with Tavily search tool

---

## Step 1: MongoDB Models for Conversations

### Models Needed

We need **general-purpose** message storage that aligns with LangChain's message format and can be used for any conversational agent (Coordinator, future agents, etc.):

```python
# models/mongo/threads/docs/conversation_threads.py

from beanie import Document
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Optional, Any


class MessageDoc(BaseModel):
    """Individual message in a conversation (LangChain-compatible format)."""
    role: str  # "user" | "assistant" | "tool"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # Tool name for tool messages
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationThreadDoc(Document):
    """General-purpose conversation thread storage.
    
    Can be used for any agent/chat interface. Thread identity is based on thread_id.
    Messages follow LangChain's message format for easy integration.
    """
    
    # Thread identification
    thread_id: str = Field(..., unique=True, description="Unique thread identifier (UUID)")
    
    # Optional: Agent/application identifier
    agent_type: Optional[str] = Field(
        default=None,
        description="Type of agent/application (e.g., 'coordinator', 'assistant', etc.)"
    )
    
    # Thread metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Conversation messages
    messages: List[MessageDoc] = Field(default_factory=list)
    
    # Thread title (auto-generated or user-defined)
    title: Optional[str] = None
    
    # LangGraph checkpoint ID (for resuming conversations)
    checkpoint_id: Optional[str] = None
    
    # Optional: Custom metadata for specific use cases
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Settings:
        name = "conversation_threads"
        indexes = [
            "thread_id",
            "agent_type",
            "created_at",
            "updated_at",
        ]
    
    async def add_message(
        self,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        """Add a message to the thread."""
        message = MessageDoc(
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            name=name,
        )
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
        await self.save()
    
    async def get_langchain_messages(self) -> List[Dict]:
        """Convert stored messages to LangChain format.
        
        Returns list of dicts compatible with LangChain's message format.
        """
        return [
            {
                "role": msg.role,
                "content": msg.content,
                **({"tool_calls": msg.tool_calls} if msg.tool_calls else {}),
                **({"tool_call_id": msg.tool_call_id} if msg.tool_call_id else {}),
                **({"name": msg.name} if msg.name else {}),
            }
            for msg in self.messages
        ]
    
    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self.messages)
    
    def get_last_message_preview(self, max_length: int = 100) -> Optional[str]:
        """Get preview of last message."""
        if not self.messages:
            return None
        return self.messages[-1].content[:max_length]
```

**Key Design Decisions:**
- **Generic naming** (`ConversationThreadDoc` not `CoordinatorThreadDoc`)
- **agent_type field** allows filtering by agent/application type
- Store messages in **LangChain-compatible format**
- Use `thread_id` as primary identifier (UUID)
- Keep `checkpoint_id` for **LangGraph state resumption**
- Auto-generate title from first user message
- Track timestamps for sorting/filtering
- **metadata field** for custom data per use case
- Can be used for Coordinator, future agents, or any chat interface

---

## Step 2: FastAPI Routes for Coordinator Agent

### Directory Structure

```
# MongoDB Models (General-purpose, shared across agents)
models/mongo/threads/
├── __init__.py
└── docs/
    ├── __init__.py
    └── conversation_threads.py    # ConversationThreadDoc, MessageDoc

# Coordinator API (Specific to Coordinator Agent)
api/coordinator/
├── __init__.py
├── main.py                        # FastAPI app
├── routes/
│   ├── __init__.py
│   ├── threads.py                 # Thread CRUD + streaming chat
│   └── health.py                  # Health check
├── schemas/
│   ├── __init__.py
│   ├── threads.py                 # Request/response models
│   └── messages.py                # Message schemas
└── services/
    ├── __init__.py
    └── agent_service.py           # Agent creation & execution
```

**Key Point**: `ConversationThreadDoc` lives in `models/mongo/threads/` (not `models/mongo/coordinator/`) because it's a **general-purpose** model that can be used by any agent or chat interface.

### Key Routes

#### 1. Create New Thread

```python
# api/coordinator/routes/threads.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/api/coordinator/threads", tags=["coordinator"])


class CreateThreadRequest(BaseModel):
    initial_message: Optional[str] = None


class CreateThreadResponse(BaseModel):
    thread_id: str
    created_at: str


@router.post("", response_model=CreateThreadResponse)
async def create_thread(request: CreateThreadRequest):
    """Create a new conversation thread."""
    thread_id = str(uuid.uuid4())
    
    thread = ConversationThreadDoc(
        thread_id=thread_id,
        agent_type="coordinator",  # Specify agent type
        title="New Conversation" if not request.initial_message else None
    )
    
    if request.initial_message:
        await thread.add_message("user", request.initial_message)
        # Generate title from first message (async task or inline)
        thread.title = generate_title(request.initial_message)
    
    await thread.save()
    
    return CreateThreadResponse(
        thread_id=thread.thread_id,
        created_at=thread.created_at.isoformat()
    )
```

#### 2. List Threads

```python
class ThreadSummary(BaseModel):
    thread_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    last_message_preview: Optional[str] = None


@router.get("", response_model=List[ThreadSummary])
async def list_threads(
    limit: int = 20,
    skip: int = 0,
    agent_type: Optional[str] = "coordinator"  # Filter by agent type
):
    """List conversation threads, most recent first."""
    query = ConversationThreadDoc.find_all()
    
    # Optional: Filter by agent type
    if agent_type:
        query = ConversationThreadDoc.find(ConversationThreadDoc.agent_type == agent_type)
    
    threads = await query.sort("-updated_at").skip(skip).limit(limit).to_list()
    
    return [
        ThreadSummary(
            thread_id=thread.thread_id,
            title=thread.title or "Untitled",
            created_at=thread.created_at.isoformat(),
            updated_at=thread.updated_at.isoformat(),
            message_count=len(thread.messages),
            last_message_preview=(
                thread.messages[-1].content[:100] if thread.messages else None
            )
        )
        for thread in threads
    ]
```

#### 3. Get Thread Details

```python
class ThreadDetail(BaseModel):
    thread_id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[MessageDoc]


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(thread_id: str):
    """Get full thread details with all messages."""
    thread = await ConversationThreadDoc.find_one(
        ConversationThreadDoc.thread_id == thread_id
    )
    
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    return ThreadDetail(
        thread_id=thread.thread_id,
        title=thread.title or "Untitled",
        created_at=thread.created_at.isoformat(),
        updated_at=thread.updated_at.isoformat(),
        messages=thread.messages
    )
```

#### 4. Send Message (Streaming)

This is the **most important route** - it handles streaming agent responses.

```python
from fastapi.responses import StreamingResponse
import json
import asyncio


class SendMessageRequest(BaseModel):
    content: str


@router.post("/{thread_id}/messages")
async def send_message(thread_id: str, request: SendMessageRequest):
    """Send a message and stream the agent's response."""
    # Load thread
    thread = await ConversationThreadDoc.find_one(
        ConversationThreadDoc.thread_id == thread_id
    )
    
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Add user message to thread
    await thread.add_message("user", request.content)
    
    # Stream agent response
    return StreamingResponse(
        stream_agent_response(thread),
        media_type="text/event-stream"
    )


async def stream_agent_response(thread: ConversationThreadDoc):
    """Stream agent response as Server-Sent Events."""
    try:
        # Get agent
        agent = get_coordinator_agent()
        
        # Get conversation messages
        messages = await thread.get_langchain_messages()
        
        # Stream agent response
        full_response = ""
        
        async for chunk in agent.astream(
            {"messages": messages},
            stream_mode="messages"
        ):
            # chunk is a message update
            if chunk.content:
                full_response += chunk.content
                
                # Send SSE event
                yield f"data: {json.dumps({'type': 'content', 'content': chunk.content})}\n\n"
        
        # Save assistant message to thread
        await thread.add_message("assistant", full_response)
        
        # Send completion event
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
    except Exception as e:
        # Send error event
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
```

---

## Step 3: Agent Service (LangChain `create_agent`)

### Agent Creation

```python
# api/coordinator/services/agent_service.py

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from functools import lru_cache
import os


@tool
def tavily_search(query: str) -> str:
    """Search the web using Tavily.
    
    Use this to find current information about entities, products, companies, etc.
    """
    tavily = TavilySearchResults(
        max_results=5,
        api_key=os.getenv("TAVILY_API_KEY")
    )
    results = tavily.invoke(query)
    
    # Format results
    formatted = []
    for result in results:
        formatted.append(
            f"Title: {result['title']}\n"
            f"URL: {result['url']}\n"
            f"Content: {result['content']}\n"
        )
    
    return "\n---\n".join(formatted)


@lru_cache(maxsize=1)
def get_coordinator_agent():
    """Create and cache the Coordinator Agent.
    
    Uses LangChain's create_agent for production-ready agent runtime.
    """
    model = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0.7,
        streaming=True,  # Enable streaming
    )
    
    tools = [tavily_search]
    
    agent = create_agent(
        model=model,
        tools=tools,
        # We'll add middleware for human-in-the-loop later
    )
    
    return agent
```

**Key Points:**
- Use `@lru_cache` to reuse agent instance (important for performance)
- Enable `streaming=True` on model
- Start with single web search tool (Tavily)
- Agent will automatically handle tool calling and message formatting

### Using LangGraph Runtime Features

LangChain's `create_agent` builds a LangGraph under the hood. We can access it:

```python
# For checkpointing/resuming conversations
from langgraph.checkpoint.memory import MemorySaver

@lru_cache(maxsize=1)
def get_coordinator_agent():
    model = ChatOpenAI(model="gpt-4.1-mini", streaming=True)
    tools = [tavily_search]
    
    # Add checkpointer for conversation state
    checkpointer = MemorySaver()  # In-memory for now, can use Postgres later
    
    agent = create_agent(
        model=model,
        tools=tools,
        checkpointer=checkpointer,  # Enable state persistence
    )
    
    return agent


# When streaming, use thread_id as config
async for chunk in agent.astream(
    {"messages": messages},
    config={"configurable": {"thread_id": thread.thread_id}},
    stream_mode="messages"
):
    # Stream handling...
```

---

## Step 4: Next.js Client Setup

### Project Initialization

```bash
# Assumes Next.js scaffold is already set up in research_client

cd research_client

pnpm install @tanstack/react-query lucide-react date-fns

npx shadcn@latest init
npx shadcn@latest add button card input textarea scroll-area separator
```
# End of Selection
```

### Project Structure

```
research_client/
├── app/
│   ├── layout.tsx                      # Root layout
│   ├── page.tsx                        # Home (thread list)
│   ├── threads/
│   │   └── [thread_id]/
│   │       └── page.tsx                # Chat interface
│   └── api/
│       └── coordinator/
│           └── [...path]/route.ts      # API proxy (optional)
│
├── components/
│   ├── threads/
│   │   ├── ThreadList.tsx              # List of threads
│   │   ├── ThreadCard.tsx              # Thread preview card
│   │   └── NewThreadButton.tsx         # Create thread button
│   ├── chat/
│   │   ├── ChatInterface.tsx           # Main chat UI
│   │   ├── MessageList.tsx             # Display messages
│   │   ├── MessageBubble.tsx           # Single message
│   │   ├── MessageInput.tsx            # User input
│   │   └── StreamingIndicator.tsx      # Loading state
│   └── ui/
│       └── ...                         # shadcn components
│
├── lib/
│   ├── api-client.ts                   # FastAPI client
│   ├── types.ts                        # TypeScript types
│   └── utils.ts                        # Utilities
│
└── hooks/
    ├── useThreads.ts                   # Thread list hook
    ├── useThread.ts                    # Single thread hook
    └── useStreamingChat.ts             # Streaming chat hook
```

---

## Step 5: Core Frontend Implementation

### 1. API Client

```typescript
// lib/api-client.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface Message {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: string;
  tool_calls?: any[];
}

export interface Thread {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string;
}

export interface ThreadDetail {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export const coordinatorAPI = {
  // Create new thread
  async createThread(initialMessage?: string): Promise<Thread> {
    const response = await fetch(`${API_BASE_URL}/api/coordinator/threads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ initial_message: initialMessage }),
    });
    if (!response.ok) throw new Error('Failed to create thread');
    return response.json();
  },

  // List threads
  async listThreads(limit = 20, skip = 0): Promise<Thread[]> {
    const response = await fetch(
      `${API_BASE_URL}/api/coordinator/threads?limit=${limit}&skip=${skip}`
    );
    if (!response.ok) throw new Error('Failed to fetch threads');
    return response.json();
  },

  // Get thread details
  async getThread(threadId: string): Promise<ThreadDetail> {
    const response = await fetch(
      `${API_BASE_URL}/api/coordinator/threads/${threadId}`
    );
    if (!response.ok) throw new Error('Failed to fetch thread');
    return response.json();
  },

  // Send message (returns EventSource for streaming)
  sendMessage(threadId: string, content: string): EventSource {
    // For SSE, we need to use EventSource
    const url = `${API_BASE_URL}/api/coordinator/threads/${threadId}/messages`;
    
    // EventSource doesn't support POST, so we'll use a workaround
    // Option 1: Use fetch with ReadableStream
    // Option 2: Add message to query params
    // For now, we'll use a custom streaming approach
    
    return new EventSource(`${url}?content=${encodeURIComponent(content)}`);
  },
};
```

### 2. Streaming Hook

```typescript
// hooks/useStreamingChat.ts

import { useState, useCallback } from 'react';
import { coordinatorAPI, Message } from '@/lib/api-client';

interface StreamingState {
  isStreaming: boolean;
  streamingContent: string;
  error: string | null;
}

export function useStreamingChat(threadId: string) {
  const [state, setState] = useState<StreamingState>({
    isStreaming: false,
    streamingContent: '',
    error: null,
  });

  const sendMessage = useCallback(async (content: string) => {
    setState({ isStreaming: true, streamingContent: '', error: null });

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/coordinator/threads/${threadId}/messages`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content }),
        }
      );

      if (!response.ok) throw new Error('Failed to send message');

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader!.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));
            
            if (data.type === 'content') {
              setState(prev => ({
                ...prev,
                streamingContent: prev.streamingContent + data.content,
              }));
            } else if (data.type === 'done') {
              setState({ isStreaming: false, streamingContent: '', error: null });
              return;
            } else if (data.type === 'error') {
              setState({ isStreaming: false, streamingContent: '', error: data.error });
              return;
            }
          }
        }
      }
    } catch (error) {
      setState({
        isStreaming: false,
        streamingContent: '',
        error: error instanceof Error ? error.message : 'Unknown error',
      });
    }
  }, [threadId]);

  return { ...state, sendMessage };
}
```

### 3. Chat Interface Component

```tsx
// components/chat/ChatInterface.tsx

'use client';

import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { coordinatorAPI } from '@/lib/api-client';
import { useStreamingChat } from '@/hooks/useStreamingChat';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ScrollArea } from '@/components/ui/scroll-area';

interface ChatInterfaceProps {
  threadId: string;
}

export function ChatInterface({ threadId }: ChatInterfaceProps) {
  const queryClient = useQueryClient();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load thread messages
  const { data: thread, isLoading } = useQuery({
    queryKey: ['thread', threadId],
    queryFn: () => coordinatorAPI.getThread(threadId),
  });

  // Streaming chat
  const { isStreaming, streamingContent, sendMessage, error } = useStreamingChat(threadId);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [thread?.messages, streamingContent]);

  const handleSendMessage = async (content: string) => {
    await sendMessage(content);
    // Refetch thread to get updated messages
    queryClient.invalidateQueries({ queryKey: ['thread', threadId] });
  };

  if (isLoading) {
    return <div className="flex items-center justify-center h-full">Loading...</div>;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b p-4">
        <h2 className="font-semibold text-lg">{thread?.title}</h2>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        <MessageList
          messages={thread?.messages || []}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />
      </ScrollArea>

      {/* Input */}
      <div className="border-t p-4">
        <MessageInput
          onSend={handleSendMessage}
          disabled={isStreaming}
        />
        {error && (
          <div className="text-red-500 text-sm mt-2">{error}</div>
        )}
      </div>
    </div>
  );
}
```

### 4. Message List Component

```tsx
// components/chat/MessageList.tsx

import { Message } from '@/lib/api-client';
import { MessageBubble } from './MessageBubble';
import { StreamingIndicator } from './StreamingIndicator';

interface MessageListProps {
  messages: Message[];
  streamingContent?: string;
  isStreaming?: boolean;
}

export function MessageList({ messages, streamingContent, isStreaming }: MessageListProps) {
  return (
    <div className="space-y-4">
      {messages.map((message, index) => (
        <MessageBubble key={index} message={message} />
      ))}
      
      {isStreaming && streamingContent && (
        <MessageBubble
          message={{
            role: 'assistant',
            content: streamingContent,
            timestamp: new Date().toISOString(),
          }}
          isStreaming
        />
      )}
      
      {isStreaming && !streamingContent && <StreamingIndicator />}
    </div>
  );
}
```

### 5. Message Bubble Component

```tsx
// components/chat/MessageBubble.tsx

import { Message } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import { User, Bot } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse')}>
      {/* Avatar */}
      <div
        className={cn(
          'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
          isUser ? 'bg-blue-500' : 'bg-gray-700'
        )}
      >
        {isUser ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-white" />}
      </div>

      {/* Message */}
      <div className={cn('flex flex-col', isUser && 'items-end')}>
        <div
          className={cn(
            'rounded-lg px-4 py-2 max-w-[80%]',
            isUser ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-900',
            isStreaming && 'animate-pulse'
          )}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
        <span className="text-xs text-gray-500 mt-1">
          {formatDistanceToNow(new Date(message.timestamp), { addSuffix: true })}
        </span>
      </div>
    </div>
  );
}
```

### 6. Message Input Component

```tsx
// components/chat/MessageInput.tsx

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send } from 'lucide-react';

interface MessageInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
}

export function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [content, setContent] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (content.trim() && !disabled) {
      onSend(content.trim());
      setContent('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <Textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type your message... (Shift+Enter for new line)"
        disabled={disabled}
        className="min-h-[60px] resize-none"
      />
      <Button type="submit" disabled={disabled || !content.trim()} size="icon">
        <Send className="w-4 h-4" />
      </Button>
    </form>
  );
}
```

---

## Step 6: Home Page (Thread List)

```tsx
// app/page.tsx

'use client';

import { useQuery } from '@tanstack/react-query';
import { coordinatorAPI } from '@/lib/api-client';
import { ThreadCard } from '@/components/threads/ThreadCard';
import { NewThreadButton } from '@/components/threads/NewThreadButton';
import { Button } from '@/components/ui/button';

export default function HomePage() {
  const { data: threads, isLoading } = useQuery({
    queryKey: ['threads'],
    queryFn: () => coordinatorAPI.listThreads(),
  });

  return (
    <div className="container mx-auto py-8 px-4">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">Research Conversations</h1>
        <NewThreadButton />
      </div>

      {isLoading ? (
        <div>Loading threads...</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {threads?.map((thread) => (
            <ThreadCard key={thread.thread_id} thread={thread} />
          ))}
        </div>
      )}
    </div>
  );
}
```

---

## Step 7: Environment Setup

### Backend `.env`

```bash
# ingestion/.env

# OpenAI
OPENAI_API_KEY=sk-...

# Tavily (for web search)
TAVILY_API_KEY=tvly-...

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_BIOTECH_DB_NAME=biotech_research_db

# FastAPI
CORS_ORIGINS=http://localhost:3000
```

### Frontend `.env.local`

```bash
# research_client/.env.local

NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Step 8: Running the System

### Terminal 1: MongoDB

```bash
# If using Docker
docker run -d -p 27017:27017 --name mongodb mongo:7
```

### Terminal 2: FastAPI Backend

```bash
cd ingestion
# Activate venv if needed
uvicorn research_agent.api.coordinator.main:app --reload --port 8000
```

### Terminal 3: Next.js Frontend

```bash
cd research_client
npm run dev
```

### Testing Flow

1. **Open** `http://localhost:3000`
2. **Click** "New Conversation"
3. **Type** "What are the latest developments in GLP-1 agonists?"
4. **Watch** streaming response appear in real-time
5. **Ask** follow-up questions
6. **Navigate** back to home, see thread in list
7. **Click** thread to resume conversation

---

## Implementation Checklist

### Backend (FastAPI + LangChain)

- [ ] Create MongoDB models (`ConversationThreadDoc`, `MessageDoc`)
  - [ ] Generic, reusable for any agent/chat interface
  - [ ] LangChain-compatible message format
  - [ ] Includes `agent_type` field for filtering
- [ ] Set up Beanie initialization
- [ ] Create `agent_service.py` with `create_agent`
- [ ] Add Tavily web search tool
- [ ] Create FastAPI routes:
  - [ ] `POST /api/coordinator/threads` (create)
  - [ ] `GET /api/coordinator/threads` (list)
  - [ ] `GET /api/coordinator/threads/{id}` (get)
  - [ ] `POST /api/coordinator/threads/{id}/messages` (stream)
- [ ] Implement SSE streaming
- [ ] Add CORS middleware
- [ ] Test with curl/Postman

### Frontend (Next.js)

- [ ] Initialize Next.js project with TypeScript
- [ ] Install dependencies (React Query, shadcn/ui, etc.)
- [ ] Create API client (`lib/api-client.ts`)
- [ ] Create streaming hook (`hooks/useStreamingChat.ts`)
- [ ] Build chat interface components:
  - [ ] `ChatInterface.tsx`
  - [ ] `MessageList.tsx`
  - [ ] `MessageBubble.tsx`
  - [ ] `MessageInput.tsx`
  - [ ] `StreamingIndicator.tsx`
- [ ] Build thread list components:
  - [ ] `ThreadList.tsx`
  - [ ] `ThreadCard.tsx`
  - [ ] `NewThreadButton.tsx`
- [ ] Create pages:
  - [ ] Home page (thread list)
  - [ ] Chat page (`/threads/[thread_id]`)
- [ ] Add React Query provider
- [ ] Test streaming in browser

### Integration Testing

- [ ] Create thread via UI
- [ ] Send message and verify streaming works
- [ ] Verify tool calling works (web search)
- [ ] Check messages persist in MongoDB
- [ ] Test conversation resumption
- [ ] Test multiple concurrent threads

---

## Phase 2: Adding Human-in-the-Loop (Later)

Once basic streaming works, we'll add:

1. **Checkpoints for Approval**
   - Use LangChain's `interrupt()` in middleware
   - Add approval UI in frontend
   - Handle approve/reject flow

2. **Research Plan Tool**
   - Create structured output for research plans
   - Add tool to agent
   - UI to display/approve plans

**Reference**: https://docs.langchain.com/oss/python/langchain/middleware/built-in#human-in-the-loop

---

## Common Issues & Solutions

### Issue: CORS errors in frontend

**Solution**: Add CORS middleware to FastAPI:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Issue: EventSource not working with POST

**Solution**: Use `fetch` with `ReadableStream` instead of `EventSource`:

```typescript
const response = await fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ content }),
});

const reader = response.body?.getReader();
// Read stream...
```

### Issue: Agent not streaming

**Solution**: Ensure:
1. Model has `streaming=True`
2. Using `agent.astream()` not `agent.ainvoke()`
3. `stream_mode="messages"` is set
4. FastAPI returns `StreamingResponse`

### Issue: Messages not persisting

**Solution**: Verify Beanie is initialized:

```python
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

async def init_db():
    client = AsyncIOMotorClient(MONGO_URI)
    await init_beanie(
        database=client[DB_NAME],
        document_models=[ConversationThreadDoc]
    )
```

---

## Next Steps After Phase 1 Complete

1. **Add Human-in-the-Loop**
   - Implement approval checkpoints
   - Add approval UI components
   - Test interrupt/resume flow

2. **Add Research Plan Tool**
   - Create structured output model
   - Implement plan generation logic
   - Add plan visualization UI

3. **Add More Tools**
   - GraphQL KG query tool
   - Past research lookup tool
   - Candidate exploration tool

4. **Enhance UX**
   - Add typing indicators
   - Show tool usage
   - Add message editing/regeneration
   - Dark mode

---

**Last Updated**: 2026-02-15  
**Status**: Phase 1 Implementation Ready  
**Estimated Time**: 2-3 days for Phase 1
