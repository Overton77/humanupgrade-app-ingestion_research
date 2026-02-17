# Research Agent Codebase Organization Plan

> **📋 Living Documentation**: As we implement this system, we will create detailed `.cursor/rules/*.mdc` files and specifications that live on. This ensures each component has persistent, AI-accessible documentation that guides future development and maintenance.

## Executive Summary

This document outlines the **NEW PHASED APPROACH** for building the `research_agent` codebase. We are moving away from the entity-candidate-domain-catalog approach to a more flexible, conversation-first architecture.

### Implementation Phases (In Order)

1. **PHASE 1: Coordinator Agent** (Priority 1) - Interactive research plan builder with human-in-the-loop
2. **PHASE 2: Research Plan & Mission Orchestration** (Priority 2 - MOST CRITICAL) - Redesigned flexible execution
3. **PHASE 3: Entity Candidates Refactor** (Priority 3) - Lightweight candidate ranking tool  
4. **PHASE 4: Extraction & Storage** (Priority 4) - Knowledge graph ingestion pipeline

### Architecture Supports

1. **FastAPI Server Layer** (4 servers: Coordinator, Mission Control, Memory/Thread, Extraction)
2. **Distributed Task Execution** (Taskiq + RabbitMQ + Redis + MongoDB state)
3. **MongoDB Persistence** (Beanie ODM for all research artifacts + thread messages)
4. **Neo4j Knowledge Graph Ingestion** (via GraphQL client)
5. **LangGraph Memory System** (Semantic, Episodic, Procedural via PostgreSQL Store)
6. **Next.js Research Client** (Human-in-the-loop interface in `research_client/`)

