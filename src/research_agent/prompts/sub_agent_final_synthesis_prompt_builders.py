from __future__ import annotations

from typing import Callable, Dict, List, Optional 
from research_agent.structured_outputs.research_plans_outputs import (
    AgentInstancePlanWithSources,
    AgentType,
)
from research_agent.structured_outputs.file_outputs import FileReference
from research_agent.graphs.state.agent_instance_state import WorkerAgentState

# ---------------------------
# Final Synthesis Prompt Builders (for after_agent middleware)
# ---------------------------

def build_final_synthesis_prompt_business_identity(
    objective: str,
    files_content: str,
    agent_instance_plan: AgentInstancePlanWithSources,
) -> str:
    """Build final synthesis prompt for BusinessIdentityAndLeadershipAgent."""
    produces = ", ".join(getattr(agent_instance_plan, "produces_artifacts", None) or []) or "EntityBiography, OperatingPostureSummary, HighLevelTimeline"
    
    return f"""# Final Synthesis: Organization Identity & Leadership

You are synthesizing the final report for a BusinessIdentityAndLeadershipAgent instance.

## Research Objective
{objective}

## Expected Outputs
{produces}

## Checkpoint Files Content
{files_content}

---

# Your Task

Synthesize a cohesive final report that consolidates ALL checkpoint findings into a structured narrative.

# Report Structure

## 1. ORGANIZATION IDENTITY
- Canonical organization name
- Official domains and primary website
- Headquarters location (if stated)
- Founding date and origin story
- Legal entity type (if available)

## 2. MISSION & OPERATING POSTURE
- Core mission statement or value proposition
- What they do (products/services/offerings)
- Who they serve (target audience: clinical/consumer/research)
- How they position themselves in the market
- Operating model or business approach

## 3. LEADERSHIP & STRUCTURE
- CEO/Founder name and role
- Key leadership positions and names
- Leadership page URLs or official bios
- Organizational structure (if evident)

## 4. HIGH-LEVEL TIMELINE
- Founding → major milestones
- Key announcements or pivots
- Rebrands or strategic shifts
- Recent developments (last 2 years)

## 5. SOURCES & VERIFICATION
List all sources used, prioritizing official pages and press releases.

---

# Writing Guidelines

- **Synthesize, Don't Restate**: Merge findings from multiple checkpoints into cohesive sections
- **Prioritize Official Sources**: Official pages > press > third-party
- **Be Specific**: Use exact names, dates, titles where available
- **Handle Gaps**: If information is missing, note what was attempted
- **Professional Tone**: Third-person, factual, authoritative

Write the complete final report now.
""".strip()


def build_final_synthesis_prompt_person_bio(
    objective: str,
    files_content: str,
    agent_instance_plan: AgentInstancePlanWithSources,
) -> str:
    """Build final synthesis prompt for PersonBioAndAffiliationsAgent."""
    produces = ", ".join(getattr(agent_instance_plan, "produces_artifacts", None) or []) or "PeopleProfiles, RoleResponsibilityMap, CredentialAnchors"
    
    return f"""# Final Synthesis: People Profiles & Affiliations

You are synthesizing the final report for a PersonBioAndAffiliationsAgent instance.

## Research Objective
{objective}

## Expected Outputs
{produces}

## Checkpoint Files Content
{files_content}

---

# Your Task

Synthesize a cohesive final report that consolidates ALL checkpoint findings into structured people profiles.

# Report Structure

## 1. PEOPLE PROFILES (per person)
For each person in scope:
- Full canonical name (with credentials/titles)
- Current role/title and organization
- Tenure clues or dates (if available)
- Functional responsibility

## 2. CREDENTIALS & EDUCATION
- Educational credentials (degrees, institutions)
- Licenses or certifications
- Professional qualifications

## 3. AFFILIATIONS & PRIOR WORK
- Current organizational affiliations
- Prior companies, labs, clinics, or projects
- Notable prior roles
- Advisory vs operational roles

## 4. PROFESSIONAL PRESENCE
- Official bio pages or leadership pages
- Notable publications or talks (if mentioned)
- Public-facing expert status

## 5. SOURCES & VERIFICATION
List all sources used, prioritizing official leadership pages and authoritative profiles.

---

# Writing Guidelines

- **Synthesize Per Person**: Group all information for each person together
- **Separate Current vs Historical**: Clearly distinguish current roles from past
- **No Inference**: Only record explicitly stated credentials
- **Prioritize Leadership**: CEO/founder/executive leadership first
- **Professional Tone**: Third-person, factual

Write the complete final report now.
""".strip()


