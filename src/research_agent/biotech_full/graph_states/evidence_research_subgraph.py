from typing import Optional, Literal, List  
from pydantic import BaseModel, Field 
from datetime import datetime
from enum import Enum 
import uuid  


class EvidenceStrength(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown" 


class EvidenceItem(BaseModel):
    study_title: str
    citation: str              # e.g. "Author et al., Journal, Year"
    link: Optional[str] = None # PubMed / DOI / etc.
    population: Optional[str] = None
    design: Optional[str] = None  # RCT, cohort, animal, in vitro
    key_finding: str
    relevance_to_claim: str

class ClaimValidation(BaseModel):
    """Structured validation output for a claim."""
    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    direction_id: str
    
    claim_text: str = Field(..., description="The exact claim being validated")
    claimed_by: List[str] = Field(default_factory=list, description="Entity IDs who made the claim")
    
    verdict: Literal["supported", "partially_supported", "not_supported", "insufficient_evidence"] = Field(
        ..., 
        description="Overall validation verdict"
    )
    
    evidence_strength: EvidenceStrength = Field(
        ..., 
        description="Strength of evidence supporting the verdict"
    )
    
    supporting_evidence: List[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence that supports the claim"
    )
    
    contradicting_evidence: List[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence that contradicts the claim"
    )
    
    nuance_explanation: str = Field(
        ...,
        description="Detailed explanation of context, limitations, and nuances"
    )
    
    confidence_score: float = Field(
        ..., 
        ge=0.0, 
        le=1.0,
        description="Research confidence in this validation (0-1)"
    )
    
    relevant_populations: List[str] = Field(
        default_factory=list,
        description="Populations this claim applies to (e.g., 'healthy adults', 'elderly')"
    )
    
    key_caveats: List[str] = Field(
        default_factory=list,
        description="Important caveats and limitations"
    ) 


class MechanismPathway(BaseModel):
    """A single step or component in a biological mechanism."""
    step_number: int
    description: str
    evidence_level: EvidenceStrength
    key_molecules: List[str] = Field(default_factory=list)
    key_processes: List[str] = Field(default_factory=list)
    supporting_evidence: List[EvidenceItem] = Field(default_factory=list)


class MechanismExplanation(BaseModel):
    """Structured explanation of a biological mechanism."""
    mechanism_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    direction_id: str
    
    mechanism_name: str = Field(..., description="Name of the mechanism (e.g., 'mTOR pathway activation')")
    
    intervention: str = Field(..., description="What triggers this mechanism (compound, practice, etc.)")
    
    target_outcome: str = Field(..., description="The desired physiological outcome")
    
    pathway_steps: List[MechanismPathway] = Field(
        default_factory=list,
        description="Ordered steps of the mechanism"
    )
    
    overall_plausibility: Literal["well_established", "plausible", "speculative", "implausible"] = Field(
        ...,
        description="Scientific consensus on this mechanism"
    )
    
    evidence_strength: EvidenceStrength = Field(
        ...,
        description="Overall strength of mechanistic evidence"
    )
    
    key_research_gaps: List[str] = Field(
        default_factory=list,
        description="What remains unknown or needs more research"
    )
    
    animal_vs_human: str = Field(
        ...,
        description="Extent to which mechanism is validated in humans vs animals"
    )
    
    timeframe: Optional[str] = Field(
        None,
        description="Expected timeframe for mechanism to manifest (e.g., 'acute: minutes', 'chronic: weeks')"
    )
    
    dose_dependency: Optional[str] = Field(
        None,
        description="How the mechanism depends on dose/intensity"
    ) 

class Benefit(BaseModel):
    """A potential benefit of an intervention."""
    description: str
    magnitude: Literal["small", "moderate", "large", "unknown"]
    evidence_strength: EvidenceStrength
    timeframe: Optional[str] = None
    supporting_evidence: List[EvidenceItem] = Field(default_factory=list)
    relevant_populations: List[str] = Field(default_factory=list)


class Risk(BaseModel):
    """A potential risk or adverse effect."""
    description: str
    severity: Literal["mild", "moderate", "severe", "unknown"]
    frequency: Literal["rare", "uncommon", "common", "very_common", "unknown"]
    evidence_strength: EvidenceStrength
    supporting_evidence: List[EvidenceItem] = Field(default_factory=list)
    at_risk_populations: List[str] = Field(default_factory=list)


class RiskBenefitProfile(BaseModel):
    """Comprehensive risk-benefit analysis."""
    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    direction_id: str
    
    intervention_name: str = Field(..., description="What is being profiled")
    
    intended_use: str = Field(..., description="What this intervention is used for")
    
    benefits: List[Benefit] = Field(default_factory=list)
    
    risks: List[Risk] = Field(default_factory=list)
    
    overall_assessment: Literal["favorable", "mixed", "unfavorable", "insufficient_data"] = Field(
        ...,
        description="Overall risk-benefit verdict"
    )
    
    assessment_rationale: str = Field(
        ...,
        description="Detailed explanation of the overall assessment"
    )
    
    populations_favorable: List[str] = Field(
        default_factory=list,
        description="Populations for whom benefits likely outweigh risks"
    )
    
    populations_cautionary: List[str] = Field(
        default_factory=list,
        description="Populations who should exercise caution"
    )
    
    contraindications: List[str] = Field(
        default_factory=list,
        description="Absolute or relative contraindications"
    )
    
    monitoring_recommendations: List[str] = Field(
        default_factory=list,
        description="What to monitor if using this intervention"
    )
    
    evidence_quality_overall: EvidenceStrength 

class InterventionComparison(BaseModel):
    """Comparison of one intervention against another."""
    intervention_name: str
    
    efficacy_rating: Literal["superior", "equivalent", "inferior", "unknown"]
    efficacy_explanation: str
    
    safety_rating: Literal["safer", "equivalent", "less_safe", "unknown"]
    safety_explanation: str
    
    cost_accessibility: Literal["more_accessible", "equivalent", "less_accessible", "unknown"]
    
    supporting_evidence: List[EvidenceItem] = Field(default_factory=list)


class ComparativeAnalysis(BaseModel):
    """Structured comparison of interventions."""
    analysis_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    direction_id: str
    
    primary_intervention: str = Field(..., description="The main intervention being evaluated")
    
    comparators: List[InterventionComparison] = Field(
        default_factory=list,
        description="Alternative interventions compared against primary"
    )
    
    comparison_outcomes: List[str] = Field(
        default_factory=list,
        description="Outcomes compared (e.g., 'mortality', 'symptom relief', 'side effects')"
    )
    
    overall_ranking: List[str] = Field(
        default_factory=list,
        description="Interventions ranked by overall effectiveness (best first)"
    )
    
    ranking_rationale: str = Field(
        ...,
        description="Explanation of the ranking"
    )
    
    evidence_quality: EvidenceStrength = Field(
        ...,
        description="Quality of comparative evidence available"
    )
    
    clinical_recommendations: List[str] = Field(
        default_factory=list,
        description="Practical recommendations based on comparison"
    )
    
    research_gaps: List[str] = Field(
        default_factory=list,
        description="Head-to-head comparisons still needed"
    ) 


class AdviceSnippet(BaseModel):
    id: str
    audience: str          # "general_adult", "men_over_40", etc.
    tl_dr: str             # one-line takeaway
    nuance: str            # short explanation / caveats
    evidence_strength: EvidenceStrength
    related_entities: List[str]  # e.g. ["Spirulina", "ENERGYbits", "Longevity"]


class AdviceSnippets(BaseModel):
    advice_snippets: List[AdviceSnippet] 

class EvidenceResearchOutput(BaseModel):  
    short_answer: str      # 2–3 sentence answer
    long_answer: str       # paragraph(s) for article-level content
    evidence_strength: EvidenceStrength
    key_points: List[str]  # bullets for UI
    evidence_items: List[EvidenceItem]   


class EvidenceResearchResult(BaseModel):
    direction_id: str      # links back to ResearchDirection.id
    short_answer: str      # 2–3 sentence answer
    long_answer: str       # paragraph(s) for article-level content
    evidence_strength: EvidenceStrength
    key_points: List[str]  # bullets for UI
    advice_snippets: List[AdviceSnippet]
    evidence_items: List[EvidenceItem]        
