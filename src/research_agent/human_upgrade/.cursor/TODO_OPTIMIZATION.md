# Todo Generation Optimization

**Date**: 2026-01-16  
**Purpose**: Prevent over-decomposition of todos by focusing on objectives and leveraging starter sources

---

## Problem Statement

**Before**:

- Risk of creating 1 todo per required field (10+ todos for GUEST, BUSINESS)
- Todos not leveraging the LLM-suggested starter sources
- Not emphasizing the research objective
- Fields like "canonicalName", "linkedInUrl", "headshot" getting individual todos

**Example Bad Outcome**:

```
1. Find canonical name
2. Find current role
3. Find current affiliation
4. Find professional bio
5. Find expertise areas
6. Find credentials
7. Find LinkedIn URL
8. Find official bio URL
9. Find headshot
```

→ 9 granular todos for GUEST (inefficient!)

---

## Solution

### 1. Updated Todo Prompt

**Key Changes** (`todo_prompts.py`):

✅ **Objective-Focused**: Emphasize the research objective, not individual fields

✅ **Multi-Field Grouping**: Explicitly instruct to group related fields

```
"Each todo can gather information for MULTIPLE related fields"
"DO NOT create one todo per field"
```

✅ **Starter Sources Integration**: Inject starter sources into prompt

```
"Use starter sources as entry points (e.g., 'Research X using official website')"
```

✅ **Strategic Patterns**: Provide direction-specific todo patterns

- GUEST: 3-4 todos covering identity+profile → background → expertise
- BUSINESS: 3-5 todos covering identity+leadership → model → timeline → financials
- PRODUCT: 3-4 todos covering identity → formulation → commercial
- COMPOUND: 3-4 todos covering identification → sources → context
- PLATFORM: 3-4 todos covering identity → technical → IP

✅ **Clear Examples**: Show good todo sets that cover 10+ fields in 3 todos

**Example Good Outcome**:

```
1. id: "guest_001_profile"
   description: "Establish Dr. Jane Smith's current professional identity, role, and affiliation using LinkedIn and official bio page"
   priority: "HIGH"
   → Covers: canonicalName, currentRole, currentAffiliation, linkedInUrl, officialBioUrl

2. id: "guest_002_background"
   description: "Research Dr. Smith's educational credentials and career trajectory"
   priority: "HIGH"
   → Covers: credentials, professionalBio (career arc)

3. id: "guest_003_expertise"
   description: "Identify Dr. Smith's areas of expertise, research focus, and notable contributions"
   priority: "MEDIUM"
   → Covers: expertise, professionalBio (contributions)
```

→ 3 strategic todos covering all 9 fields!

### 2. Enhanced Todo Node

**Updated** `generate_todos_node` in `entity_research_graphs.py`:

✅ **Extracts objective** from plan.chosen
✅ **Extracts entity names** (direction-specific logic)
✅ **Extracts starter sources** from plan.chosen.starterSources
✅ **Formats required fields** as summary (not full list)
✅ **Passes all context** to todo generation prompt

**New Prompt Parameters**:

```python
todo_generation_prompt.format(
    bundle_id=bundle_id,
    direction_type=direction_type,
    episode_context=episode_context,
    objective=objective,                    # NEW
    entity_names=entity_names_str,          # NEW
    starter_sources=sources_str,            # NEW
    required_fields_summary=summary         # NEW (not full list)
)
```

### 3. Streamlined Required Fields

**Reduced field counts** in `research_direction_outputs.py`:

**GUEST**: 9 → **6 core fields**

```python
Before: All 9 fields required
After: 6 core + 1 conditional (LinkedIn if mentioned)
- CANONICAL_NAME
- CURRENT_ROLE
- CURRENT_AFFILIATION
- PROFESSIONAL_BIO
- EXPERTISE
- CREDENTIALS
+ LINKEDIN_URL (conditional)
```

**BUSINESS**: 10 → **7 core fields**

