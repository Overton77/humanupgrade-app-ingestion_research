# Coordinator Agent Implementation Summary

## ✅ Completed: Phase 1 - Basic Conversational Agent with Web Search

### What Was Built

A fully functional conversational AI agent system integrated into your existing Research Agent API with:

1. **MongoDB Models** (General-purpose, reusable)
   - `ConversationThreadDoc` - Thread storage with LangChain-compatible messages
   - `MessageDoc` - Individual messages (user, assistant, tool)
   - Integrated into existing Beanie initialization

2. **FastAPI Routes** (Coordinator endpoints)
   - `POST /api/coordinator/threads` - Create new conversation
   - `GET /api/coordinator/threads` - List all threads
   - `GET /api/coordinator/threads/{id}` - Get thread details
   - `POST /api/coordinator/threads/{id}/messages` - Send message (streaming)
   - `DELETE /api/coordinator/threads/{id}` - Delete thread
   - Health check endpoints

3. **Agent Service** (`services/coordinator_agent.py`)
   - Uses `langchain.agents.create_agent` (not create_react_agent)
   - OpenAI GPT-4.1 with built-in web search tool
   - Postgres-backed persistence (store + checkpointer)
   - Initialized once during app startup (lifespan)

4. **Unified API** (`api/main.py`)
   - Single FastAPI app with multiple routers
   - Coordinator + Graph Execution endpoints
   - Shared lifespan (MongoDB, Postgres, RabbitMQ, Redis)

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI App (Unified)                    │
│                     api/main.py                             │
├─────────────────────────────────────────────────────────────┤
│  Lifespan:                                                  │
│  1. Initialize MongoDB/Beanie (threads + existing models)   │
│  2. Initialize Coordinator Agent (Postgres persistence)     │
│  3. Initialize Taskiq broker (RabbitMQ)                     │
│  4. Initialize Redis (progress streaming)                   │
└─────────────────────────────────────────────────────────────┘
           │                            │
           ▼                            ▼
┌──────────────────────┐    ┌──────────────────────┐
│  Coordinator Routes  │    │  Graph Exec Routes   │
│  /api/coordinator/*  │    │  /graphs/*           │
└──────────────────────┘    └──────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────┐
│         Coordinator Agent Service                │
│     services/coordinator_agent.py                │
│                                                  │
│  - LangChain create_agent                       │
│  - OpenAI GPT-4.1 + built-in web search        │
│  - Postgres store + checkpointer                │
│  - Streaming responses (SSE)                    │
└──────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────┐
│         MongoDB (ConversationThreadDoc)          │
│  - Thread metadata                               │
│  - Message history                               │
│  - LangChain-compatible format                   │
└──────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **No Motor, Use AsyncMongoClient**
   - Integrated with existing `mongo_client` and `init_beanie_biotech_db`
   - Added `ConversationThreadDoc` to existing document models

2. **Single Unified App**
   - Moved main app to `api/main.py`
   - Old `api/graph_execution/main.py` now re-exports for compatibility
   - All routers attached to one app with shared lifespan

3. **Agent Service in `services/`**
   - Not in `api/coordinator/services/` (kept API clean)
   - Global singleton initialized during app startup
   - Postgres persistence via existing `get_persistence()`

4. **Proper Async Initialization**
   - Can't use `@lru_cache` with async functions
   - Initialize agent in FastAPI lifespan
   - Routes use synchronous `get_coordinator_agent()` getter

5. **OpenAI Built-in Tools**
   - Using `model.bind_tools([openai_search_tool])`
   - Not using Tavily or external search APIs
   - Leverages OpenAI's native web search capability

### File Structure

```
ingestion/src/research_agent/
├── api/
│   ├── main.py                          # ✨ NEW: Unified FastAPI app
│   ├── coordinator/
│   │   ├── routes/
│   │   │   ├── threads.py               # ✨ NEW: Thread CRUD + streaming
│   │   │   └── health.py                # ✨ NEW: Health checks
│   │   └── schemas/
│   │       ├── threads.py               # ✨ NEW: Request/response models
│   │       └── messages.py              # ✨ NEW: Message schemas
│   └── graph_execution/
│       └── main.py                      # UPDATED: Re-exports from api/main
│
├── services/
│   └── coordinator_agent.py             # ✨ NEW: Agent creation & management
│
├── models/mongo/
│   └── threads/                         # ✨ NEW: Conversation storage
│       └── docs/
│           └── conversation_threads.py  # ConversationThreadDoc, MessageDoc
│
├── infrastructure/
│   └── storage/mongo/
│       └── biotech_research_db_beanie.py  # UPDATED: Added ConversationThreadDoc
│
└── scripts/
    ├── run_graph_api.py                 # UPDATED: Points to api/main
    └── run_coordinator_api.py           # UPDATED: Alias for unified server
```

### Running the System

```bash
# Terminal 1: Start the unified API server
cd ingestion
python -m research_agent.scripts.run_graph_api

# Or use the coordinator alias (same thing)
python -m research_agent.scripts.run_coordinator_api

# The server runs on http://localhost:8001
```

### Testing the Coordinator

```bash
# 1. Create a new thread
curl -X POST http://localhost:8001/api/coordinator/threads \
  -H "Content-Type: application/json" \
  -d '{"initial_message": "What are the latest developments in GLP-1 agonists?"}'

# Response: {"thread_id": "abc-123", "created_at": "...", "title": "..."}

# 2. Send a message (streaming)
curl -X POST http://localhost:8001/api/coordinator/threads/{thread_id}/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "Tell me more about Ozempic"}' \
  --no-buffer

# Response: Server-Sent Events stream
# data: {"type": "thinking"}
# data: {"type": "content", "content": "Ozempic is..."}
# data: {"type": "done"}

# 3. List threads
curl http://localhost:8001/api/coordinator/threads

# 4. Get thread details
curl http://localhost:8001/api/coordinator/threads/{thread_id}
```

### API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc
- **Root Info**: http://localhost:8001/

### What's Next (Phase 2)

The following features are ready to be added:

1. **Human-in-the-Loop**
   - Add middleware with `@before_model` hook
   - Implement approval checkpoints
   - Frontend approval UI

2. **Research Plan Tool**
   - Create structured output for research plans
   - Add tool to agent's tool list
   - UI to display/approve plans

3. **Additional Tools**
   - GraphQL KG query tool
   - Past research lookup
   - Candidate exploration

4. **Enhanced UX**
   - Better streaming indicators
   - Tool usage visualization
   - Message editing/regeneration

### Environment Variables Required

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# MongoDB
MONGO_URI=mongodb://localhost:27017
MONGO_BIOTECH_DB_NAME=biotech_research_db

# Postgres (for LangGraph persistence)
POSTGRES_URI=postgresql+asyncpg://user:pass@localhost:5432/research_db

# RabbitMQ (for task queue)
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Redis (for progress streaming)
REDIS_URL=redis://localhost:6379/0

# CORS (for frontend)
CORS_ORIGINS=http://localhost:3000
```

### Notes

- The coordinator agent uses the same Postgres persistence as your other agents
- Thread storage is separate in MongoDB (not in Postgres checkpoints)
- Streaming works via Server-Sent Events (SSE)
- The agent automatically handles tool calling and message formatting
- All conversation history is preserved in MongoDB for later retrieval

---

**Status**: ✅ Phase 1 Complete - Ready for Frontend Integration
**Last Updated**: 2026-02-15
