"""Health check endpoints for Coordinator API."""

from fastapi import APIRouter, status
from pydantic import BaseModel


router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check():
    """Basic health check endpoint.
    
    Returns:
        Health status indicating the service is running.
    """
    return HealthResponse(
        status="healthy",
        service="coordinator-api"
    )


@router.get("/ready", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def readiness_check():
    """Readiness check endpoint.
    
    Returns:
        Readiness status indicating the service is ready to handle requests.
    """
    # TODO: Add actual checks for:
    # - MongoDB connectivity
    # - Model initialization
    # - Any other critical dependencies
    
    return HealthResponse(
        status="ready",
        service="coordinator-api"
    )
