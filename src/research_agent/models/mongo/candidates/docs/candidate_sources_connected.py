
# research_agent/biotech_research/beanie_models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Annotated

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.mongo.candidates.embedded.entities_connected import CandidateSourcesConnectedModel



class CandidateSourcesConnectedDoc(Document):
    """
    Persisted merged connected graph output (across domains).
    """
    runId: Annotated[str, Indexed()]
    query: Annotated[str, Indexed()]

    pipelineVersion: Annotated[str, Indexed()] = "v1"

    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: Optional[datetime] = None

    payload: CandidateSourcesConnectedModel

    class Settings:
        name = "intel_candidate_sources_connected"
        indexes = [
            [("runId", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)],
            [("query", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)],
        ]

