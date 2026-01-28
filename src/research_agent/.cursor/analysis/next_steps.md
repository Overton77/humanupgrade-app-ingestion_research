## Next Steps – Research Pipeline & API Integration

### 1. Integrate `think_tool` into Direction Agent Tools

- **Goal**: Align the actual tools list with the prompt strategy that mandates `think_tool` as the first action and core planning primitive.
- **Actions**:
  - Add `think_tool` to `ALL_RESEARCH_TOOLS` in `entity_research_graphs.py` (and/or a dedicated `PLANNING_TOOLS` list that is included in `ALL_RESEARCH_TOOLS`).
  - Validate via a small test run that:
    - The first tool call is `think_tool`.
    - `required_fields_status`, `current_focus`, `open_questions`, and `last_plan` are updated.
    - `get_reminder_research_prompt` reflects these updates correctly.

---

### 2. FastAPI Layer for Graph Invocation

- **Goal**: Expose the three main graphs behind stable HTTP APIs with LangSmith/thread-aware configs.
- **Endpoints to design**:
  - `POST /intel/candidates-and-directions`: invoke `make_entity_research_directions_graph` with an episode payload.
  - `POST /intel/research-bundle`: invoke `make_bundle_research_graph` for one bundle.
  - `POST /intel/extraction`: invoke `run_structured_seed_extraction` with `plan_id` and `run_id`.
  - `POST /intel/workflow/full`: orchestrate full pipeline (episode → candidates/directions → research → extraction).
- **LangSmith / checkpoint integration**:
  - Each endpoint should accept optional `thread_id` and/or `checkpoint_ns` to:
    - Resume from an existing thread.
    - Fork from a specific checkpoint.
  - Add helper endpoints to list runs/threads/checkpoints for introspection.

---

### 3. AWS Knowledge Base for Entity Summaries (Vector Store Layer)

- **Goal**: Create a **searchable knowledge base** for entity summaries (Person, Business, Product, Compound) derived from final reports, for downstream QA and retrieval.
- **Questions to resolve**:
  - Per-entity-type vs unified index:
    - Option A: Separate collections/indexes per type (`person_kb`, `business_kb`, `product_kb`, `compound_kb`).
    - Option B: Single index with `entity_type` filter and `entity_key` metadata.
  - Chunking strategy:
    - Use final synthesized reports from `entity_research_graphs` as base documents.
    - Decide whether to:
      - Store full report per entity (no chunking, rely on long-context).
      - Or chunk by logical sections (identity, ingredients, mechanisms, etc.).
  - Metadata and keys:
    - `entity_key` (person:/business:/product:/compound:).
    - `bundle_id`, `plan_id`, `run_id`, `episode_id`, `episode_url`.
    - Direction type (GUEST/BUSINESS/PRODUCT/COMPOUND).
- **Integration point**:
  - Likely a **new node/subgraph after extraction** that:
    - Reads final reports (or structured seed outputs).
    - Writes embeddings + metadata into AWS Knowledge Base (e.g., Bedrock KB or OpenSearch-based index).

---

### 4. Provenance-First Design for Knowledge Base

- **Goal**: Ensure every KB entry can be traced back through the pipeline.
- **Decisions**:
  - Use the same `SeedProvenanceUpsertInput` model as a template for KB metadata:
    - `plan_id`, `bundle_id`, `run_id`, `execution_run_id`, `pipeline_version`, `episode_id`, `episode_url`.
    - `direction_type` (for GUEST/BUSINESS/PRODUCT/COMPOUND).
    - `final_report_paths` (for offline inspection).
  - Make KB entries **append-only** with versioning:
    - e.g., `kb_version`, `seed_version`, `indexed_at`.

---

### 5. Observability and Artifacts Strategy

- **Goal**: Standardize what gets saved where for debugging and inspection.
- **Actions**:
  - Align artifact naming across graphs:
    - Candidates & directions → `newest_research_outputs/candidates_and_directions/...`
    - Research reports → `agent_files_current/...` plus summary artifacts per bundle.
    - Extraction → `newest_research_outputs/seed_extraction/...`
    - KB indexing → `newest_research_outputs/kb_index/...` (planned).
  - Add a small internal dashboard or CLI utility to:
    - List recent runs and show their artifacts.
    - Drill into a given `plan_id` or `bundle_id`.

---

### 6. Future: Automated Tests and Regression Harness

- **Goal**: Create a repeatable test harness for the full pipeline.
- **Ideas**:
  - Golden episodes:
    - Pick 3–5 representative episodes with known entities/products/compounds.
    - Run full pipeline and snapshot key outputs:
      - Connected bundles.
      - Research directions.
      - Final reports.
      - Extraction outputs.
      - Seeded entities in GraphQL.
  - Regression checks:
    - Ensure entity counts and key fields stay within expected ranges.
    - Flag large deltas as potential regressions (not necessarily failures).

---

### 7. Rich Agent Memory: Database + Podcast Context

