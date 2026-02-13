from __future__ import annotations

from enum import Enum
from typing import  Literal



# =============================================================================
# Shared enums / literals (match your structured output contracts)
# =============================================================================

class EntityTypeHint(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    PRODUCT = "PRODUCT"
    COMPOUND = "COMPOUND"
    TECHNOLOGY = "TECHNOLOGY"
    OTHER = "OTHER"


SourceType = Literal[
    "OFFICIAL",
    "WIKIPEDIA",
    "PROFILE",
    "GOV_OR_REGISTRY",
    "PUBMED",
    "NEWS_OR_PR",
    "REVIEW_OR_RETAIL",
    "OTHER",
]

ValidationLevel = Literal[
    "NAME_ONLY",
    "ENTITY_MATCH",
]


DomainRole = Literal["primary", "shop", "help", "docs", "blog", "other"]


OfficialSourceKind = Literal[
    # Organization roots + key pages
    "org_primary_domain",
    "org_about_or_team",
    "org_leadership",
    "org_products_or_catalog",
    "org_science_or_technology",
    "org_docs_or_developers",
    "org_press_or_news",
    "org_careers",
    "org_contact",
    # Product roots + key pages
    "product_official_domain",
    "product_official_page",
    "product_docs",
    "product_pricing_or_access",
    # People roots + key pages
    "person_official_profile",
    "person_org_profile",
    "person_public_profile",
    # Technology roots + key pages
    "technology_official_domain",
    "technology_reference_page",
    "technology_docs",
    # Cross-entity disambiguation
    "third_party_disambiguation",
    "other",
    "unknown",
]


class PipelineStatus(str, Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    failed = "failed"


class CandidateStatus(str, Enum):
    new = "new"
    accepted = "accepted"
    rejected = "rejected"
    merged = "merged"
    archived = "archived"


class DedupeResolutionStatus(str, Enum):
    unresolved = "unresolved"
    resolved = "resolved"
    ignored = "ignored"



class IntelArtifactKind(str, Enum):
    domain_catalog_set = "domain_catalog_set"
    official_starter_sources = "official_starter_sources"
    seeds = "seeds"
    connected_candidates = "connected_candidates"
    candidate_sources_connected = "candidate_sources_connected"
    other = "other"
