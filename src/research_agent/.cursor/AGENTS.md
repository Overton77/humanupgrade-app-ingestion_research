# Research Ingestion System - Agent Architecture & Implementation Plan

> **📋 Living Documentation**: As we implement this system, we will create detailed `.cursor/rules/*.mdc` files and specifications that live on. This ensures each component has persistent, AI-accessible documentation that guides future development and maintenance.

---

## Executive Summary

This document outlines the **NEW architecture** for the Human Upgrade Research Ingestion System - a flexible, human-in-the-loop biotech research platform that builds knowledge graphs from unstructured sources.

**Critical Architectural Shift**: We are moving away from the entity-candidate-domain-catalog approach to a more flexible, conversation-first design where research plans are created through an interactive Coordinator Agent.

### Implementation Order (4 Phases)

1. **Coordinator Agent** (Priority 1) - Interactive research plan builder with human-in-the-loop
2. **Research Plan & Mission Orchestration** (Priority 2 - MOST CRITICAL) - Redesigned flexible execution system
3. **Entity Candidates Refactor** (Priority 3) - Lightweight candidate ranking tool
4. **Extraction & Storage** (Priority 4) - Knowledge graph ingestion pipeline

---

## Technology Stack Overview

### Core Frameworks
- **LangGraph**: State graph orchestration, checkpointing, human-in-the-loop
- **LangChain**: Agent creation, tools, prompt management
- **Pydantic**: Data validation, structured outputs
- **FastAPI**: REST + WebSocket API servers
- **Next.js**: Research client frontend (`research_client/`)

### Persistence & State
- **MongoDB + Beanie**: Research plans, runs, candidates, thread messages
- **PostgreSQL + LangGraph Store**: Memory (semantic, episodic, procedural)
- **Neo4j (via GraphQL)**: Final knowledge graph (entities, relationships, evidence)
- **Redis**: Task queues, caching

### Task Orchestration
- **Taskiq**: Async task queue framework
- **RabbitMQ**: Message broker for distributed workers
- **Redis Streams**: Runnable tasks + events

### AI Models
- **GPT-4.1**: Complex reasoning, summarization
- **GPT-5 Mini**: Primary agent work (fast, cost-effective)
- **GPT-5 Nano**: Simple tasks (source expansion, quick queries)
- **GPT-5**: Final report synthesis (highest quality)

---

## PHASE 1: Coordinator Agent (Priority 1)

### Purpose

The **Coordinator Agent** is a NEW conversational LangGraph agent that helps users interactively BUILD research plans. It replaces the old approach which used the inefficient entity candidates connected graph -> research plan graph -> mission dag execution approach. Candidate exploration and source discovery will be standalone and potentially part of research plans. 

**Key Insight**: Research plan creation is a creative, iterative process that benefits from human guidance. The Coordinator Agent facilitates this conversation.

### Core Capabilities

1. **Conversational Plan Building**
   - Multi-turn dialogue to understand research goals
   - Ask clarifying questions about scope, depth, entities of interest
   - Suggest research strategies based on user input

2. **Knowledge Graph Queries**
   - Query existing entities in the knowledge graph (via GraphQL)
   - "What do we already know about X?"
   - Avoid redundant research on well-covered entities

3. **Past Research Lookup**
   - Query previous research runs and their outcomes
   - Learn from past successes/failures
   - Suggest reusable approaches

4. **Web Search Integration**
   - Quick validation searches during planning
   - "Is this entity real?"
   - "What are the key domains for this organization?"

5. **Memory Integration**
   - Semantic memory: Entity facts we've learned
   - Episodic memory: What worked in similar research missions
   - Procedural memory: Reusable research tactics

6. **Two Human Approval Stages**
   - **Stage 1: Scope Approval** - User approves the high-level research scope
   - **Stage 2: Final Plan Approval** - User approves the complete research plan before execution

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Coordinator Agent                         │
│                    (LangGraph Graph)                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │  Understand   │  │  Query Existing│  │  Build Initial │ │
│  │  User Goals   │→ │  Knowledge     │→ │  Scope         │ │
│  └───────────────┘  └────────────────┘  └────────────────┘ │
│           │                                       ↓          │
│           │         ┌─────────────────────────────────────┐ │
│           │         │  👤 HUMAN APPROVAL #1: Scope        │ │
│           │         └─────────────────────────────────────┘ │
│           │                       ↓                          │
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │  Suggest      │  │  Define Stages │  │  Allocate      │ │
│  │  Strategies   │→ │  & Sub-Stages  │→ │  Agent Types   │ │
│  └───────────────┘  └────────────────┘  └────────────────┘ │
│           │                                       ↓          │
│           │         ┌─────────────────────────────────────┐ │
│           │         │  👤 HUMAN APPROVAL #2: Final Plan   │ │
│           │         └─────────────────────────────────────┘ │
│           │                       ↓                          │
│           │         ┌────────────────┐                       │
│           └────────→│  Save Plan &   │                       │
│                     │  Emit to       │                       │
│                     │  Mission Queue │                       │
│                     └────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### Tools Available to Coordinator Agent

