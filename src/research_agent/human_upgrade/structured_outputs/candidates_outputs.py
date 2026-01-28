from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from research_agent.human_upgrade.structured_outputs.enums_literals import EntityTypeHint
from research_agent.human_upgrade.structured_outputs.enums_literals import SourceType, ValidationLevel




class CandidateEntity(BaseModel):
    """
    A single candidate entity extracted ONLY from the webpage summary (no web/tools).
    Keep this high-recall, low-risk: names/roles/strings + local context.
    """

    name: str = Field(..., min_length=1, description="Entity surface form as seen in the summary.")
    normalizedName: str = Field(
        ...,
        min_length=1,
        description="Lowercased, trimmed, punctuation-light normalization for matching downstream.",
    )
    typeHint: EntityTypeHint = Field(
        ...,
        description="Best guess category based solely on context in the summary."
    )
    role: Optional[str] = Field(
        default=None,
        description="Role/title if explicitly stated near the entity (e.g., CEO, founder).",
    )
    contextSnippets: List[str] = Field(
        default_factory=list,
        description="1–3 short snippets/sentences where the entity is mentioned (verbatim-ish).",
        max_length=3,
    )
    mentions: int = Field(
        default=1,
        ge=1,
        description="Approximate count of mentions in the summary (can be best-effort).",
    )


class SeedExtraction(BaseModel):
    """
    Output A: purely extracted candidates and hooks from webpage_summary and episode_url.
    No web calls, no validation, no new facts.
    """

    # Candidates are separated by intended downstream workflows.
    guest_candidates: List[CandidateEntity] = Field(
        default_factory=list,
        description="People likely to be the guest(s). Usually 1, can be more.",
    )
    business_candidates: List[CandidateEntity] = Field(
        default_factory=list,
        description="Organizations/brands mentioned that are central to the episode.",
    )
    product_candidates: List[CandidateEntity] = Field(
        default_factory=list,
        description="Products explicitly mentioned (e.g., supplements, devices, services).",
    )
    compound_candidates: List[CandidateEntity] = Field(
        default_factory=list,
        description="Compounds/biomolecules/ingredients mentioned as strings only.",
    )
    evidence_claim_hooks: List[str] = Field(
        default_factory=list,
        description=(
            "Short phrases that imply evidence exists (studies/trials), copied from or tightly paraphrased "
            "from the summary. No URLs, no new claims."
        ),
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional brief notes about ambiguity or extraction uncertainty (no web validation).",
    )


OfficialKind = Literal[
    "business_primary_domain",
    "business_shop_or_storefront",
    "business_products_or_catalog",
    "business_about_or_team",
    "product_official_domain",
    "product_official_page",
    "guest_official_profile",
    "third_party_disambiguation"
]

class OfficialStarterSource(BaseModel):
    """
    A single official starter source URL that Node B can map / extract.
    """
    kind: OfficialKind = Field(..., description="What this URL represents (domain root, shop, products page, etc.).")
    url: str = Field(..., min_length=1, description="Absolute URL (https://...).")
    domain: str = Field(..., min_length=1, description="Normalized domain (e.g., example.com).")
    label: str = Field(..., min_length=1, description="Short human label (e.g., 'Official homepage', 'Shop', 'Products').")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence this is official and correctly matched.")
    evidence: List[str] = Field(default_factory=list, description="1–4 short signals why this is official/correct.")

class OfficialEntityTargets(BaseModel):
    """
    Official starter sources for one entity name.
    """
    inputName: str = Field(..., min_length=1)
    normalizedName: str = Field(..., min_length=1)
    typeHint: str = Field(..., description="EntityTypeHint as string to avoid enum coupling here.")
    sources: List[OfficialStarterSource] = Field(default_factory=list)
    notes: Optional[str] = None

class OfficialStarterSources(BaseModel):
    """
    Node A output: a small set of official roots + key pages to enable Node B mapping/catalog expansion.
    """
    episodePageUrl: str = Field(...)

    # Usually 1 guest
    guests: List[OfficialEntityTargets] = Field(default_factory=list)

    # This is the main focus
    businesses: List[OfficialEntityTargets] = Field(default_factory=list)

    # Only include product targets if they appear to be brands with separate official sites/pages
    products: List[OfficialEntityTargets] = Field(default_factory=list)

    # Convenience: Node B can map these directly, in order
    domainTargets: List[str] = Field(
        default_factory=list,
        description="Ordered list of domains (or root URLs) that should be mapped in Node B."
    )

    globalNotes: Optional[str] = None


