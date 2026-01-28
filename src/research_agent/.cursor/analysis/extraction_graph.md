## Extraction Graph – Structured Seed Extraction & Database Seeding

### Scope and Purpose

- **Graph module**: `human_upgrade/extraction_graph.py`
- **Primary role**:
  - Takes **plan_id** and **run_id** (references to MongoDB documents created by upstream graphs).
  - Loads:
    - **Plan document** (from `entity_research_graphs.py` execution) containing `execution.finalReports` → `FileReference`s to synthesized research reports.
    - **Candidate run document** (from `entity_candidates_research_directions_graph.py`) containing `payload.connectedBundle.connected` → the original connected bundle structure.
  - Groups and reads final reports by entity type (GUEST, BUSINESS, PRODUCT_OR_COMPOUND).
  - Runs two **structured extraction agents** (no tools, pure LLM + structured output):
    - `guest_business_extraction_agent` → extracts guest + business entities.
    - `product_compound_extraction_agent` → extracts products + compounds + product-compound links.
  - Seeds the **MongoDB/GraphQL backend** via ariadne-codegen client SDK with:
    - Upserted businesses, products, compounds.
    - Updated episodes (linking guests).
    - **Seed provenance** metadata tracking the entire pipeline execution.

This module is the **final transformation layer**: it converts research reports into structured database entities while maintaining full provenance.

---

### Key Files and Subsystems

- **This graph definition**
  - `human_upgrade/extraction_graph.py`
    - Defines:
      - `StructuredSeedState` – state schema for the extraction workflow.
      - Helper functions for MongoDB document navigation (`_safe_get`, `_parse_final_reports_from_plan_doc`, `_extract_connected_bundle_connected`).
      - Report classification and text joining (`classify_report`, `join_reports_text_from_mongo_paths`).
      - Node functions:
        - `init_structured_seed`
        - `load_docs_node`
        - `group_and_read_reports_node`
        - `extract_guest_business_node`
        - `extract_product_compound_node`
        - `finalize_structured_seed`
      - Graph builder: `make_structured_seed_subgraph() -> CompiledStateGraph`
      - Runner: `run_structured_seed_extraction(plan_id, run_id, user_id) -> Dict[str, Any]`

- **Structured outputs**
  - `human_upgrade/structured_outputs/entity_extractions_outputs.py`
    - `GuestBusinessExtraction`:
      - `guest: PersonSeedOut`
      - `business: BusinessSeedOut`
      - `people: List[PersonSeedOut]` (optional executives/owners)
    - `ProductCompoundExtraction`:
      - `products: List[ProductSeedOut]`
      - `compounds: List[CompoundSeedOut]`
      - `product_compound_links: List[ProductCompoundLink]` (explicit links with confidence/notes)
    - Seed output models (`PersonSeedOut`, `BusinessSeedOut`, `ProductSeedOut`, `CompoundSeedOut`) define the exact shape expected by GraphQL mutations.

- **Extraction prompts**
  - `human_upgrade/prompts/entity_extraction_prompts.py`
    - `GUEST_BUSINESS_PROMPT`:
      - Takes `connected_bundle_json` (original connected bundle structure).
      - Takes `guest_report_text` and `business_report_text` (final synthesized reports).
      - Instructs LLM to:
        - Use connected bundle as authoritative for entity identity/connections.
        - Extract guest + primary business (one canonical entity per `entity_key`).
        - Prefer bundle-derived `entity_key` values; do not invent random keys.
        - Only include fields supported by report text.
    - `PRODUCT_COMPOUND_PROMPT`:
      - Takes `connected_bundle_json` and `product_compound_report_text`.
      - Focuses on **product-compound links** (most critical requirement).
      - Outputs all products/compounds from reports that correspond to bundle entities.
      - Builds `product_compound_links` using ONLY products+compounds that exist in the connected bundle.