1. **Web Search Tools**
   - `tavily_search`: General web search
   - `exa_search`: Semantic search
   - `wikipedia_search`: Quick entity validation

2. **Knowledge Graph Query Tools** (NEW - TO BE IMPLEMENTED)
   - `query_existing_entities`: "What entities do we have for query X?"
   - `get_entity_details`: "Get full details for entity ID"
   - `search_entities_by_type`: "Find all organizations in domain X"

3. **Research History Tools** (NEW - TO BE IMPLEMENTED)
   - `query_past_research_runs`: "Find similar past research missions"
   - `get_research_run_summary`: "Get outcomes from run ID"
   - `get_research_run_agents_used`: "What agent types were effective?"

4. **Memory Tools**
   - `recall_semantic_memory`: Recall entity facts
   - `recall_episodic_memory`: Recall past run notes
   - `recall_procedural_memory`: Recall research tactics

5. **Candidate Exploration Tool** (Phase 3)
   - `explore_and_rank_candidates`: Quick candidate discovery + ranking

### State Model 

### Possible States and Examples 

```python
class CoordinatorAgentState(TypedDict):
    """State for the Coordinator Agent conversation."""
    
    # User input & context
    thread_id: str
    user_query: str
    messages: List[BaseMessage]
    
    # Extracted research goals
    research_goals: Optional[ResearchGoals]  # LLM-extracted structured goals
    entities_of_interest: List[str]
    research_depth: str  # "quick_overview" | "moderate" | "comprehensive"
    research_focus: List[str]  # ["leadership", "products", "evidence", ...]
    
    # Knowledge graph context
    existing_entities: List[ExistingEntitySummary]  # Entities already in KG
    gaps_identified: List[str]  # What's missing from KG
    
    # Past research context
    similar_past_runs: List[PastResearchRunSummary]
    lessons_learned: List[str]
    
    # Research plan construction
    proposed_scope: Optional[ResearchScope]  # High-level scope
    scope_approved: bool  # Human approval checkpoint #1
    
    research_stages: List[ResearchStage]  # S1, S2, S3, ...
    agent_allocations: List[AgentAllocation]  # Which agent types per stage
    source_recommendations: List[SourceRecommendation]
    
    final_plan: Optional[ResearchMissionPlanFinal]
    final_plan_approved: bool  # Human approval checkpoint #2
    
    # Control flow
    awaiting_human_input: bool
    human_feedback: Optional[str]
    plan_iteration_count: int
```

### MongoDB Models (NEW)

```python
# models/mongo/coordinator/docs/coordinator_threads.py

class CoordinatorThreadDoc(Document):
    """Stores conversation threads with the Coordinator Agent."""
    
    thread_id: str  # Unique thread ID
    user_id: Optional[str]  # Future: multi-user support
    
    # Thread metadata
    created_at: datetime
    updated_at: datetime
    status: str  # "active" | "scope_approved" | "plan_approved" | "plan_sent_to_execution"
    
    # Research context
    initial_query: str
    research_goals: Optional[ResearchGoals]
    
    # Messages (persisted for thread replay)
    messages: List[Dict]  # Serialized BaseMessage objects
    
    # Checkpoints (for human-in-the-loop)
    scope_checkpoint_id: Optional[str]
    final_plan_checkpoint_id: Optional[str]
    
    # Final output
    final_plan_mongo_id: Optional[PydanticObjectId]  # Ref to ResearchMissionPlanDoc
    
    class Settings:
        name = "coordinator_threads"
        indexes = ["thread_id", "status", "created_at"]


class CoordinatorCheckpointDoc(Document):
    """Stores checkpoints for human approval stages."""
    
    checkpoint_id: str
    thread_id: str
    checkpoint_type: str  # "scope_approval" | "final_plan_approval"
    
    created_at: datetime
    
    # Checkpoint data
    state_snapshot: Dict  # Full state at checkpoint
    human_prompt: str  # What we're asking the human
    
    # Human response
    approved: Optional[bool]
    human_feedback: Optional[str]
    responded_at: Optional[datetime]
    
    class Settings:
        name = "coordinator_checkpoints"
        indexes = ["thread_id", "checkpoint_type", "approved"]
```

### FastAPI Routes (NEW)

