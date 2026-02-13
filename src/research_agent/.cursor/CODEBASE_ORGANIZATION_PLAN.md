# Research Agent Codebase Organization Plan

## Executive Summary

This document outlines the comprehensive reorganization of the `research_agent` codebase to eliminate the legacy `human_upgrade/` module and establish a clean, scalable architecture that supports:

1. **FastAPI Server Layer** (3 servers: Graph Execution, Mission Control, Memory/Thread Management)
2. **Distributed Task Execution** (Taskiq + RabbitMQ + Redis + MongoDB state)
3. **MongoDB Persistence** (Beanie ODM for all research artifacts)
4. **Neo4j Knowledge Graph Ingestion** (via GraphQL client)
5. **LangGraph Memory System** (Semantic, Episodic, Procedural via PostgreSQL Store)

**Primary Goal**: Flatten `human_upgrade/` into a logical, maintainable structure within `research_agent/` that cleanly separates concerns and supports multiple FastAPI servers.

---

## Current State Analysis

### Existing Directory Structure

```
ingestion/src/research_agent/
├── human_upgrade/                    # LEGACY MODULE TO ELIMINATE
│   ├── graphs/                       # LangGraph state graphs
│   │   ├── entity_candidates_connected_graph.py
│   │   ├── research_plan_graph.py
│   │   ├── agent_instance_factory.py
│   │   ├── memory/
│   │   │   └── langmem_manager.py
│   │   └── nodes/                    # Graph node implementations
│   ├── prompts/                      # Prompt templates
│   │   ├── candidates_prompts.py
│   │   ├── research_plan_prompts.py
│   │   ├── sub_agent_prompt_builders.py
│   │   └── ...
│   ├── structured_outputs/           # Pydantic output models
│   │   ├── candidates_outputs.py
│   │   ├── research_plans_outputs.py
│   │   └── file_outputs.py
│   ├── tools/                        # LangChain tools
│   │   ├── web_search_tools.py
│   │   ├── file_system_tools.py
│   │   └── ...
│   ├── utils/                        # Helper functions
│   │   ├── candidate_graph_helpers.py
│   │   ├── entity_slice_inputs.py
│   │   ├── formatting.py
│   │   └── ...
│   ├── persistence/                  # Checkpointer + store
│   │   └── checkpointer_and_store.py
│   ├── base_models.py               # LLM model definitions
│   └── logger.py
├── mission_queue/                    # NEW: DAG execution (keep)
│   ├── mission_dag_builder.py
│   ├── scheduler_in_memory.py
│   ├── worker.py
│   └── schemas.py
├── models/                           # NEW: MongoDB Beanie models (keep)
│   └── mongo/
│       ├── research/
│       ├── candidates/
│       ├── entities/
│       └── domains/
├── services/                         # NEW: MongoDB services (keep)
│   └── mongo/
│       ├── candidates/
│       └── research/
├── infrastructure/                   # NEW: Infrastructure (keep)
│   ├── storage/
│   │   └── mongo/
│   ├── document_processing/
│   └── embeddings/
├── clients/                          # GraphQL, LangSmith clients (keep)
├── agent_tools/                      # Legacy tools (needs refactor)
└── server.py                         # Prototype FastAPI server (needs expansion)
```

### Problems with Current Structure

1. **`human_upgrade/` is a confusing legacy name** (does not reflect biotech research purpose)
2. **Mixed concerns** (graphs, prompts, tools, utils all in one module)
3. **No clear server organization** (single `server.py` prototype)
4. **Duplicate tool definitions** (`agent_tools/` vs `human_upgrade/tools/`)
5. **Inconsistent naming** (`human_upgrade.structured_outputs.research_plans_outputs` is verbose)
6. **No clear API layer** (no separation between internal models and API schemas)
7. **Memory module buried** (`human_upgrade/graphs/memory/` should be top-level)

---

## Proposed New Structure

### Overview: 5-Layer Architecture

```
research_agent/
├── api/                    # FastAPI servers (Layer 1: External Interface)
├── graphs/                 # LangGraph orchestration (Layer 2: Research Logic)
├── agents/                 # Worker agent implementations (Layer 3: Execution)
├── services/               # Business logic + DB operations (Layer 4: Services)
├── infrastructure/         # External integrations (Layer 5: Infrastructure)
├── models/                 # Data models (cross-layer)
├── memory/                 # LangGraph Store + LangMem (cross-layer)
└── shared/                 # Shared utilities (cross-layer)
```

---

## Detailed New Structure

