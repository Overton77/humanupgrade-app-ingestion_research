from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Annotated

import pymongo
from beanie import Document, Indexed
from beanie.odm.fields import PydanticObjectId
from pydantic import BaseModel, Field

from research_agent.models.mongo.research.enums import TaskType


class TaskDef(BaseModel):
    taskId: str
    taskType: TaskType
    taskKey: str
    inputs: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}


