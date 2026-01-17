from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from enum import Enum
from research_agent.human_upgrade.structured_outputs.enums_literals import SourcePriorityType, PriorityLevel


# ============================================================================
# ENUMS: Info Needs (what a source is used for)
# ============================================================================

class GuestInfoNeed(str, Enum):
    """What information a source provides for guest research"""
    BIO = "BIO"
    ROLE_AFFILIATION = "ROLE_AFFILIATION"
    CREDENTIALS = "CREDENTIALS"
    HEADSHOT = "HEADSHOT"
    SOCIAL_LINKS = "SOCIAL_LINKS"
    EXPERTISE = "EXPERTISE"

class BusinessInfoNeed(str, Enum):
    """What information a source provides for business research"""
    OVERVIEW = "OVERVIEW"
    EXEC_TEAM = "EXEC_TEAM"
    PRODUCT_LINE = "PRODUCT_LINE"
    PLATFORM_OVERVIEW = "PLATFORM_OVERVIEW"
    TIMELINE = "TIMELINE"
    FINANCIAL_INFO = "FINANCIAL_INFO"
    DIFFERENTIATOR = "DIFFERENTIATOR"

class ProductInfoNeed(str, Enum):
    """What information a source provides for product research"""
    PRODUCT_DETAILS = "PRODUCT_DETAILS"
    PRICING = "PRICING"
    INGREDIENTS = "INGREDIENTS"
    IMAGES = "IMAGES"
    AVAILABILITY = "AVAILABILITY"

class CompoundInfoNeed(str, Enum):
    """What information a source provides for compound research"""
    IDENTIFICATION = "IDENTIFICATION"
    CLASSIFICATION = "CLASSIFICATION"
    SOURCES = "SOURCES"
    RELATED_PRODUCTS = "RELATED_PRODUCTS"

class PlatformInfoNeed(str, Enum):
    """What information a source provides for platform/technology research"""
    TECHNOLOGY_DESCRIPTION = "TECHNOLOGY_DESCRIPTION"
    OUTPUTS = "OUTPUTS"
    PATENTS = "PATENTS"
    OFFICIAL_MATERIALS = "OFFICIAL_MATERIALS"


# ============================================================================
# ENUMS: Deterministic Fields (what we extract)
# ============================================================================

class GuestFieldEnum(str, Enum):
    """Essential fields for guest profiles - powerful but focused"""
    CANONICAL_NAME = "canonicalName"
    CURRENT_ROLE = "currentRole"
    CURRENT_AFFILIATION = "currentAffiliation"
    PROFESSIONAL_BIO = "professionalBio"
    EXPERTISE = "expertise"
    CREDENTIALS = "credentials"
    LINKEDIN_URL = "linkedInUrl"
    OFFICIAL_BIO_URL = "officialBioUrl"
    HEADSHOT = "headshot"

class BusinessFieldEnum(str, Enum):
    """Essential fields for business profiles - powerful but focused"""
    LEGAL_NAME = "legalName"
    WEBSITE = "website"
    DESCRIPTION = "description"
    FOUNDED_YEAR = "foundedYear"
    HEADQUARTERS = "headquarters"
    CEO_NAME = "ceoName"
    EXECUTIVE_TEAM = "executiveTeam"
    PRODUCT_BRANDS = "productBrands"
    PLATFORM_NAMES = "platformNames"
    CORE_DIFFERENTIATOR = "coreDifferentiator"
    KEY_MILESTONES = "keyMilestones"
    FUNDING = "funding"
    PUBLIC_TICKER = "publicTicker"

class ProductFieldEnum(str, Enum):
    """Essential fields for product profiles - powerful but focused"""
    PRODUCT_NAME = "productName"
    PRODUCT_PAGE_URL = "productPageUrl"
    DESCRIPTION = "description"
    PRICE = "price"
    SUBSCRIPTION_PRICE = "subscriptionPrice"
    CURRENCY = "currency"
    INGREDIENT_LIST = "ingredientList"
    ACTIVE_COMPOUNDS = "activeCompounds"
    AMOUNTS_PER_SERVING = "amountsPerServing"
    PACK_SIZES = "packSizes"
    IMAGES = "images"
    DISCONTINUED = "discontinued"

