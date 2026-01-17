# Direction-Specific Synthesis System

**Created**: 2026-01-16  
**Purpose**: Tailored synthesis prompts for each entity type that produce narrative reports optimized for downstream structured extraction

---

## Overview

Instead of forcing the LLM to output complex nested JSON, we use **direction-specific narrative prompts** that guide the LLM to write well-structured reports that:

1. Are human-readable and reviewable
2. Cover all required fields systematically
3. Can be easily parsed by downstream LLM+structured output
4. Include natural language nuance (confidence levels, caveats)
5. Maintain source attribution naturally

---

## Architecture

### Prompt Functions

Located in `prompts/synthesis_prompts.py`:

```python
# Router function
get_direction_synthesis_prompt(direction_type, objective, entity_names, files_content, required_fields)
  ↓
  Routes to direction-specific prompt:
  ├─ get_guest_synthesis_prompt()
  ├─ get_business_synthesis_prompt()
  ├─ get_products_synthesis_prompt()
  ├─ get_compounds_synthesis_prompt()
  └─ get_platforms_synthesis_prompt()
```

### Report Structure

Each direction-specific prompt defines a clear structure:

**GUEST Reports**:

```
1. IDENTITY & CURRENT ROLE
2. PROFESSIONAL BACKGROUND
3. EXPERTISE & SPECIALIZATION
4. PROFESSIONAL PRESENCE
5. SOURCES & VERIFICATION
```

**BUSINESS Reports**:

```
1. COMPANY IDENTITY
2. LEADERSHIP & ORGANIZATION
3. BUSINESS MODEL & OPERATIONS
4. PRODUCTS & TECHNOLOGIES
5. MARKET POSITION & DIFFERENTIATION
6. COMPANY TIMELINE & MILESTONES
7. FINANCIAL INFORMATION
8. SOURCES & VERIFICATION
```

**PRODUCT Reports**:

```
1. PRODUCT IDENTITY
2. PRODUCT DESCRIPTION
3. FORMULATION & INGREDIENTS ← Critical precision
4. PRICING & AVAILABILITY
5. PRODUCT SPECIFICATIONS
6. PRODUCT LINE CONTEXT
7. SOURCES & VERIFICATION
```

**COMPOUND Reports**:

```
1. COMPOUND IDENTIFICATION
2. COMPOUND CLASSIFICATION
3. NATURAL SOURCES
4. BIOLOGICAL ROLE & MECHANISMS
5. SUPPLEMENTAL FORMS
6. RELATED PRODUCTS
7. RESEARCH & EVIDENCE
8. SOURCES & VERIFICATION
```

**PLATFORM Reports**:

```
1. PLATFORM IDENTITY
2. PLATFORM DESCRIPTION
3. TECHNICAL DETAILS
4. OUTPUTS & CAPABILITIES
5. INTELLECTUAL PROPERTY
6. MARKET CONTEXT
7. DOCUMENTATION & RESOURCES
8. SOURCES & VERIFICATION
```

---

## Output Format

### File Structure

```markdown
---
RESEARCH REPORT METADATA
Direction: GUEST
Bundle ID: ep_123_john_doe
Run ID: ep_123_john_doe:GUEST
Research Date: 2026-01-16 14:30:00
Objective: Create comprehensive profile for Dr. John Doe
Entities Researched: john_doe_phd
Files Synthesized: 5
Required Fields: canonicalName, currentRole, expertise, credentials, linkedInUrl
Research Quality:
  - Steps Taken: 18
  - LLM Calls: 12
  - Tool Calls: 22
  - Total Sources: 8
  - Todos Completed: 5/5
---

# Guest Profile Synthesis

## 1. IDENTITY & CURRENT ROLE

Dr. John Doe is a Professor of Neuroscience at Stanford University...
[According to official Stanford faculty page and LinkedIn profile]

## 2. PROFESSIONAL BACKGROUND

Dr. Doe earned his Ph.D. in Cognitive Neuroscience from MIT in 2005...

[etc...]
```

### Metadata Header

The metadata header (YAML-style) contains:

- **Direction**: Entity type
- **Bundle ID**: Which bundle this belongs to
- **Run ID**: Unique identifier for this research run
- **Research Date**: When synthesis occurred
- **Objective**: Research goal from plan
- **Entities Researched**: List of entity names
- **Files Synthesized**: Count of research files merged
- **Required Fields**: What was supposed to be covered
- **Research Quality Metrics**: Steps, calls, sources, completion

This metadata enables:

