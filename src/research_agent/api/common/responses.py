"""
Standard API response schemas.
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TaskResponse(BaseModel):
    """Response when a background task is enqueued."""
    task_id: str = Field(..., description="Unique task identifier")
    run_id: str = Field(..., description="Graph run identifier for progress tracking")
    status: str = Field(default="pending", description="Initial task status")
    message: str = Field(default="Task enqueued successfully")


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
