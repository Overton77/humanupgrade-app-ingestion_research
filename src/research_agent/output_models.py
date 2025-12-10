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




# ============================================================================
# EXTRACTED ENTITY OUTPUT MODELS
# ============================================================================

class ProductOutput(BaseModel):
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


class CompoundOutput(BaseModel):
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


class BusinessOutput(BaseModel):
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


class PersonOutput(BaseModel):
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


class CaseStudyOutput(BaseModel):
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

    extraction_notes: Optional[str] = Field(
        default=None,
        description="Notes about the extraction process and any caveats or context"
    )


class EvidenceResearchEntities(BaseModel):
    """
    Container for all entities extracted from a single research direction.
    
    Used for single-pass structured extraction instead of tool loops.
    """
    case_studies: List[CaseStudyOutput] = Field(
        default_factory=list,
        description="Clinical evidence, studies, trials"
    )  

    compounds: List[CompoundOutput] = Field(
        default_factory=list,
        description="Bioactive compounds, supplements, molecules"
    ) 



# ============================================================================
# TRANSCRIPT & GUEST MODELS (existing)
# ============================================================================ 

class AttributionQuote(BaseModel):
    """
    A granular, research-ready attributed statement anchored to timestamps.
    """
    speaker: str = Field(
        ...,
        description="Name or role of the speaker, e.g. 'Brad Ley', 'Dave Asprey', 'Host', 'Guest'."
    )
    role: Optional[str] = Field(
        default=None,
        description="Role in the episode such as 'host', 'guest', 'co-host', or 'other', if known."
    )
    start_time: Optional[str] = Field(
        default=None,
        description="Start timestamp in HH:MM:SS format, if available (e.g., '00:00:25')."
    )
    end_time: Optional[str] = Field(
        default=None,
        description="End timestamp in HH:MM:SS format, if available."
    )
    statement: str = Field(
        ...,
        description=(
            "Short, third-person, objective paraphrase of what the speaker asserts. "
            "Authoritative and concise, suitable for research and hypothesis generation."
        )
    )
    verbatim: Optional[str] = Field(
        default=None,
        description=(
            "Optional short verbatim quote (≤ ~30 words) directly from the transcript, "
            "if a phrase is especially striking or useful to preserve."
        )
    )
    topics: Optional[List[str]] = Field(
        default=None,
        description="Optional list of 1–3 short topic tags (e.g., ['EWOT', 'inflammation', 'mitochondria'])."
    )


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
    product: List[str] = Field(
        default_factory=list,
        description="Key product, program, or offering associated with the guest in this episode, if mentioned."
    ) 

class UpdatedGuestInfoModel(BaseModel):
    """
    Enhanced information about the primary guest, derived from both the webpage summary
    and the transcript. Captures biographical, thematic, and expertise-related elements
    relevant to the episode.
    """

    name: str = Field(
        ...,
        description="Full name of the primary guest for this episode."
    )

    description: str = Field(
        ...,
        description="1–3 sentence objective bio describing who the guest is and why they are relevant to this episode."
    )

    company: Optional[str] = Field(
        default=None,
        description="Company or organization most associated with the guest in this episode."
    )

    product: List[str] = Field(
        default_factory=list,
        description="Key product, tool, program, or offering associated with the guest."
    )

    expertise_areas: Optional[List[str]] = Field(
        default=None,
        description="List of 3–8 domain expertise areas or recurring themes (e.g., 'oxygen therapy', 'mitochondrial health', 'autoimmune recovery')."
    )

    motivation_or_origin_story: Optional[str] = Field(
        default=None,
        description="A concise summary (1–3 sentences) of the guest’s origin story or personal motivation as described in the transcript."
    )

    notable_health_history: Optional[str] = Field(
        default=None,
        description="Short summary of relevant health events or medical conditions the guest discussed (e.g., autoimmune disorders, cancer, metabolic decline)."
    )

    key_contributions: Optional[List[str]] = Field(
        default=None,
        description="Specific contributions, claims, frameworks, or innovations associated with the guest as discussed in this episode."
    )


