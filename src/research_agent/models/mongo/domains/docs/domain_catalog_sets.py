
# research_agent/biotech_research/beanie_models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Annotated

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.mongo.domains.domain_catalog_set import DomainCatalogSetModel



class DomainCatalogSetDoc(Document):
    """
    Persisted "Domain Catalog Sets" output (Node B).
    """
    runId: Annotated[str, Indexed()]
    query: Annotated[str, Indexed()]

    pipelineVersion: Annotated[str, Indexed()] = "v1"

    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: Optional[datetime] = None

    payload: DomainCatalogSetModel

    class Settings:
        name = "intel_domain_catalog_sets"
        indexes = [
            [("runId", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)],
            [("query", pymongo.ASCENDING), ("createdAt", pymongo.DESCENDING)],
        ]