- **GraphQL client and seeding helpers**
  - `research_agent/clients/graphql_client.py`
    - `make_client_from_env()` → creates ariadne-codegen `Client` instance.
  - `human_upgrade/utils/graphql_seeding.py`
    - `build_seed_provenance(...) -> SeedProvenanceUpsertInput`:
      - Builds provenance metadata from plan_id, bundle_id, run_id, execution_run_id, pipeline_version, episode_id, episode_url, final_reports.
      - Creates `SeedFileRefInput` objects for each final report.
      - Sets `direction_type` per entity type (GUEST, BUSINESS, PRODUCT, COMPOUND, PLATFORM).
    - `seed_from_extraction_output(...) -> Dict[str, Any]`:
      - Orchestrates complete seeding workflow:
        1. Upsert business with executives (using seed provenance with `direction_type="Business"`).
        2. Upsert products (using seed provenance with `direction_type="Product"`).
        3. Upsert compounds (using seed provenance with `direction_type="Compound"`).
        4. Create product-compound links (using `ProductCompoundLink` confidence/notes).
        5. Update episode with guest (if guest exists in database).
      - Returns dictionary with all created/updated entity IDs.

- **MongoDB helpers**
  - `research_agent/retrieval/intel_mongo_helpers.py`
    - `get_plan_by_plan_id(db, plan_id) -> Dict[str, Any]`:
      - Fetches plan document (contains `execution.finalReports`, `bundleId`, `episodeUrl`, etc.).
    - `get_candidate_run_by_run_id(db, run_id) -> Dict[str, Any]`:
      - Fetches candidate run document (contains `payload.connectedBundle.connected`).

- **File system helpers**
  - `research_agent/agent_tools/file_system_functions.py`
    - `read_file_from_mongo_path(file_path: str) -> str`:
      - Reads file content from a MongoDB-stored path (used for final reports stored in Mongo file storage).

- **Artifacts**
  - `research_agent/common/artifacts.py`
    - `save_json_artifact`, `save_text_artifact`:
      - Used to persist extraction prompts and structured outputs for debugging/inspection.

---

### StructuredSeedState – Extraction Workflow State

**State schema**: `StructuredSeedState(TypedDict, total=False)`.

- **Input identifiers**
  - `plan_id: str` – MongoDB plan document ID (from research execution).
  - `run_id: str` – MongoDB candidate run document ID (from candidates + directions graph).
  - `bundle_id: str` – Extracted from plan_doc (used for artifacts/logging).

- **Loaded documents**
  - `plan_doc: Dict[str, Any]` – Full plan document from MongoDB.
  - `candidate_run_doc: Dict[str, Any]` – Full candidate run document from MongoDB.

- **Extracted data structures**
  - `connected_bundle_connected: Any` – List[ConnectedNode] from `candidate_run_doc.payload.connectedBundle.connected`.
    - Original connected bundle structure (guest + businesses + products + compounds + platforms).
    - Used as authoritative source for entity identity and connections.
  - `final_reports: List[FileReference]` – From `plan_doc.execution.finalReports`.
    - Synthesized research reports for each direction (GUEST, BUSINESS, PRODUCT, COMPOUND, PLATFORM).

- **Grouped report texts**
  - `guest_report_text: str` – Concatenated text from GUEST final reports.
  - `business_report_text: str` – Concatenated text from BUSINESS final reports.
  - `product_compound_report_text: str` – Concatenated text from PRODUCT and COMPOUND final reports.

- **Extraction outputs (stored as dicts for JSON serialization)**
  - `guest_business_extraction: Dict[str, Any]` – `GuestBusinessExtraction.model_dump()`.
  - `product_compound_extraction: Dict[str, Any]` – `ProductCompoundExtraction.model_dump()`.

- **Errors and results**
  - `errors: List[str]` – Accumulated error messages (non-fatal; graph continues).
  - `seeding_result: Dict[str, Any]` – Returned by `seed_from_extraction_output` (entity IDs, etc.).

---

