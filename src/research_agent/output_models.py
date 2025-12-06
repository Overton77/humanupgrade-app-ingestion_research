from typing import Optional, Literal, List  
from pydantic import BaseModel, Field 
from datetime import datetime
from enum import Enum


# ============================================================================
# SOURCE ATTRIBUTION MODELS
# ============================================================================

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


class SourceAttribution(BaseModel):
    """Tracks where a piece of information came from."""
    url: str = Field(..., description="Source URL or identifier (DOI, PMID)")
    source_type: SourceType = Field(
        default=SourceType.OTHER,
        description="Type of source"
    )
    title: Optional[str] = Field(
        None, 
        description="Title of the source document/page"
    )
    retrieved_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this source was retrieved"
    )


class ExtractedEntityBase(BaseModel):
    """
    Base class with provenance for all extracted entities.
    
    All entities extracted from research include attribution to track:
    - Which research direction produced them
    - What sources support the extraction
    - Confidence level in the extraction
    """
    direction_id: str = Field(
        ..., 
        description="Research direction that produced this entity"
    )
    sources: List[SourceAttribution] = Field(
        default_factory=list, 
        description="URLs/sources that support this entity"
    )
    confidence: float = Field(
        default=0.7, 
        ge=0.0, 
        le=1.0, 
        description="Extraction confidence: 0.9+=explicit, 0.7-0.9=mentioned, 0.5-0.7=inferred"
    )
    extraction_notes: Optional[str] = Field(
        None, 
        description="Why this entity was extracted, any caveats or context"
    )


# ============================================================================
# EXTRACTED ENTITY OUTPUT MODELS
# ============================================================================

class ProductOutput(ExtractedEntityBase):
    """A product, supplement, device, or program extracted from research."""
    name: str = Field(..., description="Product name")
    description: Optional[str] = Field(None, description="Product description")
    price: Optional[float] = Field(None, description="Product price if mentioned")
    ingredients: List[str] = Field(
        default_factory=list, 
        description="List of ingredients or components"
    )
    source_url: Optional[str] = Field(
        None, 
        description="Product page URL"
    )
    business_name: Optional[str] = Field(
        None, 
        description="Name of the business that makes this product (for relationship linking)"
    )
    media_links: List[str] = Field(
        default_factory=list, 
        description="Related URLs (product page, buy links, etc.)"
    )


class CompoundOutput(ExtractedEntityBase):
    """
    A bioactive compound, supplement ingredient, or intervention.
    
    Examples: NAD+, creatine, resveratrol, methylene blue, etc.
    """
    name: str = Field(..., description="Compound name")
    description: Optional[str] = Field(None, description="What this compound is/does")
    aliases: List[str] = Field(
        default_factory=list, 
        description="Alternative names for this compound"
    )
    mechanism_of_action: Optional[str] = Field(
        None, 
        description="How this compound works (brief mechanism)"
    )
    related_product_names: List[str] = Field(
        default_factory=list, 
        description="Products that contain this compound"
    )
    media_links: List[str] = Field(
        default_factory=list, 
        description="Related URLs (research links, info pages)"
    )


class BusinessOutput(ExtractedEntityBase):
    """A company, organization, or brand extracted from research."""
    name: str = Field(..., description="Business/company name")
    description: Optional[str] = Field(None, description="What this business does")
    website: Optional[str] = Field(None, description="Company website URL")
    media_links: List[str] = Field(
        default_factory=list, 
        description="Social media, press, or other relevant URLs"
    )
    product_names: List[str] = Field(
        default_factory=list, 
        description="Names of products made by this business (for relationship linking)"
    )
    executive_names: List[str] = Field(
        default_factory=list, 
        description="Names of key people at this business (for relationship linking)"
    )


class PersonOutput(ExtractedEntityBase):
    """A person (guest, founder, researcher, executive) extracted from research."""
    name: str = Field(..., description="Person's full name")
    bio: Optional[str] = Field(None, description="Brief biography")
    role: Optional[str] = Field(
        None, 
        description="Primary role (e.g., 'CEO', 'Researcher', 'Author', 'Founder')"
    )
    affiliations: List[str] = Field(
        default_factory=list, 
        description="Business/organization names this person is affiliated with"
    )
    media_links: List[str] = Field(
        default_factory=list, 
        description="Personal website, LinkedIn, social media, etc."
    )


