from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Annotated

import pymongo
from beanie import Document, Indexed
from pydantic import Field

from research_agent.models.base.enums import DedupeResolutionStatus
from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.base.enums import EntityTypeHint

from research_agent.models.mongo.entities.embedded.dedupe_members import DedupeMemberModel

class IntelDedupeGroupDoc(Document):
    dedupeGroupId: Annotated[str, Indexed()]

    typeHint: Annotated[EntityTypeHint, Indexed()]
    entityKey: Annotated[str, Indexed()]

    canonicalName: Optional[str] = None
    members: List[DedupeMemberModel] = Field(default_factory=list)

    resolutionStatus: Annotated[DedupeResolutionStatus, Indexed()] = DedupeResolutionStatus.unresolved

    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: Optional[datetime] = None

    class Settings:
        name = "intel_dedupe_groups"
        indexes = [
            [("typeHint", pymongo.ASCENDING), ("entityKey", pymongo.ASCENDING)],
            [("resolutionStatus", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)],
        ]