### Node-by-Node Breakdown

**1. `init_structured_seed(state) -> StructuredSeedState`**
- Initializes `errors: []`.
- Entry point for the graph.

**2. `load_docs_node(state) -> StructuredSeedState`**
- Validates `plan_id` and `run_id` are present.
- Fetches:
  - `plan_doc = await get_plan_by_plan_id(db=_humanupgrade_db, plan_id=plan_id)`
  - `cand_doc = await get_candidate_run_by_run_id(db=_humanupgrade_db, run_id=run_id)`
- Extracts:
  - `bundle_id` from `plan_doc.bundleId` or `plan_doc.directions.bundleId`.
  - `final_reports` from `plan_doc.execution.finalReports` via `_parse_final_reports_from_plan_doc`.
  - `connected_bundle_connected` from `cand_doc.payload.connectedBundle.connected` via `_extract_connected_bundle_connected`.
- Accumulates errors if any extraction fails (non-fatal; graph continues with warnings).

**3. `group_and_read_reports_node(state) -> StructuredSeedState`**
- Classifies `final_reports` by entity type:
  - `classify_report(fr)` uses `entity_key` prefix (`"person:"`, `"business:"`, etc.) and path segments (`"guest"`, `"business"`, `"product"`, `"compound"`).
  - Groups into: `guest`, `business`, `prodcomp`, `unknown`.
- Reads report texts:
  - `guest_text = await join_reports_text_from_mongo_paths(guest[:1])` (takes first/best guest report).
  - `business_text = await join_reports_text_from_mongo_paths(business[:1])` (takes first/best business report).
  - `prodcomp_text = await join_reports_text_from_mongo_paths(prodcomp)` (all product/compound reports).
- `join_reports_text_from_mongo_paths`:
  - Calls `read_file_from_mongo_path(fr.file_path)` for each `FileReference`.
  - Formats with headers: `"===== REPORT {entity_key} | {file_path} ====="`.
  - Returns concatenated text block.
- Accumulates warnings if reports are missing (non-fatal).

**4. `extract_guest_business_node(state, config) -> StructuredSeedState`**
- Builds prompt:
  - Serializes `connected_bundle_connected` to JSON.
  - Formats `GUEST_BUSINESS_PROMPT` with:
    - `connected_bundle_json`
    - `guest_report_text`
    - `business_report_text`
- Invokes agent:
  - `agent = build_guest_business_agent()` (no tools, `response_format=GuestBusinessExtraction`).
  - `resp = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]}, config)`
  - Extracts `structured: GuestBusinessExtraction = resp["structured_response"]`
- Saves artifacts:
  - Prompt text → `"newest_research_outputs/seed_extraction/guest_business_prompt"`.
  - Structured output JSON → `"newest_research_outputs/seed_extraction/guest_business_structured"`.
- Returns `{"guest_business_extraction": structured.model_dump()}`.

**5. `extract_product_compound_node(state, config) -> StructuredSeedState`**
- Same pattern as `extract_guest_business_node`:
  - Uses `PRODUCT_COMPOUND_PROMPT` with `connected_bundle_json` and `product_compound_report_text`.
  - Invokes `build_product_compound_agent()` (no tools, `response_format=ProductCompoundExtraction`).
  - Saves artifacts to `"newest_research_outputs/seed_extraction/product_compound_*"`.
  - Returns `{"product_compound_extraction": structured.model_dump()}`.

**6. `finalize_structured_seed(state) -> StructuredSeedState`**
- Validates required extractions are present.
- Extracts metadata from `plan_doc`:
  - `episode_url`, `execution_run_id`, `pipeline_version`, `episode_id`.
- Builds seed provenance:
  - `seed_provenance = build_seed_provenance(plan_id, bundle_id, run_id, execution_run_id, pipeline_version, episode_id, episode_url, final_reports)`
- Creates GraphQL client:
  - `client = make_client_from_env()`
