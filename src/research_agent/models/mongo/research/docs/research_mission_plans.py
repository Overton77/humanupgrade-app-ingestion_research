from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Annotated

import pymongo
from beanie import Document, Indexed
from beanie.odm.fields import PydanticObjectId
from pydantic import BaseModel, Field

from research_agent.models.mongo.research.enums import StageMode
from research_agent.models.mongo.research.embedded.plan_models import ResearchMissionPlan
from research_agent.utils.datetime_helpers import utc_now



class ResearchMissionPlanDoc(Document):
    # stable key used by /missions/{research_mission_id}/start
    researchMissionId: Annotated[str, Indexed(unique=True)]
    stageMode: StageMode
    planVersion: str = "v1"
    plan: ResearchMissionPlan

    # denormalized for filter/search
    targetBusinesses: List[str] = []
    targetPeople: List[str] = []
    targetProducts: List[str] = [] 
    targetTechnologies: List[str] = []

    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "research_mission_plans"
        indexes = [
            # researchMissionId is already indexed+unique via Annotated
            "stageMode",
        ]


