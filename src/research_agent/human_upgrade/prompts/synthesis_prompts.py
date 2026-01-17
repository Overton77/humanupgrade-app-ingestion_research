from datetime import datetime
from typing import Literal

DirectionType = Literal["GUEST", "BUSINESS", "PRODUCT", "COMPOUND", "PLATFORM"]


def get_guest_synthesis_prompt(objective: str, entity_names: list[str], files_content: str, required_fields: list[str]) -> str:
    """Generate synthesis prompt specifically for GUEST direction."""
    
    return f"""# Guest Profile Synthesis

You have completed research on: **{', '.join(entity_names)}**

## Research Objective
{objective}

## Research Files
{files_content}

## Required Information to Cover
{chr(10).join(f"- {field}" for field in required_fields)}

---

# Your Task

Write a comprehensive guest profile report that synthesizes ALL research findings into a cohesive narrative. This report will be used for downstream structured extraction, so organize it clearly by topic.

# Report Structure

## 1. IDENTITY & CURRENT ROLE
- Full canonical name (with credentials/titles)
- Current professional title and role
- Primary organizational affiliation
- Key professional identifiers (LinkedIn, official bio page)

## 2. PROFESSIONAL BACKGROUND
- Educational credentials and institutions
- Career trajectory (major positions held)
- Years of experience in field(s)
- Notable career milestones or transitions

## 3. EXPERTISE & SPECIALIZATION
- Primary areas of expertise (be specific)
- Research focus or clinical specialties
- Key contributions to field
- Publications, patents, or notable work

## 4. PROFESSIONAL PRESENCE
- Professional headshot availability
- Online presence and authority signals
- Speaking engagements or media appearances
- Awards, recognition, or certifications

## 5. SOURCES & VERIFICATION
List all sources used, indicating which information came from which source.

---

# Writing Guidelines

- **Be Specific**: Use exact titles, organizations, dates where available
- **Note Confidence**: If information is uncertain, say "appears to" or "reportedly"
- **Cite Inline**: Reference sources naturally in the text
- **Handle Gaps**: If required field is missing, state "No reliable information found for [field]"
- **Prioritize Recent**: Emphasize current role and recent 2 years
- **Professional Tone**: Third-person, factual, authoritative

# Quality Standards

- Multiple authoritative sources = State as fact
- Single good source = "According to [source]..."
- Inference or unclear = "Appears to..." or "Likely..."
- Conflicting information = Note both versions with sources

Write the complete guest profile report now.
"""


def get_business_synthesis_prompt(objective: str, entity_names: list[str], files_content: str, required_fields: list[str]) -> str:
    """Generate synthesis prompt specifically for BUSINESS direction."""
    
    return f"""# Business Profile Synthesis

You have completed research on: **{', '.join(entity_names)}**

## Research Objective
{objective}

## Research Files
{files_content}

## Required Information to Cover
{chr(10).join(f"- {field}" for field in required_fields)}

---

# Your Task

Write a comprehensive business profile report that synthesizes ALL research findings. Organize clearly for downstream extraction.

# Report Structure

## 1. COMPANY IDENTITY
- Official legal name
- Website and primary online presence
- Founded year and founding location
- Current headquarters location
- Company type (private, public, nonprofit, etc.)

## 2. LEADERSHIP & ORGANIZATION
- CEO name and background
- Key executive team members and roles
- Organizational structure highlights
- Board members (if public/notable)

## 3. BUSINESS MODEL & OPERATIONS
- Core business description (what they do)
- Primary products/services overview
- Target market and customer base
- Revenue model (if known)
- Business model category (B2B, B2C, D2C, etc.)

## 4. PRODUCTS & TECHNOLOGIES
- Product brand names and categories
- Platform or proprietary technology names
- Product line breadth and focus
- Manufacturing or distribution approach

## 5. MARKET POSITION & DIFFERENTIATION
- Core differentiator or unique value proposition
- Competitive positioning
- Market category or niche
- Notable achievements or market share

## 6. COMPANY TIMELINE & MILESTONES
- Founding story or origin
- Major funding rounds or financial events
- Key milestones (product launches, expansions, acquisitions)
- Recent developments (last 2 years)

## 7. FINANCIAL INFORMATION (if applicable)
- Funding status and total raised
- Public ticker symbol (if public)
- Valuation (if known)
- Financial performance indicators

## 8. SOURCES & VERIFICATION
List all sources used, organized by type (company website, news, filings, etc.)

---

# Writing Guidelines

- **Current State First**: Lead with present-day operations, then history
- **Quantify When Possible**: Employee count, funding amounts, launch dates
- **Note Changes**: Mention pivots, rebrands, or major strategic shifts
- **Cite Sources**: Reference where key facts came from
- **Handle Multiple Entities**: If researching multiple businesses, create separate sections
- **Business Language**: Professional tone, avoid marketing hype

Write the complete business profile report now.
"""


