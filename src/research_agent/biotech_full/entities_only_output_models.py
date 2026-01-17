from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# -------------------------
# Core helper shapes
# -------------------------

class MediaLinkOut(BaseModel):
    # GraphQL MediaLinkInput requires description (String!) in your schema :contentReference[oaicite:1]{index=1}
    url: str
    description: str = ""  # keep non-null
    poster_url: Optional[str] = None

class EntityRef(BaseModel):
    """Reference another entity in this payload by local_id."""
    local_id: str
    name: Optional[str] = None  # redundancy to help debugging / readability


# -------------------------
# Leaf entities
# -------------------------

class CompoundOut(BaseModel):
    local_id: str = Field(..., description="Unique within this payload, e.g. 'cmp_001'")
    name: str
    description: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    mechanism_of_action: Optional[str] = None  # not in Mongo model, store later in notes/claims
    media_links: List[MediaLinkOut] = Field(default_factory=list)

class PersonOut(BaseModel):
    local_id: str = Field(..., description="Unique within this payload, e.g. 'per_001'")
    name: str
    is_guest: bool = False
    role: Optional[str] = None
    bio: Optional[str] = None
    media_links: List[MediaLinkOut] = Field(default_factory=list)

class ProductOut(BaseModel):
    local_id: str = Field(..., description="Unique within this payload, e.g. 'prd_001'")
    name: str
    description: Optional[str] = None
    price_amount: Optional[float] = None
    price_currency: Optional[str] = None  # "USD" if known
    ingredients: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    media_links: List[MediaLinkOut] = Field(default_factory=list)

    # relationship nest (bounded)
    compounds: List[CompoundOut] = Field(default_factory=list)

class BusinessOut(BaseModel):
    local_id: str = Field(..., description="Unique within this payload, e.g. 'biz_001'")
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    media_links: List[MediaLinkOut] = Field(default_factory=list)

    # relationship nest (bounded)
    products: List[ProductOut] = Field(default_factory=list)
    people: List[PersonOut] = Field(default_factory=list)

class CaseStudyOut(BaseModel):
    local_id: str = Field(..., description="Unique within this payload, e.g. 'cs_001'")
    title: str
    summary: str
    url: Optional[str] = None
    source_type: Literal["pubmed", "clinical_trial", "article", "website", "news", "other"] = "other"

    media_links: List[MediaLinkOut] = Field(default_factory=list)

    # relationship nest (bounded)
    compounds: List[CompoundOut] = Field(default_factory=list)
    products: List[ProductOut] = Field(default_factory=list)

class EpisodeContextOut(BaseModel):
    episode_id: Optional[str] = None  # mongo id if you have it, optional
    episode_url: str  # episodePageUrl

class ResearchEntitiesOut(BaseModel):
    episode: EpisodeContextOut

    # prefer top-level "businesses" as the primary container
    businesses: List[BusinessOut] = Field(default_factory=list)

    # optional extras (only if they don’t belong under a business cleanly)
    orphan_people: List[PersonOut] = Field(default_factory=list)
    orphan_products: List[ProductOut] = Field(default_factory=list)

    case_studies: List[CaseStudyOut] = Field(default_factory=list)

    extraction_notes: Optional[str] = None
