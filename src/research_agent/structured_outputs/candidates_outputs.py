from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal

from research_agent.human_upgrade.structured_outputs.enums_literals import SourceType, ValidationLevel, EntityTypeHint 






class CandidateEntity(BaseModel):
    """
    A single candidate entity discovered from starter_content and/or minimal tool use.
    Keep this high-recall, low-risk: names/roles/strings + local context.
    """

    name: str = Field(..., min_length=1, description="Entity surface form as seen in the sources.")
    normalizedName: str = Field(
        ...,
        min_length=1,
        description="Lowercased, trimmed, punctuation-light normalization for matching downstream.",
    )
    typeHint: EntityTypeHint = Field(..., description="Best guess category based on local context.")
    role: Optional[str] = Field(
        default=None,
        description="Role/title if explicitly stated near the entity (e.g., CEO, founder, PI).",
    )
    contextSnippets: List[str] = Field(
        default_factory=list,
        description="1–3 short snippets where the entity is mentioned (verbatim-ish).",
        max_length=3,
    )
    mentions: int = Field(
        default=1,
        ge=1,
        description="Approximate count of mentions in the sources (best-effort).",
    )
    sourceUrls: List[str] = Field(
        default_factory=list,
        description="Up to 1–3 URLs consulted that mention/confirm this entity (optional).",
        max_length=3,
    )


class SeedExtraction(BaseModel):
    """
    Seed entity discovery for a biotech/industry query.
    High-recall candidates + hooks. Minimal tool use allowed.
    """

    query: str = Field(..., min_length=1, description="The input research query that drove extraction.")

    primary_person: Optional[CandidateEntity] = Field(
        default=None,
        description="Single most central person to the query (if clearly dominant).",
    )
    primary_organization: Optional[CandidateEntity] = Field(
        default=None,
        description="Single most central organization to the query (if clearly dominant).",
    )

    people_candidates: List[CandidateEntity] = Field(
        default_factory=list,
        description="People central to the query (executives, scientists, clinicians, KOLs).",
    )
    organization_candidates: List[CandidateEntity] = Field(
        default_factory=list,
        description="Organizations central to the query (companies, labs, universities, agencies, etc.).",
    )
    product_candidates: List[CandidateEntity] = Field(
        default_factory=list,
        description="Products/services/devices/therapeutics/diagnostics central to the query.",
    )
    compound_candidates: List[CandidateEntity] = Field(
        default_factory=list,
        description="Compounds/biomolecules/ingredients/drug names (strings only).",
    )
    technology_candidates: List[CandidateEntity] = Field(
        default_factory=list,
        description="Platforms/technologies/processes/modalities central to the query.",
    )

    evidence_claim_hooks: List[str] = Field(
        default_factory=list,
        description=(
            "5–20 short phrases suggesting evidence exists (studies/trials/results/claims/regulatory language). "
            "No URLs, no long quotes, no invented claims."
        ),
    )
    notes: Optional[str] = Field(
        default=None,
        description="Brief notes about ambiguity or what sources/tools were used.",
    )

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


class OfficialStarterSource(BaseModel):
    """
    A single 'starter' URL used to anchor downstream domain mapping (Node B).
    Keep these actionable and few: roots + 1-3 key pages that help Node B produce a DomainCatalog.
    """

    kind: OfficialSourceKind = Field(..., description="What this URL represents in the mapping workflow.")
    url: str = Field(..., min_length=1, description="Absolute URL (https://...).")
    domain: str = Field(..., min_length=1, description="Normalized domain (e.g., example.com).")
    label: str = Field(..., min_length=1, description="Short label (e.g., 'Homepage', 'Products', 'Docs', 'Team').")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence this is official and correctly matched.")
    evidence: List[str] = Field(
        default_factory=list,
        description="1–4 short signals why this is official/correct (e.g., 'matches org name', 'verified in footer').",
        max_length=4,
    )


class OfficialEntityTargets(BaseModel):
    """
    Starter sources for one extracted entity.
    These sources should be sufficient for Node B to map the domain and build a DomainCatalog.
    """

    inputName: str = Field(..., min_length=1, description="Name string from SeedExtraction.")
    normalizedName: str = Field(..., min_length=1, description="Lowercased + trimmed normalization.")
    typeHint: str = Field(..., description="EntityTypeHint as string (PERSON/ORGANIZATION/PRODUCT/TECHNOLOGY/...).")
    sources: List[OfficialStarterSource] = Field(
        default_factory=list,
        description="Small bounded set of official roots + key pages to map/extract downstream.",
    )
    notes: Optional[str] = Field(default=None, description="Optional short disambiguation or caveats.")