class CompoundFieldEnum(str, Enum):
    """Essential fields for compound profiles - powerful but focused"""
    CANONICAL_NAME = "canonicalName"
    ALIASES = "aliases"
    CAS = "cas"
    MOLECULAR_FORMULA = "molecularFormula"
    COMPOUND_TYPE = "compoundType"
    IS_BIOMARKER = "isBiomarker"
    COMMON_SOURCES = "commonSources"
    RELATED_TO_PRODUCTS = "relatedToProducts"

class PlatformFieldEnum(str, Enum):
    """Essential fields for platform/technology profiles - powerful but focused"""
    PLATFORM_NAME = "platformName"
    DESCRIPTION = "description"
    TECHNOLOGY_PAGE_URL = "technologyPageUrl"
    TRADEMARK_PHRASING = "trademarkPhrasing"
    WHAT_IT_PRODUCES = "whatItProduces"
    PATENTS = "patents"
    OFFICIAL_EXPLAINER = "officialExplainer"


# ============================================================================
# SHARED: Starter Source Model
# ============================================================================



class StarterSource(BaseModel):
    """
    A candidate source suggested by the LLM to start research.
    These are good starting points but don't confine the research.
    """
    url: str = Field(..., description="URL of the source")
    sourceType: SourcePriorityType = Field(..., description="Type/priority of source")
    usedFor: List[str] = Field(
        ..., 
        description="What info needs this source addresses (e.g., ['BIO', 'CREDENTIALS'])"
    )
    reason: str = Field(..., description="Why this source is valuable")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in source quality (0-1)")


# ============================================================================
# OUTPUT A: LLM Layer (Small, Opinionated Decisions)
# ============================================================================

class GuestDirectionOutputA(BaseModel):
    """
    LLM output for guest research: minimal, opinionated decisions.
    The LLM chooses the objective and suggests starter sources.
    """
    guestCanonicalName: str = Field(..., description="Canonical name of the guest")
    objective: str = Field(
        ...,
        description="What we're trying to accomplish for this guest"
    )
    starterSources: List[StarterSource] = Field(
        default_factory=list,
        description="Ranked starter sources to begin research (not exhaustive)"
    )
    scopeNotes: Optional[str] = Field(
        default=None,
        description="Notes about scope, focus areas, or research approach"
    )
    riskFlags: List[str] = Field(
        default_factory=list,
        description="Potential issues or things to watch out for"
    )


class BusinessDirectionOutputA(BaseModel):
    """
    LLM output for business research: minimal, opinionated decisions.
    Can handle multiple businesses in one direction.
    """
    businessNames: List[str] = Field(
        ..., 
        min_length=1,
        description="List of business canonical names to research"
    )
    objective: str = Field(
        ...,
        description="What we're trying to accomplish for these businesses"
    )
    starterSources: List[StarterSource] = Field(
        default_factory=list,
        description="Ranked starter sources to begin research (not exhaustive)"
    )
    scopeNotes: Optional[str] = Field(
        default=None,
        description="Notes about scope, focus areas, or research approach"
    )
    riskFlags: List[str] = Field(
        default_factory=list,
        description="Potential issues or things to watch out for"
    )


class ProductsDirectionOutputA(BaseModel):
    """
    LLM output for product research: minimal, opinionated decisions.
    Handles multiple products in one direction.
    """
    productNames: List[str] = Field(
        ...,
        min_length=1,
        description="List of product canonical names to research"
    )
    objective: str = Field(
        ...,
        description="What we're trying to accomplish for these products"
    )
    starterSources: List[StarterSource] = Field(
        default_factory=list,
        description="Ranked starter sources to begin research (not exhaustive)"
    )
    scopeNotes: Optional[str] = Field(
        default=None,
        description="Notes about scope, focus areas, or research approach"
    )
    riskFlags: List[str] = Field(
        default_factory=list,
        description="Potential issues or things to watch out for"
    )


