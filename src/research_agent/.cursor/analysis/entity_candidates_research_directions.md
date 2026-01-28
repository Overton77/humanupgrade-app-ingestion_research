## Entity Candidates & Research Directions Graph – Analysis

### Scope and Purpose

- **Graph module**: `human_upgrade/entity_candidates_research_directions_graph.py`
- **Primary role**: Given an **episode webpage summary + URL**, this graph:
  - Extracts **high‑recall candidate entities** (guests, businesses, products, compounds, platforms).
  - Validates and connects those candidates into **guest‑centric bundles** with source URLs.
  - Plans downstream research by generating **Entity Research Direction Bundles** with deterministic required fields.
  - Persists **candidate entities** and **research plans** into MongoDB for later graphs.

This graph is the **ingestion + planning front‑door** to the whole entity intelligence pipeline.

---

### Key Files and Subsystems

- **Graph definition**
  - `human_upgrade/entity_candidates_research_directions_graph.py`
    - Defines `EntityIntelCandidateAndResearchDirectionsState`.
    - Implements three main nodes:
      - `seed_extraction_node`
      - `candidate_sources_node`
      - `generate_research_directions_node`
    - Wires two persistence nodes:
      - `persist_candidates_node`
      - `persist_research_plans_node`
    - Provides builder/factory:
      - `build_entity_research_directions_builder()`
      - `make_entity_research_directions_graph(config: RunnableConfig) -> CompiledStateGraph`

- **Structured outputs – candidates and validation**
  - `structured_outputs/candidates_outputs.py`
    - `SeedExtraction`
      - High‑recall, **no‑web** extraction from the episode summary:
        - `guest_candidates: List[CandidateEntity]`
        - `business_candidates: List[CandidateEntity]`
        - `product_candidates: List[CandidateEntity]`
        - `platform_candidates: List[CandidateEntity]`
        - `compound_candidates: List[CandidateEntity]`
        - `evidence_claim_hooks: List[str]`
        - `notes: Optional[str]`
    - `CandidateSourcesConnected`
      - Connected bundles of **validated sources** per guest:
        - `connected: List[ConnectedCandidates]`
        - Each `ConnectedCandidates` has:
          - `guest: EntitySourceResult`
          - `businesses: List[BusinessBundle]`
          - `notes: Optional[str]`
    - `OutputA2Envelope` – wrapper for `CandidateSourcesConnected`.

- **Structured outputs – research plans**
  - `structured_outputs/research_direction_outputs.py`
    - `EntityBundlesListOutputA`
      - Raw LLM output (OutputA) for **entity research direction bundles**.
    - `EntityBundlesListFinal`
      - Deterministic, compiled research plans (OutputFinal) used by the **research agent graphs**.
    - Compiler functions:
      - `compile_bundles_list(bundles_list_a: EntityBundlesListOutputA) -> EntityBundlesListFinal`
      - Direction‑specific compilers:
        - `compile_guest_direction`
        - `compile_business_direction`
        - `compile_products_direction`
        - `compile_compounds_direction`
        - `compile_platforms_direction`

- **Prompts (referenced, not in this file)**
  - `PROMPT_OUTPUT_A_SEED_EXTRACTION` – for initial candidate extraction.
  - `PROMPT_OUTPUT_A2_CONNECTED_CANDIDATE_SOURCES` – for validation + connection.
  - `PROMPT_OUTPUT_A3_ENTITY_RESEARCH_DIRECTIONS` – for research plans.
  - All are imported from:
    - `human_upgrade/prompts/seed_prompts.py`
    - `human_upgrade/prompts/candidates_prompts.py`
    - `human_upgrade/prompts/research_directions_prompts.py`

- **Tools and infra**
  - Web search / validation tools:
    - `wiki_tool`
    - `tavily_map_validation`
    - `tavily_search_validation`
    - `tavily_extract_validation`
  - Provided by `human_upgrade/tools/web_search_tools.py`.
  - Persistence nodes:
    - `persist_candidates_node`
    - `persist_research_plans_node`
    - From `human_upgrade/intel_mongo_nodes.py` (writes to MongoDB).
  - Model configuration:
    - `gpt_5_mini`, `gpt_4_1`, etc. from `human_upgrade/base_models.py`.
  - Checkpoint + store:
    - `get_persistence()` from `human_upgrade/persistence/checkpointer_and_store.py`.

---

### State Definition and Lifecycle

**State schema**: `EntityIntelCandidateAndResearchDirectionsState` (TypedDict, `total=False`).

- **Core execution counters**
  - `llm_calls: int` – total LLM model invocations (not fully wired everywhere yet).
  - `tool_calls: int` – total tool calls (same note as above).

- **Episode context**
  - `episode: Dict[str, Any]`
    - Expected fields (used explicitly):
      - `episode["webPageSummary"]`
      - `episode["episodePageUrl"]`

- **Pipeline outputs**
  - `seed_extraction: SeedExtraction`
  - `candidate_sources: CandidateSourcesConnected`
  - `research_directions: EntityBundlesListFinal`