- **Goal**: Give the research/ingestion agents **precise, durable memory** of:
  - Current entities in the database (businesses, products, compounds, guests).
  - Past research runs and their outcomes.
  - Canonical context about the Human Upgrade podcast (show-level metadata, recurring patterns, exclusions).
- **Approach options**:
  - **Targeted injection**:
    - Build small helper functions that:
      - Query MongoDB / GraphQL for entities relevant to the current bundle/episode.
      - Query the Postgres checkpointer store for past runs for the same bundle/episode/entity.
    - Inject this data into the direction agent’s `entity_context` and/or as additional system messages.
  - **LangMem / memory manager**:
    - Use a dedicated memory manager that:
      - Writes summaries of each run (per entity/bundle) into a long-term store.
      - Retrieves relevant memories by `entity_key`, `bundle_id`, `episode_id`, or topic.
    - Integrate with the direction agent via middleware or pre-run enrichment step.
- **Concrete steps**:
  - Design a **memory schema** (what fields we store: entities, fields covered, key citations, last updated).
  - Implement a small **“memory fetch” node or tool** used at the start of direction runs:
    - Reads from Postgres store + Mongo/GraphQL.
    - Populates `entity_context` and/or separate `memory_context` in `DirectionAgentState`.

---

### 8. Worker-Based Execution for FastAPI Endpoints

- **Goal**: Ensure API endpoints are **non-blocking** and scalable by delegating long-running graph executions to worker processes.
- **Design**:
  - FastAPI layer:
    - Endpoints accept requests (episode payloads, plan/run IDs, workflow configs).
    - Enqueue a **task/message** onto a queue (e.g., SQS, SNS, Redis, RabbitMQ, or managed service).
    - Immediately return a job ID / run ID and possibly a preliminary LangSmith URL.
  - Worker processes:
    - Run in a separate service (likely on AWS ECS) that:
      - Dequeues tasks.
      - Instantiates the appropriate graph (candidates+directions, research bundles, extraction, or full workflow).
      - Runs the graph with appropriate `thread_id`/`checkpoint_ns` and persists results.
  - Status + results:
    - Additional API endpoints to:
      - Check job status (pending/running/succeeded/failed).
      - Fetch run metadata and key outputs (final reports, extractions, seeded entity IDs).
- **Tech decisions to make**:
  - Task queue / message bus:
    - e.g., AWS SQS, SNS + SQS fanout, or a hosted queue (e.g., CloudAMQP, Redis Streams).
  - Containerization + orchestration:
    - Likely **AWS ECS** with Fargate or EC2 launch types.
  - How LangSmith is wired in (per-worker or external ingestion).

---

### 9. Transcript-Centric Claims & Protocols Pipeline

- **Goal**: Extend the ingestion system to process **episode transcripts**, extracting:
  - Claims.
  - References to trials / case studies.
  - Protocols (dosages, regimens, stacks).
- **High-level pipeline**:
  1. **Transcript ingestion**:
     - Normalize raw transcripts (segment by speaker/section).
  2. **Claims & evidence extraction**:
     - New graph/agents that:
       - Extract structured claims, each linked to:
         - Speaker, timecode, entities (guest, product, compound).
         - Any explicit references to trials/case studies (with URLs/PMIDs when possible).
  3. **Protocol extraction**:
     - Extract structured protocols:
       - Ingredients/compounds, dosages, timing, contraindications, goals.
  4. **Research on claims/protocols**:
     - Optional follow-on research agents that:
       - Validate claims against external literature.
       - Attach confidence scores and references.
  5. **Persistence & KB integration**:
     - Save structured outputs to the database (Mongo/GraphQL models for claims, trials, protocols).
     - Generate AWS Knowledge Base documents for:
       - Claims.
       - Protocols.
       - Trial references (where available).
     - Combine these with **entity summaries from previous workflows** to create:
       - A **master episode summary** ready for the client web app.
       - Store that master summary in the AWS Knowledge Base with strong provenance.

---

### 10. Minimal Frontend Interface for Research/Ingestion

- **Goal**: Provide a small internal UI to **inspect and control** the research/ingestion system.
- **Core features**:
  - **Run browser**:
    - List current and past research runs (candidates/directions, bundle research, extraction, transcript pipeline).
    - Filter by episode, bundle, entity type, status, and date.
  - **Run detail view**:
    - Show key artifacts:
      - Connected bundles.
      - Directions and plans.
      - Final reports (per direction).
      - Extraction outputs and seeded entities.
      - Transcript-derived claims/protocols (when implemented).
    - Surface links to LangSmith runs and raw artifacts on disk/S3.
  - **Control panel**:
    - Invoke new runs (per graph or full workflow) from a form.
    - Fork resumes from a given thread/checkpoint.
    - Rerun failed steps with adjusted parameters (e.g., different model, web budget).
- **Implementation sketch**:
  - Minimal SPA or server-rendered app:
    - Could live alongside the API as an admin-only interface (auth required).
  - Uses the same FastAPI endpoints + additional admin endpoints to:
    - Query MongoDB/GraphQL for runs and entities.
    - Read artifacts metadata (JSON indexes) rather than raw files when possible.