- Seeds database:
  - `seeding_result = await seed_from_extraction_output(client, guest_business_extraction, product_compound_extraction, episode_url, business_name, seed_provenance)`
  - This orchestrates:
    - Business upsert (with executives).
    - Product upserts (with seed provenance per product).
    - Compound upserts (with seed provenance per compound).
    - Product-compound link creation.
    - Episode update (linking guest, if guest exists).
- Logs warnings if guest/episode update fails (guest may not exist yet).
- Closes client: `await client.http_client.aclose()`.
- Returns `{"seeding_result": seeding_result, "errors": errors}`.

---

### Graph Structure and Execution Flow

**Graph builder**: `make_structured_seed_subgraph() -> CompiledStateGraph`

- **Nodes**:
  - `"init"` → `init_structured_seed`
  - `"load_docs"` → `load_docs_node`
  - `"group_and_read"` → `group_and_read_reports_node`
  - `"extract_guest_business"` → `extract_guest_business_node`
  - `"extract_product_compound"` → `extract_product_compound_node`
  - `"finalize"` → `finalize_structured_seed`

- **Edges** (sequential pipeline):
  - Entry: `START` → `"init"`
  - `"init"` → `"load_docs"`
  - `"load_docs"` → `"group_and_read"`
  - `"group_and_read"` → `"extract_guest_business"` (business first, so we can upsert and capture business_id for later use).
  - `"extract_guest_business"` → `"extract_product_compound"`
  - `"extract_product_compound"` → `"finalize"`
  - `"finalize"` → `END`

- **Runner**: `run_structured_seed_extraction(plan_id, run_id, user_id="dev") -> Dict[str, Any]`
  - Creates graph: `graph = make_structured_seed_subgraph()`
  - Builds config: `RunnableConfig(configurable={"thread_id": f"seed_extract__plan__{plan_id}__run__{run_id}", "user_id": user_id})`
  - Initializes state: `{"plan_id": plan_id, "run_id": run_id, "errors": []}`
  - Invokes graph: `out = await graph.ainvoke(init_state, cfg)`
  - Saves final output artifact: `"newest_research_outputs/seed_extraction/structured_seed_graph_output"`
  - Returns full state output.

---

### How This Graph Connects to Upstream Graphs

**Input dependencies**:

1. **From `entity_candidates_research_directions_graph.py`**:
   - Produces `candidate_run_doc` with `payload.connectedBundle.connected`.
   - This is the **authoritative source** for entity identity and connections.
   - Extraction agents use it to:
     - Resolve canonical names and `entity_key` values.
     - Understand which products link to which compounds.
     - Avoid inventing new entities (prefer bundle-derived identities).

2. **From `entity_research_graphs.py`**:
   - Produces `plan_doc` with `execution.finalReports` (list of `FileReference` objects).
   - These are the **synthesized research reports** written by direction agents.
   - Extraction agents read these reports to extract structured fields.

**Output dependencies**:

- Seeds MongoDB/GraphQL backend with:
  - Businesses, products, compounds (upserted with seed provenance).
  - Product-compound links (explicit relationships).
  - Episode updates (linking guests to episodes).

**Sequential execution rationale**:

- The extraction graph runs **sequentially** (not in parallel) to:
  - Avoid complexity of maintaining connection maps across concurrent mutations.
  - Ensure business is upserted first (so we can capture `business_id` for product associations).
  - Simplify error handling and rollback (if any step fails, we can retry from that point).

---

### GraphQL Seeding Details

**Seed provenance structure**:

- `SeedProvenanceUpsertInput` contains:
  - `plan_id` (required)
  - `bundle_id`, `run_id`, `execution_run_id`, `pipeline_version`, `episode_id`, `episode_url` (optional)
  - `direction_type: SeedDirectionType` (set per entity: GUEST, BUSINESS, PRODUCT, COMPOUND, PLATFORM)
  - `final_reports: List[SeedFileRefInput]` (file references with `kind: SeedFileRefKind`, `file_path`, `description`)

