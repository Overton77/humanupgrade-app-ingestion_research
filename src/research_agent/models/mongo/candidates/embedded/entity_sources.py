# research_agent/biotech_research/beanie_models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Annotated

import pymongo
from pydantic import BaseModel, ConfigDict, Field

from research_agent.models.base.enums import SourceType, ValidationLevel, EntityTypeHint


class SourceCandidateModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    url: str
    label: str = Field(..., min_length=1)
    sourceType: SourceType
    rank: int = Field(..., ge=1)
    score: float = Field(..., ge=0.0, le=1.0)
    signals: List[str] = Field(default_factory=list)
    validationLevel: ValidationLevel = "NAME_ONLY" 


class EntitySourceResultModel(BaseModel):
    """
    Canonical-ish entity + candidate source list.
    """
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    inputName: str = Field(..., min_length=1)
    normalizedName: str = Field(..., min_length=1)
    typeHint: EntityTypeHint

    canonicalName: Optional[str] = None
    canonicalConfidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    candidates: List[SourceCandidateModel] = Field(default_factory=list)
    notes: Optional[str] = None