```python
# api/coordinator/routes/threads.py

@router.post("/coordinator/threads")
async def create_coordinator_thread(
    request: CreateThreadRequest
) -> CreateThreadResponse:
    """Start a new Coordinator Agent conversation."""
    # Create thread, invoke graph with initial message
    pass


@router.post("/coordinator/threads/{thread_id}/messages")
async def send_message_to_coordinator(
    thread_id: str,
    message: SendMessageRequest
) -> SendMessageResponse:
    """Send a message to the Coordinator Agent."""
    # Append message, invoke graph, stream response
    pass


@router.get("/coordinator/threads/{thread_id}")
async def get_thread(thread_id: str) -> ThreadResponse:
    """Get thread details and message history."""
    pass


@router.get("/coordinator/threads/{thread_id}/checkpoints")
async def get_thread_checkpoints(thread_id: str) -> CheckpointsResponse:
    """Get all checkpoints for a thread (awaiting human approval)."""
    pass


@router.post("/coordinator/checkpoints/{checkpoint_id}/approve")
async def approve_checkpoint(
    checkpoint_id: str,
    approval: CheckpointApprovalRequest
) -> CheckpointApprovalResponse:
    """Approve or reject a checkpoint (human-in-the-loop)."""
    # Update checkpoint, resume graph from checkpoint
    pass


# WebSocket endpoint for streaming
@router.websocket("/coordinator/threads/{thread_id}/stream")
async def stream_coordinator_messages(websocket: WebSocket, thread_id: str):
    """Stream Coordinator Agent messages in real-time."""
    pass
```

### Next.js Research Client

```
research_client/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                    # Home: List threads or create new
│   ├── threads/
│   │   ├── [thread_id]/
│   │   │   └── page.tsx            # Main chat interface
│   │   └── new/
│   │       └── page.tsx            # Create new thread
│   └── api/
│       └── coordinator/            # API proxy to FastAPI
│
├── components/
│   ├── chat/
│   │   ├── ChatInterface.tsx       # Main chat UI
│   │   ├── MessageBubble.tsx
│   │   ├── ApprovalCheckpoint.tsx  # Human approval UI
│   │   └── PlanVisualization.tsx   # Show research plan structure
│   ├── plan/
│   │   ├── ResearchPlanView.tsx    # Detailed plan view
│   │   ├── StageCard.tsx
│   │   └── AgentAllocationView.tsx
│   └── knowledge-graph/
│       └── ExistingEntitiesView.tsx # Show entities already in KG
│
├── lib/
│   ├── api-client.ts               # FastAPI client
│   ├── websocket.ts                # WebSocket connection manager
│   └── types.ts                    # TypeScript types
│
├── hooks/
│   ├── useCoordinatorThread.ts
│   ├── useCheckpointApproval.ts
│   └── useWebSocket.ts
│
└── package.json
```

### Implementation Steps for Phase 1

1. **Create Beanie Models**
   - `CoordinatorThreadDoc`
   - `CoordinatorCheckpointDoc`

2. **Create GraphQL Query Tools**
   - Implement tools that query the GraphQL API
   - Tools for entity lookup, entity search, entity details

3. **Create Research History Tools**
   - Query `ResearchRunDoc` collection
   - Summarize past research outcomes

4. **Build Coordinator LangGraph**
   - Define `CoordinatorAgentState`
   - Implement nodes: understand_goals, query_knowledge, build_scope, etc.
   - Implement human-in-the-loop checkpoints
   - Use `interrupt()` for human approval stages

5. **Create FastAPI Routes**
   - Thread management routes
   - Checkpoint approval routes
   - WebSocket streaming

6. **Build Next.js Client**
   - Chat interface
   - Approval checkpoint UI
   - Plan visualization
   - WebSocket integration

7. **Testing**
   - Unit tests for tools
   - Integration tests for graph flow
   - E2E tests for full conversation → plan approval flow

---

## PHASE 2: Research Plan & Mission Orchestration (MOST CRITICAL)

### The Problem with Current Approach

**Current (BAD) Approach:**
1. Entity Discovery Graph generates domain catalogs for EVERY entity
2. Domain catalogs are rigid URL structures
3. Research Plan Graph relies on these domain catalogs to assign sources
4. This is **inefficient**, **slow**, and **inflexible**

**Why It Doesn't Make Sense:**
- Not all research missions need domain catalogs
- Domain catalogs are expensive to generate (many LLM calls)
- Some research is better served by web search, not domain crawling
- Research plans should be flexible, not rigidly tied to URL structures

### New Approach: Flexible Research Plans

**Research Plans should be:**
- **Agent-centric**: Define what agents do, not what domains they crawl
- **Objective-driven**: Each agent has clear objectives, not just "crawl these URLs"
- **Tool-flexible**: Agents can use web search, filesystem, memory, AND optional starter sources
- **Output-aware**: Stages pass outputs to downstream stages
- **Execution-flexible**: Can run sequential, incremental, or fully parallel

### Research Plan Structure (REDESIGNED)