def get_products_synthesis_prompt(objective: str, entity_names: list[str], files_content: str, required_fields: list[str]) -> str:
    """Generate synthesis prompt specifically for PRODUCTS direction."""
    
    return f"""# Product Profile Synthesis

You have completed research on: **{', '.join(entity_names)}**

## Research Objective
{objective}

## Research Files
{files_content}

## Required Information to Cover
{chr(10).join(f"- {field}" for field in required_fields)}

---

# Your Task

Write a comprehensive product profile report that synthesizes ALL research findings. Be extremely precise about formulations and ingredients.

# Report Structure

## 1. PRODUCT IDENTITY
- Full product name (including brand)
- Product category and type
- Manufacturer/parent company
- Official product page URL
- Product status (active, discontinued, reformulated)

## 2. PRODUCT DESCRIPTION
- Official product description
- Intended use and benefits claimed
- Target audience or use cases
- Form factor (capsules, powder, liquid, etc.)

## 3. FORMULATION & INGREDIENTS
- Complete ingredient list (in order if available)
- Active compounds with amounts per serving
- Inactive ingredients or excipients
- Delivery mechanism or bioavailability enhancers
- Allergen warnings or certifications

## 4. PRICING & AVAILABILITY
- Current retail price (with date checked)
- Subscription pricing (if available)
- Currency
- Pack sizes or variants available
- Where to purchase (retailers, direct, etc.)
- Geographic availability

## 5. PRODUCT SPECIFICATIONS
- Serving size and servings per container
- Dosage instructions
- Storage requirements
- Shelf life or expiration
- Product images availability

## 6. PRODUCT LINE CONTEXT
- Relationship to other products (line, variants)
- Version history (if reformulated)
- Comparison to similar products in line
- Bundle or kit offerings

## 7. SOURCES & VERIFICATION
List all sources, prioritizing official product labels and manufacturer sites

---

# Writing Guidelines

- **Precision is Critical**: Exact ingredient amounts, not ranges
- **Current Information**: Note date when pricing/availability checked
- **Scientific Names**: Use both common and scientific names for compounds
- **Regulatory Compliance**: Note certifications (GMP, organic, third-party tested)
- **Handle Variants**: If multiple SKUs, be clear about which is which
- **Label Accuracy**: When citing label, note if you've seen actual label vs. website

# Special Attention

For supplement/health products:
- Distinguish active ingredients from fillers
- Note bioavailability forms (e.g., "methylcobalamin" vs "cyanocobalamin")
- Include amounts in standard units (mg, mcg, IU)

Write the complete product profile report now.
"""