**Primary Goal**: Build a flexible, human-guided research system where plans are created conversationally (Coordinator Agent) and executed flexibly (redesigned Mission Orchestration), with existing code refactored/reused where appropriate.

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
│   ├── coordinator/                      # Server 1: Coordinator Agent API (PHASE 1 - NEW)
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI app
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── threads.py                # POST/GET /coordinator/threads/*
│   │   │   ├── checkpoints.py            # POST /coordinator/checkpoints/{id}/approve
│   │   │   └── health.py                 # GET /health, /ready
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── threads.py                # Thread request/response models
│   │   │   └── checkpoints.py            # Checkpoint approval models
│   │   └── websockets/
│   │       ├── __init__.py
│   │       └── coordinator_stream.py     # WebSocket streaming for Coordinator
│   │
│   ├── mission_control/                  # Server 2: Mission Control API (PHASE 2 - ENHANCED)
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
│   ├── coordinator/                      # PHASE 1: Coordinator Agent Graph (NEW)
│   │   ├── __init__.py
│   │   ├── graph.py                      # Main coordinator graph builder
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── understand_goals.py       # Extract research goals from user
│   │   │   ├── query_knowledge.py        # Query existing KG entities
│   │   │   ├── query_past_research.py    # Query similar past runs
│   │   │   ├── build_scope.py            # Build research scope
│   │   │   ├── scope_checkpoint.py       # Human approval checkpoint #1
│   │   │   ├── suggest_strategies.py     # Suggest research strategies
│   │   │   ├── build_stages.py           # Build research stages
│   │   │   ├── allocate_agents.py        # Allocate agent types
│   │   │   ├── final_plan_checkpoint.py  # Human approval checkpoint #2
│   │   │   └── save_and_emit.py          # Save plan, emit to mission queue
│   │   ├── state.py                      # CoordinatorAgentState
│   │   └── helpers.py                    # Coordinator-specific helpers
│   │
│   ├── candidate_exploration/            # PHASE 3: Candidate Exploration (REFACTORED)
│   │   ├── __init__.py
│   │   ├── graph.py                      # Lightweight exploration graph
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── quick_extraction.py       # Fast entity extraction
│   │   │   ├── relevance_ranking.py      # Rank by relevance
│   │   │   ├── novelty_check.py          # Check against KG
│   │   │   └── completeness_estimate.py  # Estimate researchability
│   │   ├── state.py
│   │   └── helpers.py
│   │
│   ├── research_planning/                # PHASE 2: Research Planning (REDESIGNED)
│   │   ├── __init__.py
│   │   ├── graph.py                      # Flexible research plan graph
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── validate_plan.py          # Validate plan structure
│   │   │   ├── optimize_dependencies.py  # Optimize stage dependencies
│   │   │   └── prepare_for_execution.py  # Final prep before execution
│   │   ├── state.py
│   │   └── helpers.py
│   │
│   ├── entity_extraction/                # PHASE 4: Extraction Graph (TO BE IMPLEMENTED)
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
│   │   ├── coordinator/                  # PHASE 1: Coordinator Models (NEW)
│   │   │   ├── __init__.py
│   │   │   ├── docs/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── coordinator_threads.py    # Conversation threads
│   │   │   │   └── coordinator_checkpoints.py # Human approval checkpoints
│   │   │   └── embedded/
│   │   │       ├── __init__.py
│   │   │       ├── research_goals.py         # Structured research goals
│   │   │       └── research_scope.py         # Research scope model
│   │   │
│   │   ├── research/                     # PHASE 2: Research Models (REDESIGNED)
│   │   │   ├── __init__.py
│   │   │   ├── docs/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── research_mission_plans.py # Flexible research plans
│   │   │   │   ├── research_runs.py          # Mission execution tracking
│   │   │   │   ├── agent_instance_outputs.py # Agent instance outputs (NEW)
│   │   │   │   └── substage_outputs.py       # Sub-stage aggregated outputs (NEW)
│   │   │   ├── embedded/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── research_objectives.py    # ResearchObjective model (NEW)
│   │   │   │   ├── agent_instance_plan.py    # AgentInstancePlan model (NEW)
│   │   │   │   ├── sub_stage.py              # SubStage model (NEW)
│   │   │   │   └── stage.py                  # Stage model (NEW)
│   │   │   └── enums.py
│   │   │
│   │   ├── candidates/                   # PHASE 3: Candidates (SIMPLIFIED)
│   │   │   ├── __init__.py
│   │   │   ├── docs/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── candidate_explorations.py # Exploration results (NEW)
│   │   │   │   └── ranked_candidates.py      # Ranked candidates (NEW)
│   │   │   └── embedded/
│   │   │       ├── __init__.py
│   │   │       └── ranked_candidate.py       # Single ranked candidate
│   │   │
│   │   ├── extraction/                   # PHASE 4: Extraction Models (NEW)
│   │   │   ├── __init__.py
│   │   │   ├── docs/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── extraction_runs.py        # Extraction pipeline runs
│   │   │   │   └── extracted_entities.py     # Pre-KG extracted entities
│   │   │   └── embedded/
│   │   │       ├── __init__.py
│   │   │       ├── organization_extracted.py
│   │   │       ├── person_extracted.py
│   │   │       ├── product_extracted.py
│   │   │       └── compound_extracted.py
│   │   │
│   │   ├── entities/                     # Keep for backward compatibility
│   │   │   ├── __init__.py
│   │   │   ├── docs/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── candidate_entities.py
│   │   │   │   ├── dedupe_groups.py
│   │   │   │   ├── candidate_runs.py
│   │   │   │   └── artifacts.py
│   │   │   └── embedded/
│   │   │
│   │   └── domains/                      # DEPRECATED (keep for backward compat)
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
│   ├── graphql/                          # PHASE 1: GraphQL Query Tools (NEW)
│   │   ├── __init__.py
│   │   ├── query_entities.py             # Query existing entities in KG
│   │   ├── get_entity_details.py         # Get full entity details
│   │   └── search_by_type.py             # Search entities by type
│   │
│   ├── research_history/                 # PHASE 1: Research History Tools (NEW)
│   │   ├── __init__.py
│   │   ├── query_past_runs.py            # Query similar past research
│   │   ├── get_run_summary.py            # Get run summary/outcomes
│   │   └── get_effective_agents.py       # Get agent types that worked
│   │
│   ├── candidate_exploration/            # PHASE 3: Candidate Tools (NEW)
│   │   ├── __init__.py
│   │   └── explore_and_rank.py           # Explore and rank candidates tool
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

## NEW Implementation Strategy (Phased Approach)

> **Critical Change**: We are NOT migrating the old structure. We are building NEW components first (Phases 1-4), then refactoring existing code to integrate.

---

## PHASE 1: Coordinator Agent (Week 1)

**Goal**: Build interactive research plan builder with human-in-the-loop

### Step 1: Create Coordinator Directory Structure

```bash
# Phase 1 directories
mkdir -p api/coordinator/{routes,schemas,websockets}
mkdir -p graphs/coordinator/nodes
mkdir -p models/mongo/coordinator/{docs,embedded}
mkdir -p tools/{graphql,research_history}
mkdir -p tests/unit/coordinator
mkdir -p tests/integration/coordinator
```

### Step 2: Create MongoDB Models

```python
# models/mongo/coordinator/docs/coordinator_threads.py
class CoordinatorThreadDoc(Document):
    thread_id: str
    user_id: Optional[str]
    status: str  # "active" | "scope_approved" | "plan_approved"
    initial_query: str
    messages: List[Dict]  # Serialized BaseMessage
    # ... (see AGENTS.md for full spec)

# models/mongo/coordinator/docs/coordinator_checkpoints.py
class CoordinatorCheckpointDoc(Document):
    checkpoint_id: str
    thread_id: str
    checkpoint_type: str  # "scope_approval" | "final_plan_approval"
    state_snapshot: Dict
    approved: Optional[bool]
    # ... (see AGENTS.md for full spec)
```

### Step 3: Create GraphQL Query Tools

