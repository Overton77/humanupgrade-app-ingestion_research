
# research_agent/biotech_research/beanie_models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Annotated

import pymongo
from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from research_agent.utils.datetime_helpers import utc_now




class DomainCatalogModel(BaseModel):
    """
    Output of "Domain Catalog" mapping step (Node B) for a single domain/subdomain.
    """
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    priority: int = Field(default=99, ge=1, le=99)
    targetEntityKey: Optional[str] = None

    baseDomain: str
    mappedFromUrl: Optional[str] = None
    sourceDomainRole: Optional[str] = None

    mappedUrls: List[str] = Field(default_factory=list)

    productIndexUrls: List[str] = Field(default_factory=list)
    productPageUrls: List[str] = Field(default_factory=list)
    platformUrls: List[str] = Field(default_factory=list)

    homepageUrls: List[str] = Field(default_factory=list)
    aboutUrls: List[str] = Field(default_factory=list)
    blogUrls: List[str] = Field(default_factory=list)
    leadershipUrls: List[str] = Field(default_factory=list)
    helpCenterUrls: List[str] = Field(default_factory=list)
    documentationUrls: List[str] = Field(default_factory=list)
    labelUrls: List[str] = Field(default_factory=list)
    researchUrls: List[str] = Field(default_factory=list)
    caseStudyUrls: List[str] = Field(default_factory=list)
    testimonialUrls: List[str] = Field(default_factory=list)
    patentUrls: List[str] = Field(default_factory=list)
    landingPageUrls: List[str] = Field(default_factory=list)
    pressUrls: List[str] = Field(default_factory=list)
    policyUrls: List[str] = Field(default_factory=list)
    regulatoryUrls: List[str] = Field(default_factory=list)

    notes: Optional[str] = None

