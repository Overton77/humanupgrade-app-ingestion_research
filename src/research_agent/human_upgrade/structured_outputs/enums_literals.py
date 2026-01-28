from enum import Enum
from typing import Literal 

DirectionType = Literal["GUEST", "BUSINESS", "PRODUCT", "COMPOUND"]

class SourceType(str, Enum):
    """Types of sources that can provide evidence for extracted entities."""
    COMPANY_WEBSITE = "company_website"
    PUBMED = "pubmed"
    WIKIPEDIA = "wikipedia"
    NEWS = "news"
    TAVILY_SEARCH = "tavily_search"
    FIRECRAWL_SCRAPE = "firecrawl_scrape"
    EPISODE_TRANSCRIPT = "episode_transcript"
    CLINICAL_TRIAL = "clinical_trial"
    OTHER = "other" 


class EntityType(str, Enum):
    """Types of entities that can be profiled in entity intelligence research."""
    PERSON = "person"
    BUSINESS = "business"
    PRODUCT = "product"
    COMPOUND = "compound"
    OTHER = "other"


EntityTypeHint = Literal["PERSON", "ORGANIZATION", "PRODUCT", "PLATFORM", "COMPOUND", "OTHER"] 


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


PriorityLevel = Literal["HIGH", "MEDIUM", "LOW"]
EntityResearchType = Literal["PERSON", "BUSINESS", "PRODUCT", "COMPOUND", "PLATFORM"]
TodoStatus = Literal["pending", "in_progress", "completed", "blocked", "skipped"]
SourcePriorityType = Literal[
    "OFFICIAL",
    "REGULATOR_OR_EXCHANGE",
    "REPUTABLE_SECONDARY",
    "WIKI_LAST",
    "OTHER"
]