class DomainCatalog(BaseModel):
    """
    Node B output: mapping + enumeration results for one official domain.
    This is the breadth step: collect product index URLs and product page URLs.
    """

    baseDomain: str = Field(..., description="Normalized domain, e.g. 'example.com' or 'shop.example.com'")

    mappedFromUrl: Optional[str] = Field(
        default=None,
        description="The root URL actually mapped (may be https://example.com or a shop subpath).",
    )

    mappedUrls: List[str] = Field(
        default_factory=list,
        description="Deduped list of discovered URLs considered relevant (not necessarily all raw URLs).",
    )

    productIndexUrls: List[str] = Field(
        default_factory=list,
        description="URLs likely to list product lines/collections (/products, /shop, /collections, /store).",
    )

    productPageUrls: List[str] = Field(
        default_factory=list,
        description="URLs that appear to be specific products/SKUs/services (aim for completeness, deduped).",
    )

    platformUrls: List[str] = Field(
        default_factory=list,
        description="URLs for about/technology/platform/science/team/press/FAQ pages.",
    )

    notes: Optional[str] = Field(
        default=None,
        description="Coverage notes: what was mapped, whether escalation was needed, gaps, storefront quirks.",
    )


class DomainCatalogSet(BaseModel):
    episodePageUrl: str
    catalogs: List[DomainCatalog] = Field(default_factory=list)
    globalNotes: Optional[str] = None
class SourceCandidate(BaseModel):
   

    url: str
    label: str = Field(..., min_length=1)
    sourceType: SourceType
    rank: int = Field(..., ge=1)
    score: float = Field(..., ge=0.0, le=1.0)
    signals: List[str] = Field(default_factory=list)
    validationLevel: ValidationLevel = "NAME_ONLY"


class EntitySourceResult(BaseModel):
    """
    Sources for one entity candidate, plus optional canonicalization.
    """
   

    inputName: str = Field(..., min_length=1)
    normalizedName: str = Field(..., min_length=1)
    typeHint: EntityTypeHint

    canonicalName: Optional[str] = None
    canonicalConfidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    candidates: List[SourceCandidate] = Field(default_factory=list)
    notes: Optional[str] = None


class ProductWithCompounds(BaseModel):
    """
    A product and the compounds that are specifically associated with it
    (based on episode context and/or product page signals).
    """
   

    product: EntitySourceResult
    compounds: List[EntitySourceResult] = Field(default_factory=list)

    # Helps downstream when ambiguous
    compoundLinkNotes: Optional[str] = Field(
        default=None,
        description="Short note explaining why these compounds are linked to the product (or ambiguity).",
    )
    compoundLinkConfidence: Optional[float] = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="How confident we are that compounds truly belong to this product (not just the business).",
    )
    
    @field_validator('compoundLinkConfidence', mode='before')
    @classmethod
    def ensure_confidence_default(cls, v: Optional[float]) -> float:
        """Ensure compoundLinkConfidence defaults to 0.75 if None is provided."""
        if v is None:
            return 0.75
        return v


class BusinessBundle(BaseModel):
    """
    The guest's business and its connected products/platforms.
    """
    

    business: EntitySourceResult 
    products: List[ProductWithCompounds] = Field(default_factory=list)
    platforms: List[EntitySourceResult] = Field(default_factory=list)
    notes: Optional[str] = None


class ConnectedCandidates(BaseModel):
    """
    One connected bundle for a guest: guest -> business(es) -> products -> compounds, plus business platforms.
    """
   

    guest: EntitySourceResult
    businesses: List[BusinessBundle] = Field(default_factory=list)

    notes: Optional[str] = None 

    


class CandidateSourcesConnected(BaseModel):
    """
    Output A2: connected candidate sources focusing on guest + their business ecosystem.
    """
   

   
    connected: List[ConnectedCandidates] = Field(default_factory=list)

    globalNotes: Optional[str] = None