class CompoundsDirectionOutputA(BaseModel):
    """
    LLM output for compound research: minimal, opinionated decisions.
    Handles multiple compounds in one direction.
    """
    compoundNames: List[str] = Field(
        ...,
        min_length=1,
        description="List of compound canonical names to research"
    )
    objective: str = Field(
        ...,
        description="What we're trying to accomplish for these compounds"
    )
    starterSources: List[StarterSource] = Field(
        default_factory=list,
        description="Ranked starter sources to begin research (not exhaustive)"
    )
    scopeNotes: Optional[str] = Field(
        default=None,
        description="Notes about scope, focus areas, or research approach"
    )
    riskFlags: List[str] = Field(
        default_factory=list,
        description="Potential issues or things to watch out for"
    )


class PlatformsDirectionOutputA(BaseModel):
    """
    LLM output for platform/technology research: minimal, opinionated decisions.
    Handles multiple platforms in one direction.
    """
    platformNames: List[str] = Field(
        ...,
        min_length=1,
        description="List of platform canonical names to research"
    )
    objective: str = Field(
        ...,
        description="What we're trying to accomplish for these platforms"
    )
    starterSources: List[StarterSource] = Field(
        default_factory=list,
        description="Ranked starter sources to begin research (not exhaustive)"
    )
    scopeNotes: Optional[str] = Field(
        default=None,
        description="Notes about scope, focus areas, or research approach"
    )
    riskFlags: List[str] = Field(
        default_factory=list,
        description="Potential issues or things to watch out for"
    )


# ============================================================================
# OUTPUT FINAL: Deterministic Layer (Complete Plan)
# ============================================================================

class GuestDirectionOutputFinal(BaseModel):
    """
    Complete guest research plan: LLM output + deterministic field requirements.
    This is what the research agent actually executes.
    """
    chosenDirection: GuestDirectionOutputA = Field(
        ...,
        description="The LLM's chosen direction and starter sources"
    )
    requiredFields: List[GuestFieldEnum] = Field(
        ...,
        description="Deterministic: must-have fields for quality research"
    )


class BusinessDirectionOutputFinal(BaseModel):
    """
    Complete business research plan: LLM output + deterministic field requirements.
    This is what the research agent actually executes.
    """
    chosenDirection: BusinessDirectionOutputA = Field(
        ...,
        description="The LLM's chosen direction and starter sources"
    )
    requiredFields: List[BusinessFieldEnum] = Field(
        ...,
        description="Deterministic: must-have fields for quality research"
    )


class ProductsDirectionOutputFinal(BaseModel):
    """
    Complete product research plan: LLM output + deterministic field requirements.
    This is what the research agent actually executes.
    """
    chosenDirection: ProductsDirectionOutputA = Field(
        ...,
        description="The LLM's chosen direction and starter sources"
    )
    requiredFields: List[ProductFieldEnum] = Field(
        ...,
        description="Deterministic: must-have fields for quality research"
    )


class CompoundsDirectionOutputFinal(BaseModel):
    """
    Complete compound research plan: LLM output + deterministic field requirements.
    This is what the research agent actually executes.
    """
    chosenDirection: CompoundsDirectionOutputA = Field(
        ...,
        description="The LLM's chosen direction and starter sources"
    )
    requiredFields: List[CompoundFieldEnum] = Field(
        ...,
        description="Deterministic: must-have fields for quality research"
    )


class PlatformsDirectionOutputFinal(BaseModel):
    """
    Complete platform research plan: LLM output + deterministic field requirements.
    This is what the research agent actually executes.
    """
    chosenDirection: PlatformsDirectionOutputA = Field(
        ...,
        description="The LLM's chosen direction and starter sources"
    )
    requiredFields: List[PlatformFieldEnum] = Field(
        ...,
        description="Deterministic: must-have fields for quality research"
    )


# ============================================================================
# BUNDLE LEVEL: Both Layers
# ============================================================================

