from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Annotated

import pymongo
from beanie import Document, Indexed
from pydantic import Field

from research_agent.models.base.enums import IntelArtifactKind
from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.mongo.entities.embedded.run_inputs import CandidateRunInputsModel

class IntelArtifactDoc(Document):
    artifactId: Annotated[str, Indexed()]

    runId: Annotated[str, Indexed()]
    pipelineVersion: Annotated[str, Indexed()] = "v1"

    kind: Annotated[IntelArtifactKind, Indexed()] = IntelArtifactKind.other
    payloadHash: Annotated[str, Indexed()]

    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: Optional[datetime] = None
    extractedAt: Optional[datetime] = None

    # optional: attach run inputs snapshot for easy provenance
    inputs: Optional[CandidateRunInputsModel] = None

    payload: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None

    class Settings:
        name = "intel_artifacts"
        indexes = [
            [("runId", pymongo.ASCENDING), ("kind", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)],
            [("payloadHash", pymongo.ASCENDING)],
        ]