```python
# tools/graphql/query_entities.py
class QueryExistingEntitiesTool(BaseTool):
    """Query existing entities in the knowledge graph."""
    name = "query_existing_entities"
    description = "Search for entities already in the knowledge graph"
    
    async def _arun(self, query: str) -> str:
        # Call GraphQL API to search entities
        pass

# tools/graphql/get_entity_details.py
# tools/graphql/search_by_type.py
```

### Step 4: Create Research History Tools

```python
# tools/research_history/query_past_runs.py
class QueryPastResearchRunsTool(BaseTool):
    """Query similar past research missions."""
    name = "query_past_research_runs"
    description = "Find similar past research missions and their outcomes"
    
    async def _arun(self, query: str) -> str:
        # Query ResearchRunDoc collection
        # Return summaries of similar runs
        pass

# tools/research_history/get_run_summary.py
# tools/research_history/get_effective_agents.py
```

### Step 5: Build Coordinator LangGraph

```python
# graphs/coordinator/graph.py
from langgraph.graph import StateGraph, START, END

def build_coordinator_agent_graph():
    """Build the Coordinator Agent LangGraph."""
    
    builder = StateGraph(CoordinatorAgentState)
    
    # Nodes
    builder.add_node("understand_goals", understand_goals_node)
    builder.add_node("query_knowledge", query_knowledge_node)
    builder.add_node("build_scope", build_scope_node)
    builder.add_node("scope_checkpoint", scope_checkpoint_node)  # interrupt()
    builder.add_node("suggest_strategies", suggest_strategies_node)
    builder.add_node("build_stages", build_stages_node)
    builder.add_node("allocate_agents", allocate_agents_node)
    builder.add_node("final_plan_checkpoint", final_plan_checkpoint_node)  # interrupt()
    builder.add_node("save_and_emit", save_and_emit_node)
    
    # Edges
    builder.add_edge(START, "understand_goals")
    builder.add_edge("understand_goals", "query_knowledge")
    builder.add_edge("query_knowledge", "build_scope")
    builder.add_edge("build_scope", "scope_checkpoint")
    # ... (full flow in AGENTS.md)
    
    return builder.compile(
        checkpointer=get_postgres_checkpointer(),
        interrupt_before=["scope_checkpoint", "final_plan_checkpoint"]
    )
```

### Step 6: Create FastAPI Routes

```python
# api/coordinator/routes/threads.py
@router.post("/coordinator/threads")
async def create_coordinator_thread(request: CreateThreadRequest):
    """Start a new Coordinator Agent conversation."""
    # Create thread in MongoDB
    # Invoke graph with initial message
    # Return thread_id
    pass

@router.post("/coordinator/threads/{thread_id}/messages")
async def send_message(thread_id: str, message: SendMessageRequest):
    """Send a message to the Coordinator Agent."""
    # Append message to thread
    # Invoke graph
    # Return response
    pass

# api/coordinator/routes/checkpoints.py
@router.post("/coordinator/checkpoints/{checkpoint_id}/approve")
async def approve_checkpoint(checkpoint_id: str, approval: CheckpointApprovalRequest):
    """Approve or reject a checkpoint."""
    # Update checkpoint
    # Resume graph from checkpoint
    pass
```

### Step 7: Initialize Next.js Research Client

```bash
cd ../../  # Go to repo root
mkdir -p research_client
cd research_client
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir
```

```typescript
// research_client/app/page.tsx
export default function Home() {
  return (
    <div>
      <h1>Research Plan Builder</h1>
      {/* Thread list or create new thread */}
    </div>
  );
}

// research_client/app/threads/[thread_id]/page.tsx
export default function ThreadPage({ params }: { params: { thread_id: string } }) {
  return (
    <ChatInterface threadId={params.thread_id} />
  );
}
```

### Step 8: Create .cursor/rules Specification

```markdown
# .cursor/rules/coordinator-agent.mdc
---
description: Coordinator Agent implementation specification
---

# Coordinator Agent Specification

[Full detailed spec with examples, state transitions, tool usage patterns]
```

---

## PHASE 2: Research Plan & Mission Orchestration (Week 2-3)

**Goal**: Redesign research plan structure and enhance execution engine

### Step 1: Redesign Research Plan Models