class EntityBundleDirectionsA(BaseModel):
    """
    LLM output for entire bundle (guest + their ecosystem).
    Contains 1-5 OutputA directions.
    
    This is what the LLM directly outputs - one per connected bundle.
    """
    bundleId: str = Field(
        ...,
        description="Unique identifier for this bundle (typically guest + episode)"
    )
    guestDirection:GuestDirectionOutputA = Field(
        default=None,
        description="Guest research direction"
    )
    businessDirection: Optional[BusinessDirectionOutputA] = Field(
        default=None,
        description="Business research direction (if applicable)"
    )
    productsDirection: Optional[ProductsDirectionOutputA] = Field(
        default=None,
        description="Products research direction (if applicable)"
    )
    compoundsDirection: Optional[CompoundsDirectionOutputA] = Field(
        default=None,
        description="Compounds research direction (if applicable)"
    )
    platformsDirection: Optional[PlatformsDirectionOutputA] = Field(
        default=None,
        description="Platforms research direction (if applicable)"
    )
    notes: Optional[str] = None



class EntityBundleDirectionsFinal(BaseModel):
    """
    Complete research plan for entire bundle (guest + their ecosystem).
    This is what the research agent actually executes.
    Contains 1-5 OutputFinal directions with deterministic field assignments.
    """
    bundleId: str = Field(
        ...,
        description="Unique identifier for this bundle (typically guest + episode)"
    )
    guestDirection: GuestDirectionOutputFinal = Field(
        ...,
        description="Complete guest research plan"
    )
    businessDirection: Optional[BusinessDirectionOutputFinal] = Field(
        default=None,
        description="Complete business research plan (if applicable)"
    )
    productsDirection: Optional[ProductsDirectionOutputFinal] = Field(
        default=None,
        description="Complete products research plan (if applicable)"
    )
    compoundsDirection: Optional[CompoundsDirectionOutputFinal] = Field(
        default=None,
        description="Complete compounds research plan (if applicable)"
    )
    platformsDirection: Optional[PlatformsDirectionOutputFinal] = Field(
        default=None,
        description="Complete platforms research plan (if applicable)"
    )
    notes: Optional[str] = None



class EntityBundlesListOutputA(BaseModel): 
    """ 
    LLM output: List of distinct Entity Research Direction Bundles, grouped by bundleId.
    Each bundle represents a guest + their ecosystem (business, products, compounds, platforms).
    
    This is what the LLM directly outputs.
    """ 

    bundles: List[EntityBundleDirectionsA]
    notes: Optional[str] = None


class EntityBundlesListFinal(BaseModel): 
    """ 
    Complete list of Entity Research Direction Bundles with deterministic field requirements.
    Each bundle contains the complete research plan ready for execution.
    
    This is what gets executed by the research agent.
    """  

    bundles: List[EntityBundleDirectionsFinal]
    notes: Optional[str] = None

# ============================================================================
# COMPILER FUNCTIONS: OutputA → OutputFinal (Deterministic Field Assignment)
# ============================================================================

def compile_guest_direction(direction_a: GuestDirectionOutputA) -> GuestDirectionOutputFinal:
    """
    Compile guest OutputA to OutputFinal with deterministic required fields.
    
    Core fields: Essential 6 fields for quality guest profiles.
    Optional fields (like headshot, multiple URLs) can be discovered opportunistically.
    """
    required_fields = [
        GuestFieldEnum.CANONICAL_NAME,
        GuestFieldEnum.CURRENT_ROLE,
        GuestFieldEnum.CURRENT_AFFILIATION,
        GuestFieldEnum.PROFESSIONAL_BIO,
        GuestFieldEnum.EXPERTISE,
        GuestFieldEnum.CREDENTIALS,
    ]
    
    # Conditionally add LINKEDIN_URL if objective mentions social/professional links
    objective_lower = direction_a.objective.lower()
    if any(term in objective_lower for term in ["linkedin", "social", "professional network", "profile"]):
        required_fields.append(GuestFieldEnum.LINKEDIN_URL)
    
    return GuestDirectionOutputFinal(
        chosenDirection=direction_a,
        requiredFields=required_fields,
    )


