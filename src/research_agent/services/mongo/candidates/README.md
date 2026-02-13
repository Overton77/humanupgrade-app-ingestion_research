# MongoDB Candidate Services (Beanie-based)

This directory contains repository/service functions for persisting entity intelligence pipeline outputs using Beanie ODM.

## Architecture Overview

The candidate intelligence pipeline produces several key outputs at different stages:

1. **Seed Extraction** → `CandidateSeedDoc`
2. **Official Sources** → `OfficialStarterSourcesDoc`
3. **Domain Catalogs** → `DomainCatalogSetDoc`
4. **Connected Candidates (per-domain)** → `ConnectedCandidatesDoc`
5. **Merged Graph** → `CandidateSourcesConnectedDoc`
6. **Flattened Entities** → `IntelCandidateEntityDoc` + `IntelDedupeGroupDoc`
7. **Run Metadata** → `IntelCandidateRunDoc`

## Repository Files

### `runs_repo.py`
Manages the overall candidate run lifecycle:
- `create_or_get_candidate_run()` - Initialize or retrieve a run
- `update_run_status()` - Update run status (queued, running, complete, failed)
- `update_run_outputs()` - Link output document IDs to the run
- `update_run_stats()` - Update entity/group counts

### `seeds_repo.py`
Persists seed extraction output (Node A):
- `upsert_candidate_seed_doc()` - Upsert seed extraction results
- Converts `SeedExtraction` (structured output) → `SeedExtractionModel` (Beanie embedded)

### `official_sources_repo.py`
Persists official starter sources (Node A):
- `upsert_official_starter_sources_doc()` - Upsert official sources
- Converts `OfficialStarterSources` → `OfficialStarterSourcesModel`

### `domain_catalogs_repo.py`
Persists domain catalog sets (Node B):
- `upsert_domain_catalog_set_doc()` - Upsert domain mapping results
- Converts `DomainCatalogSet` → `DomainCatalogSetModel`

### `connected_candidates_repo.py`
Persists per-domain connected candidates (Node C):
- `upsert_connected_candidates_doc()` - Upsert a single domain slice
- `get_connected_candidates_docs_by_run_id()` - Retrieve all slices for a run
- Converts `ConnectedCandidates` → `ConnectedCandidatesModel`

### `candidate_sources_repo.py`
Persists merged graph output:
- `upsert_candidate_sources_connected_doc()` - Upsert final merged graph
- Converts `CandidateSourcesConnected` → `CandidateSourcesConnectedModel`

### `entities_repo.py`
Flattens graph into entity documents + dedupe groups:
- `flatten_connected_candidates_to_entity_docs()` - Extract all entities from a connected bundle
- `bulk_insert_candidate_entities()` - Insert entity docs in bulk
- `upsert_dedupe_group_and_add_member()` - Create/update dedupe groups
- `build_entity_key()` - Generate stable entity keys (TYPE:normalized_name)

## Data Flow in Graph

```
1. initialize_run_node
   ↓ (creates IntelCandidateRunDoc with status=running)
   
2. seed_extraction_node → persist_seeds_node
   ↓ (creates CandidateSeedDoc, updates run.outputs.seedsDocId)
   
3. official_sources_node → persist_official_sources_node
   ↓ (creates OfficialStarterSourcesDoc, updates run.outputs.officialStarterSourcesDocId)
   
4. domain_catalogs_node → persist_domain_catalogs_node_beanie
   ↓ (creates DomainCatalogSetDoc, updates run.outputs.domainCatalogSetDocId)
   
5. [FANOUT] candidate_sources_slice_node (per-domain)
   ↓ (creates ConnectedCandidatesDoc per domain)
   
6. merge_candidate_sources_node → persist_candidates_node_beanie
   ↓ (creates CandidateSourcesConnectedDoc,
      flattens to IntelCandidateEntityDoc,
      creates IntelDedupeGroupDoc,
      updates run.status = complete)
```

## Key Design Decisions

### 1. Structured Outputs vs. Beanie Models
- **LLM Outputs**: Use Pydantic models from `research_agent.human_upgrade.structured_outputs.candidates_outputs`
- **Database Storage**: Use Beanie models from `research_agent.models.mongo.candidates.*`
- **Conversion**: Each repository has a `_convert_*_to_model()` helper

### 2. Upsert Strategy
All upsert functions use `runId` (and sometimes `baseDomain`) as the unique key:
- For runs: `runId` is unique
- For seeds/sources/catalogs: One per `runId`
- For connected candidates: One per `(runId, baseDomain)`
- For merged graph: One per `runId`

### 3. Rerun Safety
- `delete_candidate_entities_for_run()` clears old entities before inserting new ones
- Upserts use `find_one()` + conditional insert/update

### 4. Dedupe Groups
- Uses stable entity keys: `{EntityTypeHint}:{normalizedName}`
- Groups track all member entities across runs
- Allows future resolution (user accepts/rejects/merges)

## Usage Example

```python
from research_agent.services.mongo.candidates import (
    create_or_get_candidate_run,
    update_run_status,
    upsert_candidate_seed_doc,
)
from research_agent.models.base.enums import PipelineStatus

# Initialize run
run_doc = await create_or_get_candidate_run(
    query="What is Ozempic?",
    starter_sources=["https://novo.com"],
    pipeline_version="v1",
)

# Update status
await update_run_status(run_doc.runId, PipelineStatus.running)

# Persist seed extraction
seed_doc_id = await upsert_candidate_seed_doc(
    run_id=run_doc.runId,
    query="What is Ozempic?",
    seed_extraction=seed_extraction_output,
)
```

## Testing

To test the repositories, ensure:
1. Beanie is initialized: `await init_beanie_biotech_db(mongo_client)`
2. MongoDB is running and accessible
3. Use unique `runId` values per test run

## Migration Notes

This replaces the old `intel_mongo_helpers.py` approach with:
- ✅ Type-safe Beanie ODM
- ✅ Async/await throughout
- ✅ Clear repository pattern
- ✅ Better error handling
- ✅ Direct document references (no dict manipulation)