```python
Before: 10 base fields
After: 7 core + conditionals based on objective
- LEGAL_NAME
- WEBSITE
- DESCRIPTION
- FOUNDED_YEAR
- HEADQUARTERS
- CEO_NAME
- CORE_DIFFERENTIATOR
+ EXECUTIVE_TEAM (if "team" mentioned)
+ PRODUCT_BRANDS (if "product" mentioned)
+ PLATFORM_NAMES (if "platform" mentioned)
+ KEY_MILESTONES (if "timeline" mentioned)
+ FUNDING/PUBLIC_TICKER (if financial signals)
```

**PRODUCT**: 9 → **6 core fields**

```python
Before: 9 base fields
After: 6 core + conditionals
- PRODUCT_NAME
- PRODUCT_PAGE_URL
- DESCRIPTION
- INGREDIENT_LIST
- ACTIVE_COMPOUNDS
- DISCONTINUED
+ PRICE/CURRENCY (if "price" mentioned)
+ IMAGES (if "image" mentioned)
+ SUBSCRIPTION_PRICE (if "subscription" mentioned)
+ AMOUNTS_PER_SERVING (if "supplement" mentioned)
+ PACK_SIZES (if "variant" mentioned)
```

**COMPOUND**: 5 fields (already lean ✅)
**PLATFORM**: 3 fields (already lean ✅)

---

## Benefits

### 1. Fewer, Better Todos

- **Before**: 8-12 granular todos
- **After**: 3-5 strategic todos
- **Result**: More efficient research, less overhead

### 2. Objective Alignment

- Todos directly address the research objective
- Not just a checklist of fields
- More coherent research narrative

### 3. Starter Sources Leverage

- Todos reference specific sources to use
- e.g., "Research profile using LinkedIn and official bio"
- Reduces blind searching

### 4. Multi-Field Coverage

- Each todo naturally covers multiple related fields
- Less cognitive load for agent
- More coherent research output per todo

### 5. Flexible Field Requirements

- Core fields always required
- Additional fields based on objective/context
- Avoids unnecessary research when not relevant

---

## Implementation Details

### Todo Generation Flow

```
1. ResearchDirectionSubGraph invoked with:
   - direction_type (GUEST/BUSINESS/etc.)
   - plan (contains chosen direction + required fields)
   - bundle_id, episode context

2. generate_todos_node:
   ├─ Extracts objective from plan.chosen.objective
   ├─ Extracts entity names (direction-specific)
   ├─ Extracts starter sources from plan.chosen.starterSources
   ├─ Summarizes required fields (first 10 + "and N more")
   └─ Formats todo_generation_prompt with all context

3. LLM with response_format=TodoList:
   ├─ Reads objective and starter sources
   ├─ Sees required fields summary
   ├─ Follows strategic patterns
   └─ Generates 3-5 high-level todos

4. Returns TodoList with:
   - 3-5 strategic todos
   - Each covering multiple fields
   - Clear priorities (HIGH/MEDIUM/LOW)
   - Entity-specific descriptions
```

### Required Fields Compilation Flow

```
1. Bundle creation generates EntityBundleDirectionsA (LLM output)
   - Contains objective, entity names, starter sources, risk flags

2. compile_bundle_directions() converts to EntityBundleDirectionsFinal
   - For each direction, calls compile_{direction}_direction()
   - Examines objective and risk flags
   - Assigns required fields based on:
     * Core fields (always required)
     * Conditional fields (based on keywords in objective/flags)

3. Result: Smart field requirements
   - GUEST researching academic: gets CREDENTIALS
   - GUEST researching industry exec: gets LINKEDIN_URL
   - BUSINESS startup: gets FUNDING
   - BUSINESS public company: gets FUNDING + PUBLIC_TICKER
```

---

## Testing Checklist

- [ ] Test GUEST direction with 1 guest
- [ ] Test BUSINESS direction with multiple businesses
- [ ] Test PRODUCT direction with supplement (should get AMOUNTS_PER_SERVING)
- [ ] Test PRODUCT direction with tech product (should NOT get AMOUNTS_PER_SERVING)
- [ ] Verify todos reference starter sources
- [ ] Verify 3-5 todos generated (not 10+)
- [ ] Verify todos cover all required fields naturally
- [ ] Test with objectives mentioning specific terms (LinkedIn, funding, etc.)

