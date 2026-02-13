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
from research_agent.models.mongo.candidates.embedded.products_and_compounds import ProductWithCompoundsModel
from research_agent.models.base.enums import DomainRole






class OrganizationIntelBundleModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    organization: EntitySourceResultModel
    people: List[EntitySourceResultModel] = Field(default_factory=list)
    technologies: List[EntitySourceResultModel] = Field(default_factory=list)
    products: List[ProductWithCompoundsModel] = Field(default_factory=list)
    businessLevelCompounds: List[EntitySourceResultModel] = Field(default_factory=list)

    relatedOrganizations: Optional[List[EntitySourceResultModel]] = None

    keySourceUrls: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class ConnectedCandidatesModel(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    query: str
    baseDomain: str
    mappedFromUrl: Optional[str] = None
    sourceDomainRole: Optional[DomainRole] = None

    primary_person: Optional[EntitySourceResultModel] = None
    primary_organization: Optional[EntitySourceResultModel] = None
    primary_technology: Optional[EntitySourceResultModel] = None

    intel_bundle: OrganizationIntelBundleModel
    notes: Optional[str] = None


class CandidateSourcesConnectedModel(BaseModel):
    """
    Graph output: merged slice-level ConnectedCandidates.
    """
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    connected: List[ConnectedCandidatesModel] = Field(default_factory=list)
    globalNotes: Optional[str] = None
