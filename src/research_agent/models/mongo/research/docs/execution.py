from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Annotated

import pymongo
from beanie import Document, Indexed
from beanie.odm.fields import PydanticObjectId
from pydantic import BaseModel, Field

from research_agent.models.mongo.research.enums import TaskStatus
from research_agent.utils.datetime_helpers import utc_now



class InstanceRunDoc(Document):
    mongoRunId: Annotated[PydanticObjectId, Indexed()]
    instanceId: Annotated[str, Indexed()]
    stageId: Optional[str] = None
    subStageId: Optional[str] = None

    status: Annotated[TaskStatus, Indexed()] = TaskStatus.RUNNING
    startedAt: datetime = Field(default_factory=utc_now)
    endedAt: Optional[datetime] = None

    finalReport: Optional[Dict[str, Any]] = None
    fileRefs: List[Dict[str, Any]] = []
    notes: Optional[str] = None

    class Settings:
        name = "instance_runs"
        indexes = [
            [("mongoRunId", pymongo.ASCENDING), ("instanceId", pymongo.ASCENDING)],
            [("mongoRunId", pymongo.ASCENDING), ("subStageId", pymongo.ASCENDING)],
        ]


class SubStageReduceDoc(Document):
    mongoRunId: Annotated[PydanticObjectId, Indexed()]
    stageId: Annotated[str, Indexed()]
    subStageId: Annotated[str, Indexed()]

    startedAt: datetime = Field(default_factory=utc_now)
    endedAt: Optional[datetime] = None

    reducedOutput: Dict[str, Any] = {}
    producedOutputIds: List[PydanticObjectId] = []

    class Settings:
        name = "substage_reduces"
        indexes = [
            [("mongoRunId", pymongo.ASCENDING), ("stageId", pymongo.ASCENDING), ("subStageId", pymongo.ASCENDING)],
        ]