```python
class ResearchObjective(BaseModel):
    """A specific research objective for an agent."""
    
    objective_id: str
    description: str  # "Identify the leadership team of Novo Nordisk"
    success_criteria: List[str]  # ["Find CEO name", "Find at least 5 exec names"]
    priority: str  # "critical" | "high" | "medium" | "low"


class AgentInstancePlan(BaseModel):
    """Plan for a single agent instance execution."""
    
    instance_id: str
    agent_type: str  # "BusinessIdentityAndLeadershipAgent"
    
    # What the agent should do
    objectives: List[ResearchObjective]
    
    # What the agent gets as input
    seed_context: Dict[str, Any]  # Entities, focus areas, etc.
    starter_sources: List[str]  # OPTIONAL starter URLs
    
    # What tools the agent can use
    allowed_tools: List[str]
    
    # Dependencies
    requires_outputs_from: List[str]  # List of instance_ids
    previous_stage_outputs: Optional[Dict]  # Outputs from prev stage
    
    # Execution config
    max_steps: int
    timeout_minutes: int


class SubStage(BaseModel):
    """A sub-stage groups related agent instances."""
    
    sub_stage_id: str
    name: str
    description: str
    
    # Agent instances in this sub-stage
    agent_instances: List[str]  # instance_ids
    
    # Execution mode
    execution_mode: str  # "parallel" | "sequential"
    
    # Dependencies
    depends_on_sub_stages: List[str]  # sub_stage_ids that must complete first
    
    # Output handling
    output_aggregation: str  # "merge_all" | "best_of" | "consensus"


class Stage(BaseModel):
    """A stage groups related sub-stages."""
    
    stage_id: str
    name: str
    description: str
    
    # Sub-stages in this stage
    sub_stages: List[str]  # sub_stage_ids
    
    # Execution mode
    execution_mode: str  # "parallel" | "sequential"
    
    # Dependencies
    depends_on_stages: List[str]  # stage_ids that must complete first
    
    # Output handling
    stage_outputs: Dict[str, Any]  # Aggregated outputs from all sub-stages


class ResearchMissionPlan(BaseModel):
    """Complete research mission plan."""
    
    mission_id: str
    created_by: str  # "coordinator_agent" | "manual"
    
    # Mission metadata
    mission_name: str
    mission_description: str
    research_depth: str  # "quick" | "moderate" | "comprehensive"
    
    # Research structure
    stages: List[Stage]
    sub_stages: List[SubStage]
    agent_instances: List[AgentInstancePlan]
    
    # Execution config
    execution_strategy: str  # "sequential" | "parallel" | "hybrid"
    fail_fast: bool
    
    # WebSocket progress
    progress_webhook_url: Optional[str]
    
    # Output config
    save_to_knowledge_graph: bool
    extraction_config: Optional[ExtractionConfig]
```

### Execution Modes Explained

**Sequential Execution:**
```
Stage 1 (Identity)
  → Complete → Pass outputs to Stage 2
                 ↓
               Stage 2 (Products)
                 → Complete → Pass outputs to Stage 3
                               ↓
                             Stage 3 (Evidence)
```

**Parallel Execution:**
```
Stage 1 (Identity)  ──┐
Stage 2 (Products)  ──┼──→ All run simultaneously
Stage 3 (Evidence)  ──┘
```

**Hybrid (Most Common):**
```
Stage 1 (Identity - Foundation)
  → Complete → Outputs passed to:
                 ┌─────────────┬─────────────┐
                 ↓             ↓             ↓
              Stage 2a      Stage 2b      Stage 2c
              (Products)    (Tech)        (Evidence)
              [PARALLEL]    [PARALLEL]    [PARALLEL]
                 └─────────────┴─────────────┘
                              ↓
                      Stage 3 (Synthesis)
```

### Research Mission Orchestration

**Flow:**
1. **Coordinator Agent** creates `ResearchMissionPlan`
2. **Mission Control API** receives plan, builds DAG
3. **DAG Builder** creates task definitions with dependencies
4. **Scheduler** enqueues tasks as dependencies complete
5. **Workers** execute agent instances
6. **Progress** streamed via WebSocket
7. **Outputs** passed between stages
8. **Final Results** sent to Extraction Pipeline (Phase 4)

**Enhanced DAG Builder:**
```python
def build_mission_dag(plan: ResearchMissionPlan) -> MissionDAG:
    """Build DAG from flexible research plan."""
    
    tasks = {}
    
    # Create tasks for each agent instance
    for instance in plan.agent_instances:
        task_id = f"instance::{plan.mission_id}::{instance.instance_id}"
        
        # Determine dependencies
        depends_on = []
        for required_instance_id in instance.requires_outputs_from:
            depends_on.append(f"instance::{plan.mission_id}::{required_instance_id}")
        
        # Add sub-stage dependencies
        sub_stage = find_sub_stage_for_instance(instance.instance_id, plan)
        for dep_sub_stage_id in sub_stage.depends_on_sub_stages:
            depends_on.append(f"substage_reduce::{plan.mission_id}::{dep_sub_stage_id}")
        
        tasks[task_id] = TaskDefinition(
            task_id=task_id,
            task_type="INSTANCE_RUN",
            depends_on=depends_on,
            payload=instance.model_dump(),
        )
    
    # Create aggregation tasks for sub-stages
    for sub_stage in plan.sub_stages:
        task_id = f"substage_reduce::{plan.mission_id}::{sub_stage.sub_stage_id}"
        
        # Depends on all agent instances in sub-stage
        depends_on = [
            f"instance::{plan.mission_id}::{inst_id}"
            for inst_id in sub_stage.agent_instances
        ]
        
        tasks[task_id] = TaskDefinition(
            task_id=task_id,
            task_type="SUBSTAGE_REDUCE",
            depends_on=depends_on,
            payload=sub_stage.model_dump(),
        )
    
    return MissionDAG(tasks=tasks)
```