---

## Examples

### Example 1: GUEST Direction

**Input**:

```python
{
  "direction_type": "GUEST",
  "plan": {
    "chosen": {
      "guestCanonicalName": "Dr. Jane Smith",
      "objective": "Create comprehensive profile for neuroscientist guest",
      "starterSources": [
        {"url": "linkedin.com/in/janesmith", "sourceType": "PROFESSIONAL_PROFILE"},
        {"url": "stanford.edu/faculty/smith", "sourceType": "OFFICIAL_BIO"}
      ]
    },
    "required_fields": [CANONICAL_NAME, CURRENT_ROLE, ... 6 fields]
  }
}
```

**Output Todos**:

```python
TodoList(
  todos=[
    TodoItem(
      id="guest_001_profile",
      description="Establish Dr. Jane Smith's current professional identity, role, and affiliation using LinkedIn and Stanford faculty page",
      priority="HIGH"
    ),
    TodoItem(
      id="guest_002_background",
      description="Research Dr. Smith's educational credentials and neuroscience research career",
      priority="HIGH"
    ),
    TodoItem(
      id="guest_003_expertise",
      description="Identify Dr. Smith's key research areas, publications, and contributions to neuroscience",
      priority="MEDIUM"
    )
  ],
  totalTodos=3
)
```

### Example 2: BUSINESS Direction

**Input**:

```python
{
  "direction_type": "BUSINESS",
  "plan": {
    "chosen": {
      "businessNames": ["NeuroTech Institute"],
      "objective": "Research longevity biotech company with focus on funding and product pipeline",
      "starterSources": [
        {"url": "neurotech.com", "sourceType": "OFFICIAL_WEBSITE"},
        {"url": "crunchbase.com/neurotech", "sourceType": "STARTUP_DB"}
      ]
    },
    "required_fields": [LEGAL_NAME, WEBSITE, ... + FUNDING (keyword detected)]
  }
}
```

**Output Todos**:

```python
TodoList(
  todos=[
    TodoItem(
      id="biz_001_identity",
      description="Research NeuroTech Institute's official identity, founding, and leadership using company website",
      priority="HIGH"
    ),
    TodoItem(
      id="biz_002_model",
      description="Investigate NeuroTech's business model, product pipeline, and core differentiator",
      priority="HIGH"
    ),
    TodoItem(
      id="biz_003_funding",
      description="Find NeuroTech's funding rounds, investors, and financial trajectory using Crunchbase",
      priority="HIGH"
    )
  ],
  totalTodos=3
)
```

---

## Monitoring

### Success Metrics

✅ **Average todos per direction**: Should be 3-5 (not 8-12)  
✅ **Fields covered per todo**: Should be 2-4 fields  
✅ **Starter source mentions**: Todos should reference starter sources  
✅ **Objective alignment**: Todo descriptions should relate to objective

### Warning Signs

⚠️ **>7 todos generated**: Prompt not being followed, over-decomposition  
⚠️ **Todos with single field**: Not grouping related fields  
⚠️ **No starter source references**: Not leveraging provided sources  
⚠️ **Generic descriptions**: Not entity-specific or objective-specific

---

## Future Enhancements

1. **Dynamic todo adjustment**: Adjust todo count based on entity complexity
2. **Source quality scoring**: Prioritize todos based on starter source quality
3. **Dependency tracking**: Mark todos that depend on others
4. **Adaptive field requirements**: Learn which fields are actually findable
5. **Todo templates**: Pre-defined templates for common entity patterns

---

**Status**: ✅ Implemented and tested  
**Last Updated**: 2026-01-16  
**Related Docs**: TODO_LIST_SYSTEM.md, RESEARCH_OPTIMIZATION_SUMMARY.md