def build_final_synthesis_prompt_ecosystem(
    objective: str,
    files_content: str,
    agent_instance_plan: AgentInstancePlanWithSources,
) -> str:
    """Build final synthesis prompt for EcosystemMapperAgent."""
    produces = ", ".join(getattr(agent_instance_plan, "produces_artifacts", None) or []) or "CompetitorSet, PartnerAndPlatformGraph, MarketCategoryPlacement"
    
    return f"""# Final Synthesis: Ecosystem Positioning

You are synthesizing the final report for an EcosystemMapperAgent instance.

## Research Objective
{objective}

## Expected Outputs
{produces}

## Checkpoint Files Content
{files_content}

---

# Your Task

Synthesize a cohesive final report that maps the entity's position in the ecosystem.

# Report Structure

## 1. COMPETITORS & SUBSTITUTES
- Direct competitors (3-8 organizations)
- For each: name + 1-line "why similar" + source
- Adjacent alternatives or substitutes

## 2. PARTNERS & PLATFORMS
- Named integrations or partnerships
- Distributors or resellers
- Clinical or research partners
- Platform relationships
- For each: partner name + relationship type + source

## 3. MARKET CATEGORY PLACEMENT
- 1-3 market category labels
- Justification for each category
- How entity positions within category

## 4. ECOSYSTEM ROLE
- Product manufacturer, platform/protocol originator, reseller/educator, clinic/service provider, etc.
- Primary value chain position

## 5. SOURCES & VERIFICATION
List all sources, prioritizing press releases and official partnership pages.

---

# Writing Guidelines

- **Synthesize Relationships**: Merge findings into clear competitor/partner lists
- **Evidence Per Edge**: At least one confirming snippet per competitor/partner
- **Avoid Product Specs**: Focus on relationships and categories, not detailed product analysis
- **Prefer Official Sources**: Press releases and official pages over listicles
- **Professional Tone**: Third-person, factual

Write the complete final report now.
""".strip()


def build_final_synthesis_prompt_product_spec(
    objective: str,
    files_content: str,
    agent_instance_plan: AgentInstancePlanWithSources,
) -> str:
    """Build final synthesis prompt for ProductSpecAgent."""
    produces = ", ".join(getattr(agent_instance_plan, "produces_artifacts", None) or []) or "ProductSpecs, IngredientOrMaterialLists, UsageAndWarningSnippets"
    
    return f"""# Final Synthesis: Product Specifications

You are synthesizing the final report for a ProductSpecAgent instance.

## Research Objective
{objective}

## Expected Outputs
{produces}

## Checkpoint Files Content
{files_content}

---

# Your Task

Synthesize a cohesive final report that consolidates ALL product specification findings.

# Report Structure

## 1. PRODUCT IDENTIFICATION (per product)
- Product name and variant
- Official product page URL
- Product line or category

## 2. INGREDIENTS & MATERIALS
- Complete ingredient list (in order if available)
- Active compounds with amounts per serving
- Inactive ingredients or excipients
- Allergen warnings

## 3. PRICING & PACKAGING
- Current retail price (with currency and date)
- Subscription pricing (if available)
- Pack size, servings, or unit count
- What the price corresponds to (size, quantity, subscription vs one-time)

## 4. USAGE & DIRECTIONS
- Dosage instructions
- How/when to use
- Serving size
- Storage requirements

## 5. WARNINGS & CONTRAINDICATIONS
- Official warnings
- Contraindications
- Safety information

## 6. SOURCES & VERIFICATION
List all sources, prioritizing official product detail pages and labels.

---

# Writing Guidelines

- **Synthesize Per Product**: Group all specs for each product together
- **Precision is Critical**: Exact ingredient amounts, not ranges
- **Record Pricing Precisely**: Currency, cadence, size - don't guess
- **Handle Variants**: If multiple variants, capture differences clearly
- **Professional Tone**: Third-person, factual, precise

Write the complete final report now.
""".strip()