### WebSocket Progress Updates

```python
# Real-time progress events streamed to client

class ProgressEvent(BaseModel):
    mission_id: str
    event_type: str
    timestamp: datetime
    
    # Event-specific data
    task_id: Optional[str]
    stage_id: Optional[str]
    sub_stage_id: Optional[str]
    instance_id: Optional[str]
    
    message: str
    progress_percent: float

# Example events:
# - "MISSION_STARTED"
# - "STAGE_STARTED" (stage_id: "S1")
# - "INSTANCE_STARTED" (instance_id: "inst_001")
# - "INSTANCE_PROGRESS" (instance_id: "inst_001", message: "Completed 5/10 objectives")
# - "INSTANCE_COMPLETED" (instance_id: "inst_001")
# - "SUBSTAGE_REDUCE_STARTED" (sub_stage_id: "S1.1")
# - "SUBSTAGE_COMPLETED" (sub_stage_id: "S1.1")
# - "STAGE_COMPLETED" (stage_id: "S1")
# - "MISSION_COMPLETED"
```

### Agent Instance Execution (Enhanced)

**Agent gets:**
- Clear objectives (not just "research this domain")
- Seed context (entities, focus areas)
- Optional starter sources (if provided)
- Full tool access (web search, filesystem, memory)
- Previous stage outputs (if applicable)

**Agent execution flow:**
```python
async def execute_agent_instance(
    plan: AgentInstancePlan,
    previous_outputs: Optional[Dict] = None
) -> AgentInstanceOutput:
    """Execute a single agent instance."""
    
    # Build agent with tools
    agent = build_worker_agent(
        agent_type=plan.agent_type,
        allowed_tools=plan.allowed_tools,
    )
    
    # Prepare initial state
    state = WorkerAgentState(
        agent_instance_plan=plan,
        seed_context=plan.seed_context,
        starter_sources=plan.starter_sources,
        previous_outputs=previous_outputs,  # NEW: outputs from prev stage
        objectives=plan.objectives,
        messages=[],
        workspace_root=f"/workspace/{plan.instance_id}",
    )
    
    # Execute agent
    result = await agent.ainvoke(state)
    
    # Extract outputs
    outputs = {
        "objectives_completed": result["objectives_completed"],
        "findings": result["research_notes"],
        "entities_discovered": result["entities_discovered"],
        "files_created": result["file_refs"],
    }
    
    return AgentInstanceOutput(
        instance_id=plan.instance_id,
        status="completed",
        outputs=outputs,
    )
```

### Sub-Stage Output Aggregation

```python
async def aggregate_substage_outputs(
    sub_stage: SubStage,
    instance_outputs: List[AgentInstanceOutput]
) -> SubStageOutput:
    """Aggregate outputs from all instances in a sub-stage."""
    
    if sub_stage.output_aggregation == "merge_all":
        # Simply merge all outputs
        merged = {
            "findings": [],
            "entities_discovered": [],
            "files_created": [],
        }
        for output in instance_outputs:
            merged["findings"].extend(output.outputs["findings"])
            merged["entities_discovered"].extend(output.outputs["entities_discovered"])
            merged["files_created"].extend(output.outputs["files_created"])
        
        return SubStageOutput(
            sub_stage_id=sub_stage.sub_stage_id,
            aggregated_outputs=merged,
        )
    
    elif sub_stage.output_aggregation == "best_of":
        # Use LLM to select best outputs
        best = await llm_select_best_outputs(instance_outputs)
        return SubStageOutput(
            sub_stage_id=sub_stage.sub_stage_id,
            aggregated_outputs=best,
        )
    
    elif sub_stage.output_aggregation == "consensus":
        # Use LLM to find consensus across outputs
        consensus = await llm_find_consensus(instance_outputs)
        return SubStageOutput(
            sub_stage_id=sub_stage.sub_stage_id,
            aggregated_outputs=consensus,
        )
```

### Implementation Steps for Phase 2

1. **Redesign Research Plan Models**
   - Create new `ResearchObjective`, `AgentInstancePlan`, `SubStage`, `Stage` models
   - Remove domain catalog dependencies

2. **Update DAG Builder**
   - Support flexible dependencies (instance → instance, sub-stage → stage)
   - Support output passing between tasks

3. **Enhance Worker Execution**
   - Accept `previous_outputs` parameter
   - Make starter sources optional
   - Focus on objectives, not domain crawling

4. **Implement Sub-Stage Aggregation**
   - Merge, best-of, consensus strategies
   - Pass aggregated outputs to downstream stages