class OfficialStarterSources(BaseModel):
    """
    Node output: Official starter sources sufficient to drive Node B domain mapping into DomainCatalogSets.

    This object intentionally stays SMALL and ACTIONABLE:
    - Identify official domains/root URLs
    - Provide a few key pages per domain (products/docs/about/tech) so mapping is targeted
    """

    query: str = Field(..., description="The user-provided research query that initiated the run.")

    # Targets derived from SeedExtraction buckets
    people: List[OfficialEntityTargets] = Field(
        default_factory=list,
        description="People targets: official profile pages that help confirm identity & affiliation (1–3 URLs each).",
    )
    organizations: List[OfficialEntityTargets] = Field(
        default_factory=list,
        description="Organization targets: official roots + key pages for mapping (2–6 URLs each).",
    )
    products: List[OfficialEntityTargets] = Field(
        default_factory=list,
        description="Product targets: only if product has distinct official pages/domains (0–3 URLs each).",
    )
    technologies: List[OfficialEntityTargets] = Field(
        default_factory=list,
        description="Technology targets: only if there is a clear official reference/docs domain (0–3 URLs each).",
    )

    domainTargets: List[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of domains or root URLs to map in Node B (highest priority first). "
            "Prefer organization primary domains, then product/tech domains if distinct."
        ),
    )

    globalNotes: Optional[str] = Field(
        default=None,
        description="Short notes about tool usage, uncertainty, or prioritization decisions.",
    )


class DomainCatalog(BaseModel):
    """
    Node output: mapping + enumeration results for one official domain/subdomain.

    This is the breadth step: collect URLs that can later seed:
      - product enumeration
      - leadership enumeration
      - help/KB mining
      - case study harvesting
      - policies/docs/manuals
    """

    # --- selection metadata (NEW) ---
    priority: int = Field(
        default=99,
        ge=1,
        le=99,
        description="Selection priority within the run. 1 = highest priority domain catalog."
    )
    targetEntityKey: Optional[str] = Field(
        default=None,
        description=(
            "Optional: what this catalog primarily supports, e.g. "
            "'ORG:<name>', 'PRODUCT:<name>', 'TECH:<name>', 'PERSON:<name>'."
        )
    )

    # --- identity / provenance ---
    baseDomain: str = Field(..., description="Normalized domain, e.g. 'example.com' or 'help.example.com'")
    mappedFromUrl: Optional[str] = Field(
        default=None,
        description="The root URL actually mapped (may be https://example.com or a shop/help subpath).",
    )
    sourceDomainRole: Optional[str] = Field(
        default=None,
        description="Optional: 'primary', 'shop', 'help', 'blog', 'docs', 'other'.",
    )

    mappedUrls: List[str] = Field(
        default_factory=list,
        description="Deduped list of discovered URLs considered relevant (not necessarily all raw URLs).",
    )

    # --- core buckets (existing) ---
    productIndexUrls: List[str] = Field(default_factory=list, description="URLs likely to list product lines/collections.")
    productPageUrls: List[str] = Field(default_factory=list, description="URLs that appear to be specific products/SKUs/services.")
    platformUrls: List[str] = Field(default_factory=list, description="Legacy bucket for technology/platform/science pages.")

    homepageUrls: List[str] = Field(default_factory=list, description="Official homepage/root URLs (usually 1–2).")
    aboutUrls: List[str] = Field(default_factory=list, description="About/company/mission pages.")
    blogUrls: List[str] = Field(default_factory=list, description="Blog/news/article pages hosted on official domain.")
    leadershipUrls: List[str] = Field(default_factory=list, description="Leadership/team/executive pages.")
    helpCenterUrls: List[str] = Field(default_factory=list, description="Support/KB/help center hubs and category pages.")
    documentationUrls: List[str] = Field(default_factory=list, description="Manuals/instructions/spec sheets/PDFs/downloads.")
    labelUrls: List[str] = Field(default_factory=list, description="Labels/ingredient lists/supplement facts (often PDFs/images).")
    researchUrls: List[str] = Field(default_factory=list, description="Official science/tech/platform/mechanism pages.")
    caseStudyUrls: List[str] = Field(default_factory=list, description="Case studies/outcomes/whitepapers/evidence hubs.")
    testimonialUrls: List[str] = Field(default_factory=list, description="First-party testimonials/customer stories.")
    patentUrls: List[str] = Field(default_factory=list, description="Patent references/proprietary process disclosures.")
    landingPageUrls: List[str] = Field(default_factory=list, description="Marketing landing/campaign pages.")
    pressUrls: List[str] = Field(default_factory=list, description="Press/media/newsroom pages on official domain.")
    policyUrls: List[str] = Field(default_factory=list, description="Warranty/returns/shipping/privacy/terms pages.")
    regulatoryUrls: List[str] = Field(default_factory=list, description="Regulatory/compliance/safety warnings/notice pages.")

    notes: Optional[str] = Field(default=None, description="Coverage notes: what was mapped, escalation, gaps.")

class DomainCatalogSet(BaseModel):
    """
    A SMALL set of the most important domain catalogs for the user's query.
    Intentionally bounded to keep the pipeline cheap and focused.
    """

    query: str = Field(..., description="The research query that initiated this mapping run.")
    selectedDomainBudget: int = Field(
        default=3,
        ge=1,
        le=4,
        description="Hard guardrail: number of domains/subdomains actually mapped."
    )
    catalogs: List[DomainCatalog] = Field(
        default_factory=list,
        description="One DomainCatalog per selected domain/subdomain, ordered by priority."
    )
    globalNotes: Optional[str] = None


