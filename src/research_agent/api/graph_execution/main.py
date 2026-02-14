"""
Graph Execution API - FastAPI application.

Provides endpoints for:
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    
    Startup: Initialize Taskiq broker, MongoDB/Beanie
    Shutdown: Close broker and Redis
    """
    # Startup
    if not broker.is_worker_process:
        print("[fastapi] Starting Taskiq broker...")
        try:
            await broker.startup()
            print("[fastapi] ✅ Taskiq broker connected to RabbitMQ")
        except Exception as e:
            print(f"[fastapi] ❌ Failed to start Taskiq broker: {e}")
            raise
    
    # Initialize MongoDB/Beanie
    # This is required for graph nodes that persist to MongoDB
    print("[fastapi] Initializing MongoDB/Beanie...")
    try:
        await init_beanie_biotech_db(mongo_client)
        print("[fastapi] ✅ MongoDB/Beanie initialized")
    except Exception as e:
        print(f"[fastapi] ❌ Failed to initialize MongoDB: {e}")
        raise
    
    print("[fastapi] 🚀 All services ready")
    
    yield
    
    # Shutdown
    print("[fastapi] Shutting down...")
    if not broker.is_worker_process:
        await broker.shutdown()
        print("[fastapi] ✅ Broker shutdown complete")
    
    await close_redis_client()
    print("[fastapi] ✅ Redis connection closed")
    
    # Close MongoDB connection
    await mongo_client.close()
    print("[fastapi] ✅ MongoDB connection closed")


app = FastAPI(
    title="Graph Execution API",
    description="Execute research graphs asynchronously with real-time progress streaming",
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
app.include_router(health.router)
app.include_router(entity_discovery.router, prefix="/graphs")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Graph Execution API",
        "version": "1.0.0",
        "docs": "/docs",
    }