5. **WebSocket Progress**
   - Emit progress events at each step
   - Stream to research client

6. **Update Coordinator Agent**
   - Generate flexible research plans (not domain-catalog-dependent)
   - Suggest execution strategies based on research goals

---

## PHASE 3: Entity Candidates Refactor

### Current Problems

The current `entity_candidates_connected_graph.py` is **highly inefficient**:
- Generates domain catalogs for EVERY entity (slow, expensive)
- Over-generates candidates (too many false positives)
- Tightly coupled to research plan generation

### New Approach: Lightweight Candidate Ranking

**Purpose:** Transform into a **special tool** that can be used by the Coordinator Agent to:
- Quickly explore candidate entities
- Rank candidates by relevance/importance
- Suggest which entities are worth deep research

**NOT** a mandatory step in every research mission.

### Refactored Graph Structure

```python
class CandidateExplorationInput(BaseModel):
    """Input for candidate exploration."""
    query: str
    max_candidates: int = 10
    candidate_types: List[str]  # ["organization", "person", "product"]
    ranking_criteria: str  # "relevance" | "completeness" | "novelty"


class CandidateExplorationOutput(BaseModel):
    """Output from candidate exploration."""
    candidates: List[RankedCandidate]
    exploration_summary: str


class RankedCandidate(BaseModel):
    """A single candidate with ranking score."""
    
    entity_type: str
    canonical_name: str
    aliases: List[str]
    
    # Ranking
    relevance_score: float  # 0-1
    completeness_score: float  # 0-1 (how much info we have)
    novelty_score: float  # 0-1 (is this new or do we already have it?)
    
    # Quick context
    quick_summary: str
    official_domains: List[str]
    
    # Recommendation
    recommended_for_research: bool
    research_priority: str  # "high" | "medium" | "low"
```

### Simplified Graph Flow

```
User Query: "Research GLP-1 agonist manufacturers"
          ↓
[Quick Entity Extraction]
  → Extract: Organizations (Novo Nordisk, Eli Lilly, etc.)
             Products (Ozempic, Mounjaro, etc.)
          ↓
[Relevance Ranking]
  → Score each candidate:
     - Relevance to query: 0.95 (Novo Nordisk)
     - Relevance to query: 0.92 (Eli Lilly)
     - Relevance to query: 0.45 (Generic Pharma Corp) → FILTER OUT
          ↓
[Novelty Check]
  → Query Knowledge Graph:
     - Novo Nordisk: Already have comprehensive data → Novelty: 0.1
     - Eli Lilly: Minimal data → Novelty: 0.9
          ↓
[Completeness Estimation]
  → Quick web search for each:
     - Novo Nordisk: Rich official sources → Completeness: 0.9
     - Eli Lilly: Limited sources → Completeness: 0.6
          ↓
[Output Ranked List]
  1. Eli Lilly (Priority: HIGH - novel, relevant, completable)
  2. Novo Nordisk (Priority: LOW - already have data)
```

### Integration as Tool

```python
# tools/candidate_exploration/explore_and_rank.py

class ExploreAndRankCandidatesTool(BaseTool):
    """Tool for Coordinator Agent to explore and rank candidates."""
    
    name = "explore_and_rank_candidates"
    description = """
    Quickly explore candidate entities related to a query and rank them
    by research priority. Returns top candidates worth deep research.
    
    Input: query string, optional max_candidates (default 10)
    Output: Ranked list of candidates with recommendations
    """
    
    async def _arun(self, query: str, max_candidates: int = 10) -> str:
        # Invoke simplified entity exploration graph
        graph = build_candidate_exploration_graph()
        result = await graph.ainvoke({
            "query": query,
            "max_candidates": max_candidates,
        })
        
        # Format output for LLM
        return format_candidates_for_llm(result["candidates"])
```

### Implementation Steps for Phase 3

1. **Simplify Entity Discovery Graph**
   - Remove domain catalog generation
   - Remove official sources deep dive
   - Keep only: quick extraction + ranking

2. **Implement Ranking Logic**
   - Relevance scoring (based on query)
   - Novelty scoring (query KG for existing entities)
   - Completeness estimation (quick web search)

3. **Create Tool Interface**
   - Wrap simplified graph as LangChain tool
   - Make available to Coordinator Agent

4. **Update Coordinator Agent**
   - Use tool to help users prioritize entities
   - "I found 10 candidates. Eli Lilly and Sanofi are high priority because..."

5. **Optional Route**
   - Keep as standalone API route for manual exploration
   - `POST /candidates/explore-and-rank`

---

## PHASE 4: Extraction & Storage

### Purpose

After research missions complete, we need to:
1. Extract structured entities from agent outputs
2. Store entities in the knowledge graph (Neo4j via GraphQL)
3. Link entities to evidence (document chunks)

### Extraction Pipeline