```python
# models/mongo/research/embedded/research_objectives.py
class ResearchObjective(BaseModel):
    objective_id: str
    description: str  # "Identify the leadership team"
    success_criteria: List[str]
    priority: str  # "critical" | "high" | "medium" | "low"

# models/mongo/research/embedded/agent_instance_plan.py
class AgentInstancePlan(BaseModel):
    instance_id: str
    agent_type: str
    objectives: List[ResearchObjective]  # What to do
    seed_context: Dict[str, Any]
    starter_sources: List[str]  # OPTIONAL
    allowed_tools: List[str]
    requires_outputs_from: List[str]  # Dependencies
    previous_stage_outputs: Optional[Dict]  # From prev stage

# models/mongo/research/embedded/sub_stage.py
class SubStage(BaseModel):
    sub_stage_id: str
    name: str
    agent_instances: List[str]  # instance_ids
    execution_mode: str  # "parallel" | "sequential"
    depends_on_sub_stages: List[str]
    output_aggregation: str  # "merge_all" | "best_of" | "consensus"

# models/mongo/research/embedded/stage.py
class Stage(BaseModel):
    stage_id: str
    name: str
    sub_stages: List[str]  # sub_stage_ids
    execution_mode: str
    depends_on_stages: List[str]

# models/mongo/research/docs/research_mission_plans.py
class ResearchMissionPlanDoc(Document):
    mission_id: str
    created_by: str  # "coordinator_agent"
    mission_name: str
    stages: List[Stage]
    sub_stages: List[SubStage]
    agent_instances: List[AgentInstancePlan]
    execution_strategy: str  # "sequential" | "parallel" | "hybrid"
    # ... (see AGENTS.md for full spec)
```

### Step 2: Update DAG Builder for Flexible Execution

```python
# orchestration/dag/builder.py (ENHANCED)
def build_mission_dag(plan: ResearchMissionPlan) -> MissionDAG:
    """Build DAG from flexible research plan."""
    
    tasks = {}
    
    # Create tasks for agent instances
    for instance in plan.agent_instances:
        task_id = f"instance::{plan.mission_id}::{instance.instance_id}"
        
        # Build dependencies from:
        # 1. requires_outputs_from (instance dependencies)
        # 2. sub_stage dependencies
        # 3. stage dependencies
        depends_on = build_dependencies(instance, plan)
        
        tasks[task_id] = TaskDefinition(
            task_id=task_id,
            task_type="INSTANCE_RUN",
            depends_on=depends_on,
            payload=instance.model_dump(),
        )
    
    # Create aggregation tasks for sub-stages
    for sub_stage in plan.sub_stages:
        task_id = f"substage_reduce::{plan.mission_id}::{sub_stage.sub_stage_id}"
        depends_on = [f"instance::{plan.mission_id}::{inst_id}" 
                      for inst_id in sub_stage.agent_instances]
        
        tasks[task_id] = TaskDefinition(
            task_id=task_id,
            task_type="SUBSTAGE_REDUCE",
            depends_on=depends_on,
            payload=sub_stage.model_dump(),
        )
    
    return MissionDAG(tasks=tasks)
```

### Step 3: Enhance Worker Execution (Output Passing)

```python
# orchestration/workers/handlers/instance_run.py (ENHANCED)
async def handle_instance_run(task: TaskDefinition) -> TaskResult:
    """Execute agent instance with output passing support."""
    
    plan = AgentInstancePlan(**task.payload)
    
    # Load previous stage outputs if this instance depends on others
    previous_outputs = None
    if plan.requires_outputs_from:
        previous_outputs = await load_outputs_from_instances(plan.requires_outputs_from)
    
    # Build agent
    agent = build_worker_agent(
        agent_type=plan.agent_type,
        allowed_tools=plan.allowed_tools,
    )
    
    # Execute with previous outputs
    result = await execute_agent_instance(
        plan=plan,
        previous_outputs=previous_outputs,  # NEW: pass outputs
    )
    
    # Save outputs for downstream instances
    await save_instance_outputs(
        instance_id=plan.instance_id,
        outputs=result.outputs,
    )
    
    return TaskResult(status="completed", outputs=result.outputs)
```

### Step 4: Implement Sub-Stage Aggregation

```python
# orchestration/workers/handlers/substage_reduce.py (NEW)
async def handle_substage_reduce(task: TaskDefinition) -> TaskResult:
    """Aggregate outputs from all instances in a sub-stage."""
    
    sub_stage = SubStage(**task.payload)
    
    # Load outputs from all instances in this sub-stage
    instance_outputs = await load_instance_outputs(sub_stage.agent_instances)
    
    # Aggregate based on strategy
    if sub_stage.output_aggregation == "merge_all":
        aggregated = merge_all_outputs(instance_outputs)
    elif sub_stage.output_aggregation == "best_of":
        aggregated = await llm_select_best_outputs(instance_outputs)
    elif sub_stage.output_aggregation == "consensus":
        aggregated = await llm_find_consensus(instance_outputs)
    
    # Save aggregated outputs
    await save_substage_outputs(
        sub_stage_id=sub_stage.sub_stage_id,
        outputs=aggregated,
    )
    
    return TaskResult(status="completed", outputs=aggregated)
```

### Step 5: Implement WebSocket Progress Streaming