- **Intel orchestration identifiers**
  - `intel_run_id: str` – stable per‑run identifier (not yet wired in all nodes).
  - `intel_pipeline_version: str` – explicit pipeline version (for provenance).

- **Persistence outputs**
  - From `persist_candidates_node`:
    - `candidate_entity_ids: List[str]` – created `candidateEntityId`s.
    - `dedupe_group_map: Dict[str, str]` – map from `entityKey` to `dedupeGroupId`.
  - From `persist_research_plans_node`:
    - `research_plan_ids: List[str]` – inserted `planId`s.

- **Error handling / meta**
  - `error: str` – single error string used in some nodes.
  - `steps_taken: int` – optional orchestration metric count.

The graph uses **LangGraph’s default state merging** semantics: each node returns a **partial dict** which is merged into the working state.

---

### Node‑Level Behavior

#### 1. `seed_extraction_node`

- **Input requirements**
  - `state["episode"]["webPageSummary"]` – non‑empty, or `ValueError`.
  - `state["episode"]["episodePageUrl"]` – non‑empty, or `ValueError`.

- **Prompting + model**
  - Builds `seed_extraction_prompt` via `PROMPT_OUTPUT_A_SEED_EXTRACTION.format(...)`.
  - Creates a `seed_extraction_agent` using:
    - `create_agent(model=gpt_5_mini, tools=[openai_search_tool], response_format=ProviderStrategy(SeedExtraction))`.
    - `openai_search_tool` is the OpenAI **server‑side web_search tool**: `{"type": "web_search"}`.
  - Invokes agent with:
    - `{"messages": [{"role": "user", "content": seed_extraction_prompt}]}`.

- **Output / state update**
  - Expects `response["structured_response"]` of type `SeedExtraction`.
  - Logs candidate counts for each entity type.
  - Returns `{ "seed_extraction": seed_extraction_output }`.

**Key properties**
- This step is **high‑recall seed extraction** with minimal external web tools (OpenAI web_search only).
- Structured output is Pydantic, making later steps deterministic and easily testable.

---

#### 2. `candidate_sources_node`

- **Input requirements**
  - `state["seed_extraction"]` must be present and non‑`None`.
  - Pulls `episode_url` from `state["episode"]["episodePageUrl"]` (for logging + artifacts).

- **Prompting**
  - Uses `format_seed_extraction_for_prompt(seed_extraction)` to stringify candidate lists.
  - Formats `PROMPT_OUTPUT_A2_CONNECTED_CANDIDATE_SOURCES` with:
    - `guest_candidates`
    - `business_candidates`
    - `product_candidates`
    - `platform_candidates`
    - `compound_candidates`
    - `evidence_claim_hooks`
    - `notes`

- **Tools + agent**
  - Validation tools: `VALIDATION_TOOLS = [wiki_tool, tavily_search_validation, tavily_extract_validation, tavily_map_validation]`.
  - Agent:
    - `create_agent(model=gpt_5_mini, tools=VALIDATION_TOOLS, response_format=ProviderStrategy(CandidateSourcesConnected), middleware=[SummarizationMiddleware(...)])`.
    - Summarization middleware:
      - `model="gpt-4.1"`
      - `trigger=("tokens", 170000)`
      - `keep=("messages", 20)`

- **Output / state update**
  - `candidate_sources_output: CandidateSourcesConnected = response["structured_response"]`.
  - Logs `len(candidate_sources_output.connected)`.
  - Attempts to save a JSON artifact via `save_json_artifact(..., "candidate_sources_connected", suffix=...)`.
  - Returns:
    - On success: `{ "candidate_sources": candidate_sources_output }`.
    - On artifact error: includes `"error": str(e)` but **still** sets `"candidate_sources"`.

**Key properties**
- This step **connects candidates into guest‑centric bundles** and validates with external tools.
- Uses long‑context summarization middleware to prevent runaway history growth.

---

#### 3. `generate_research_directions_node`

- **Input requirements**
  - `state["candidate_sources"]` must be present and `candidate_sources.connected` must be non‑empty.

- **Prompting**
  - Uses `format_connected_candidates_for_prompt(candidate_sources)` to create a textual representation.
  - Formats `PROMPT_OUTPUT_A3_ENTITY_RESEARCH_DIRECTIONS` with `connected_bundles`.

- **Agent + response_format**
  - `research_directions_agent = create_agent(model=gpt_5_mini, response_format=ProviderStrategy(EntityBundlesListOutputA), name="research_directions_agent")`.
  - Invoked with a single `user` message containing the prompt.
  - Expects `response["structured_response"]` as `EntityBundlesListOutputA`.