```
Agent Outputs (files, research notes)
          ↓
[Parse Reports]
  → Read all final reports
  → Read all checkpoint files
          ↓
[Extract Entities]
  → LLM structured extraction:
     - Organizations (name, domains, description, etc.)
     - People (name, affiliations, bio, etc.)
     - Products (name, organization, claims, etc.)
     - Compounds (name, mechanism, structure, etc.)
          ↓
[Extract Relationships]
  → Identify connections:
     - Person WORKS_FOR Organization
     - Organization DEVELOPS Product
     - Product CONTAINS Compound
     - Document MENTIONS Entity
          ↓
[GraphQL Mutations]
  → Upsert entities to Neo4j
  → Create relationships
  → Link documents to entities
          ↓
[Knowledge Graph Updated]
```

### Extraction Graph

```python
class ExtractionState(TypedDict):
    """State for extraction graph."""
    
    mission_id: str
    research_run_id: str
    
    # Input files
    final_reports: List[FileReference]
    checkpoint_files: List[FileReference]
    
    # Extracted entities
    organizations: List[OrganizationExtracted]
    people: List[PersonExtracted]
    products: List[ProductExtracted]
    compounds: List[CompoundExtracted]
    
    # Extracted relationships
    relationships: List[RelationshipExtracted]
    
    # Evidence links
    evidence_links: List[EvidenceLink]
    
    # GraphQL results
    graphql_entity_ids: Dict[str, str]  # local_id → neo4j_id
    graphql_errors: List[str]
```

### GraphQL Mutations (via Ariadne Client)

```python
# services/graphql/mutations.py

async def upsert_organization(
    client: GraphQLClient,
    org: OrganizationExtracted
) -> str:
    """Upsert organization to Neo4j, return Neo4j ID."""
    
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


async def create_relationship(
    client: GraphQLClient,
    source_id: str,
    target_id: str,
    relationship_type: str,
    properties: Dict
) -> str:
    """Create relationship between entities."""
    
    mutation = """
    mutation CreateRelationship($input: RelationshipInput!) {
        createRelationship(input: $input) {
            id
        }
    }
    """
    
    result = await client.execute(mutation, variables={
        "input": {
            "sourceId": source_id,
            "targetId": target_id,
            "type": relationship_type,
            "properties": properties,
        }
    })
    
    return result["createRelationship"]["id"]
```

### Implementation Steps for Phase 4

1. **Create Extraction Graph**
   - Parse reports node
   - Extract entities node
   - Extract relationships node
   - Link evidence node

2. **Implement GraphQL Mutations**
   - Entity upsert mutations (org, person, product, compound)
   - Relationship creation mutations
   - Evidence link mutations

3. **Create Extraction API Route**
   - `POST /extraction/extract-from-mission`
   - Input: mission_id
   - Output: extraction_summary

4. **Integrate with Mission Control**
   - After mission completes, trigger extraction
   - Stream extraction progress via WebSocket

5. **Update Research Client**
   - Show extraction progress
   - Show entities added to KG
   - Link to KG visualization

---

## MongoDB Collections Summary

### Coordinator (Phase 1)
- `coordinator_threads`: Conversation threads
- `coordinator_checkpoints`: Human approval checkpoints

### Research (Phase 2 - Updated)
- `research_mission_plans`: Flexible research plans (redesigned structure)
- `research_runs`: Mission execution tracking
- `research_outputs`: Agent instance outputs (NEW)
- `substage_outputs`: Aggregated sub-stage outputs (NEW)

### Candidates (Phase 3 - Simplified)
- `candidate_explorations`: Quick candidate exploration results
- `ranked_candidates`: Candidate rankings (simplified)

### Entities (Phase 4)
- `extracted_entities`: Entities extracted from research (pre-KG)
- `extraction_runs`: Extraction pipeline run tracking

### Existing (Keep As Is)
- Domain catalogs: **DEPRECATED** (remove dependency, keep for backward compat)
- Connected candidates: **DEPRECATED** (replaced by ranked_candidates)

---

## API Servers Summary

### 1. Coordinator API (NEW)
- **Port**: 8001
- **Purpose**: Coordinator Agent interaction
- **Routes**:
  - `POST /coordinator/threads`
  - `POST /coordinator/threads/{id}/messages`
  - `GET /coordinator/threads/{id}`
  - `POST /coordinator/checkpoints/{id}/approve`
  - `WS /coordinator/threads/{id}/stream`

### 2. Mission Control API (ENHANCED)
- **Port**: 8002
- **Purpose**: Research mission orchestration
- **Routes**:
  - `POST /missions` (create and start)
  - `GET /missions/{id}`
  - `GET /missions/{id}/runs`
  - `POST /missions/runs/{id}/cancel`
  - `WS /missions/runs/{id}/progress` (NEW: WebSocket progress)

### 3. Memory & Thread API (KEEP)
- **Port**: 8003
- **Purpose**: LangGraph memory and checkpointing
- **Routes**: (existing routes remain)

