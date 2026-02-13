# research_agent/biotech_research/beanie_models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Annotated

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.mongo.candidates.embedded.seeds import SeedExtractionModel



class CandidateSeedDoc(Document):
    """
    Persisted "Seeds" output (minimally validated candidates).
    """
    runId: Annotated[str, Indexed()]  # tie to research run / candidate run
    query: Annotated[str, Indexed()]

    pipelineVersion: Annotated[str, Indexed()] = "v1"

    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: Optional[datetime] = None

    payload: SeedExtractionModel

    class Settings:
        name = "intel_candidate_seeds"
        indexes = [
            [("runId", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)],
            [("query", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)],
        ]