```python
# api/mission_control/websockets/progress_stream.py (NEW)
@router.websocket("/missions/runs/{run_id}/progress")
async def stream_mission_progress(websocket: WebSocket, run_id: str):
    """Stream real-time progress updates."""
    await websocket.accept()
    
    # Subscribe to Redis events for this mission
    async for event in subscribe_to_mission_events(run_id):
        await websocket.send_json({
            "event_type": event.event_type,
            "message": event.message,
            "progress_percent": event.progress_percent,
            "timestamp": event.timestamp.isoformat(),
        })
```

### Step 6: Update Coordinator Agent to Generate Flexible Plans

```python
# graphs/coordinator/nodes/allocate_agents.py (UPDATED)
async def allocate_agents_node(state: CoordinatorAgentState) -> Dict:
    """Allocate agent types with flexible objectives."""
    
    # Generate agent instances with objectives (not domain catalogs)
    agent_instances = []
    for stage in state["research_stages"]:
        for objective_group in stage.objective_groups:
            instance = AgentInstancePlan(
                instance_id=generate_id(),
                agent_type=select_agent_type(objective_group),
                objectives=objective_group.objectives,
                seed_context=build_seed_context(objective_group),
                starter_sources=state.get("source_recommendations", []),  # Optional
                allowed_tools=["tavily_search", "tavily_extract", "write_file", ...],
            )
            agent_instances.append(instance)
    
    return {"agent_instances": agent_instances}
```

### Step 7: Create .cursor/rules Specification

```markdown
# .cursor/rules/research-plan-structure.mdc
---
description: Research Plan flexible structure specification
---

# Research Plan Structure

[Full spec with examples of sequential, parallel, and hybrid execution]
```

---

## PHASE 3: Entity Candidates Refactor (Week 3-4)

**Goal**: Transform entity discovery into lightweight candidate ranking tool

### Step 1: Simplify Entity Discovery Graph

```python
# graphs/candidate_exploration/graph.py (SIMPLIFIED)
def build_candidate_exploration_graph():
    """Build lightweight candidate exploration graph."""
    
    builder = StateGraph(CandidateExplorationState)
    
    # Simplified nodes (NO domain catalogs)
    builder.add_node("quick_extraction", quick_extraction_node)  # Fast LLM extraction
    builder.add_node("relevance_ranking", relevance_ranking_node)  # Score relevance
    builder.add_node("novelty_check", novelty_check_node)  # Query KG
    builder.add_node("completeness_estimate", completeness_estimate_node)  # Quick check
    
    builder.add_edge(START, "quick_extraction")
    builder.add_edge("quick_extraction", "relevance_ranking")
    builder.add_edge("relevance_ranking", "novelty_check")
    builder.add_edge("novelty_check", "completeness_estimate")
    builder.add_edge("completeness_estimate", END)
    
    return builder.compile()
```

### Step 2: Implement Ranking Logic

```python
# graphs/candidate_exploration/nodes/relevance_ranking.py
async def relevance_ranking_node(state: CandidateExplorationState) -> Dict:
    """Rank candidates by relevance to query."""
    
    candidates = state["extracted_candidates"]
    query = state["query"]
    
    # Use LLM to score relevance (0-1)
    ranked = await llm_rank_candidates_by_relevance(
        candidates=candidates,
        query=query,
    )
    
    return {"ranked_candidates": ranked}

# graphs/candidate_exploration/nodes/novelty_check.py
async def novelty_check_node(state: CandidateExplorationState) -> Dict:
    """Check if candidates are already in KG."""
    
    for candidate in state["ranked_candidates"]:
        # Query GraphQL API
        existing = await query_kg_for_entity(candidate.canonical_name)
        
        if existing:
            candidate.novelty_score = 0.1  # Already have it
        else:
            candidate.novelty_score = 0.9  # New entity
    
    return {"ranked_candidates": state["ranked_candidates"]}
```

### Step 3: Create Tool Interface

```python
# tools/candidate_exploration/explore_and_rank.py
class ExploreAndRankCandidatesTool(BaseTool):
    """Tool for Coordinator Agent to explore and rank candidates."""
    
    name = "explore_and_rank_candidates"
    description = """
    Quickly explore candidate entities and rank them by research priority.
    Use this to help users prioritize which entities to research deeply.
    
    Input: query (string), max_candidates (int, default 10)
    Output: Ranked list with recommendations
    """
    
    async def _arun(self, query: str, max_candidates: int = 10) -> str:
        graph = build_candidate_exploration_graph()
        result = await graph.ainvoke({
            "query": query,
            "max_candidates": max_candidates,
        })
        
        # Format for LLM
        output = "Ranked Candidates:\n\n"
        for i, candidate in enumerate(result["ranked_candidates"], 1):
            output += f"{i}. {candidate.canonical_name}\n"
            output += f"   Priority: {candidate.research_priority}\n"
            output += f"   Relevance: {candidate.relevance_score:.2f}\n"
            output += f"   Novelty: {candidate.novelty_score:.2f}\n"
            output += f"   Summary: {candidate.quick_summary}\n\n"
        
        return output
```

