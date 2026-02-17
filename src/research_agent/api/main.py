"""
Research Agent API - Unified FastAPI application.

Provides endpoints for:
- Coordinator Agent (conversational AI with web search)
- Entity discovery graph execution
- Real-time progress streaming via WebSocket
- Task status queries
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from research_agent.infrastructure.queue.taskiq_broker import broker
from research_agent.infrastructure.storage.redis.client import close_redis_client
from research_agent.infrastructure.storage.mongo.base_client import mongo_client
from research_agent.infrastructure.storage.mongo.biotech_research_db_beanie import init_beanie_biotech_db
from research_agent.api.graph_execution.routes import entity_discovery, health
from research_agent.api.coordinator.routes import threads as coordinator_threads
from research_agent.api.coordinator.routes import health as coordinator_health
from research_agent.api.coordinator.routes import files as coordinator_files
from research_agent.api.coordinator.routes import hitl_websocket
from research_agent.services.coordinator_agent import initialize_coordinator_agent
from fastapi.staticfiles import StaticFiles
from pathlib import Path


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    
    Startup: Initialize Taskiq broker, MongoDB/Beanie, Coordinator Agent
    Shutdown: Close broker, Redis, and MongoDB
    """
    # Startup
    print("[api] 🚀 Starting Research Agent API...")
    
    # 1. Start Taskiq broker (for async task execution)
    if not broker.is_worker_process:
        print("[api] Starting Taskiq broker...")
        try:
            await broker.startup()
            print("[api] ✅ Taskiq broker connected to RabbitMQ")
        except Exception as e:
            print(f"[api] ❌ Failed to start Taskiq broker: {e}")
            raise
    
    # 2. Initialize MongoDB/Beanie
    # This is required for graph nodes that persist to MongoDB
    print("[api] Initializing MongoDB/Beanie...")
    try:
        await init_beanie_biotech_db(mongo_client)
        print("[api] ✅ MongoDB/Beanie initialized")
    except Exception as e:
        print(f"[api] ❌ Failed to initialize MongoDB: {e}")
        raise
    
    # 3. Initialize Coordinator Agent (with Postgres store/checkpointer)
    print("[api] Initializing Coordinator Agent...")
    try:
        await initialize_coordinator_agent()
        print("[api] ✅ Coordinator Agent initialized")
    except Exception as e:
        print(f"[api] ❌ Failed to initialize Coordinator Agent: {e}")
        raise
    
    print("[api] 🎉 All services ready!")
    
    yield
    
    # Shutdown
    print("[api] 👋 Shutting down...")
    
    if not broker.is_worker_process:
        await broker.shutdown()
        print("[api] ✅ Broker shutdown complete")
    
    await close_redis_client()
    print("[api] ✅ Redis connection closed")
    
    # Close MongoDB connection
    await mongo_client.close()
    print("[api] ✅ MongoDB connection closed")
    
    print("[api] ✅ Shutdown complete")


app = FastAPI(
    title="Research Agent API",
    description="Research agent system with graph execution and conversational coordinator",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# Health checks
app.include_router(health.router)
app.include_router(coordinator_health.router, prefix="/coordinator")

# Graph execution
app.include_router(entity_discovery.router, prefix="/graphs")

# Coordinator agent (conversational)
app.include_router(coordinator_threads.router)
app.include_router(coordinator_files.router)
app.include_router(hitl_websocket.router)  # WebSocket for HITL

# Serve uploaded files
upload_dir = Path("uploads")
upload_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Research Agent API",
        "version": "1.0.0",
        "description": "Research agent system with graph execution and conversational coordinator",
        "endpoints": {
            "health": {
                "graph_execution": "/health",
                "coordinator": "/coordinator/health",
            },
            "coordinator": {
                "threads": "/api/coordinator/threads",
                "create_thread": "POST /api/coordinator/threads",
                "list_threads": "GET /api/coordinator/threads",
                "get_thread": "GET /api/coordinator/threads/{thread_id}",
                "send_message": "POST /api/coordinator/threads/{thread_id}/messages",
                "websocket_hitl": "WS /api/coordinator/threads/{thread_id}/hitl",
            },
            "graphs": {
                "entity_discovery": "/graphs/entity-discovery/execute",
                "status": "/graphs/entity-discovery/status/{run_id}",
                "websocket": "/graphs/entity-discovery/ws/{run_id}",
            },
            "docs": "/docs",
        },
    }