```
ingestion/src/research_agent/
│
├── api/                                      # Layer 1: FastAPI Servers
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── dependencies.py               # Shared FastAPI dependencies
│   │   ├── middleware.py                 # CORS, auth, logging
│   │   ├── exceptions.py                 # Custom exception handlers
│   │   └── responses.py                  # Standard response schemas
│   │
│   ├── graph_execution/                  # Server 1: Graph Execution API
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI app
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── entity_discovery.py       # POST/WS /graphs/entity-discovery/*
│   │   │   ├── research_planning.py      # POST/WS /graphs/research-plan/*
│   │   │   └── health.py                 # GET /health, /ready
│   │   ├── schemas/                      # Request/response models
│   │   │   ├── __init__.py
│   │   │   ├── entity_discovery.py       # EntityDiscoveryRequest/Response
│   │   │   └── research_planning.py      # ResearchPlanRequest/Response
│   │   └── websockets/
│   │       ├── __init__.py
│   │       ├── graph_stream.py           # WebSocket graph streaming
│   │       └── connection_manager.py     # WS connection pool
│   │
│   ├── mission_control/                  # Server 2: Mission Control API
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── missions.py               # POST/GET /missions/*
│   │   │   ├── runs.py                   # GET/POST /missions/runs/*
│   │   │   ├── tasks.py                  # GET /tasks/{task_id}
│   │   │   └── plans.py                  # GET/POST /plans/*
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── missions.py               # MissionCreate/Read/Update
│   │   │   ├── runs.py                   # RunStatus/Progress
│   │   │   └── tasks.py                  # TaskDefinition/Status
│   │   └── services/                     # Mission orchestration logic
│   │       ├── __init__.py
│   │       ├── mission_orchestrator.py   # Build DAG, enqueue tasks
│   │       └── task_monitor.py           # Monitor task progress
│   │
│   ├── memory_and_threads/               # Server 3: Memory & Thread API
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── threads.py                # GET/POST /threads/*
│   │   │   ├── checkpoints.py            # GET/POST /threads/{id}/checkpoints
│   │   │   ├── memory.py                 # GET/POST /store/memories/*
│   │   │   └── recall.py                 # POST /store/recall (semantic search)
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── threads.py
│   │       ├── checkpoints.py
│   │       └── memory.py
│   │
│   └── mongodb_models/                   # Server 4: MongoDB Model API (CRUD)
│       ├── __init__.py
│       ├── main.py
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── research_plans.py         # CRUD for ResearchMissionPlanDoc
│       │   ├── research_runs.py          # CRUD for ResearchRunDoc
│       │   ├── candidates.py             # CRUD for candidate docs
│       │   └── entities.py               # CRUD for entity docs
│       └── schemas/
│           ├── __init__.py
│           └── mongo_models.py           # API-friendly Pydantic schemas
│
├── graphs/                                # Layer 2: LangGraph Orchestration
│   ├── __init__.py
│   ├── entity_discovery/
│   │   ├── __init__.py
│   │   ├── graph.py                      # Main graph builder
│   │   ├── nodes/                        # Node implementations
│   │   │   ├── __init__.py
│   │   │   ├── seed_extraction.py
│   │   │   ├── official_sources.py
│   │   │   ├── domain_catalogs.py
│   │   │   ├── candidate_slices.py
│   │   │   └── persistence.py            # Beanie persistence nodes
│   │   ├── state.py                      # Graph state definitions
│   │   └── helpers.py                    # Graph-specific helpers
│   │
│   ├── research_planning/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── initial_plan.py
│   │   │   ├── source_expansion.py
│   │   │   ├── attach_sources.py
│   │   │   └── assemble_final.py
│   │   ├── state.py
│   │   └── helpers.py
│   │
│   ├── entity_extraction/                # Future: Re-implemented extraction graph
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── parse_reports.py
│   │   │   ├── extract_entities.py
│   │   │   ├── extract_relationships.py
│   │   │   └── neo4j_ingestion.py
│   │   └── state.py
│   │
│   └── common/                           # Shared graph utilities
│       ├── __init__.py
│       ├── persistence_nodes.py          # Generic Beanie persistence nodes
│       ├── checkpointing.py              # Checkpoint + store config
│       └── error_handling.py             # Graph error recovery
│
├── agents/                                # Layer 3: Worker Agent Execution
│   ├── __init__.py
│   ├── factory/
│   │   ├── __init__.py
│   │   ├── builder.py                    # build_worker_agent()
│   │   ├── runner.py                     # run_worker_once()
│   │   └── middleware.py                 # Summarization, dynamic prompts
│   │
│   ├── types/                            # Agent type implementations
│   │   ├── __init__.py
│   │   ├── business_identity.py          # BusinessIdentityAndLeadershipAgent
│   │   ├── person_bio.py                 # PersonBioAndAffiliationsAgent
│   │   ├── ecosystem_mapper.py
│   │   ├── product_spec.py
│   │   ├── claims_extractor.py
│   │   ├── case_study_harvest.py
│   │   └── ...                           # All 11 agent types
│   │
│   ├── state/
│   │   ├── __init__.py
│   │   └── worker_agent_state.py         # WorkerAgentState TypedDict
│   │
│   ├── prompts/                          # Agent prompt builders
│   │   ├── __init__.py
│   │   ├── initial/                      # Initial system prompts
│   │   │   ├── __init__.py
│   │   │   ├── business_identity.py
│   │   │   ├── person_bio.py
│   │   │   └── generic.py
│   │   ├── reminder/                     # Reminder prompts (w/ telemetry)
│   │   │   ├── __init__.py
│   │   │   ├── business_identity.py
│   │   │   └── generic.py
│   │   └── final_synthesis/             # Final report synthesis prompts
│   │       ├── __init__.py
│   │       ├── business_identity.py
│   │       └── generic.py
│   │
│   └── tools/                            # Agent tool configurations
│       ├── __init__.py
│       ├── tool_registry.py              # Central tool registry
│       ├── default_tool_maps.py          # Default tools per agent type
│       └── tool_selection.py             # Dynamic tool selection logic
│
├── orchestration/                         # Layer 3.5: Mission DAG Execution
│   ├── __init__.py
│   ├── dag/
│   │   ├── __init__.py
│   │   ├── builder.py                    # build_mission_dag()
│   │   ├── schemas.py                    # MissionDAG, TaskDefinition
│   │   └── task_ids.py                   # Deterministic task ID builders
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   ├── in_memory.py                  # In-memory scheduler (MVP)
│   │   ├── mongo_backed.py               # Future: Mongo-backed scheduler
│   │   └── events.py                     # Event schemas (TASK_SUCCEEDED, etc.)
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── taskiq_worker.py              # Taskiq worker implementation
│   │   ├── handlers/
│   │   │   ├── __init__.py
│   │   │   ├── instance_run.py           # Handle INSTANCE_RUN task
│   │   │   └── substage_reduce.py        # Handle SUBSTAGE_REDUCE task
│   │   └── redis_consumer.py             # Redis stream consumer
│   │
│   └── queue/
│       ├── __init__.py
│       ├── taskiq_broker.py              # Taskiq broker setup
│       └── redis_streams.py              # Redis stream utilities
│
├── services/                              # Layer 4: Business Logic + DB Operations
│   ├── __init__.py
│   ├── mongo/
│   │   ├── __init__.py
│   │   ├── research/                     # Research plan/run services
│   │   │   ├── __init__.py
│   │   │   ├── plan_service.py           # CRUD + queries for plans
│   │   │   └── run_service.py            # CRUD + queries for runs
│   │   ├── candidates/                   # Candidate discovery services
│   │   │   ├── __init__.py
│   │   │   ├── seed_service.py
│   │   │   ├── official_sources_service.py
│   │   │   ├── domain_catalog_service.py
│   │   │   └── connected_candidates_service.py
│   │   ├── entities/                     # Entity services
│   │   │   ├── __init__.py
│   │   │   ├── candidate_entity_service.py
│   │   │   └── dedupe_group_service.py
│   │   └── common/
│   │       ├── __init__.py
│   │       └── base_service.py           # Generic CRUD operations
│   │
│   ├── neo4j/                            # Future: Neo4j services
│   │   ├── __init__.py
│   │   ├── entity_ingestion_service.py   # Ingest entities to Neo4j
│   │   └── relationship_service.py       # Manage relationships
│   │
│   └── graphql/                          # GraphQL client services
│       ├── __init__.py
│       ├── client.py                     # Ariadne-generated client
│       └── mutations.py                  # Common mutation builders
│
├── memory/                                # Cross-Layer: Memory System
│   ├── __init__.py
│   ├── langmem/
│   │   ├── __init__.py
│   │   ├── manager.py                    # LangMem SDK wrapper
│   │   ├── schemas.py                    # Memory schemas (Semantic, Episodic, etc.)
│   │   ├── namespaces.py                 # Namespace routing logic
│   │   └── extraction.py                 # Memory extraction workflows
│   │
│   ├── store/
│   │   ├── __init__.py
│   │   ├── checkpointer.py               # LangGraph checkpointer config
│   │   ├── postgres_store.py             # AsyncPostgresStore config
│   │   └── recall.py                     # Memory recall utilities
│   │
│   └── tools/
│       ├── __init__.py
│       └── memory_tools.py               # LangChain tools for memory recall
│
├── models/                                # Cross-Layer: Data Models
│   ├── __init__.py
│   ├── base/
│   │   ├── __init__.py
│   │   ├── enums.py                      # Shared enums
│   │   └── base_models.py                # Base Pydantic models
│   │
│   ├── mongo/                            # MongoDB Beanie models
│   │   ├── __init__.py
│   │   ├── research/
│   │   │   ├── __init__.py
│   │   │   ├── docs/                     # Document models
│   │   │   │   ├── __init__.py
│   │   │   │   ├── research_mission_plans.py
│   │   │   │   ├── research_runs.py
│   │   │   │   └── outputs.py
│   │   │   ├── embedded/                 # Embedded models
│   │   │   │   ├── __init__.py
│   │   │   │   ├── plan_models.py
│   │   │   │   └── stage_models.py
│   │   │   └── enums.py
│   │   │
│   │   ├── candidates/
│   │   │   ├── __init__.py
│   │   │   ├── docs/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── candidate_seeds.py
│   │   │   │   ├── official_starter_sources.py
│   │   │   │   ├── connected_candidates.py
│   │   │   │   └── candidate_sources_connected.py
│   │   │   └── embedded/
│   │   │
│   │   ├── entities/
│   │   │   ├── __init__.py
│   │   │   ├── docs/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── candidate_entities.py
│   │   │   │   ├── dedupe_groups.py
│   │   │   │   ├── candidate_runs.py
│   │   │   │   └── artifacts.py
│   │   │   └── embedded/
│   │   │
│   │   └── domains/
│   │       ├── __init__.py
│   │       ├── docs/
│   │       │   ├── __init__.py
│   │       │   └── domain_catalog_sets.py
│   │       └── embedded/
│   │
│   ├── api/                              # API schemas (FastAPI request/response)
│   │   ├── __init__.py
│   │   ├── common.py                     # Common API schemas
│   │   ├── graph_execution.py
│   │   ├── mission_control.py
│   │   └── memory.py
│   │
│   └── graph/                            # Graph-specific models
│       ├── __init__.py
│       ├── candidates.py                 # Entity discovery structured outputs
│       ├── research_plans.py             # Research planning structured outputs
│       ├── agent_plans.py                # Agent instance plan models
│       └── slicing.py                    # Slicing models
│
├── tools/                                 # Cross-Layer: LangChain Tools
│   ├── __init__.py
│   ├── web/
│   │   ├── __init__.py
│   │   ├── tavily_search.py              # Tavily search tool
│   │   ├── tavily_extract.py             # Tavily extract tool
│   │   ├── exa_search.py                 # Exa search tool
│   │   └── wikipedia.py                  # Wikipedia tool
│   │
│   ├── browser/
│   │   ├── __init__.py
│   │   └── playwright_browser.py         # Playwright browser tool
│   │
│   ├── filesystem/
│   │   ├── __init__.py
│   │   ├── read_file.py
│   │   ├── write_file.py
│   │   └── workspace_helpers.py          # Workspace path helpers
│   │
│   ├── scholarly/
│   │   ├── __init__.py
│   │   ├── pubmed.py                     # PubMed tool
│   │   ├── semantic_scholar.py           # Semantic Scholar tool
│   │   └── clinical_trials.py            # ClinicalTrials.gov tool
│   │
│   ├── context/
│   │   ├── __init__.py
│   │   └── summarize.py                  # Context summarization tool
│   │
│   └── registry.py                       # Central tool registry
│
├── prompts/                               # Cross-Layer: Prompt Templates
│   ├── __init__.py
│   ├── graphs/
│   │   ├── __init__.py
│   │   ├── entity_discovery/
│   │   │   ├── __init__.py
│   │   │   ├── seed_extraction.py
│   │   │   ├── official_sources.py
│   │   │   ├── domain_catalogs.py
│   │   │   └── candidate_slices.py
│   │   └── research_planning/
│   │       ├── __init__.py
│   │       ├── initial_plan.py
│   │       ├── source_expansion.py
│   │       └── attach_sources.py
│   │
│   └── agents/                           # Agent prompts (moved to agents/prompts/)
│       └── __init__.py
│
├── infrastructure/                        # Layer 5: External Integrations
│   ├── __init__.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── mongo/
│   │   │   ├── __init__.py
│   │   │   ├── base_client.py            # PyMongo client
│   │   │   ├── biotech_research_db_beanie.py
│   │   │   └── connection_manager.py
│   │   ├── s3/
│   │   │   ├── __init__.py
│   │   │   ├── client.py                 # S3 client
│   │   │   └── artifact_storage.py       # Store reports/transcripts
│   │   └── redis/
│   │       ├── __init__.py
│   │       ├── client.py                 # Redis client
│   │       └── cache.py                  # Caching utilities
│   │
│   ├── document_processing/
│   │   ├── __init__.py
│   │   ├── docling_processor.py          # Docling PDF processing
│   │   └── chunking.py                   # Text chunking
│   │
│   ├── embeddings/
│   │   ├── __init__.py
│   │   ├── openai_embeddings.py          # OpenAI embeddings
│   │   └── batch_embeddings.py           # Batch embedding generation
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── model_registry.py             # gpt_5_mini, gpt_4_1, etc.
│   │   └── token_counting.py             # Token counting utilities
│   │
│   └── queue/
│       ├── __init__.py
│       ├── taskiq_broker.py              # Taskiq broker setup
│       └── rabbitmq_client.py            # RabbitMQ client
│
├── shared/                                # Cross-Layer: Shared Utilities
│   ├── __init__.py
│   ├── artifacts.py                      # Artifact saving (JSON, text)
│   ├── datetime_helpers.py               # UTC now, formatting
│   ├── dedupe.py                         # Deduplication helpers
│   ├── formatting.py                     # Prompt formatting
│   ├── validation.py                     # Input validation
│   ├── logging_utils.py                  # Logging configuration
│   └── constants.py                      # Shared constants
│
├── clients/                               # External API clients (keep as is)
│   ├── __init__.py
│   ├── graphql_client.py                 # Ariadne-generated GraphQL client
│   ├── langsmith_client.py               # LangSmith client
│   └── async_tavily_client.py            # Async Tavily client
│
├── config/                                # Configuration
│   ├── __init__.py
│   ├── settings.py                       # Pydantic settings (env vars)
│   └── environments/
│       ├── __init__.py
│       ├── development.py
│       ├── staging.py
│       └── production.py
│
├── scripts/                               # CLI scripts
│   ├── __init__.py
│   ├── init_db.py                        # Initialize MongoDB indexes
│   ├── run_discovery.py                  # Run entity discovery graph
│   ├── run_planner.py                    # Run research plan graph
│   ├── run_scheduler.py                  # Run scheduler
│   ├── run_worker.py                     # Run worker
│   └── test_data/                        # Test data for scripts
│       ├── __init__.py
│       └── one_thousand_roads.py
│
├── tests/                                 # Test suite
│   ├── __init__.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── graphs/
│   │   ├── agents/
│   │   ├── services/
│   │   └── tools/
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_entity_discovery_graph.py
│   │   ├── test_research_plan_graph.py
│   │   └── test_mission_dag_execution.py
│   └── fixtures/
│       ├── __init__.py
│       ├── mongo_fixtures.py
│       └── graph_fixtures.py
│
├── .cursor/                               # Cursor AI context
│   ├── AGENTS.md
│   ├── CODEBASE_ORGANIZATION_PLAN.md
│   ├── PROJECT_GOALS_AGENT.md
│   └── text_diagrams/
│
├── __init__.py
└── README.md
```