### Step 4: Integrate with Coordinator Agent

```python
# graphs/coordinator/graph.py (ADD TOOL)
def build_coordinator_agent_graph():
    """Build Coordinator Agent with candidate exploration tool."""
    
    tools = [
        tavily_search_tool,
        query_existing_entities_tool,
        query_past_research_runs_tool,
        explore_and_rank_candidates_tool,  # NEW TOOL
    ]
    
    # ... rest of graph setup
```

---

## PHASE 4: Extraction & Storage (Week 4+)

**Goal**: Build extraction pipeline to populate knowledge graph

### Step 1: Create Extraction Graph

```python
# graphs/entity_extraction/graph.py
def build_extraction_graph():
    """Build entity extraction graph."""
    
    builder = StateGraph(ExtractionState)
    
    builder.add_node("parse_reports", parse_reports_node)
    builder.add_node("extract_entities", extract_entities_node)
    builder.add_node("extract_relationships", extract_relationships_node)
    builder.add_node("link_evidence", link_evidence_node)
    builder.add_node("graphql_upsert", graphql_upsert_node)
    
    builder.add_edge(START, "parse_reports")
    builder.add_edge("parse_reports", "extract_entities")
    builder.add_edge("extract_entities", "extract_relationships")
    builder.add_edge("extract_relationships", "link_evidence")
    builder.add_edge("link_evidence", "graphql_upsert")
    builder.add_edge("graphql_upsert", END)
    
    return builder.compile()

# graphs/entity_extraction/nodes/extract_entities.py
async def extract_entities_node(state: ExtractionState) -> Dict:
    """Extract structured entities from reports using LLM."""
    
    reports_content = state["parsed_reports"]
    
    # Use LLM with structured outputs
    organizations = await llm_extract_organizations(reports_content)
    people = await llm_extract_people(reports_content)
    products = await llm_extract_products(reports_content)
    compounds = await llm_extract_compounds(reports_content)
    
    return {
        "organizations": organizations,
        "people": people,
        "products": products,
        "compounds": compounds,
    }
```

### Step 2: Implement GraphQL Mutations

```python
# services/graphql/mutations.py
async def upsert_organization(client: GraphQLClient, org: OrganizationExtracted) -> str:
    """Upsert organization to Neo4j."""
    
    mutation = """
    mutation UpsertOrganization($input: OrganizationInput!) {
        upsertOrganization(input: $input) {
            id
            canonicalName
        }
    }
    """
    
    result = await client.execute(mutation, variables={
        "input": {
            "canonicalName": org.canonical_name,
            "domains": org.domains,
            "description": org.description,
            "aliases": org.aliases,
        }
    })
    
    return result["upsertOrganization"]["id"]

# Similar functions for:
# - upsert_person()
# - upsert_product()
# - upsert_compound()
# - create_relationship()
# - link_evidence()
```

### Step 3: Create Extraction API Routes

```python
# api/extraction/routes/extract.py
@router.post("/extraction/extract-from-mission")
async def extract_from_mission(request: ExtractFromMissionRequest) -> ExtractFromMissionResponse:
    """Extract entities from a completed research mission."""
    
    # Load mission outputs
    mission_outputs = await load_mission_outputs(request.mission_id)
    
    # Build extraction graph
    graph = build_extraction_graph()
    
    # Execute extraction
    result = await graph.ainvoke({
        "mission_id": request.mission_id,
        "final_reports": mission_outputs.final_reports,
        "checkpoint_files": mission_outputs.checkpoint_files,
    })
    
    return ExtractFromMissionResponse(
        extraction_run_id=result["extraction_run_id"],
        entities_added=len(result["graphql_entity_ids"]),
        relationships_created=len(result["relationships"]),
    )
```

### Step 4: Integrate with Mission Control

```python
# api/mission_control/routes/missions.py (ENHANCED)
@router.post("/missions/{mission_id}/complete")
async def complete_mission(mission_id: str):
    """Mark mission complete and trigger extraction."""
    
    # Update mission status
    await update_mission_status(mission_id, "completed")
    
    # Trigger extraction (async)
    extraction_task = await trigger_extraction(mission_id)
    
    return {
        "mission_id": mission_id,
        "status": "completed",
        "extraction_run_id": extraction_task.extraction_run_id,
    }
```

### Step 5: Update Research Client UI

```typescript
// research_client/components/mission/MissionProgress.tsx
export function MissionProgress({ missionId }: { missionId: string }) {
  const { progress, isComplete } = useMissionProgress(missionId);
  
  return (
    <div>
      {/* Mission execution progress */}
      <ProgressBar percent={progress.percent} />
      
      {isComplete && (
        <div>
          <h3>Extraction in Progress</h3>
          <ExtractionProgress missionId={missionId} />
        </div>
      )}
    </div>
  );
}
```

---