def compile_business_direction(direction_a: BusinessDirectionOutputA) -> BusinessDirectionOutputFinal:
    """
    Compile business OutputA to OutputFinal with deterministic required fields.
    
    Core fields: Essential 7 company info fields.
    Conditional fields based on objective and risk flags.
    """
    required_fields = [
        BusinessFieldEnum.LEGAL_NAME,
        BusinessFieldEnum.WEBSITE,
        BusinessFieldEnum.DESCRIPTION,
        BusinessFieldEnum.FOUNDED_YEAR,
        BusinessFieldEnum.HEADQUARTERS,
        BusinessFieldEnum.CEO_NAME,
        BusinessFieldEnum.CORE_DIFFERENTIATOR,
    ]
    
    objective_and_flags = (direction_a.objective + " " + " ".join(direction_a.riskFlags)).lower()
    
    # Add EXECUTIVE_TEAM if mentioned
    if any(term in objective_and_flags for term in ["team", "leadership", "executives", "founder"]):
        required_fields.append(BusinessFieldEnum.EXECUTIVE_TEAM)
    
    # Add PRODUCT_BRANDS if products are focus
    if any(term in objective_and_flags for term in ["product", "brand", "offering"]):
        required_fields.append(BusinessFieldEnum.PRODUCT_BRANDS)
    
    # Add PLATFORM_NAMES if technology is focus
    if any(term in objective_and_flags for term in ["platform", "technology", "patent", "proprietary"]):
        required_fields.append(BusinessFieldEnum.PLATFORM_NAMES)
    
    # Add KEY_MILESTONES if timeline/history is focus
    if any(term in objective_and_flags for term in ["milestone", "timeline", "history", "achievement"]):
        required_fields.append(BusinessFieldEnum.KEY_MILESTONES)
    
    # Add financial fields if public company signals exist
    if any(term in objective_and_flags for term in ["public", "traded", "exchange", "ticker", "nasdaq", "nyse", "ipo"]):
        required_fields.extend([
            BusinessFieldEnum.FUNDING,
            BusinessFieldEnum.PUBLIC_TICKER,
        ])
    elif any(term in objective_and_flags for term in ["funding", "venture", "investment", "series"]):
        required_fields.append(BusinessFieldEnum.FUNDING)
    
    return BusinessDirectionOutputFinal(
        chosenDirection=direction_a,
        requiredFields=required_fields,
    )


def compile_products_direction(direction_a: ProductsDirectionOutputA) -> ProductsDirectionOutputFinal:
    """
    Compile products OutputA to OutputFinal with deterministic required fields.
    
    Core fields: Product identity, formulation, basic commercial info (6 essential)
    Conditional fields based on objective for supplements vs. other products
    """
    required_fields = [
        ProductFieldEnum.PRODUCT_NAME,
        ProductFieldEnum.PRODUCT_PAGE_URL,
        ProductFieldEnum.DESCRIPTION,
        ProductFieldEnum.INGREDIENT_LIST,
        ProductFieldEnum.ACTIVE_COMPOUNDS,
        ProductFieldEnum.DISCONTINUED,
    ]
    
    objective_and_flags = (direction_a.objective + " " + " ".join(direction_a.riskFlags)).lower()
    
    # Pricing is important for most products
    if any(term in objective_and_flags for term in ["price", "pricing", "cost", "buy", "purchase", "commercial"]):
        required_fields.extend([
            ProductFieldEnum.PRICE,
            ProductFieldEnum.CURRENCY,
        ])
    
    # Images for visual products or if mentioned
    if any(term in objective_and_flags for term in ["image", "photo", "visual", "package", "label"]):
        required_fields.append(ProductFieldEnum.IMAGES)
    
    # Subscription for recurring products
    if any(term in objective_and_flags for term in ["subscription", "recurring", "monthly"]):
        required_fields.append(ProductFieldEnum.SUBSCRIPTION_PRICE)
    
    # Serving sizes for supplements/consumables
    if any(term in objective_and_flags for term in ["serving", "dosage", "amount", "supplement", "nutrition"]):
        required_fields.append(ProductFieldEnum.AMOUNTS_PER_SERVING)
    
    # Pack sizes for products with variants
    if any(term in objective_and_flags for term in ["size", "variant", "sku", "pack", "bottle"]):
        required_fields.append(ProductFieldEnum.PACK_SIZES)
    
    return ProductsDirectionOutputFinal(
        chosenDirection=direction_a,
        requiredFields=required_fields,
    )


