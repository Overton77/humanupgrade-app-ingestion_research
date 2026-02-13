# research_agent/biotech_research/beanie_models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Annotated

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.mongo.candidates.embedded.entity_sources import EntitySourceResultModel





class ProductWithCompoundsModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    product: EntitySourceResultModel
    compounds: List[EntitySourceResultModel] = Field(default_factory=list)

    compoundLinkNotes: Optional[str] = None
    compoundLinkConfidence: float = Field(default=0.75, ge=0.0, le=1.0)