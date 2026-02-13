# research_agent/biotech_research/beanie_models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Annotated

import pymongo
from pydantic import BaseModel, ConfigDict, Field

from research_agent.models.base.enums import EntityTypeHint, OfficialSourceKind



class OfficialStarterSourceModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    kind: OfficialSourceKind
    url: str = Field(..., min_length=1)
    domain: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list, max_length=4)

class OfficialEntityTargetsModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)
    inputName: str = Field(..., min_length=1)
    normalizedName: str = Field(..., min_length=1)
    typeHint: str
    sources: List[OfficialStarterSourceModel] = Field(default_factory=list)
    notes: Optional[str] = None


class OfficialStarterSourcesModel(BaseModel):
    """
    Output of "Official Sources" step (Node A).
    """
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    query: str

    people: List[OfficialEntityTargetsModel] = Field(default_factory=list)
    organizations: List[OfficialEntityTargetsModel] = Field(default_factory=list)
    products: List[OfficialEntityTargetsModel] = Field(default_factory=list)
    technologies: List[OfficialEntityTargetsModel] = Field(default_factory=list)

    domainTargets: List[str] = Field(default_factory=list)
    globalNotes: Optional[str] = None