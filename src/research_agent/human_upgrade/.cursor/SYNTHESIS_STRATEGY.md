# Final Report Synthesis Strategy

## Overview

After each ResearchDirectionSubGraph completes its research (all todos done or max steps reached), we need to synthesize the multiple research files into coherent final reports. This document explains the implemented strategy.

## The Challenge

During research, the agent creates multiple files:

- `guest_john_doe_identity.json` - basic profile info
- `guest_john_doe_credentials.json` - education and certifications
- `guest_john_doe_expertise.json` - areas of expertise

We need to consolidate these into ONE definitive report per entity while:

- Eliminating redundancy
- Resolving conflicts
- Maintaining source attribution
- Ensuring all required fields are covered

## Implemented Solution

### Level 1: Direction-Level Synthesis (Per Research Direction)

**When**: After each ResearchDirectionSubGraph completes (in `finalize_research_node`)

**Process**:

1. **Group files by entity_key**: All file_refs are grouped by their `entity_key` field
2. **Read all files**: Content from all files for each entity is read
3. **Direction-Specific LLM Synthesis**: Use direction-specific prompts to guide the LLM:
   - `get_guest_synthesis_prompt()` - Guest profile structure
   - `get_business_synthesis_prompt()` - Business profile structure
   - `get_products_synthesis_prompt()` - Product profile with precise formulations
   - `get_compounds_synthesis_prompt()` - Scientific compound profiles
   - `get_platforms_synthesis_prompt()` - Technology/platform descriptions
4. **Output**: Narrative report with metadata header:

```markdown
---
RESEARCH REPORT METADATA
Direction: GUEST
Bundle ID: ep_123_john_doe
Research Date: 2026-01-16 14:30:00
Objective: Create comprehensive guest profile for Dr. John Doe
Entities Researched: john_doe_phd
Files Synthesized: 5
Required Fields: canonicalName, currentRole, expertise, ...
Research Quality:
  - Steps Taken: 18
  - LLM Calls: 12
  - Tool Calls: 22
  - Total Sources: 8
  - Todos Completed: 5/5
---

# Guest Profile Synthesis

## 1. IDENTITY & CURRENT ROLE

Dr. John Doe is a neuroscientist and Professor of Cognitive Science at...
[Structured narrative covering all required fields]

## 2. PROFESSIONAL BACKGROUND

...

[etc.]

## 8. SOURCES & VERIFICATION

- https://stanford.edu/faculty/johndoe - Official bio
- https://pubmed.ncbi.nlm.nih.gov/... - Publications
  ...
```

5. **Save**: Final report saved as `final_report_{direction}_{bundle_id}.md`

### Why Narrative Reports Instead of JSON?

**Benefits**:

- ✅ **Human Readable**: Can be reviewed directly
- ✅ **LLM-Friendly for Downstream**: Easy to parse with structured output on next step
- ✅ **Flexible**: Can include nuance, caveats, confidence levels naturally
- ✅ **Extensible**: Easy to add sections without breaking schema
- ✅ **Quality**: LLMs write better narratives than complex nested JSON
- ✅ **Metadata Separation**: Structured metadata in header, narrative in body

### Level 2: Bundle-Level Synthesis (Optional Future Enhancement)

**When**: After ALL directions in a bundle complete (in `finalize_bundle_research_node`)

**Process**:

1. Collect all final reports from all directions (GUEST, BUSINESS, PRODUCT, etc.)
2. Use `get_multi_direction_synthesis_prompt()` to create an ecosystem view
3. Output: ONE bundle summary showing entity relationships and narrative

```json
{
  "bundle_id": "ep_123_john_doe",
  "ecosystem_map": {
    "guest": "Dr. John Doe, Neuroscientist",
    "primary_affiliation": "NeuroTech Institute",
    "products_mentioned": ["BrainBoost", "CogniCare"],
    "key_compounds": ["resveratrol", "NAD+"]
  },
  "narrative_summary": "3-5 paragraph story",
  "connections": [
    {
      "from": "john_doe",
      "to": "neurotech_institute",
      "relationship": "founder"
    }
  ]
}
```

## Why This Approach?

### ✅ Advantages

1. **Information Preservation**: All sources and findings retained
2. **Quality Assessment**: Explicit confidence levels and completeness scores
3. **Conflict Resolution**: LLM can note when sources disagree
4. **Structured Output**: Consistent JSON schema for downstream processing
5. **Scalability**: Works for 1 entity or 10+ entities per direction

### 🆚 Alternative Approaches Considered

#### Option A: Let Agent Synthesize During Research

- ❌ Burdens agent with synthesis while researching
- ❌ May lose intermediate findings
- ✅ Fewer total LLM calls

#### Option B: No Synthesis, Just Aggregate Files

- ❌ Duplicate information across files
- ❌ No conflict resolution
- ❌ Harder for downstream systems to consume
- ✅ Simpler implementation

#### Option C: Use create_agent with File Tools

- ✅ Agent could interactively read/write files
- ❌ Adds complexity and unpredictability
- ❌ Harder to control output format
- ❌ More LLM calls

