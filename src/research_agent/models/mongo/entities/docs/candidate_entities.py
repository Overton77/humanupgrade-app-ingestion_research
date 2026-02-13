from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Annotated

import pymongo
from beanie import Document, Indexed
from pydantic import Field

from research_agent.models.base.enums import CandidateStatus
from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.base.enums import EntityTypeHint

from research_agent.models.mongo.candidates.embedded.entity_sources import SourceCandidateModel

class IntelCandidateEntityDoc(Document):
    candidateEntityId: Annotated[str, Indexed()]
    runId: Annotated[str, Indexed()]
    pipelineVersion: Annotated[str, Indexed()] = "v1"

    # what the UX consumes
    typeHint: Annotated[EntityTypeHint, Indexed()]
    inputName: str
    normalizedName: Annotated[str, Indexed()]

    canonicalName: Optional[str] = None
    canonicalConfidence: Optional[float] = None

    # stable identifier for dedupe / graph merges
    entityKey: Annotated[str, Indexed()]

    # evidence / provenance
    candidateSources: List[SourceCandidateModel] = Field(default_factory=list)

    # helpful context for UX grouping/filtering
    baseDomain: Optional[str] = None
    mappedFromUrl: Optional[str] = None

    status: Annotated[CandidateStatus, Indexed()] = CandidateStatus.new
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: Optional[datetime] = None

    notes: Optional[str] = None

    class Settings:
        name = "intel_candidate_entities"
        indexes = [
            [("runId", pymongo.ASCENDING), ("typeHint", pymongo.ASCENDING)],
            [("entityKey", pymongo.ASCENDING)],
            [("normalizedName", pymongo.ASCENDING)],
        ]