## Research Client (Next.js Frontend)

The `research_client/` directory is located at the **repository root** (sibling to `ingestion/` and `api/`) and contains the Next.js application for interacting with the Coordinator Agent and monitoring research missions.

**Location**: `C:\Users\Pinda\Proyectos\humanupgradeapp\research_client/`

```
research_client/
├── app/
│   ├── layout.tsx                      # Root layout
│   ├── page.tsx                        # Home page (thread list/create)
│   ├── threads/
│   │   ├── [thread_id]/
│   │   │   └── page.tsx                # Chat interface with Coordinator
│   │   └── new/
│   │       └── page.tsx                # Create new thread
│   ├── missions/
│   │   ├── [mission_id]/
│   │   │   └── page.tsx                # Mission execution progress
│   │   └── list/
│   │       └── page.tsx                # List all missions
│   └── api/
│       └── coordinator/                # API route proxies (optional)
│
├── components/
│   ├── chat/
│   │   ├── ChatInterface.tsx           # Main chat UI
│   │   ├── MessageBubble.tsx           # Message display
│   │   ├── MessageInput.tsx            # User input
│   │   ├── ApprovalCheckpoint.tsx      # Human approval UI
│   │   └── StreamingIndicator.tsx      # Loading/streaming state
│   ├── plan/
│   │   ├── ResearchPlanView.tsx        # Full plan visualization
│   │   ├── StageCard.tsx               # Stage display
│   │   ├── SubStageCard.tsx            # Sub-stage display
│   │   ├── AgentAllocationView.tsx     # Agent types per stage
│   │   └── DependencyGraph.tsx         # Visual dependency graph
│   ├── mission/
│   │   ├── MissionProgress.tsx         # Real-time progress
│   │   ├── StageProgress.tsx           # Per-stage progress
│   │   ├── AgentProgress.tsx           # Per-agent progress
│   │   └── ExtractionProgress.tsx      # Extraction progress
│   ├── knowledge-graph/
│   │   ├── ExistingEntitiesView.tsx    # Show entities in KG
│   │   ├── EntityCard.tsx              # Single entity display
│   │   └── RelationshipGraph.tsx       # Entity relationships
│   └── ui/
│       ├── Button.tsx                  # shadcn/ui components
│       ├── Card.tsx
│       └── ...
│
├── lib/
│   ├── api-client.ts                   # FastAPI client (fetch wrapper)
│   ├── websocket.ts                    # WebSocket manager
│   ├── types.ts                        # TypeScript types
│   └── utils.ts                        # Utility functions
│
├── hooks/
│   ├── useCoordinatorThread.ts         # Thread state management
│   ├── useCheckpointApproval.ts        # Approval flow
│   ├── useMissionProgress.ts           # Mission progress subscription
│   └── useWebSocket.ts                 # WebSocket connection
│
├── package.json                        # Dependencies
├── tsconfig.json                       # TypeScript config
├── tailwind.config.ts                  # Tailwind config
└── next.config.js                      # Next.js config
```

**Key Features:**
- Real-time chat with Coordinator Agent (WebSocket streaming)
- Human-in-the-loop approval UI (scope + final plan)
- Visual research plan builder/viewer
- Live mission progress tracking
- Knowledge graph entity browser

---

## Project Structure (Updated with Phase Components)

The following directories are added/modified per phase:

### Phase 1 Additions
```
api/coordinator/
graphs/coordinator/
models/mongo/coordinator/
tools/graphql/
tools/research_history/
research_client/  # NEW: Next.js frontend
```

### Phase 2 Modifications
```
models/mongo/research/  # Redesigned models
orchestration/dag/  # Enhanced DAG builder
orchestration/workers/handlers/  # Enhanced handlers
api/mission_control/websockets/  # Progress streaming
```

### Phase 3 Additions
```
graphs/candidate_exploration/  # Simplified from entity_discovery
models/mongo/candidates/  # Simplified models
tools/candidate_exploration/
```

### Phase 4 Additions
```
graphs/entity_extraction/
models/mongo/extraction/
services/graphql/
api/extraction/
```

---

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

## Success Criteria by Phase

### Phase 1: Coordinator Agent ✅ When:
1. ✅ User can start conversation with Coordinator Agent via Next.js client
2. ✅ Coordinator can query existing KG entities (GraphQL tools working)
3. ✅ Coordinator can query past research runs
4. ✅ Coordinator can build research plans conversationally
5. ✅ Scope approval checkpoint works (human can approve/reject)
6. ✅ Final plan approval checkpoint works
7. ✅ Approved plans saved to MongoDB
8. ✅ `.cursor/rules/coordinator-agent.mdc` specification created