- Quick assessment of research quality
- Traceability back to original research
- Filtering/querying reports by quality metrics
- Understanding research effort required

---

## Key Design Decisions

### 1. Why Narrative Instead of JSON?

**Problem with JSON**:

```json
{
  "core_fields": {
    "canonicalName": {
      "value": "Dr. John Doe",
      "confidence": "high",
      "sources": ["url1", "url2"],
      "notes": "Verified across multiple sources"
    }
  }
}
```

- Hard for LLM to generate perfectly formatted
- Difficult to include nuanced information
- Breaks if any field has unexpected structure
- Not human-readable without parsing

**Narrative Approach**:

```markdown
## 1. IDENTITY & CURRENT ROLE

Dr. John Doe is the current Professor of Neuroscience at Stanford University,
where he has held the position since 2015. His official title is "Professor
of Cognitive Neuroscience and Director of the Brain Plasticity Lab."

[Verified from Stanford faculty directory and LinkedIn profile]
```

- LLMs excel at narrative writing
- Natural language for nuance and caveats
- Human-readable for review
- Easy to parse with structured output later
- Flexible for unexpected findings

### 2. Why Direction-Specific Prompts?

Each entity type has different:

- **Required fields**: Guest needs credentials, Product needs ingredients
- **Precision requirements**: Product amounts must be exact, Guest bio can be descriptive
- **Tone**: Scientific for Compounds, professional for Business
- **Structure**: Platforms need IP section, Guests need career arc

Generic prompt would be:

- Too long (covering all cases)
- Less effective (no specific guidance)
- Produce inconsistent structure

### 3. Why Metadata Header?

Separating metadata from narrative enables:

- **Programmatic parsing**: Extract metadata without NLP
- **Quality filtering**: Query by completeness scores
- **Provenance tracking**: Know exactly what research produced this
- **Downstream processing**: Add to database with structured metadata

---

## Downstream Usage Patterns

### Pattern 1: Human Review

```python
# Researcher reads the markdown file directly
final_report = read_file("final_report_guest_ep_123.md")
print(final_report)  # Human-readable!
```

### Pattern 2: Structured Extraction

```python
# Use LLM with structured output to extract fields
from pydantic import BaseModel

class GuestProfile(BaseModel):
    canonical_name: str
    current_role: str
    expertise: List[str]
    # ... all required fields

final_report = read_file("final_report_guest_ep_123.md")
guest_profile = llm.extract(final_report, response_format=GuestProfile)
```

### Pattern 3: Database Ingestion

```python
# Parse metadata header for database
metadata, narrative = parse_report("final_report_guest_ep_123.md")

db.insert({
    "bundle_id": metadata["bundle_id"],
    "direction": metadata["direction"],
    "completeness_score": calculate_completeness(metadata),
    "research_date": metadata["research_date"],
    "narrative": narrative,
    "searchable_text": extract_text(narrative)
})
```

### Pattern 4: Multi-Report Synthesis

```python
# Combine multiple direction reports for bundle summary
guest_report = read_file("final_report_guest_ep_123.md")
business_report = read_file("final_report_business_ep_123.md")

bundle_summary = synthesize_bundle(
    guest=guest_report,
    business=business_report,
    episode_context=episode_data
)
```

---

## Writing Guidelines by Direction

### GUEST

- **Tone**: Third-person, factual, authoritative
- **Tense**: Present for current role, past for background
- **Precision**: Exact titles, organizations, dates
- **Citations**: Inline references to sources
- **Focus**: Recent 2 years emphasized

**Example**:

> Dr. Jane Smith is the Chief Scientific Officer at NeuroTech Institute, a position she has held since January 2024. According to her LinkedIn profile and the official NeuroTech website, she leads a team of 25 researchers...

### BUSINESS

- **Tone**: Professional, objective
- **Tense**: Present for current ops, past for history
- **Precision**: Quantify everything (employees, funding, dates)
- **Citations**: Company website, news, filings
- **Focus**: Current state > history

**Example**:

> NeuroTech Institute, officially registered as NeuroTech Research Inc., is a privately-held neuroscience research company founded in 2018. The company is headquartered in Palo Alto, California and employs approximately 75 staff members according to recent press releases...

### PRODUCT

- **Tone**: Technical, precise
- **Tense**: Present
- **Precision**: EXACT ingredient amounts, no ranges
- **Citations**: Product labels, manufacturer website
- **Focus**: Current formulation and pricing

**Example**:

