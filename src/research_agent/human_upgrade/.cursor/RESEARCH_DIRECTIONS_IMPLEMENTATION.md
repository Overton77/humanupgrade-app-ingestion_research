# Entity Research Directions Implementation

## Overview

This document describes the implementation of the **Entity Research Directions Generator** - a deterministic system that converts connected candidate entities into bounded, agent-executable extraction tasks.

## What We Built

### 1. Pydantic Models (`entity_fast_output_models.py`)

Created comprehensive models for research directions:

#### Core Models

- **`ResearchDirection`**: A single bounded extraction task with:

  - `entityType`: PERSON | BUSINESS | PRODUCT | COMPOUND | PLATFORM
  - `entityCanonicalName`: Canonical name of the entity
  - `priority`: HIGH | MEDIUM | LOW
  - `objective`: Clear statement of what to extract/confirm
  - `fieldsToExtract`: Database-ready field names
  - `sourcePriority`: Ordered list of source types (OFFICIAL → REGULATOR → REPUTABLE → WIKI)
  - `acceptanceCriteria`: Completion conditions
  - `kbSummarySpec`: Knowledge base document specification
  - `notes`: Optional notes about ambiguity/dependencies
  - **Note**: IDs are generated programmatically from episode data, not by the LLM

- **`KBSummarySpec`**: Specification for knowledge base summaries:
  - `targetAudience`: Who will read this (e.g., "user-facing")
  - `maxWords`: Word count limit (50-500)
  - `mustInclude`: Required elements
  - `mustAvoid`: Things to explicitly avoid

#### Entity-Specific Direction Bundles

- **`GuestDueDiligenceDirections`**: 3 required directions per guest

  1. Role & affiliation confirmation
  2. Bio extraction
  3. Canonical profile sources

- **`BusinessDueDiligenceDirections`**: 4 required directions per business

  1. Business identity & overview
  2. History & timeline
  3. Executives & key people
  4. Brand / product line map

- **`ProductResearchDirections`**: 3-4 directions per product

  1. Product canonical identity
  2. Pricing extraction
  3. Ingredients / actives extraction
  4. Variant / SKU enumeration (optional)

- **`CompoundNormalizationDirections`**: 1-2 directions per compound

  1. Compound normalization
  2. Compound vs biomarker classification (optional)

- **`PlatformResearchDirections`**: 1-2 directions per platform
  1. Platform definition & overview
  2. Technology explainer (optional)

#### Top-Level Output

- **`EntityBundleResearchDirections`**: Complete set for one connected bundle (guest → businesses → products → compounds + platforms)

- **`EntitiesResearchDirections`**: Complete specification for entire episode

  - `bundles`: List of EntityBundleResearchDirections
  - `totalDirections`: Total count across all bundles
  - `globalNotes`: Optional global notes
  - **Note**: Episode ID and URL are available in the graph state, not in this output

- **`OutputA3Envelope`**: Envelope for research directions output

### 2. Prompt (`human_upgrade_prompts.py`)

Created **`PROMPT_OUTPUT_A3_ENTITY_RESEARCH_DIRECTIONS`** - a comprehensive prompt that:

- Takes connected candidate bundles as input
- Generates deterministic research directions following fixed buckets
- Provides detailed specifications for each entity type
- Includes concrete examples and ID format conventions
- Enforces quality checks before output

#### Key Features

1. **Fixed Buckets**: Deterministic generation for each entity type
2. **Clear Objectives**: Each direction has a specific, bounded objective
3. **Source Hierarchy**: Official → Regulatory → Reputable → Wikipedia
4. **KB Specifications**: Detailed specs for user-facing knowledge base docs
5. **Quality Checks**: Pre-output verification checklist

### 3. Code Implementation (`entity_intel_fast.py`)

#### Helper Functions

- **`format_entity_source_result()`**: Format EntitySourceResult for prompt display
- **`format_connected_candidates_for_prompt()`**: Format complete connected bundles with hierarchical structure showing:
  - Guest details
  - Business(es) with sources
  - Products under each business
  - Compounds linked to products
  - Platforms under businesses
  - All source candidates with rankings

#### Graph Node

- **`research_directions_node()`**: Async node that:
  1. Validates candidate_sources input
  2. Extracts episode metadata
  3. Formats connected bundles for prompt
  4. Invokes directions_model (GPT-4.1) with structured output
  5. Logs detailed breakdown by entity type
  6. Saves artifact to disk
  7. Returns EntitiesResearchDirections in state

#### State Management

- Added `research_directions: EntitiesResearchDirections` to `EntityIntelResearchState`

#### Graph Flow

Updated graph to include research directions:

```
seed_extraction → candidate_sources → research_directions → END
```

## Research Direction Structure

### ID Generation

Research direction IDs and episode metadata are **generated programmatically** from the graph state, not by the LLM. This ensures:

- Consistent ID format across all directions
- Proper linkage to episode records in the database
- No hallucination or inconsistency in IDs

The LLM generates the research direction content (objectives, fields, criteria, etc.), while the code generates unique IDs based on:

- Episode ID from graph state (`episode._id`)
- Episode URL from graph state (`episode.episodePageUrl`)
- Entity type and canonical name
- Sequence numbers within each bundle

