from __future__ import annotations  
from research_agent.utils.datetime_helpers import utc_now  
from typing import Any, Dict, List, Optional, Annotated 
from datetime import datetime

import pymongo
from beanie import Document, Indexed
from beanie.odm.fields import PydanticObjectId
from pydantic import BaseModel, Field


class RunEventDoc(Document):
    mongoRunId: Annotated[PydanticObjectId, Indexed()]
    ts: datetime = Field(default_factory=utc_now)

    eventType: Annotated[str, Indexed()]
    taskRunId: Optional[PydanticObjectId] = None
    taskId: Optional[str] = None
    taskType: Optional[str] = None
    taskKey: Optional[str] = None
    data: Dict[str, Any] = {}

    class Settings:
        name = "run_events"
        indexes = [
            [("mongoRunId", pymongo.ASCENDING), ("ts", pymongo.ASCENDING)],
            [("mongoRunId", pymongo.ASCENDING), ("eventType", pymongo.ASCENDING)],
        ]