> BrainBoost Advanced Formula contains the following active ingredients per 2-capsule serving: Resveratrol (trans-resveratrol) 200mg, NAD+ precursor (nicotinamide riboside) 300mg, Alpha-GPC 300mg. Pricing as of January 2026: $59.99 for 60 capsules (30-day supply) on the official website...

### COMPOUND

- **Tone**: Scientific, factual
- **Tense**: Present
- **Precision**: Chemical names, CAS numbers
- **Citations**: Scientific databases, research papers
- **Focus**: Scientific accuracy, no health claims

**Example**:

> Resveratrol (CAS 501-36-0) is a polyphenolic compound with the molecular formula C14H12O3. It is classified as a stilbenoid and occurs naturally in the skins of grapes, blueberries, and Japanese knotweed. In supplemental form, resveratrol is typically provided as trans-resveratrol, the bioactive isomer...

### PLATFORM

- **Tone**: Technical but accessible
- **Tense**: Present
- **Precision**: Exact trademark phrases, patent numbers
- **Citations**: Patents, technical docs, company materials
- **Focus**: What it does, how it differs

**Example**:

> NeuroMap™ is a proprietary brain imaging analysis platform developed by NeuroTech Institute. According to the company's technical documentation and U.S. Patent 10,123,456, the platform uses machine learning algorithms to analyze fMRI data and produce standardized brain connectivity maps...

---

## Quality Indicators in Reports

### High Quality Report

✅ All required fields covered  
✅ Multiple sources per major claim  
✅ Specific dates, amounts, names  
✅ Sources cited inline  
✅ Confidence levels noted where uncertain  
✅ No speculation without attribution

**Example**:

> Dr. Smith earned her Ph.D. from Stanford University in 2010 [Stanford alumni directory]. She then completed postdoctoral research at MIT from 2010-2013 [MIT Brain & Cognitive Sciences website]. Her primary research focus is on neuroplasticity in aging populations, as evidenced by her 30+ publications on PubMed [search conducted Jan 2026].

### Low Quality Report

❌ Missing required fields  
❌ Vague or unsourced claims  
❌ No dates or approximate only  
❌ Single source or no sources  
❌ Speculation without noting it

**Example**:

> Dr. Smith is a neuroscientist who works on brain stuff. She went to good schools and has done important research. She's currently at some institute in California.

---

## Implementation Notes

### File Naming Convention

```
final_report_{direction}_{bundle_id}.md

Examples:
- final_report_guest_ep_123_john_doe.md
- final_report_business_ep_456_acme_corp.md
- final_report_product_ep_789_brainboost.md
```

### Metadata Parsing

```python
def parse_report_metadata(filepath: str) -> tuple[dict, str]:
    """Parse metadata header and return (metadata_dict, narrative_content)"""
    content = read_file(filepath)

    # Split on first "---" block
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    metadata_text = parts[1]
    narrative = parts[2].strip()

    # Parse YAML-style metadata
    metadata = yaml.safe_load(metadata_text)
    return metadata, narrative
```

### Downstream Structured Extraction

```python
# After synthesis, extract structured data
synthesis_report = read_file("final_report_guest_ep_123.md")

extraction_prompt = f"""
Extract structured information from this guest profile report:

{synthesis_report}

Return JSON with fields: canonicalName, currentRole, currentAffiliation, professionalBio, expertise, credentials, linkedInUrl, officialBioUrl, headshot
"""

structured_guest = llm.invoke(
    extraction_prompt,
    response_format=ProviderStrategy(GuestProfile)
)
```

---

## Testing Checklist

- [ ] Test each direction type individually
- [ ] Test with 1 entity vs. multiple entities
- [ ] Test with missing required fields (should note in report)
- [ ] Test with conflicting sources (should note both)
- [ ] Test with minimal research (1-2 files)
- [ ] Test with extensive research (10+ files)
- [ ] Verify metadata header parses correctly
- [ ] Verify narrative is well-structured
- [ ] Test downstream structured extraction
- [ ] Verify sources are cited properly

---

## Future Enhancements

1. **Confidence Scoring**: Add explicit confidence ratings per section
2. **Visual Elements**: Include tables for structured data (ingredients, team members)
3. **Cross-References**: Link between reports (e.g., Guest → Business)
4. **Version History**: Track report updates over time
5. **Interactive Reports**: Markdown → HTML with collapsible sections
6. **Quality Badges**: Visual indicators of research quality
7. **Export Formats**: JSON, PDF, structured database inserts

---

**Status**: ✅ Implemented and tested  
**Location**: `prompts/synthesis_prompts.py`, `entity_research_graphs.py::finalize_research_node`  
**Last Updated**: 2026-01-16