class CaseStudyOutput(ExtractedEntityBase):
    """
    A case study, clinical study, or research paper extracted from research.
    
    Used for evidence supporting claims about compounds, products, or interventions.
    """
    title: str = Field(..., description="Title of the case study or paper")
    summary: str = Field(..., description="Summary of findings")
    url: Optional[str] = Field(None, description="URL to the study (PubMed, DOI, etc.)")
    source_type: Literal["pubmed", "clinical_trial", "website", "news", "other"] = Field(
        default="other",
        description="Type of source for this case study"
    )
    related_compound_names: List[str] = Field(
        default_factory=list, 
        description="Compounds mentioned in this study"
    )
    related_product_names: List[str] = Field(
        default_factory=list, 
        description="Products mentioned in this study"
    )


class ResearchEntities(BaseModel):
    """
    Container for all entities extracted from a single research direction.
    
    Used for single-pass structured extraction instead of tool loops.
    """
    businesses: List[BusinessOutput] = Field(
        default_factory=list,
        description="Companies, organizations, brands"
    )
    products: List[ProductOutput] = Field(
        default_factory=list,
        description="Products, supplements, devices, programs"
    )
    people: List[PersonOutput] = Field(
        default_factory=list,
        description="Guests, founders, researchers, executives"
    )
    compounds: List[CompoundOutput] = Field(
        default_factory=list,
        description="Bioactive compounds, supplements, molecules"
    )
    case_studies: List[CaseStudyOutput] = Field(
        default_factory=list,
        description="Clinical evidence, studies, trials"
    )


# ============================================================================
# TRANSCRIPT & GUEST MODELS (existing)
# ============================================================================

class GuestInfoModel(BaseModel):
    """Structured information about the primary guest for an episode."""
    name: str = Field(
        ...,
        description="Full name of the primary guest for this episode."
    )
    description: str = Field(
        ...,
        description="1–2 sentence bio describing who the guest is and why they are relevant to this episode."
    )
    company: Optional[str] = Field(
        default=None,
        description="Company or organization most associated with the guest in this episode, if mentioned."
    )
    product: Optional[str] = Field(
        default=None,
        description="Key product, program, or offering associated with the guest in this episode, if mentioned."
    )


class SummaryOnlyOutput(BaseModel):
    """
    Output model for the summary-only agent.
    
    Used when running summary and guest extraction as separate parallel operations.
    """
    summary: str = Field(
        ...,
        description=(
            "A multi-section, information-dense summary of the episode. "
            "Uses <summary_break> markers at concept/topic boundaries for downstream splitting."
        )
    )


class TranscriptSummaryOutput(BaseModel):
    """Combined output containing both summary and guest information."""
    summary: str = Field(
        ...,
        description="A concise, episode-specific summary emphasizing human performance and longevity takeaways."
    )
    guest_information: GuestInfoModel = Field(
        ...,
        description="Structured information about the primary guest for this episode."
    )  


class DirectionResearchResult(BaseModel):
    direction_id: str
    extensive_summary: str
    key_findings: List[str]
    citations: List[str]          


class ResearchDirection(BaseModel):
    """
    A single research direction for the agent to investigate.
    
    The agent will have access to ALL tools (web search, scraping, Wikipedia, PubMed)
    and will be guided by the prompt to prioritize tools based on the 
    `include_scientific_literature` flag.
    """
    id: str = Field(..., description="Unique identifier for this research direction")
    
    topic: str = Field(
        ..., 
        description="Short, specific topic name (e.g., 'Dr. Andrew Huberman', 'EnergyBits Products', 'NAD+ Mechanisms')"
    )
    
    description: str = Field(
        ...,
        description="1-2 sentence explanation of what to investigate"
    )
    
    overview: str = Field(
        ...,
        description="Detailed outline of the research angle and scope"
    )
    
    include_scientific_literature: bool = Field(
        default=False,
        description=(
            "Whether this research direction should include biomedical/scientific literature search. "
            "Set to True when: "
            "1) Researching mechanisms, compounds, interventions, or pathways; "
            "2) Investigating products/companies that make scientific claims; "
            "3) Looking into researchers, doctors, or scientists who publish; "
            "4) Needing clinical evidence or case studies to support claims. "
            "When True, the agent will prioritize PubMed alongside web search."
        )
    )
    
    depth: Literal["shallow", "medium", "deep"] = Field(
        default="medium",
        description="How deeply to investigate: shallow (quick context), medium (multiple sources), deep (thorough investigation)"
    )
    
    priority: int = Field(
        default=1,
        description="Priority level (higher = more important). Use 1-3 for high priority."
    )
    
    max_steps: int = Field(
        default=8,
        description="Maximum number of tool calls allowed for this direction"
    )


class ResearchDirectionOutput(BaseModel):  
    research_directions: List[ResearchDirection] = Field(
        ...,
        description="The list of research directions to be conducted."
    )  