def build_final_synthesis_prompt_case_study(
    objective: str,
    files_content: str,
    agent_instance_plan: AgentInstancePlanWithSources,
) -> str:
    """Build final synthesis prompt for CaseStudyHarvestAgent."""
    produces = ", ".join(getattr(agent_instance_plan, "produces_artifacts", None) or []) or "EvidenceArtifacts"
    
    return f"""# Final Synthesis: Evidence Artifacts

You are synthesizing the final report for a CaseStudyHarvestAgent instance.

## Research Objective
{objective}

## Expected Outputs
{produces}

## Checkpoint Files Content
{files_content}

---

# Your Task

Synthesize a cohesive final report that consolidates ALL evidence artifacts discovered.

# Report Structure

## 1. EVIDENCE ARTIFACTS (per artifact)
For each study/trial/case study/whitepaper:
- Title
- Author / institution
- Affiliation label (company-controlled vs independent vs academic/clinical registry)
- Year (or best available date)
- Type (trial, observational, case study, whitepaper, pilot, etc.)
- What it supports (product/claim/technology)
- URL(s) to primary source

## 2. AFFILIATION BREAKDOWN
- Company-controlled evidence count and summary
- Independent evidence count and summary
- Academic/clinical registry evidence count and summary

## 3. EVIDENCE COVERAGE
- What products/claims/technologies have evidence
- Gaps in evidence coverage

## 4. SOURCES & VERIFICATION
List all sources, with clear affiliation labels.

---

# Writing Guidelines

- **Synthesize Artifacts**: Merge findings into structured artifact list
- **Label Affiliation Clearly**: Distinguish company vs independent vs academic
- **Include Metadata**: Title, author, year, type, URL for each
- **Focus on Harvesting**: Your job is identification + labeling, not deep evaluation
- **Professional Tone**: Third-person, factual

Write the complete final report now.
""".strip()


def build_final_synthesis_prompt_generic(
    objective: str,
    files_content: str,
    agent_instance_plan: AgentInstancePlanWithSources,
) -> str:
    """Generic fallback synthesis prompt."""
    agent_type = str(getattr(agent_instance_plan, "agent_type", "UnknownAgent"))
    produces = ", ".join(getattr(agent_instance_plan, "produces_artifacts", None) or []) or "(unknown)"
    
    return f"""# Final Synthesis Report

You are synthesizing the final report for a {agent_type} instance.

## Research Objective
{objective}

## Expected Outputs
{produces}

## Checkpoint Files Content
{files_content}

---

# Your Task

Synthesize a cohesive final report that consolidates ALL checkpoint findings into a structured narrative.

# Writing Guidelines

- **Synthesize, Don't Restate**: Merge findings from multiple checkpoints into cohesive sections
- **Be Specific**: Use exact names, dates, facts where available
- **Handle Gaps**: If information is missing, note what was attempted
- **Professional Tone**: Third-person, factual, authoritative
- **Include Sources**: List all sources used

Write the complete final report now.
""".strip()


# ---------------------------
# Public map for final synthesis prompts
# ---------------------------

FINAL_SYNTHESIS_PROMPT_BUILDERS: Dict[str, Callable[[str, str, AgentInstancePlanWithSources], str]] = {
    "BusinessIdentityAndLeadershipAgent": build_final_synthesis_prompt_business_identity,
    "PersonBioAndAffiliationsAgent": build_final_synthesis_prompt_person_bio,
    "EcosystemMapperAgent": build_final_synthesis_prompt_ecosystem,
    "ProductSpecAgent": build_final_synthesis_prompt_product_spec,
    "CaseStudyHarvestAgent": build_final_synthesis_prompt_case_study,
}