### Phase 2: Research Plan & Orchestration ✅ When:
1. ✅ Flexible research plan models implemented (no domain catalog dependency)
2. ✅ Agents execute with objectives + optional starter sources
3. ✅ DAG builder supports flexible dependencies (instance → instance, sub-stage → stage)
4. ✅ Output passing works (agents can receive previous_outputs)
5. ✅ Sub-stage aggregation works (merge_all, best_of, consensus)
6. ✅ WebSocket progress streams to research client
7. ✅ Missions complete with correct outputs passed between stages
8. ✅ `.cursor/rules/research-plan-structure.mdc` specification created

### Phase 3: Candidate Exploration ✅ When:
1. ✅ Simplified exploration graph completes in <30 seconds
2. ✅ Candidates ranked by relevance, novelty, completeness
3. ✅ Tool integrated with Coordinator Agent
4. ✅ Coordinator can recommend prioritized candidates to users
5. ✅ No dependency on domain catalog generation

### Phase 4: Extraction & Storage ✅ When:
1. ✅ Extraction graph processes research outputs successfully
2. ✅ Entities extracted using LLM structured outputs
3. ✅ GraphQL mutations working (entities created in Neo4j)
4. ✅ Relationships created correctly
5. ✅ Evidence linked to entities
6. ✅ Knowledge graph grows with each research mission
7. ✅ Extraction progress visible in research client

### Overall System ✅ When:
1. ✅ End-to-end flow works: Coordinator → Plan → Execute → Extract → KG
2. ✅ All 4 FastAPI servers running (Coordinator, Mission Control, Memory, Extraction)
3. ✅ Next.js research client functional
4. ✅ Human-in-the-loop flow smooth (scope + final approval)
5. ✅ WebSocket progress streaming works end-to-end
6. ✅ Tests passing (unit + integration per phase)
7. ✅ Documentation complete (AGENTS.md, .cursor/rules/*.mdc files)
8. ✅ Research system is flexible (not rigid domain-catalog-based)

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

## Implementation Timeline

**Target**: 3-4 weeks for full MVP

| **Phase** | **Duration** | **Key Deliverables** | **Priority** |
|-----------|--------------|----------------------|--------------|
| **Phase 1: Coordinator Agent** | Week 1 | MongoDB models, GraphQL tools, Coordinator graph, FastAPI routes, Next.js client, Human-in-the-loop checkpoints | **HIGHEST** |
| **Phase 2: Research Plan & Orchestration** | Week 2-3 | Flexible plan models, Enhanced DAG builder, Output passing, WebSocket progress, Sub-stage aggregation | **CRITICAL** |
| **Phase 3: Candidate Exploration** | Week 3-4 | Simplified exploration graph, Ranking logic, Tool integration, Coordinator integration | **HIGH** |
| **Phase 4: Extraction & Storage** | Week 4+ | Extraction graph, GraphQL mutations, Extraction API, KG population | **MEDIUM** |

**Development Strategy**: Build new components first (Phases 1-4), then refactor existing code to integrate.

---

## Immediate Next Steps (Phase 1 - This Week)

### Day 1-2: MongoDB Models + Tools
1. ✅ Create `CoordinatorThreadDoc` and `CoordinatorCheckpointDoc` Beanie models
2. ✅ Implement GraphQL query tools (`query_existing_entities`, `get_entity_details`)
3. ✅ Implement research history tools (`query_past_runs`, `get_run_summary`)
4. ✅ Write unit tests for models and tools

### Day 3-4: Coordinator LangGraph
1. ✅ Create `CoordinatorAgentState` TypedDict
2. ✅ Implement coordinator graph nodes (understand_goals, query_knowledge, etc.)
3. ✅ Implement human-in-the-loop checkpoints (`interrupt()`)
4. ✅ Write integration tests for graph flow
5. ✅ Create `.cursor/rules/coordinator-agent.mdc` specification

### Day 5-6: FastAPI Routes + Next.js Client
1. ✅ Create FastAPI Coordinator routes (threads, messages, checkpoints)
2. ✅ Implement WebSocket streaming
3. ✅ Initialize Next.js `research_client/` app
4. ✅ Build basic chat interface component
5. ✅ Build approval checkpoint UI component

### Day 7: Testing + Integration
1. ✅ E2E test: Create thread → chat → approve scope → approve plan
2. ✅ Test WebSocket streaming
3. ✅ Test checkpoint approval flow
4. ✅ Documentation review

**Phase 1 Complete** → Move to Phase 2

---

## Development Principles

1. **Build New First**: Create new components (Phases 1-4) before refactoring old code
2. **Document as We Go**: Create `.cursor/rules/*.mdc` files for each major component
3. **Test Early**: Write tests alongside implementation
4. **Iterate Based on Feedback**: Human-in-the-loop means iterating on UX
5. **Flexible Over Perfect**: Build for flexibility first, optimize later

---

**Last Updated**: 2026-02-15  
**Version**: 2.0 (NEW PHASED ARCHITECTURE)  
**Status**: Living Document - Active Development Phase 1  
**Next Review**: After Phase 1 Complete