---

## Migration Strategy (Step-by-Step)

### Phase 1: Foundation (Week 1)

**Goal**: Set up new directory structure + move non-breaking modules

1. **Create new directory structure**:
   ```bash
   mkdir -p api/{common,graph_execution,mission_control,memory_and_threads,mongodb_models}
   mkdir -p graphs/{entity_discovery,research_planning,common}
   mkdir -p agents/{factory,types,state,prompts,tools}
   mkdir -p orchestration/{dag,scheduler,workers,queue}
   mkdir -p services/{mongo,neo4j,graphql}
   mkdir -p memory/{langmem,store,tools}
   mkdir -p models/{base,mongo,api,graph}
   mkdir -p tools/{web,browser,filesystem,scholarly,context}
   mkdir -p prompts/{graphs,agents}
   mkdir -p shared
   mkdir -p config/{environments}
   mkdir -p scripts/{test_data}
   mkdir -p tests/{unit,integration,fixtures}
   ```

2. **Move low-risk modules first** (no import dependencies):
   ```bash
   # Utilities
   mv human_upgrade/utils/datetime_helpers.py shared/datetime_helpers.py
   mv human_upgrade/utils/dedupe.py shared/dedupe.py
   mv human_upgrade/utils/formatting.py shared/formatting.py
   mv human_upgrade/utils/artifacts.py shared/artifacts.py
   
   # Logging
   mv human_upgrade/logger.py shared/logging_utils.py
   
   # Constants
   mv human_upgrade/constants/ shared/constants/
   
   # Base models (LLMs)
   mv human_upgrade/base_models.py infrastructure/llm/model_registry.py
   ```

