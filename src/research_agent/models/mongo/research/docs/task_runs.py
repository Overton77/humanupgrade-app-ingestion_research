from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Annotated

import pymongo
from beanie import Document, Indexed
from beanie.odm.fields import PydanticObjectId
from pydantic import BaseModel, Field

from research_agent.models.mongo.research.enums import TaskStatus
from research_agent.models.mongo.research.embedded.tasks import TaskDef
from research_agent.utils.datetime_helpers import utc_now





class TaskRunDoc(Document):
    mongoRunId: Annotated[PydanticObjectId, Indexed()]        # NOT unique
    mongoPlanId: Annotated[PydanticObjectId, Indexed()]
    researchMissionId: Annotated[str, Indexed()]

    task: TaskDef

    status: Annotated[TaskStatus, Indexed()] = TaskStatus.PENDING
    depsRemaining: int = 0
    parents: List[str] = []      # list[taskId]
    dependents: List[str] = []   # list[taskId]

    attempt: int = 1
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)

    # leasing / anti-double-enqueue
    leaseOwner: Optional[str] = None
    leaseExpiresAt: Optional[datetime] = None

    outputRef: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    class Settings:
        name = "task_runs"
        indexes = [
            [("mongoRunId", pymongo.ASCENDING), ("status", pymongo.ASCENDING)],
            [("mongoRunId", pymongo.ASCENDING), ("task.taskId", pymongo.ASCENDING)],
            [("mongoRunId", pymongo.ASCENDING), ("leaseExpiresAt", pymongo.ASCENDING)],
            # optional: to ensure no duplicate taskId within a run
            # (highly recommended)
            [
                ("mongoRunId", pymongo.ASCENDING),
                ("task.taskId", pymongo.ASCENDING),
            ],
        ]