**Seeding workflow** (inside `seed_from_extraction_output`):

1. **Business upsert**:
   - Uses `direction_type="Business"` in seed provenance.
   - Upserts business with executives (from `guest_business_extraction.people`).
   - Returns `business_id` for later use.

2. **Product upserts**:
   - Iterates over `product_compound_extraction.products`.
   - Each product uses `direction_type="Product"` in seed provenance.
   - Associates products with business (via `business_id`).

3. **Compound upserts**:
   - Iterates over `product_compound_extraction.compounds`.
   - Each compound uses `direction_type="Compound"` in seed provenance.

4. **Product-compound links**:
   - Iterates over `product_compound_extraction.product_compound_links`.
   - Creates explicit relationship records with confidence/notes.

5. **Episode update**:
   - Attempts to update episode with guest (if guest exists in database).
   - May fail gracefully if guest doesn't exist yet (logged as warning).

**Error handling**:

- GraphQL mutations are wrapped in try/except.
- Errors are accumulated in `state["errors"]` (non-fatal; graph continues).
- Client lifecycle is managed via `finally: await client.http_client.aclose()`.

---

### Integration Notes and Future API/Rules Hooks

- **Invocation from FastAPI / LangSmith**
  - `run_structured_seed_extraction(plan_id, run_id, user_id)` is the main entry point.
  - Can be called directly or via LangGraph/LangSmith with thread IDs.
  - External API can:
    - Query MongoDB for available `plan_id`/`run_id` pairs (from upstream graphs).
    - Invoke extraction graph for a specific plan/run.
    - Monitor seeding results (entity IDs, errors).

- **MongoDB document structure assumptions**
  - `plan_doc.execution.finalReports` → `List[FileReference dicts]`
  - `candidate_run_doc.payload.connectedBundle.connected` → `List[ConnectedNode dicts]`
  - These structures are created by upstream graphs; extraction graph assumes they exist.

- **File path handling**
  - `FileReference.file_path` stores relative paths (relative to Mongo file storage root).
  - `read_file_from_mongo_path` handles reading from Mongo file storage.
  - Paths are preserved as-is from upstream graphs.

- **Artifacts and debugging**
  - Extraction prompts and structured outputs are saved to `"newest_research_outputs/seed_extraction/"`.
  - Final graph output is saved as `"structured_seed_graph_output"` JSON.
  - These can be inspected for debugging extraction quality.

- **.cursor context**
  - This analysis doc lives in:
    - `ingestion/src/research_agent/.cursor/analysis/extraction_graph.md`
  - Intended future usage:
    - Generate `.cursor/rules` entries describing:
      - How to invoke `run_structured_seed_extraction`.
      - What MongoDB documents are required.
      - How to handle extraction errors.
    - Seed a project plan for:
      - FastAPI endpoints (extraction graph invocation).
      - MongoDB query helpers (list available plans/runs).
      - GraphQL mutation monitoring (track seeding success/failure).

---

### Design Decisions and Rationale

- **Sequential execution** (not parallel):
  - Simplifies connection map management.
  - Ensures business is created before products (for associations).
  - Easier error handling and retry.

- **No tools in extraction agents**:
  - Extraction is a pure LLM task (structured output from reports + bundle).
  - No web search or filesystem operations needed (all data is already in state).

- **Connected bundle as authoritative**:
  - Prevents entity key drift (extraction must align with bundle-derived identities).
  - Ensures product-compound links match bundle structure.

- **Seed provenance per entity**:
  - Each entity (business, product, compound) gets its own provenance with `direction_type`.
  - Enables fine-grained tracking of which research direction produced which entity.

- **Graceful error handling**:
  - Errors are accumulated in `state["errors"]` (non-fatal).
  - Graph continues even if some reports are missing or GraphQL mutations fail.
  - Final output includes both `seeding_result` and `errors` for inspection.

