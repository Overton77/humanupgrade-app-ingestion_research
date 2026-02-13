from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Annotated

import pymongo
from beanie import Document, Indexed
from beanie.odm.fields import PydanticObjectId
from pydantic import BaseModel, Field


from research_agent.models.mongo.research.enums import OutputType
from research_agent.utils.datetime_helpers import utc_now




class OutputDoc(Document):
    mongoRunId: Annotated[PydanticObjectId, Indexed()]        # NOT unique
    researchMissionId: Annotated[str, Indexed()]

    producerTaskRunId: Optional[PydanticObjectId] = None
    producerInstanceId: Optional[str] = None
    stageId: Optional[str] = None
    subStageId: Optional[str] = None

    outputType: Annotated[OutputType, Indexed()]
    subjectKey: Optional[str] = None  # e.g. "person:Brad Pitzele", "product:10 LPM EWOT System"

    payload: Dict[str, Any] = {}

    sourceUrls: List[str] = []
    sourceDocIds: List[str] = []
    chunkIds: List[str] = []

    createdAt: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "outputs"
        indexes = [
            [("mongoRunId", pymongo.ASCENDING), ("outputType", pymongo.ASCENDING)],
            [("mongoRunId", pymongo.ASCENDING), ("subjectKey", pymongo.ASCENDING), ("outputType", pymongo.ASCENDING)],
            # optional uniqueness to prevent duplicates for the same producer+subject+type
            # Uncomment if you want hard enforcement:
            # pymongo.IndexModel(
            #     [
            #         ("mongoRunId", pymongo.ASCENDING),
            #         ("outputType", pymongo.ASCENDING),
            #         ("subjectKey", pymongo.ASCENDING),
            #         ("producerInstanceId", pymongo.ASCENDING),
            #     ],
            #     unique=True,
            # ),
        ]