- **Compilation to final plans**
  - Calls `compile_bundles_list(bundles_list_output_a)` to obtain `EntityBundlesListFinal`.
    - Internally:
      - For each `EntityBundleDirectionsA`, builds `EntityBundleDirectionsFinal` with **deterministic required fields** per direction type (guest/business/product/compound/platform).
      - Encodes heuristics based on `objective` and `riskFlags` to decide which fields must be extracted downstream.
  - Saves compiled bundles as an artifact:
    - `save_json_artifact(..., "research_directions_compiled_bundles_list", suffix=f"{episode_url_slug}_{timestamp}")`.

- **Output / state update**
  - Returns: `{ "research_directions": compiled_bundles_list }`.

**Key properties**
- This node converts from **validated, connected candidates** → **executable research plans** with deterministic field requirements.
- Output is the primary input to `entity_research_graphs.py` downstream.

---

### Graph Topology

Builder: `build_entity_research_directions_builder() -> StateGraph`

- **Nodes**
  - `"seed_extraction"` → `seed_extraction_node`
  - `"candidate_sources"` → `candidate_sources_node`
  - `"generate_research_directions"` → `generate_research_directions_node`
  - `"persist_candidates"` → `persist_candidates_node`
  - `"persist_research_plans"` → `persist_research_plans_node`

- **Edges**
  - Entry: `START` → `"seed_extraction"`
  - `"seed_extraction"` → `"candidate_sources"`
  - `"candidate_sources"` → `"persist_candidates"`
  - `"candidate_sources"` → `"generate_research_directions"`
  - `"generate_research_directions"` → `"persist_research_plans"`
  - `"generate_research_directions"` → `END`

Notes:
- Persistence nodes (`persist_candidates`, `persist_research_plans`) are **currently on the graph** but their exact outputs are not strictly required by later nodes in this module.
- The graph is compiled with a process‑wide `store` and `checkpointer` obtained from `get_persistence()`, but **checkpoint namespace** is controlled at runtime via `config["configurable"]["checkpoint_ns"]` (to be used by API layer or LangSmith).

---

### External Dependencies and Integration Points

- **LangGraph / LangChain**
  - `StateGraph`, `CompiledStateGraph`, `RunnableConfig`.
  - `create_agent` from `langchain.agents` with `response_format=ProviderStrategy(...)`.
  - `SummarizationMiddleware` for long‑running validation loops.

- **Persistence**
  - `get_persistence()` from `human_upgrade/persistence/checkpointer_and_store.py`:
    - Supplies `BaseStore` and `BaseCheckpointSaver` for the compiled graph.
    - Intended to be shared with downstream graphs for **thread‑aware execution**.
  - `persist_candidates_node`, `persist_research_plans_node` from `human_upgrade/intel_mongo_nodes.py`:
    - Writes candidate entities and research plans into MongoDB.
    - Likely uses `_humanupgrade_db` and explicit intel collections (not detailed here).

- **Artifacts and observability**
  - `save_json_artifact` and `save_text_artifact` from `human_upgrade/utils/artifacts.py`:
    - Used to persist intermediate and compiled outputs under `newest_research_outputs/...`.
    - Supports offline inspection and debugging.

---

### How This Graph Feeds Other Subsystems

- **Downstream graphs**
  - `entity_research_graphs.py`
    - Consumes `EntityBundlesListFinal` (per bundle) produced here.
    - Uses `bundle.bundleId` and direction‑specific plans to orchestrate research agents per direction.
  - `extraction_graph.py`
    - Does not call this graph directly, but operates on:
      - `plan_doc`s created from `research_directions` via `persist_research_plans_node`.
      - `candidate_run_doc` created from earlier candidate runs.

- **Database / GraphQL**
  - Candidates and research plans persisted by this graph are later used by:
    - MongoDB intel collections (via `intel_mongo_nodes`).
    - GraphQL seeding logic in `extraction_graph.py` (through plan documents and final reports).

---

### Open Questions / Design Notes (for future FastAPI integration)

- **Invocation boundaries**
  - Should the API expose this graph as:
    - A **single‑shot endpoint**: episode payload → `research_directions` + persisted IDs?
    - Or also support **resume/fork** semantics via LangSmith threads and checkpoint IDs?

- **Episode payload contract**
  - The `episode` dict is currently free‑form. For an external API, we likely want a typed model such as `EpisodeIngestionRequest` that guarantees:
    - `episodePageUrl: str`
    - `webPageSummary: str`
    - Optional metadata (episodeId, showId, etc.).

- **Error propagation**
  - Current state uses a single `error: str` field and some ad‑hoc logging.
  - For API usage, we may want:
    - A structured `errors: List[str]` field (similar to `extraction_graph`).
    - Clear mapping from node‑level failures → HTTP error codes vs. retriable states.

- **Run identifiers**
  - `intel_run_id` / `intel_pipeline_version` are present but not yet first‑class:
    - API may define how to generate/propagate them (e.g., from request headers or LangSmith run IDs).

This file is intended as a **living analysis document**; future passes can link it to:
- `.cursor/rules` entries for this graph.
- API endpoint specs and example payloads.
- Specific LangSmith run configuration (thread IDs, checkpoint namespaces) once the FastAPI layer is defined.


