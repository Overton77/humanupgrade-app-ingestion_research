from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

EntityType = Literal["PERSON","ORGANIZATION","PRODUCT","COMPOUND","PLATFORM"]

class PersonSeedOut(BaseModel):
    entity_key: str  # person:...
    canonical_name: str
    biography: Optional[str] = None
    website: Optional[str] = None
    media_links: List[dict] = Field(default_factory=list)
    role: Optional[str] = None  # "Founder", "CEO", etc (optional)

class BusinessSeedOut(BaseModel):
    entity_key: str  # business:...
    canonical_name: str
    description: Optional[str] = None
    biography: Optional[str] = None
    website: Optional[str] = None
    media_links: List[dict] = Field(default_factory=list)

class GuestBusinessExtraction(BaseModel):
    guest: PersonSeedOut
    business: BusinessSeedOut
    # optional: additional people mentioned as execs/owners etc.
    people: List[PersonSeedOut] = Field(default_factory=list) 

class ProductSeedOut(BaseModel):
    entity_key: str  # product:...
    canonical_name: str
    description: Optional[str] = None
    product_page_url: Optional[str] = None
    price: Optional[str] = None
    currency: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    ingredient_list: List[str] = Field(default_factory=list)

class CompoundSeedOut(BaseModel):
    entity_key: str  # compound:...
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None

class ProductCompoundLink(BaseModel):
    product_entity_key: str
    compound_entity_key: str
    confidence: Optional[float] = None
    notes: Optional[str] = None

class ProductCompoundExtraction(BaseModel):
    products: List[ProductSeedOut] = Field(default_factory=list)
    compounds: List[CompoundSeedOut] = Field(default_factory=list)
    product_compound_links: List[ProductCompoundLink] = Field(default_factory=list)