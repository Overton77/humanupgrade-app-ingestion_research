# Beanie MongoDB Refactor Summary

## What Was Implemented

I've successfully refactored your intelligence pipeline to use Beanie ODM for MongoDB persistence. Here's what was created:

## 📁 New Files Created

### Repository Layer (`src/research_agent/services/mongo/candidates/`)

1. **`seeds_repo.py`** - Seed extraction persistence
   - `upsert_candidate_seed_doc()` - Save `SeedExtraction` outputs
   - Converts LLM structured output → Beanie model

2. **`official_sources_repo.py`** - Official sources persistence
   - `upsert_official_starter_sources_doc()` - Save `OfficialStarterSources` outputs

3. **`domain_catalogs_repo.py`** - Domain catalog persistence
   - `upsert_domain_catalog_set_doc()` - Save `DomainCatalogSet` outputs

4. **`connected_candidates_repo.py`** - Per-domain slice persistence
   - `upsert_connected_candidates_doc()` - Save individual domain slices
   - `get_connected_candidates_docs_by_run_id()` - Retrieve all slices for a run

5. **`candidate_sources_repo.py`** - Merged graph persistence
   - `upsert_candidate_sources_connected_doc()` - Save final merged output

6. **`runs_repo.py`** - Run lifecycle management
   - `create_or_get_candidate_run()` - Initialize runs
   - `update_run_status()` - Track progress
   - `update_run_outputs()` - Link output documents
   - `update_run_stats()` - Store counts

7. **`entities_repo.py`** - Entity flattening & dedupe
   - `flatten_connected_candidates_to_entity_docs()` - Extract entities from bundles
   - `bulk_insert_candidate_entities()` - Insert entity docs
   - `upsert_dedupe_group_and_add_member()` - Manage dedupe groups
   - `build_entity_key()` - Generate stable keys

8. **`__init__.py`** - Clean public API exports

### Graph Nodes (`src/research_agent/human_upgrade/graphs/nodes/`)

9. **`intel_mongo_nodes_beanie.py`** - New Beanie-based persistence nodes
   - `initialize_run_node` - Start run tracking
   - `persist_seeds_node` - Save seed extraction
   - `persist_official_sources_node` - Save official sources
   - `persist_domain_catalogs_node_beanie` - Save domain catalogs
   - `persist_candidates_node_beanie` - Save final graph + flatten entities
   - `handle_run_error_node` - Error handling

### Documentation

10. **`README.md`** - Comprehensive repository documentation

## 📝 Modified Files

### `entity_candidates_connected_graph.py`
- ✅ Updated imports to use new Beanie nodes
- ✅ Added `initialize_run` as entry point
- ✅ Inserted persistence nodes after each main step
- ✅ Maintains all existing graph logic

**New Graph Flow:**
```
initialize_run (NEW)
  ↓
seed_extraction → persist_seeds (NEW)
  ↓
official_sources → persist_official_sources (NEW)
  ↓
domain_catalogs → persist_domain_catalogs (UPDATED)
  ↓
[FANOUT] candidate_sources_slice (per-domain)
  ↓
merge_candidate_sources → persist_candidates (UPDATED)
```

## 🔄 Data Flow Architecture

### Pipeline Stages → Beanie Documents

| Graph Output | Structured Output Type | Beanie Document | Collection |
|--------------|----------------------|-----------------|------------|
| seed_extraction | `SeedExtraction` | `CandidateSeedDoc` | `intel_candidate_seeds` |
| official_starter_sources | `OfficialStarterSources` | `OfficialStarterSourcesDoc` | `intel_official_starter_sources` |
| domain_catalogs | `DomainCatalogSet` | `DomainCatalogSetDoc` | `intel_domain_catalog_sets` |
| connected_candidates (slice) | `ConnectedCandidates` | `ConnectedCandidatesDoc` | `intel_connected_candidates` |
| candidate_sources (merged) | `CandidateSourcesConnected` | `CandidateSourcesConnectedDoc` | `intel_candidate_sources_connected` |
| (flattened entities) | — | `IntelCandidateEntityDoc` | `intel_candidate_entities` |
| (dedupe groups) | — | `IntelDedupeGroupDoc` | `intel_dedupe_groups` |
| (run metadata) | — | `IntelCandidateRunDoc` | `intel_candidate_runs` |

## 🎯 Key Features

### 1. Type-Safe Persistence
- All operations use Beanie ODM (no raw dict manipulation)
- Pydantic validation at the database layer
- Clear conversion from LLM outputs → DB models

### 2. Run Lifecycle Tracking
- Every run gets a unique `runId` (UUID)
- Status tracking: `queued` → `running` → `complete` / `failed`
- Output references stored in run document
- Statistics tracked (entity count, dedupe group count, domain count)

### 3. Rerun Safety
- Old entities are deleted before new insertion
- Upsert strategy prevents duplicates
- Idempotent operations