DomainRole = Literal["primary", "shop", "help", "docs", "blog", "other"]


class SourceCandidate(BaseModel):
    url: str
    label: str = Field(..., min_length=1)
    sourceType: "SourceType"
    rank: int = Field(..., ge=1)
    score: float = Field(..., ge=0.0, le=1.0)
    signals: List[str] = Field(default_factory=list)
    validationLevel: "ValidationLevel" = "NAME_ONLY"


class EntitySourceResult(BaseModel):
    """
    Sources for one entity candidate, plus optional canonicalization.
    """

    inputName: str = Field(..., min_length=1)
    normalizedName: str = Field(..., min_length=1)
    typeHint: "EntityTypeHint"

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





class OrgIdentityPeopleTechnologySlice(BaseModel):
    """
    Slice output for one domain: determine owning organization, key people,
    and core technology/platform signals from official pages.
    """
    baseDomain: str
    mappedFromUrl: Optional[str] = None
    sourceDomainRole: Optional[DomainRole] = None

    organization: EntitySourceResult
    people: List[EntitySourceResult] = Field(default_factory=list)
    technologies: List[EntitySourceResult] = Field(default_factory=list)

    # URLs actually used (traceability)
    homepageUrls: List[str] = Field(default_factory=list)
    aboutUrls: List[str] = Field(default_factory=list)
    leadershipUrls: List[str] = Field(default_factory=list)
    researchOrPlatformUrls: List[str] = Field(default_factory=list)
    pressUrls: List[str] = Field(default_factory=list)
    helpOrContactUrls: List[str] = Field(default_factory=list)

    notes: Optional[str] = None


class ProductsAndCompoundsSlice(BaseModel):
    """
    Output of the Offerings agent for one DomainCatalog.
    """
    baseDomain: str
    mappedFromUrl: Optional[str] = None
    sourceDomainRole: Optional[DomainRole] = None

    productIndexUrls: List[str] = Field(default_factory=list)
    productPageUrls: List[str] = Field(default_factory=list)
    helpCenterUrls: List[str] = Field(default_factory=list)
    documentationUrls: List[str] = Field(default_factory=list)
    labelUrls: List[str] = Field(default_factory=list)

    products: List[ProductWithCompounds] = Field(default_factory=list)
    businessLevelCompounds: List[EntitySourceResult] = Field(default_factory=list)

    technologiesMentioned: List[EntitySourceResult] = Field(default_factory=list)

    notes: Optional[str] = None


class ConnectedCandidatesAssemblerInput(BaseModel):
    """
    Input to the assembler for one domain slice.
    """
    query: str
    baseDomain: str
    mappedFromUrl: Optional[str] = None
    sourceDomainRole: Optional[DomainRole] = None

    # Optional anchors (do not invent)
    primary_person: Optional[EntitySourceResult] = None
    primary_organization: Optional[EntitySourceResult] = None
    primary_technology: Optional[EntitySourceResult] = None

    orgSlice: OrgIdentityPeopleTechnologySlice
    productsSlice: ProductsAndCompoundsSlice



class OrganizationIntelBundle(BaseModel):
    """
    One connected bundle for a single domain slice (usually one org domain universe).
    """
    organization: EntitySourceResult
    people: List[EntitySourceResult] = Field(default_factory=list)
    technologies: List[EntitySourceResult] = Field(default_factory=list)
    products: List[ProductWithCompounds] = Field(default_factory=list)
    businessLevelCompounds: List[EntitySourceResult] = Field(default_factory=list)

    # ✅ NEW: optional parent/brand/subsidiary context (bounded)
    relatedOrganizations: Optional[List[EntitySourceResult]] = Field(
        default=None,
        description=(
            "Optional: small set (0–3) of closely related organizations when ownership/operation context matters "
            "(e.g., parent company, operating subsidiary, brand owner). Must be supported by official sources."
        ),
    )

    # Provenance: what URLs drove this bundle (small, high-signal)
    keySourceUrls: List[str] = Field(
        default_factory=list,
        description="Deduped list of the most important URLs used across slices (max ~20 recommended).",
    )

    notes: Optional[str] = None



class ConnectedCandidates(BaseModel):
    """
    Slice-level assembled output (one per DomainCatalog slice).
    """
    query: str
    baseDomain: str
    mappedFromUrl: Optional[str] = None
    sourceDomainRole: Optional[DomainRole] = None

    primary_person: Optional[EntitySourceResult] = None
    primary_organization: Optional[EntitySourceResult] = None
    primary_technology: Optional[EntitySourceResult] = None

    intel_bundle: OrganizationIntelBundle

    notes: Optional[str] = None


class CandidateSourcesConnected(BaseModel):
    """
    Graph output: merged slice-level ConnectedCandidates objects.
    """
    connected: List[ConnectedCandidates] = Field(default_factory=list)
    globalNotes: Optional[str] = None