def get_compounds_synthesis_prompt(objective: str, entity_names: list[str], files_content: str, required_fields: list[str]) -> str:
    """Generate synthesis prompt specifically for COMPOUNDS direction."""
    
    return f"""# Compound Profile Synthesis

You have completed research on: **{', '.join(entity_names)}**

## Research Objective
{objective}

## Research Files
{files_content}

## Required Information to Cover
{chr(10).join(f"- {field}" for field in required_fields)}

---

# Your Task

Write a comprehensive compound profile report that synthesizes ALL research findings. Scientific accuracy is paramount.

# Report Structure

## 1. COMPOUND IDENTIFICATION
- Canonical scientific name
- Common names and aliases
- CAS Registry Number (if applicable)
- Chemical formula (molecular formula)
- Chemical structure class or family

## 2. COMPOUND CLASSIFICATION
- Compound type (vitamin, mineral, amino acid, botanical, synthetic, etc.)
- Biochemical classification
- Natural vs. synthetic origin
- Regulatory status (dietary ingredient, drug, GRAS, etc.)

## 3. NATURAL SOURCES
- Primary natural sources (foods, plants, etc.)
- Typical concentrations in natural sources
- Bioavailability from natural vs. supplemental forms
- Traditional use history (if applicable)

## 4. BIOLOGICAL ROLE & MECHANISMS
- Physiological role in body
- Mechanisms of action (if well-established)
- Metabolic pathways involved
- Biomarker status (if used as a measurable marker)

## 5. SUPPLEMENTAL FORMS
- Common supplemental forms and variants
- Bioavailability differences between forms
- Typical dosage ranges in supplements
- Synergistic compounds or cofactors

## 6. RELATED PRODUCTS
- Products known to contain this compound
- Typical inclusion levels in products
- Often combined with which other compounds
- Market positioning (mainstream vs. niche)

## 7. RESEARCH & EVIDENCE
- Areas of scientific study or interest
- Notable research findings (high-level)
- Consensus vs. controversial claims
- Quality of evidence base

## 8. SOURCES & VERIFICATION
List all sources, prioritizing scientific databases and authoritative references

---

# Writing Guidelines

- **Scientific Accuracy**: Use precise terminology
- **Multiple Names**: Include all common aliases for searchability
- **Distinguish Forms**: Be clear about different molecular forms (e.g., different B12 variants)
- **Avoid Health Claims**: Describe mechanisms, don't make efficacy claims
- **Note Ambiguity**: If compound name is ambiguous (e.g., "Vitamin E" = multiple tocopherols), clarify
- **Biomarker Clarity**: If compound is measured as a health marker, explain that

Write the complete compound profile report now.
"""


def get_platforms_synthesis_prompt(objective: str, entity_names: list[str], files_content: str, required_fields: list[str]) -> str:
    """Generate synthesis prompt specifically for PLATFORMS/TECHNOLOGIES direction."""
    
    return f"""# Platform/Technology Profile Synthesis

You have completed research on: **{', '.join(entity_names)}**

## Research Objective
{objective}

## Research Files
{files_content}

## Required Information to Cover
{chr(10).join(f"- {field}" for field in required_fields)}

---

# Your Task

Write a comprehensive platform/technology profile report that synthesizes ALL research findings. Balance technical accuracy with accessibility.

# Report Structure

## 1. PLATFORM IDENTITY
- Official platform/technology name
- Owning company or organization
- Technology category or type
- Official technology page URL
- Trademark or proprietary status

## 2. PLATFORM DESCRIPTION
- What the platform/technology is (in accessible terms)
- Core technical approach or innovation
- Problem it solves or need it addresses
- Target users or applications

## 3. TECHNICAL DETAILS
- How it works (mechanism or process)
- Key technical components or steps
- Scientific or engineering principles involved
- Distinguishing technical features

## 4. OUTPUTS & CAPABILITIES
- What the platform produces or enables
- Deliverables or end products
- Performance characteristics or metrics
- Scalability or limitations

## 5. INTELLECTUAL PROPERTY
- Patent status (pending, granted, numbers if available)
- Trademark phrasing or branded terminology
- Proprietary vs. licensed components
- IP portfolio context

## 6. MARKET CONTEXT
- How it differs from competing technologies
- Market positioning or category creation
- Products or services built on this platform
- Commercial maturity (R&D, commercialized, etc.)

## 7. DOCUMENTATION & RESOURCES
- Official explainer materials (whitepapers, videos)
- Technical documentation availability
- Published validation studies
- Media coverage or expert commentary

## 8. SOURCES & VERIFICATION
List all sources, prioritizing official technical resources and patents

---

# Writing Guidelines

- **Accessible Technical Writing**: Explain clearly without oversimplifying
- **Avoid Jargon Overload**: Use technical terms but define them
- **Distinguish from Similar**: Clarify how it differs from related technologies
- **Trademark Accuracy**: Use exact trademarked phrasing when applicable
- **Commercial Reality**: Note if still in development vs. market-ready
- **Validation Level**: Indicate if claims are proven, preliminary, or theoretical

Write the complete platform/technology profile report now.
"""


