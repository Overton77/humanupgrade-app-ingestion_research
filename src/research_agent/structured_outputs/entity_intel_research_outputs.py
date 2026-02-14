
from __future__ import annotations
from typing import Optional, Literal, List, Dict, Any  
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum 
from research_agent.structured_outputs.enums_literals import SourceType
import uuid


class KBSummarySpec(BaseModel):
    """Specification for the knowledge base summary to generate."""
    targetAudience: str = Field(
        default="user-facing",
        description="Who will read this (e.g., 'user-facing', 'internal', 'technical')"
    )
    maxWords: int = Field(
        default=180,
        ge=50,
        le=500,
        description="Maximum word count for the KB summary"
    )
    mustInclude: List[str] = Field(
        default_factory=list,
        description="Required elements to include (e.g., 'what it is', 'who runs it', 'where to learn more')"
    )
    mustAvoid: List[str] = Field(
        default_factory=list,
        description="Things to explicitly avoid (e.g., 'medical claims validation', 'efficacy conclusions')"
    )


