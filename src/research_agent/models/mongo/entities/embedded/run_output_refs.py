from __future__ import annotations

from typing import List, Optional
from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field

class CandidateRunOutputsRefsModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    seedsDocId: Optional[PydanticObjectId] = None
    officialStarterSourcesDocId: Optional[PydanticObjectId] = None
    domainCatalogSetDocId: Optional[PydanticObjectId] = None

    # per-domain slices
    connectedCandidatesDocIds: List[PydanticObjectId] = Field(default_factory=list)

    # merged graph
    connectedGraphDocId: Optional[PydanticObjectId] = None
