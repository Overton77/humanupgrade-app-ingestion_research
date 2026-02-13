# research_agent/biotech_research/beanie_models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Annotated

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field

from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.base.enums import EntityTypeHint



# =============================================================================
# Embedded models (Beanie stores these inside Documents)
# =============================================================================

class CandidateEntityModel(BaseModel):
    """
    High-recall seed candidate entity (small, low-risk).
    """
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    name: str = Field(..., min_length=1)
    normalizedName: str = Field(..., min_length=1)
    typeHint: EntityTypeHint
    role: Optional[str] = None
    contextSnippets: List[str] = Field(default_factory=list, max_length=3)
    mentions: int = Field(default=1, ge=1)
    sourceUrls: List[str] = Field(default_factory=list, max_length=3)