def compile_compounds_direction(direction_a: CompoundsDirectionOutputA) -> CompoundsDirectionOutputFinal:
    """
    Compile compounds OutputA to OutputFinal with deterministic required fields.
    
    Core fields: Identification and classification
    """
    required_fields = [
        CompoundFieldEnum.CANONICAL_NAME,
        CompoundFieldEnum.ALIASES,
        CompoundFieldEnum.COMPOUND_TYPE,
        CompoundFieldEnum.COMMON_SOURCES,
        CompoundFieldEnum.RELATED_TO_PRODUCTS,
    ]
    
    # Add technical fields if objective mentions it
    objective_lower = direction_a.objective.lower()
    if any(term in objective_lower for term in ["cas", "chemical", "formula", "molecular"]):
        required_fields.extend([
            CompoundFieldEnum.CAS,
            CompoundFieldEnum.MOLECULAR_FORMULA,
        ])
    
    if any(term in objective_lower for term in ["biomarker", "marker", "pathway"]):
        required_fields.append(CompoundFieldEnum.IS_BIOMARKER)
    
    return CompoundsDirectionOutputFinal(
        chosenDirection=direction_a,
        requiredFields=required_fields,
    )


def compile_platforms_direction(direction_a: PlatformsDirectionOutputA) -> PlatformsDirectionOutputFinal:
    """
    Compile platforms OutputA to OutputFinal with deterministic required fields.
    
    Core fields: Platform identity and description
    """
    required_fields = [
        PlatformFieldEnum.PLATFORM_NAME,
        PlatformFieldEnum.DESCRIPTION,
        PlatformFieldEnum.WHAT_IT_PRODUCES,
    ]
    
    # Add technical fields based on objective
    objective_lower = direction_a.objective.lower()
    
    if any(term in objective_lower for term in ["technology", "tech page", "url"]):
        required_fields.append(PlatformFieldEnum.TECHNOLOGY_PAGE_URL)
    
    if any(term in objective_lower for term in ["trademark", "branded", "proprietary"]):
        required_fields.append(PlatformFieldEnum.TRADEMARK_PHRASING)
    
    if any(term in objective_lower for term in ["patent", "intellectual property", "ip"]):
        required_fields.append(PlatformFieldEnum.PATENTS)
    
    if any(term in objective_lower for term in ["explainer", "technical", "whitepaper"]):
        required_fields.append(PlatformFieldEnum.OFFICIAL_EXPLAINER)
    
    return PlatformsDirectionOutputFinal(
        chosenDirection=direction_a,
        requiredFields=required_fields,
    )


def compile_bundle_directions(bundle_a: EntityBundleDirectionsA) -> EntityBundleDirectionsFinal:
    """
    Compile entire bundle from OutputA to OutputFinal.
    Applies deterministic field assignment rules to each direction.
    """
    return EntityBundleDirectionsFinal(
        bundleId=bundle_a.bundleId,
        guestDirection=compile_guest_direction(bundle_a.guestDirection),
        businessDirection=compile_business_direction(bundle_a.businessDirection) if bundle_a.businessDirection else None,
        productsDirection=compile_products_direction(bundle_a.productsDirection) if bundle_a.productsDirection else None,
        compoundsDirection=compile_compounds_direction(bundle_a.compoundsDirection) if bundle_a.compoundsDirection else None,
        platformsDirection=compile_platforms_direction(bundle_a.platformsDirection) if bundle_a.platformsDirection else None,
        notes=bundle_a.notes,
    )


def compile_bundles_list(bundles_list_a: EntityBundlesListOutputA) -> EntityBundlesListFinal:
    """
    Compile entire list of bundles from OutputA to Final.
    Applies deterministic field assignment rules to each bundle's directions.
    """
    compiled_bundles = [
        compile_bundle_directions(bundle_a)
        for bundle_a in bundles_list_a.bundles
    ]
    
    return EntityBundlesListFinal(
        bundles=compiled_bundles,
        notes=bundles_list_a.notes,
    )