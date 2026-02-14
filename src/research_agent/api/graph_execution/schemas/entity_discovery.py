"""
Request/response schemas for entity discovery graph execution.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class EntityDiscoveryRequest(BaseModel):
    """Request to execute entity discovery graph."""
    
    query: str = Field(
        ...,
        description="User's research query or target entity to investigate",
        min_length=3,
        max_length=500,
    )
    
    starter_sources: List[str] = Field(
        default_factory=list,
        description="Optional starting URLs/domains to anchor discovery",
        max_length=10,
    )
    
    starter_content: Optional[str] = Field(
        None,
        description="Optional starter context (notes, pasted text, previous summary)",
        max_length=5000,
    )
    
    thread_id: Optional[str] = Field(
        None,
        description="LangGraph thread ID for checkpointing (auto-generated if not provided)",
    )
    
    checkpoint_ns: Optional[str] = Field(
        None,
        description="LangGraph checkpoint namespace (auto-generated if not provided)",
    )


class EntityDiscoveryResponse(BaseModel):
    """Response from entity discovery graph execution."""
    
    run_id: str = Field(..., description="Unique run identifier")
    candidate_sources: Dict[str, Any] = Field(..., description="Connected candidates with sources")
    pipeline_version: str = Field(..., description="Pipeline version")
    intel_run_id: str = Field(..., description="Intel run ID for tracking")
