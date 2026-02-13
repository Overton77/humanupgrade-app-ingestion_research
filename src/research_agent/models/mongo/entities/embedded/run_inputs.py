from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from research_agent.models.base.enums import OfficialSourceKind

class StarterSourceRefModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    url: str = Field(..., min_length=1)
    kind: Optional[OfficialSourceKind] = None
    label: Optional[str] = None
    domain: Optional[str] = None


class StarterContentRefModel(BaseModel):
    """
    Reference to ingested content used to seed the run.
    This should match how your ingestion layer stores content.
    """
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    # pick what you actually have available today:
    chunkIds: List[str] = Field(default_factory=list)
    fileIds: List[str] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)

    # optional fingerprints
    contentHash: Optional[str] = None
    notes: Optional[str] = None


class CandidateRunInputsModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    query: str = Field(..., min_length=1)
    starterSources: List[StarterSourceRefModel] = Field(default_factory=list)
    starterContent: Optional[StarterContentRefModel] = None
    notes: Optional[str] = None