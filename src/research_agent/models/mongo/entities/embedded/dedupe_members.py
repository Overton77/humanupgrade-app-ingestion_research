from __future__ import annotations

from typing import Optional
from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict

class DedupeMemberModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    candidateEntityId: str
    runId: str
    entityDocId: Optional[PydanticObjectId] = None