### 4. Extraction API (NEW)
- **Port**: 8004
- **Purpose**: Entity extraction and KG storage
- **Routes**:
  - `POST /extraction/extract-from-mission`
  - `GET /extraction/runs/{id}`
  - `WS /extraction/runs/{id}/progress`

---

## Development Workflow

### 1. Start Coordinator Agent Conversation

```bash
# Terminal 1: Start Coordinator API
uvicorn research_agent.api.coordinator.main:app --reload --port 8001

# Terminal 2: Start Next.js client
cd research_client/
npm run dev
```

**User flow:**
1. User opens research client
2. Creates new thread
3. Chats with Coordinator Agent
4. Approves scope
5. Reviews and approves final plan
6. Plan sent to Mission Control

### 2. Execute Research Mission

```bash
# Terminal 3: Start Mission Control API
uvicorn research_agent.api.mission_control.main:app --reload --port 8002

# Terminal 4: Start Scheduler
python -m research_agent.orchestration.scheduler.in_memory

# Terminal 5-N: Start Workers
python -m research_agent.orchestration.workers.taskiq_worker
```

**Execution flow:**
1. Mission Control receives plan from Coordinator
2. Builds DAG with flexible dependencies
3. Enqueues tasks to Redis
4. Workers execute agent instances
5. Progress streamed to research client via WebSocket
6. Outputs passed between stages
7. Mission completes

### 3. Extract and Store Results

```bash
# Terminal X: Start Extraction API
uvicorn research_agent.api.extraction.main:app --reload --port 8004
```

**Extraction flow:**
1. Extraction API triggered (manually or automatically)
2. Extraction graph processes outputs
3. GraphQL mutations sent to Neo4j
4. Entities and relationships stored in KG
5. Progress streamed to research client

---

## Key Design Principles

### 1. Conversation-First Design
- Research plans are created through dialogue, not automation
- Human input guides the research scope and strategy
- Coordinator Agent provides expertise, but human approves

### 2. Flexibility Over Rigidity
- No mandatory domain catalogs
- No rigid URL structures
- Agents use whatever tools make sense (web search, sources, memory)
- Execution can be sequential, parallel, or hybrid

### 3. Output-Aware Execution
- Stages can pass outputs to downstream stages
- Agents can build on previous work
- Sub-stage aggregation combines related findings

### 4. Progressive Disclosure
- Start with lightweight exploration (Phase 3 tool)
- Deep research only for high-priority entities
- Human approves before committing resources

### 5. Observable by Default
- WebSocket progress at every step
- Clear visibility into what agents are doing
- Easy to debug and iterate

---

## Next Steps

### Immediate (Phase 1 - Week 1)
1. ✅ Document new architecture (this file)
2. Create `.cursor/rules/coordinator-agent.mdc` specification
3. Create `.cursor/rules/research-plan-structure.mdc` specification
4. Implement Coordinator Agent Beanie models
5. Create GraphQL query tools
6. Build Coordinator LangGraph
7. Create Coordinator API routes
8. Initialize Next.js research client

### Short-Term (Phase 2 - Week 2-3)
1. Redesign Research Plan models
2. Update DAG Builder for flexible execution
3. Enhance worker execution (output passing)
4. Implement WebSocket progress streaming
5. Update Coordinator Agent to generate flexible plans

### Medium-Term (Phase 3 - Week 3-4)
1. Refactor entity candidates graph
2. Implement ranking logic
3. Create exploration tool
4. Integrate with Coordinator Agent

### Long-Term (Phase 4 - Week 4+)
1. Build Extraction Graph
2. Implement GraphQL mutations
3. Create Extraction API
4. Integrate with Mission Control

---

## Success Criteria

### Phase 1 Complete When:
- ✅ User can start a conversation with Coordinator Agent
- ✅ Coordinator Agent can query existing KG entities
- ✅ Coordinator Agent can create a research plan
- ✅ User can approve scope and final plan via UI
- ✅ Approved plan saved to MongoDB

### Phase 2 Complete When:
- ✅ Research plans are flexible (no domain catalog dependency)
- ✅ Agents execute with objectives + optional sources
- ✅ Stages can pass outputs to downstream stages
- ✅ WebSocket progress streams to client
- ✅ Missions complete successfully with correct outputs

### Phase 3 Complete When:
- ✅ Candidate exploration is fast (<30 seconds)
- ✅ Candidates ranked by relevance/novelty/completeness
- ✅ Coordinator Agent can use exploration tool
- ✅ Users can see prioritized candidate recommendations

### Phase 4 Complete When:
- ✅ Entities extracted from research outputs
- ✅ Entities stored in Neo4j via GraphQL
- ✅ Relationships created correctly
- ✅ Evidence linked to entities
- ✅ Knowledge graph grows with each research mission

---

**Last Updated**: 2026-02-15  
**Version**: 2.0 (NEW ARCHITECTURE)  
**Status**: Active Development - Phase 1 Starting  
**Next Review**: After Phase 1 Complete
