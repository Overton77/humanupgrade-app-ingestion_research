
# research_agent/biotech_research/beanie_models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Annotated

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from research_agent.utils.datetime_helpers import utc_now
from research_agent.models.mongo.domains.domain_catalog import DomainCatalogModel


class DomainCatalogSetModel(BaseModel):
    """
    Bounded set of DomainCatalogs for a query.
    """
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    query: str
    selectedDomainBudget: int = Field(default=3, ge=1, le=4)
    catalogs: List[DomainCatalogModel] = Field(default_factory=list)
    globalNotes: Optional[str] = None





