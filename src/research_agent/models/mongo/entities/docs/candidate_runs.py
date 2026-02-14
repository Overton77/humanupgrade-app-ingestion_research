from __future__ import annotations

from datetime import datetime
from typing import Optional, Annotated

import pymongo
from beanie import Document, Indexed
from pydantic import Field

from research_agent.models.base.enums import PipelineStatus
from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.mongo.entities.embedded.run_inputs import CandidateRunInputsModel
from research_agent.models.mongo.entities.embedded.run_output_refs import CandidateRunOutputsRefsModel

class IntelCandidateRunDoc(Document):
    runId: Annotated[str, Indexed()]
    pipelineVersion: Annotated[str, Indexed()] = "v1"
    status: Annotated[PipelineStatus, Indexed()] = PipelineStatus.queued

    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: Optional[datetime] = None

    # ✅ replaces episodeId/episodeUrl
    inputs: CandidateRunInputsModel

    # ✅ references to pipeline outputs you already store as docs
    outputs: CandidateRunOutputsRefsModel = Field(default_factory=CandidateRunOutputsRefsModel)

    # optional quick stats for dashboards
    candidateEntityCount: int = 0
    dedupeGroupCount: int = 0
    domainCount: int = 0
    
    # Track dedupe group IDs created during this run for easy querying
    dedupeGroupIds: list[str] = Field(default_factory=list)

    notes: Optional[str] = None

    class Settings:
        name = "intel_candidate_runs"
        indexes = [
            [("runId", pymongo.ASCENDING)],
            [("status", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)],
            [("inputs.query", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)], 
        ]