class SummaryAndAttributionOutput(BaseModel):
    """
    Output model for the summary and attribution agent.

    - `summary` is a timeline-structured, dense episode summary using <time …> markers.
    - `attribution_quotes` is a granular set of key, timestamped statements for research agents.
    """
    summary: str = Field(
        ...,
        description=(
            "A multi-block, information-dense summary of the episode. "
            "Structured by time using <time HH:MM:SS–HH:MM:SS> markers at the start "
            "of each block, written in a third-person, objective, authoritative voice."
        )
    )
    attribution_quotes: List[AttributionQuote] = Field(
        default_factory=list,
        description=(
            "Granular, high-value claims and statements with speaker attribution and timestamps, "
            "suitable for driving downstream research directions."
        )
    )  

    enhanced_guest_information: UpdatedGuestInfoModel = Field(
        ...,
        description="Enhanced information about the primary guest for this episode, if available."
    )

class TranscriptSummaryOutput(BaseModel):
    """Combined output containing both summary and guest information."""
    summary: str = Field(
        ...,
        description="A concise, episode-specific summary emphasizing human performance and longevity takeaways."
    )
    guest_information: UpdatedGuestInfoModel = Field(
        ...,
        description="Structured and enhanced information about the primary guest for this episode."
    )   

    attribution_quotes: List[AttributionQuote] = Field(
        default_factory=list,
        description=(
            "Granular, high-value statements with speaker attribution and timestamps, "
            "suitable for driving downstream research directions."
        )
    )


class EntityType(str, Enum):
    """Types of entities that can be profiled in entity intelligence research."""
    PERSON = "person"
    BUSINESS = "business"
    PRODUCT = "product"
    COMPOUND = "compound"
    OTHER = "other"


class GeneralCitation(BaseModel): 
    url: str = Field(..., description="The URL of the source")   
    title: str = Field(..., description="The title of the source")    
    description: Optional[str] = Field(None, description="The description of the source")   
    published_date: Optional[str] = Field(None, description="The published date of the source")   
    score: Optional[float] = Field(None, description="The score of the source")    

class EntityIntelSummary(BaseModel):
    """
    A lightweight checkpoint summary for entity intelligence research.
    
    Used to offload and consolidate findings about People, Businesses,
    Products, and Compounds without overwhelming context.
    """

    summary_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])

    entity_type: EntityType = Field(
        ..., description="person | business | product | compound | other"
    )

    entity_name: str = Field(
        ..., description="Primary name of the entity being profiled"
    )

    # Core 3–5 sentence synthesis about the entity
    synthesis_summary: str = Field(
        ..., description="Short synthesized summary of what is known about this entity"
    )

    # URLs used to extract the profile (2–10 URLs max)
    key_source_citations: List[GeneralCitation] = Field(
        default_factory=list,
        description="Most authoritative URLs titles and optional descriptions, scores, and published dates that informed this summary",
    )

    # Questions still unanswered (1–5 bullets)
    open_questions: List[str] = Field(
        default_factory=list,
        description="What is not yet clear and might need further investigation",
    )

    # Optional: what the website claims about efficacy, mechanisms, benefits
    # This is very helpful for spawning downstream EvidenceResearch directions.
    onsite_efficacy_claims: List[str] = Field(
        default_factory=list,
        description="Short summaries of efficacy or mechanism claims found on official sites",
    )

    # Optional: other entities discovered (brand-owner links, founders, ingredients)
    related_entities: List[str] = Field(
        default_factory=list,
        description="Names or IDs of related entities discovered while profiling",
    )


class EntitiesIntelResearchResult(BaseModel):
    direction_id: str
    extensive_summary: str 
    entity_intel_ids: List[str]
    key_findings: List[str]
    key_source_citations: Optional[List[GeneralCitation]] = None          




class ResearchDirectionType(str, Enum):
    """
    Types of research tasks that the Deep Research Agent can perform.

    - CLAIM_VALIDATION: Validate a specific claim made in the episode.
    - MECHANISM_EXPLANATION: Explain biological or mechanistic pathways.
    - RISK_BENEFIT_PROFILE: Summarize benefits vs risks for an intervention.
    - COMPARATIVE_EFFECTIVENESS: Compare an intervention vs alternatives.
    - ENTITIES_DUE_DILIGENCE: Profile people / businesses / products and
      their relationships (bios, overviews, ingredients, pricing, onsite evidence).
    """

    CLAIM_VALIDATION = "claim_validation"
    MECHANISM_EXPLANATION = "mechanism_explanation"
    RISK_BENEFIT_PROFILE = "risk_benefit_profile"
    COMPARATIVE_EFFECTIVENESS = "comparative_effectiveness"
    ENTITIES_DUE_DILIGENCE = "entities_due_diligence"