3. **Update imports in moved files**:
   ```python
   # Before:
   from research_agent.human_upgrade.utils.artifacts import save_json_artifact
   
   # After:
   from research_agent.shared.artifacts import save_json_artifact
   ```

### Phase 2: Models & Schemas (Week 1-2)

**Goal**: Reorganize all Pydantic models

1. **Move structured outputs → models/graph/**:
   ```bash
   mv human_upgrade/structured_outputs/candidates_outputs.py models/graph/candidates.py
   mv human_upgrade/structured_outputs/research_plans_outputs.py models/graph/research_plans.py
   mv human_upgrade/structured_outputs/file_outputs.py models/graph/file_outputs.py
   ```

2. **Keep MongoDB models as is** (already well-organized in `models/mongo/`)

3. **Create API schemas** (new):
   ```python
   # models/api/graph_execution.py
   from pydantic import BaseModel
   from typing import List, Optional
   
   class EntityDiscoveryRequest(BaseModel):
       query: str
       starter_sources: List[str] = []
       starter_content: str = ""
   
   class EntityDiscoveryResponse(BaseModel):
       candidate_sources: dict  # CandidateSourcesConnected serialized
       run_id: str
       pipeline_version: str
   ```

4. **Update all imports**:
   ```python
   # Before:
   from research_agent.human_upgrade.structured_outputs.candidates_outputs import ConnectedCandidates
   
   # After:
   from research_agent.models.graph.candidates import ConnectedCandidates
   ```

### Phase 3: Tools (Week 2)

**Goal**: Consolidate and organize all LangChain tools

1. **Move web search tools**:
   ```bash
   mv human_upgrade/tools/web_search_tools.py tools/web/tavily_search.py
   # Split into separate files: tavily_search.py, tavily_extract.py, wikipedia.py
   ```

2. **Move filesystem tools**:
   ```bash
   mv human_upgrade/tools/file_system_tools.py tools/filesystem/
   # Split: read_file.py, write_file.py, workspace_helpers.py
   ```

3. **Create tool registry**:
   ```python
   # tools/registry.py
   from typing import Dict, List
   from langchain.tools import BaseTool
   from .web.tavily_search import tavily_search_validation
   from .web.tavily_extract import tavily_extract_validation
   # ... import all tools
   
   TOOL_REGISTRY: Dict[str, BaseTool] = {
       "search.tavily": tavily_search_validation,
       "extract.tavily": tavily_extract_validation,
       # ... register all tools
   }
   
   def get_tools(tool_names: List[str]) -> List[BaseTool]:
       return [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]
   ```

4. **Eliminate duplicate `agent_tools/`**:
   - Merge any unique tools into `tools/`
   - Delete `agent_tools/` directory

### Phase 4: Prompts (Week 2-3)

**Goal**: Organize all prompt templates

1. **Move graph prompts**:
   ```bash
   mv human_upgrade/prompts/candidates_prompts.py prompts/graphs/entity_discovery/
   # Split into: seed_extraction.py, official_sources.py, domain_catalogs.py, candidate_slices.py
   
   mv human_upgrade/prompts/research_plan_prompts.py prompts/graphs/research_planning/
   # Split into: initial_plan.py, source_expansion.py, attach_sources.py
   ```

2. **Move agent prompts**:
   ```bash
   mv human_upgrade/prompts/sub_agent_prompt_builders.py agents/prompts/initial/
   mv human_upgrade/prompts/sub_agent_final_synthesis_prompt_builders.py agents/prompts/final_synthesis/
   ```

3. **Update prompt imports**:
   ```python
   # Before:
   from research_agent.human_upgrade.prompts.candidates_prompts import PROMPT_NODE_SEED_ENTITY_EXTRACTION
   
   # After:
   from research_agent.prompts.graphs.entity_discovery.seed_extraction import PROMPT_NODE_SEED_ENTITY_EXTRACTION
   ```

### Phase 5: Graphs (Week 3)

**Goal**: Reorganize LangGraph implementations

1. **Move entity discovery graph**:
   ```bash
   mv human_upgrade/graphs/entity_candidates_connected_graph.py graphs/entity_discovery/graph.py
   
   # Split nodes into separate files:
   # graphs/entity_discovery/nodes/seed_extraction.py
   # graphs/entity_discovery/nodes/official_sources.py
   # graphs/entity_discovery/nodes/domain_catalogs.py
   # graphs/entity_discovery/nodes/candidate_slices.py
   # graphs/entity_discovery/nodes/persistence.py
   
   # Extract state:
   # graphs/entity_discovery/state.py (EntityIntelConnectedCandidatesAndSourcesState)
   
   # Extract helpers:
   # graphs/entity_discovery/helpers.py (_filter_catalogs_for_fanout, etc.)
   ```

2. **Move research plan graph**:
   ```bash
   mv human_upgrade/graphs/research_plan_graph.py graphs/research_planning/graph.py
   
   # Split nodes:
   # graphs/research_planning/nodes/initial_plan.py
   # graphs/research_planning/nodes/source_expansion.py
   # graphs/research_planning/nodes/attach_sources.py
   # graphs/research_planning/nodes/assemble_final.py
   ```

3. **Move agent instance factory**:
   ```bash
   mv human_upgrade/graphs/agent_instance_factory.py agents/factory/
   # Split into: builder.py, runner.py, middleware.py
   ```

4. **Move persistence/checkpointing**:
   ```bash
   mv human_upgrade/persistence/checkpointer_and_store.py memory/store/checkpointer.py
   ```

5. **Update graph imports**:
   ```python
   # Before:
   from research_agent.human_upgrade.graphs.entity_candidates_connected_graph import (
       make_entity_intel_connected_candidates_and_sources_graph
   )
   
   # After:
   from research_agent.graphs.entity_discovery.graph import (
       make_entity_intel_connected_candidates_and_sources_graph
   )
   ```

### Phase 6: Agents (Week 3-4)

**Goal**: Organize worker agent implementations

1. **Create agent factory**:
   ```bash
   # agents/factory/builder.py (build_worker_agent function)
   # agents/factory/runner.py (run_worker_once function)
   # agents/factory/middleware.py (dynamic_prompt, summarizer, after_agent)
   ```

2. **Move agent state**:
   ```bash
   mv human_upgrade/graphs/state/agent_instance_state.py agents/state/worker_agent_state.py
   ```

3. **Create agent type implementations** (optional for now):
   ```python
   # agents/types/business_identity.py
   # Future: Agent-specific configuration overrides
   ```

4. **Move tool configuration**:
   ```bash
   mv human_upgrade/utils/default_tools_by_agent_type.py agents/tools/default_tool_maps.py
   mv human_upgrade/utils/research_tools_map.py agents/tools/tool_registry.py
   ```

### Phase 7: Orchestration (Week 4)

**Goal**: Organize mission DAG + scheduler + workers

1. **Rename mission_queue → orchestration**:
   ```bash
   mv mission_queue/ orchestration/
   mv orchestration/mission_dag_builder.py orchestration/dag/builder.py
   mv orchestration/schemas.py orchestration/dag/schemas.py
   mv orchestration/scheduler_in_memory.py orchestration/scheduler/in_memory.py
   mv orchestration/worker.py orchestration/workers/taskiq_worker.py
   ```

2. **Split worker handlers**:
   ```python
   # orchestration/workers/handlers/instance_run.py (handle_instance_run)
   # orchestration/workers/handlers/substage_reduce.py (handle_substage_reduce)
   ```

3. **Move Taskiq broker**:
   ```bash
   mv taskiq_tests/setup.py orchestration/queue/taskiq_broker.py
   # Clean up taskiq_tests/ (keep only test files)
   ```

### Phase 8: Services (Week 4-5)

**Goal**: Ensure MongoDB services are well-organized

1. **Verify services/ structure** (already good):
   ```
   services/
   ├── mongo/
   │   ├── candidates/
   │   ├── research/
   │   └── common/
   ```

2. **Add Neo4j services** (future):
   ```python
   # services/neo4j/entity_ingestion_service.py
   # services/neo4j/relationship_service.py
   ```

3. **Add GraphQL client service**:
   ```python
   # services/graphql/client.py (Ariadne-generated client)
   # services/graphql/mutations.py (Common mutation builders)
   ```

### Phase 9: Memory (Week 5)

**Goal**: Organize LangMem + LangGraph Store

1. **Move memory module**:
   ```bash
   mv human_upgrade/graphs/memory/ memory/langmem/
   # Rename langmem_manager.py → manager.py
   # Rename langmem_schemas.py → schemas.py
   # Rename langmem_namespaces.py → namespaces.py
   ```

2. **Move store utilities**:
   ```bash
   # memory/store/checkpointer.py (from human_upgrade/persistence/)
   # memory/store/postgres_store.py (new: AsyncPostgresStore config)
   # memory/store/recall.py (memory recall utilities)
   ```

3. **Create memory tools** (LangChain tools for agent memory recall):
   ```python
   # memory/tools/memory_tools.py
   from langchain.tools import BaseTool
   from ..langmem.manager import recall_semantic_for_org
   
   class RecallSemanticMemoryTool(BaseTool):
       name = "recall_semantic_memory"
       description = "Recall semantic memories for an entity"
       
       async def _arun(self, entity_id: str) -> str:
           memories = await recall_semantic_for_org(entity_id)
           return str(memories)
   ```

### Phase 10: API Servers (Week 5-6)

**Goal**: Build out FastAPI server layer

1. **Create Graph Execution API**:
   ```python
   # api/graph_execution/main.py
   from fastapi import FastAPI
   from .routes import entity_discovery, research_planning, health
   
   app = FastAPI(title="Graph Execution API")
   app.include_router(entity_discovery.router)
   app.include_router(research_planning.router)
   app.include_router(health.router)
   ```

2. **Create Mission Control API**:
   ```python
   # api/mission_control/main.py
   from fastapi import FastAPI
   from .routes import missions, runs, tasks, plans
   
   app = FastAPI(title="Mission Control API")
   app.include_router(missions.router)
   app.include_router(runs.router)
   app.include_router(tasks.router)
   app.include_router(plans.router)
   ```

3. **Create Memory & Thread API**:
   ```python
   # api/memory_and_threads/main.py
   from fastapi import FastAPI
   from .routes import threads, checkpoints, memory, recall
   
   app = FastAPI(title="Memory & Thread API")
   app.include_router(threads.router)
   app.include_router(checkpoints.router)
   app.include_router(memory.router)
   app.include_router(recall.router)
   ```

4. **Create MongoDB Model API**:
   ```python
   # api/mongodb_models/main.py
   from fastapi import FastAPI
   from .routes import research_plans, research_runs, candidates, entities
   
   app = FastAPI(title="MongoDB Model API")
   app.include_router(research_plans.router)
   app.include_router(research_runs.router)
   app.include_router(candidates.router)
   app.include_router(entities.router)
   ```

5. **Implement routes** (iteratively per server)

### Phase 11: Configuration & Testing (Week 6-7)

**Goal**: Add configuration management + comprehensive tests

1. **Create settings module**:
   ```python
   # config/settings.py
   from pydantic_settings import BaseSettings
   
   class Settings(BaseSettings):
       MONGO_URI: str
       MONGO_BIOTECH_DB_NAME: str
       REDIS_URL: str
       RABBITMQ_URL: str
       NEO4J_URI: str
       OPENAI_API_KEY: str
       # ... all env vars
       
       class Config:
           env_file = ".env"
   ```

2. **Write unit tests**:
   ```python
   # tests/unit/graphs/test_entity_discovery_nodes.py
   # tests/unit/agents/test_worker_agent_factory.py
   # tests/unit/services/test_mongo_services.py
   ```

3. **Write integration tests**:
   ```python
   # tests/integration/test_entity_discovery_graph.py
   # tests/integration/test_research_plan_graph.py
   # tests/integration/test_mission_dag_execution.py
   ```

4. **Create test fixtures**:
   ```python
   # tests/fixtures/mongo_fixtures.py (Beanie test fixtures)
   # tests/fixtures/graph_fixtures.py (Mock graph states)
   ```

### Phase 12: Cleanup & Documentation (Week 7)

**Goal**: Delete human_upgrade/, update all docs

1. **Verify all imports updated**:
   ```bash
   # Search for any remaining human_upgrade imports
   grep -r "from research_agent.human_upgrade" .
   grep -r "import research_agent.human_upgrade" .
   ```

2. **Delete legacy module**:
   ```bash
   rm -rf human_upgrade/
   ```

3. **Update README.md**:
   - Document new structure
   - Update import examples
   - Add setup instructions

4. **Update AGENTS.md** (reflect new structure)

5. **Create migration guide** (MIGRATION_GUIDE.md):
   - Old imports → new imports mapping
   - Key architectural changes
   - Breaking changes (if any)

---

## Import Path Changes (Reference)

### Before → After Mapping

| **Before** | **After** |
|------------|-----------|
| `research_agent.human_upgrade.graphs.entity_candidates_connected_graph` | `research_agent.graphs.entity_discovery.graph` |
| `research_agent.human_upgrade.graphs.research_plan_graph` | `research_agent.graphs.research_planning.graph` |
| `research_agent.human_upgrade.graphs.agent_instance_factory` | `research_agent.agents.factory.builder` |
| `research_agent.human_upgrade.structured_outputs.candidates_outputs` | `research_agent.models.graph.candidates` |
| `research_agent.human_upgrade.structured_outputs.research_plans_outputs` | `research_agent.models.graph.research_plans` |
| `research_agent.human_upgrade.tools.web_search_tools` | `research_agent.tools.web` (split) |
| `research_agent.human_upgrade.prompts.candidates_prompts` | `research_agent.prompts.graphs.entity_discovery` (split) |
| `research_agent.human_upgrade.prompts.sub_agent_prompt_builders` | `research_agent.agents.prompts.initial` |
| `research_agent.human_upgrade.utils.artifacts` | `research_agent.shared.artifacts` |
| `research_agent.human_upgrade.base_models` | `research_agent.infrastructure.llm.model_registry` |
| `research_agent.human_upgrade.logger` | `research_agent.shared.logging_utils` |
| `research_agent.human_upgrade.graphs.memory.langmem_manager` | `research_agent.memory.langmem.manager` |
| `research_agent.human_upgrade.persistence.checkpointer_and_store` | `research_agent.memory.store.checkpointer` |
| `research_agent.mission_queue.mission_dag_builder` | `research_agent.orchestration.dag.builder` |
| `research_agent.mission_queue.scheduler_in_memory` | `research_agent.orchestration.scheduler.in_memory` |
| `research_agent.mission_queue.worker` | `research_agent.orchestration.workers.taskiq_worker` |

---

## Testing Strategy

### Unit Tests (Fast, isolated)

```python
# tests/unit/graphs/test_entity_discovery_nodes.py
import pytest
from research_agent.graphs.entity_discovery.nodes import seed_extraction

@pytest.mark.asyncio
async def test_seed_extraction_node():
    state = {"query": "Research Ozempic", "starter_sources": []}
    result = await seed_extraction.seed_extraction_node(state)
    assert "seed_extraction" in result
    assert result["seed_extraction"].organization_candidates
```

### Integration Tests (Slower, full workflows)

```python
# tests/integration/test_entity_discovery_graph.py
import pytest
from research_agent.graphs.entity_discovery.graph import (
    make_entity_intel_connected_candidates_and_sources_graph
)

@pytest.mark.asyncio
async def test_full_entity_discovery_workflow():
    graph = await make_entity_intel_connected_candidates_and_sources_graph({})
    result = await graph.ainvoke({
        "query": "Research Ozempic",
        "starter_sources": ["https://www.novonordisk.com"],
        "starter_content": "",
    })
    assert "candidate_sources" in result
    assert result["candidate_sources"].connected
```

### Fixture Strategy

```python
# tests/fixtures/mongo_fixtures.py
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from research_agent.models.mongo import get_document_models

@pytest.fixture(scope="session")
async def mongo_test_db():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["test_biotech_research_db"]
    await init_beanie(database=db, document_models=get_document_models())
    yield db
    await client.drop_database("test_biotech_research_db")
    client.close()
```

---

## Server Deployment Strategy

### Development (Local)

```bash
# Terminal 1: Graph Execution API
uvicorn research_agent.api.graph_execution.main:app --reload --port 8001

# Terminal 2: Mission Control API
uvicorn research_agent.api.mission_control.main:app --reload --port 8002

# Terminal 3: Memory & Thread API
uvicorn research_agent.api.memory_and_threads.main:app --reload --port 8003

# Terminal 4: MongoDB Model API
uvicorn research_agent.api.mongodb_models.main:app --reload --port 8004

# Terminal 5: Scheduler
python -m research_agent.orchestration.scheduler.in_memory

# Terminal 6-N: Workers (scale as needed)
python -m research_agent.orchestration.workers.taskiq_worker
```

### Production (Docker Compose)

```yaml
# docker-compose.yml
version: '3.8'

services:
  graph-execution-api:
    build: .
    command: uvicorn research_agent.api.graph_execution.main:app --host 0.0.0.0 --port 8001
    ports:
      - "8001:8001"
    environment:
      - MONGO_URI=${MONGO_URI}
      - REDIS_URL=${REDIS_URL}
    depends_on:
      - mongo
      - redis
  
  mission-control-api:
    build: .
    command: uvicorn research_agent.api.mission_control.main:app --host 0.0.0.0 --port 8002
    ports:
      - "8002:8002"
    depends_on:
      - mongo
      - redis
  
  scheduler:
    build: .
    command: python -m research_agent.orchestration.scheduler.in_memory
    depends_on:
      - redis
      - rabbitmq
  
  worker:
    build: .
    command: python -m research_agent.orchestration.workers.taskiq_worker
    deploy:
      replicas: 4
    depends_on:
      - redis
      - rabbitmq
      - mongo
  
  mongo:
    image: mongo:7
    ports:
      - "27017:27017"
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  rabbitmq:
    image: rabbitmq:3-management
    ports:
      - "5672:5672"
      - "15672:15672"
```

---

## Success Criteria

The reorganization is complete when:

1. ✅ **`human_upgrade/` directory deleted**
2. ✅ **All imports updated** (no broken imports)
3. ✅ **All tests passing** (unit + integration)
4. ✅ **4 FastAPI servers implemented** (graph exec, mission control, memory, mongo models)
5. ✅ **Documentation updated** (AGENTS.md, README.md, MIGRATION_GUIDE.md)
6. ✅ **Clear layer separation** (API ↔ Graphs ↔ Agents ↔ Services ↔ Infrastructure)
7. ✅ **Orchestration renamed** (mission_queue → orchestration)
8. ✅ **Memory module top-level** (memory/langmem, memory/store)
9. ✅ **Tool consolidation** (single tools/ directory, registry pattern)
10. ✅ **Configuration management** (config/settings.py with Pydantic)

---

## Benefits of New Structure

### 1. Clear Separation of Concerns
- **API Layer**: FastAPI servers (external interface)
- **Graph Layer**: LangGraph orchestration (research logic)
- **Agent Layer**: Worker agents (execution)
- **Service Layer**: MongoDB + Neo4j operations (persistence)
- **Infrastructure Layer**: External integrations (storage, queue, LLMs)

### 2. Independent Server Scaling
- Graph Execution API: Scale for concurrent graph runs
- Mission Control API: Scale for mission orchestration
- Workers: Scale for parallel agent execution
- Each server has clear responsibility

### 3. Easier Testing
- Unit tests per layer (isolated)
- Integration tests per workflow
- Clear fixture strategy (MongoDB, Redis, RabbitMQ)

### 4. Better Developer Experience
- Intuitive directory names (graphs, agents, services)
- Logical grouping (web tools, filesystem tools, scholarly tools)
- Centralized registries (tool registry, model registry)
- Clear import paths (research_agent.graphs.entity_discovery.graph)

### 5. Future-Proof Architecture
- Easy to add new agent types (agents/types/)
- Easy to add new graphs (graphs/new_graph/)
- Easy to add new API servers (api/new_server/)
- Easy to swap implementations (e.g., in_memory scheduler → mongo_backed scheduler)

### 6. Maintainability
- Single source of truth for models (models/)
- Single source of truth for prompts (prompts/)
- Single source of truth for tools (tools/)
- Clear deprecation path (delete old module when ready)

---

## Migration Risks & Mitigation

### Risk 1: Import Hell (High Likelihood)

**Risk**: Updating hundreds of imports across the codebase
**Mitigation**:
- Automated find-replace scripts
- Incremental migration (phase by phase)
- Keep both paths working temporarily (deprecated imports)
- Comprehensive test suite to catch broken imports

### Risk 2: Circular Dependencies (Medium Likelihood)

**Risk**: New structure introduces circular imports
**Mitigation**:
- Careful layer design (API → Graphs → Agents → Services)
- Use dependency injection where needed
- Lazy imports (`from typing import TYPE_CHECKING`)
- Clear interface definitions

### Risk 3: Breaking Production (Low Likelihood)

**Risk**: Migration breaks existing production workflows
**Mitigation**:
- Feature flag new structure (run both old + new in parallel)
- Comprehensive integration tests before cutover
- Gradual rollout (internal testing → staging → production)
- Rollback plan (Git branch + Docker image)

### Risk 4: Lost Context (Medium Likelihood)

**Risk**: Team loses familiarity with codebase during migration
**Mitigation**:
- Detailed MIGRATION_GUIDE.md (import path mapping)
- Pair programming during migration
- Code review every phase
- Update AGENTS.md incrementally

---

## Timeline Summary  

## Next few days refactor Next 3 weeks complete research agent codebase MVP complete. 

| **Phase** | **Duration** | **Key Deliverables** |
|-----------|--------------|----------------------|
| 1. Foundation | Week 1 | New directory structure, move utilities |
| 2. Models & Schemas | Week 1 | Reorganize Pydantic models, create API schemas |
| 3. Tools | Week 1 | Consolidate tools, create registry |
| 4. Prompts | Week 1 | Organize prompts by graph/agent |
| 5. Graphs | Week 1 | Move graphs, split nodes, extract state |
| 6. Agents | Week 1 | Organize agent factory + types |
| 7. Orchestration | Week 1 | Rename mission_queue, split handlers |
| 8. Services | Week 1 | Organize MongoDB services, add Neo4j |
| 9. Memory | Week 1 | Move memory module, create tools |
| 10. API Servers | Week 1| Build 4 FastAPI servers |
| 11. Config & Testing | Week 1 | Settings, unit tests, integration tests |
| 12. Cleanup & Docs | Week 1 | Delete human_upgrade/, update docs |

**Total Duration**: ~1 week (incremental, non-blocking)

---

## Next Steps

1. **Review this plan** with the team
2. **Create migration branch** (`feat/reorganize-codebase`)
3. **Start with Phase 1** (foundation + utilities)
4. **Run tests after each phase** (ensure no regressions)
5. **Update AGENTS.md** as structure evolves
6. **Merge incrementally** (PR per phase)
7. **Cut over to new structure** (delete human_upgrade/)

---

**Last Updated**: 2026-02-12  
**Version**: 1.0  
**Status**: Living Document (update as migration progresses)  
**Owner**: Research Agent Team
