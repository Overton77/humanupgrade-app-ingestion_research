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
from research_agent.api.graph_execution.routes import entity_discovery, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    
    Startup: Initialize Taskiq broker
    Shutdown: Close broker and Redis
    """
    # Startup
    if not broker.is_worker_process:
        await broker.startup()
    
    yield
    
    # Shutdown
    if not broker.is_worker_process:
        await broker.shutdown()
    
    await close_redis_client()


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