### Example Bundle (BioHarvest/VINIA)

For a typical episode, expect:

- **3 guest directions** (role, bio, profiles)
- **4 business directions** per business (identity, history, executives, brands)
- **3-4 product directions** per product (identity, pricing, ingredients, variants)
- **1-2 compound directions** per compound (normalization, classification)
- **1-2 platform directions** per platform (definition, explainer)

**Total: ~13-15 directions per complete bundle**

## Key Design Decisions

### 1. Deterministic Generation

Research directions are **not** generated from open-ended queries. Instead, they follow **fixed buckets** based on entity type, ensuring:

- Predictable output
- Easy QA
- Consistent coverage
- No redundancy

### 2. Agent-Executable Format

Each direction is a **bounded extraction task** with:

- Clear objective
- Specific fields to extract
- Source priority ordering
- Acceptance criteria
- KB summary spec

This makes directions ready for parallel execution by research agents.

### 3. DB-Seeding Focus

Fields specified in `fieldsToExtract` are **DB-ready** - they map directly to MongoDB schema fields, enabling direct persistence after research completion.

### 4. KB Summary Specifications

Each direction that produces user-facing content includes a `kbSummarySpec` that specifies:

- Target audience
- Word count limits
- Required elements
- Things to avoid (e.g., "medical claims validation")

This ensures consistent, high-quality knowledge base documents.

### 5. Source Hierarchy

All directions follow a consistent source priority:

1. **OFFICIAL**: Company websites, official product pages
2. **REGULATOR_OR_EXCHANGE**: FDA, SEC, stock exchanges (for public companies)
3. **REPUTABLE_SECONDARY**: LinkedIn, Crunchbase, reputable news
4. **WIKI_LAST**: Wikipedia (for disambiguation only)
5. **OTHER**: Last resort

### 6. Separation of Concerns

This phase focuses on **identity, composition, and factual extraction** only:

- ✅ Product ingredients/actives
- ✅ Compound normalization
- ✅ Business history/leadership
- ❌ Claims validation
- ❌ Mechanism research
- ❌ Efficacy conclusions

Claims/mechanisms/case studies come in the **Episode Transcript Analysis phase**.

## Output Artifacts

### JSON Files Saved

- `research_directions_<timestamp>_<episode_slug>.json`
  - Complete EntitiesResearchDirections object
  - All bundles with all directions
  - Total direction count
  - Global notes

### State Updates

The graph state is updated with:

```python
{
  "research_directions": EntitiesResearchDirections
}
```

## Next Steps

After research directions are generated, the workflow will:

1. **Split directions into parallel research jobs**

   - Group by priority (HIGH first, then MEDIUM, then LOW)
   - Run in parallel SubGraphs or separate graphs

2. **Execute research for each direction**

   - Use specified tools (tavily_search, tavily_extract, wiki, etc.)
   - Extract specified fields
   - Collect sources matching priority order
   - Generate KB summary per spec

3. **Collect structured outputs**

   - Merge all extracted fields into entity seed records
   - Create KB documents for embedding
   - Persist to MongoDB via GraphQL API
   - Embed KB docs in AWS Knowledge Base

4. **Proceed to Episode Transcript Analysis**
   - Use researched entities as context
   - Generate claims verification directions
   - Generate mechanism understanding directions
   - Generate case study identification directions
   - Compile comprehensive episode report

## Example Usage

```python
# Graph execution
final_state = await entity_intel_subgraph.ainvoke(initial_state)

# Access research directions and episode metadata
research_directions = final_state["research_directions"]
episode = final_state["episode"]
episode_id = str(episode["_id"])
episode_url = episode["episodePageUrl"]

print(f"Episode: {episode_url}")
print(f"Total directions: {research_directions.totalDirections}")
print(f"Bundles: {len(research_directions.bundles)}")

for bundle in research_directions.bundles:
    print(f"\nBundle: {bundle.bundleId}")
    print(f"Guest: {bundle.guestDirections.guestCanonicalName}")
    print(f"  - {len(bundle.businessDirections)} business(es)")
    print(f"  - {len(bundle.productDirections)} product(s)")
    print(f"  - {len(bundle.compoundDirections)} compound(s)")
    print(f"  - {len(bundle.platformDirections)} platform(s)")

# IDs can be generated programmatically for downstream use
# Example: dir_{episode_id}_{entity_type}_{entity_name_slug}_{sequence}
```

## Testing

Run the graph with:

```bash
cd ingestion
python -m src.research_agent.human_upgrade.entity_intel_fast
```

This will:

1. Extract seed entities from episode summary
2. Find and rank candidate sources
3. Generate research directions
4. Save all artifacts to `newest_research_outputs/test_run/`
5. Print results to console

## Quality Assurance

The prompt includes built-in quality checks:

- ✅ Every guest has exactly 3 directions
- ✅ Every business has exactly 4 directions
- ✅ Every product has 3-4 directions
- ✅ All direction IDs are unique and follow convention
- ✅ totalDirections matches actual count

Additional validation in code:

- Logs breakdown by entity type
- Saves artifacts for manual review
- Clear error handling and logging