def get_direction_synthesis_prompt(
    direction_type: DirectionType,
    objective: str,
    entity_names: list[str],
    files_content: str,
    required_fields: list[str]
) -> str:
    """
    Router function that returns direction-specific synthesis prompts.
    Each direction type has a tailored prompt that guides report structure.
    """
    
    if direction_type == "GUEST":
        return get_guest_synthesis_prompt(objective, entity_names, files_content, required_fields)
    elif direction_type == "BUSINESS":
        return get_business_synthesis_prompt(objective, entity_names, files_content, required_fields)
    elif direction_type == "PRODUCT":
        return get_products_synthesis_prompt(objective, entity_names, files_content, required_fields)
    elif direction_type == "COMPOUND":
        return get_compounds_synthesis_prompt(objective, entity_names, files_content, required_fields)
    elif direction_type == "PLATFORM":
        return get_platforms_synthesis_prompt(objective, entity_names, files_content, required_fields)


def get_multi_direction_synthesis_prompt(bundle_id: str, completed_directions: dict, episode_context: str) -> str:
    """
    Generate prompt for synthesizing multiple direction reports into a bundle-level summary.
    Used at the bundle level after all directions are complete.
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    directions_summary = "\n\n".join([
        f"## {dir_type}\n{content[:500]}..." if len(content) > 500 else f"## {dir_type}\n{content}"
        for dir_type, content in completed_directions.items()
    ])
    
    return f"""# Bundle-Level Research Synthesis
**Date**: {current_date}
**Bundle ID**: {bundle_id}
**Episode Context**: {episode_context}

You are creating a final bundle-level summary that connects research across multiple entity types (Guest, Business, Product, Compound, Platform).

# Completed Direction Reports
{directions_summary}

# Your Task

Create a coherent narrative that:

1. **Establishes Connections**: How do these entities relate to each other?
2. **Tells the Story**: What's the ecosystem around this guest/episode?
3. **Highlights Key Insights**: What's most notable or surprising?
4. **Notes Quality**: What's well-researched vs. gaps remaining?

# Output Format

```json
{{
  "bundle_id": "{bundle_id}",
  "research_date": "{current_date}",
  "episode_context": "...",
  
  "ecosystem_map": {{
    "guest": "Guest name and key attributes",
    "primary_affiliation": "Main business/organization",
    "products_mentioned": ["product1", "product2"],
    "key_compounds": ["compound1", "compound2"],
    "technologies": ["platform1", "platform2"]
  }},
  
  "narrative_summary": "3-5 paragraph cohesive summary of the entire ecosystem",
  
  "key_insights": [
    "Notable finding 1",
    "Notable finding 2"
  ],
  
  "connections": [
    {{
      "from": "entity_key_1",
      "to": "entity_key_2",
      "relationship": "founder|product_of|contains|uses|invented",
      "confidence": "high|medium|low"
    }}
  ],
  
  "research_quality_summary": {{
    "total_entities_researched": 0,
    "high_quality_entities": 0,
    "entities_with_gaps": [],
    "overall_completeness": 0.0-1.0
  }},
  
  "recommended_followup": [
    "What additional research would be valuable"
  ]
}}
```

Return ONLY valid JSON, no markdown fences.
"""