**Selected**: Our implemented approach (LLM synthesis with structured prompt) because it provides the best balance of quality, control, and efficiency.

## File Organization Pattern

```
agent_files/
├── bundle_ep_123_john_doe/
│   ├── guest_john_doe_identity.json          # Individual research files
│   ├── guest_john_doe_credentials.json
│   ├── guest_john_doe_expertise.json
│   ├── final_report_guest_ep_123.md          # ← Synthesized narrative report
│   ├── business_neurotech_overview.json
│   ├── business_neurotech_products.json
│   ├── final_report_business_ep_123.md       # ← Synthesized narrative report
│   └── bundle_summary_ep_123.md              # ← Optional bundle synthesis
```

### File Types

- **Individual research files** (`.json`): Raw findings from each todo
- **Final reports** (`.md`): Synthesized narrative reports with metadata
- **Bundle summaries** (`.md`): Cross-direction ecosystem narratives

## Implementation Details

### Synthesis Prompt Design

**Direction-Specific Prompts**: Each entity type has a tailored synthesis prompt:

**GUEST Synthesis** (`get_guest_synthesis_prompt`):

- Organized around: Identity, Background, Expertise, Professional Presence
- Emphasizes current role and recent professional trajectory
- Third-person, factual, authoritative tone
- Inline citation of sources

**BUSINESS Synthesis** (`get_business_synthesis_prompt`):

- Organized around: Identity, Leadership, Business Model, Products, Market Position, Timeline
- Current state emphasized over history
- Quantifiable metrics prioritized (funding, employees, dates)
- Professional business language

**PRODUCT Synthesis** (`get_products_synthesis_prompt`):

- Organized around: Identity, Description, Formulation, Pricing, Specifications
- **Critical precision on ingredients and amounts**
- Current pricing with date noted
- Scientific names for compounds

**COMPOUND Synthesis** (`get_compounds_synthesis_prompt`):

- Organized around: Identification, Classification, Natural Sources, Mechanisms, Forms
- Scientific accuracy paramount
- Distinguishes between molecular forms
- Avoids health claims, describes mechanisms

**PLATFORM Synthesis** (`get_platforms_synthesis_prompt`):

- Organized around: Identity, Description, Technical Details, Outputs, IP, Market Context
- Balance technical accuracy with accessibility
- Trademark phrasing exactness
- Differentiation from similar technologies

All prompts include:

- Full content of all research files
- Research objective restatement
- List of required fields
- Quality standards and confidence levels
- Source attribution guidelines

### Error Handling

- Missing files: Log warning, skip that file
- Read errors: Log error, continue with available files
- No files created: Skip synthesis, log warning
- LLM synthesis failure: Log error, still return partial state

### State Updates

The `finalize_research_node` returns:

- `research_notes`: Summary of synthesis
- `file_refs`: Adds the final report FileReference
- `llm_calls`: Incremented for synthesis call

## Future Enhancements

### 1. Multi-Entity Direction Handling

Currently, if one direction researches 5 products, we group by entity_key and could produce 5 separate final reports OR one combined report. Decision point for implementation.

### 2. Bundle-Level Synthesis

Add a node in BundleResearchSubGraph's finalize that:

- Collects all direction final reports
- Creates ecosystem narrative
- Maps entity relationships
- Generates visual graph data

### 3. Incremental Synthesis

Instead of synthesizing at the end, synthesize after every N files or N completed todos. Trade-off: more LLM calls vs. better context management.

### 4. Structured Output Validation

Add Pydantic models for final report schemas and use `response_format` to ensure valid JSON output.

## Usage Example

```python
# After ResearchDirectionSubGraph completes
direction_state = await ResearchDirectionSubGraph.ainvoke({
    "direction_type": "GUEST",
    "bundle_id": "ep_123_john_doe",
    "plan": guest_plan,
    # ... other fields
})

# The finalize_research_node automatically:
# 1. Groups file_refs by entity
# 2. Reads all files
# 3. Synthesizes into final report
# 4. Saves final_report_guest_ep_123.json

final_report_ref = direction_state["file_refs"][-1]  # Last file_ref is synthesis
print(f"Final report: {final_report_ref.file_path}")
```

## Testing Considerations

- Test with 0 files (should skip synthesis gracefully)
- Test with 1 file (should still synthesize for consistency)
- Test with 10+ files (should handle large context)
- Test with conflicting information in files
- Test with missing required fields
- Test entity grouping (multiple entities in one direction)

## Performance Characteristics

- **LLM Calls**: +1 per direction for synthesis
- **Context Size**: Proportional to number and size of research files
- **Time**: ~5-15 seconds for synthesis (depending on file count)
- **Cost**: ~$0.01-0.05 per synthesis (with GPT-4/5)

## Monitoring & Observability

Log entries to track:

- Number of files per entity
- Synthesis prompt size (tokens)
- Synthesis LLM call duration
- Final report size
- Completeness scores

---

**Status**: ✅ Implemented in `entity_research_graphs.py::finalize_research_node`
**Last Updated**: 2026-01-16