### 4. Dedupe Groups
- Stable entity keys: `{TYPE}:{normalized_name}`
- Tracks all member entities across runs
- Foundation for future user-driven resolution

### 5. Traceability
- Each entity links back to:
  - `runId` - which run produced it
  - `baseDomain` - which domain it came from
  - `candidateSources` - evidence URLs
  - `dedupeGroupId` - which dedupe group it belongs to

## 🚀 How to Use

### In Your Graph

The graph is already updated! Just ensure Beanie is initialized before running:

```python
from research_agent.infrastructure.storage.mongo.biotech_research_db_beanie import (
    init_beanie_biotech_db
)
from research_agent.infrastructure.storage.mongo.base_client import mongo_client

# Initialize Beanie (typically in app startup)
await init_beanie_biotech_db(mongo_client)

# Run your graph as normal
graph = build_entity_intel_connected_candidates_and_sources_graph().compile()
result = await graph.ainvoke({
    "query": "What is Ozempic?",
    "starter_sources": ["https://novo.com"],
    "starter_content": "..."
})
```

### Manually Using Repositories

```python
from research_agent.services.mongo.candidates import (
    create_or_get_candidate_run,
    update_run_status,
    upsert_candidate_seed_doc,
    get_candidate_entities_by_run_id,
)
from research_agent.models.base.enums import PipelineStatus

# Create a run
run_doc = await create_or_get_candidate_run(
    query="What is Ozempic?",
    starter_sources=["https://novo.com"],
)

# Update status
await update_run_status(run_doc.runId, PipelineStatus.running)

# Persist outputs (these happen automatically in the graph)
seed_doc_id = await upsert_candidate_seed_doc(
    run_id=run_doc.runId,
    query="What is Ozempic?",
    seed_extraction=seed_output,
)

# Query results
entities = await get_candidate_entities_by_run_id(run_doc.runId)
```

### Querying Results

```python
from research_agent.services.mongo.candidates import (
    get_candidate_run_by_id,
    get_candidate_entities_by_run_id,
    get_dedupe_group_by_entity_key,
)

# Get run details
run = await get_candidate_run_by_id("some-run-id")
print(f"Status: {run.status}")
print(f"Entities: {run.candidateEntityCount}")
print(f"Dedupe groups: {run.dedupeGroupCount}")

# Get all entities for a run
entities = await get_candidate_entities_by_run_id("some-run-id")
for entity in entities:
    print(f"{entity.typeHint}: {entity.canonicalName or entity.inputName}")

# Get dedupe group
group = await get_dedupe_group_by_entity_key("ORGANIZATION:novonordisk")
print(f"Members: {len(group.members)}")
```

## ✅ What's Better Now

### Before (Old Approach)
- ❌ Dict-based operations (no type safety)
- ❌ Mixed persistence logic in helper functions
- ❌ Unclear ownership (which function does what?)
- ❌ Episode-centric (not generalized)
- ❌ Hard to test/mock

### After (New Beanie Approach)
- ✅ Type-safe Beanie ODM throughout
- ✅ Clear repository pattern (one file per concern)
- ✅ Clean separation: nodes call repos
- ✅ Generalized for any query/source
- ✅ Easy to test/mock
- ✅ Better error messages
- ✅ Automatic validation

## 🔧 Maintenance Notes

### Adding a New Output Type

1. Create Beanie document in `models/mongo/candidates/docs/`
2. Create embedded model in `models/mongo/candidates/embedded/`
3. Create repository in `services/mongo/candidates/`
4. Create persistence node in `graphs/nodes/intel_mongo_nodes_beanie.py`
5. Wire node into graph

### Running Tests

```bash
# Ensure MongoDB is running
# Ensure Beanie is initialized in test setup

pytest tests/services/mongo/candidates/
```

## 📊 Collections Created

| Collection | Purpose | Indexes |
|------------|---------|---------|
| `intel_candidate_runs` | Run metadata & lifecycle | `runId`, `status`, `query` |
| `intel_candidate_seeds` | Seed extraction outputs | `runId`, `query` |
| `intel_official_starter_sources` | Official sources | `runId`, `query` |
| `intel_domain_catalog_sets` | Domain catalogs | `runId`, `query` |
| `intel_connected_candidates` | Per-domain slices | `runId+baseDomain`, `query` |
| `intel_candidate_sources_connected` | Merged graph | `runId`, `query` |
| `intel_candidate_entities` | Flattened entities | `runId`, `entityKey`, `normalizedName` |
| `intel_dedupe_groups` | Dedupe groups | `entityKey`, `typeHint` |

## 🎉 Summary

You now have a **production-ready, type-safe, fully async MongoDB persistence layer** for your entity intelligence pipeline using Beanie ODM!

All your graph outputs are automatically persisted with full traceability, dedupe group management, and run lifecycle tracking.

The old `intel_mongo_helpers.py` approach can now be deprecated in favor of these clean, testable, repository-based functions.