class ResearchDirection(BaseModel):
    """
    A single unit of work for the Deep Research Agent.

    This is what the parent graph routes into either the EvidenceResearchSubgraph
    or the EntityIntel/EntitiesDueDiligence subgraph.

    Examples of primary_entities:
      - ["person:dave_asprey"]
      - ["business:energybits"]
      - ["person:catharine_arnston", "product:energybits", "business:energybits"]
      - ["compound:spirulina", "compound:chlorella"]
    """

    id: str = Field(..., description="Stable ID for this research direction.")
    episode_id: str = Field(..., description="Podcast episode ID this direction comes from.")

    title: str = Field(..., description="Human-readable title for this direction.")
    research_questions: List[str] = Field(
        default_factory=list,
        description="Clear question the agent should answer for this direction."
    )

    direction_type: ResearchDirectionType = Field(
        ...,
        description="Determines which subgraph + tools to use."
    )

    # Who / what this direction is about (can be 1 or many)
    primary_entities: List[str] = Field(
        default_factory=list,
        description=(
            "Graph entity IDs this direction concerns, e.g. "
            "'person:dave_asprey', 'business:energybits', "
            "'product:energybits', 'compound:spirulina'."
        ),
    )

    # For claim-related directions, this is the central statement
    claim_text: Optional[str] = Field(
        default=None,
        description=(
            "For claim-related directions, the central claim text to be "
            "validated or explained. None for pure entities_due_diligence directions."
        ),
    )

    claimed_by: List[str] = Field(
        default_factory=list,
        description=(
            "Entity IDs (usually people/businesses) who make or strongly endorse "
            "the claim. Can be empty for pure entities_due_diligence directions."
        ),
    )

    key_outcomes_of_interest: List[str] = Field(
        default_factory=list,
        description=(
            "Endpoints or outcomes this direction should prioritize, e.g. "
            "'oxidative_stress', 'cardiometabolic_markers', 'subjective_energy'." 
            "Discovery of entities like people, businesses, products, and compounds that are relevant to the research direction."
        ),
    )

    key_mechanisms_to_examine: List[str] = Field(
        default_factory=list,
        description=(
            "Mechanistic angles to explore, e.g. 'mitochondrial_support', "
            "'SOD', 'glutathione', 'iron_metabolism'." 
            "Business processes, product features and ingredients, and other mechanisms that are relevant to the research direction."
        ),
    )

    priority: int = Field(
        default=3,
        ge=1,
        le=5,
        description="1 = highest priority, 5 = lowest. Used for scheduling / resource allocation."
    )

    max_steps: int = Field(
        default=10,
        ge=1,
        le=10,
        description=(
            "Soft cap on how many planner/execution steps the subgraph should "
            "be allowed to take for this direction. 10 is the default upper bound."
        ),
    )


class ResearchDirectionOutput(BaseModel):  
    research_directions: List[ResearchDirection] = Field(
        ...,
        description="The list of research directions to be conducted."
    )  


class TavilyCitation(BaseModel): 
    url: str = Field(..., description="The URL of the source")  
    title: str = Field(..., description="The title of the source")   
    published_date: Optional[str] = Field(None, description="The published date of the source")   
    score: Optional[float] = Field(None, description="The score of the source")    

class FirecrawlCitation(BaseModel): 
    url: str = Field(..., description="The URL of the source")  
    title: str = Field(..., description="The title of the source")    
    description: Optional[str] = Field(None, description="The description of the source")   


class TavilyResultsSummary(BaseModel):  
    summary: str = Field(..., description="An extensive  summary of the search results")   
    citations: List[TavilyCitation] = Field(..., description="The citations of the search results")   

class FirecrawlResultsSummary(BaseModel):  
    summary: str = Field(..., description="A faithful summary of the markdown representation of the content")
    citations: List[FirecrawlCitation] = Field(..., description="A summary of the markdown of the content")  
