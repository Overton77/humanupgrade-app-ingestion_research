from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Annotated

import pymongo
from beanie import Document, Indexed
from beanie.odm.fields import PydanticObjectId
from pydantic import BaseModel, Field

from research_agent.models.mongo.research.embedded.plan_models import ResearchMissionPlan
from research_agent.utils.datetime_helpers import utc_now



class ResearchRunDoc(Document):
    researchMissionId: Annotated[str, Indexed()]  # NOT unique; many runs per mission
    mongoPlanId: Annotated[PydanticObjectId, Indexed()]  # link to plan doc

    # Immutable snapshot (reproducibility)
    planSnapshot: ResearchMissionPlan

    status: Annotated[str, Indexed()] = "RUNNING"  # RUNNING | SUCCEEDED | FAILED | CANCELED
    startedAt: datetime = Field(default_factory=utc_now)
    endedAt: Optional[datetime] = None

    totalTasks: int = 0
    succeededTasks: int = 0
    failedTasks: int = 0

    failFast: bool = False

    class Settings:
        name = "research_runs"
        indexes = [
            # common listing query: “all running runs for a mission”
            [("researchMissionId", pymongo.ASCENDING), ("status", pymongo.ASCENDING)],
            # mongoPlanId already indexed via Annotated
        ]


