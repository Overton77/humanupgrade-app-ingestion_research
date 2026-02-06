# Research Agent & Ingestion Pipeline - Project Goals

This document defines the current state, goals, and vision for the research agent and ingestion pipeline system.

---

## Table of Contents

1. [Current State](#current-state)
2. [Workflow Overview](#workflow-overview)
3. [Final Form Vision](#final-form-vision)
4. [Special Considerations](#special-considerations)
5. [Implementation Roadmap](#implementation-roadmap)

---

## Current State

### Architecture

The system is currently a **Multi-Graph LangGraph workflow** that researches biotech entities, topics, research, and anything biotech-related. The implementation is located in `ingestion/src/research_agent/human_upgrade/`.

### Technology Stack

- **LangGraph**: Multi-graph workflow orchestration
- **LangChain**: Agent framework and tooling
- **Pydantic**: Data validation and structured outputs
- **MongoDB**: Current data storage (to be migrated to Beanie)
- **Python**: Primary implementation language

### Current Components

1. **Entity Candidates Graph**: Discovers and validates candidate entities
2. **Connected Candidates Graph**: Builds relationships between candidates
3. **Research Plan Graph**: Creates initial and final research plans
4. **Research Mission Graph**: Orchestrates multi-stage research missions
5. **Stage Graph**: Executes individual research stages
6. **Sub-Agent Graphs**: Specialized agents for specific research tasks

### Current Limitations

- **Fragile Pydantic models**: MongoDB models are represented as Pydantic, not Beanie
- **No persistent memory**: No LangMem or similar memory system
- **No FastAPI server**: No API layer for workflow execution
- **No knowledge graph storage**: Entities not stored in Neo4j/GraphQL
- **No document conversion**: No Docling integration for document processing
- **No frontend**: No React interface for interaction
- **Limited human-in-the-loop**: No structured approval/review gates
- **No memory learning**: System doesn't learn from past research runs

---

## Workflow Overview

### End-to-End Research Flow

```
Query + Starter Sources + Starter Media + System Prompt
    ↓
[Candidates Graph]
    ↓
Entity Candidates (businesses, people, products, compounds)
    ↓
[Connected Candidates Graph]
    ↓
Connected Candidate Bundle
    ↓
[Research Plan Graph - Initial]
    ↓
Initial Research Plan
    (stages + sub-stages + agent instances, NO sources yet)
    ↓
[Source Expansion Node]
    ↓
[Research Plan Graph - Final]
    ↓
Final Research Plan
    (stages + sub-stages + agent instances WITH sources)
    ↓
[Research Mission Graph]
    ↓
Stage Execution (parallel where possible)
    ↓
Sub-Agent Execution
    ↓
Research Outputs
```

### Detailed Workflow Stages

#### 1. Candidate Discovery

**Input**: Query, starter sources, starter media, system prompt

**Process**:
- Extract entity mentions from sources
- Validate and deduplicate candidates
- Classify entities (business, person, product, compound, etc.)

**Output**: List of entity candidates with metadata

#### 2. Connected Candidates

**Input**: Entity candidates

**Process**:
- Identify relationships between candidates
- Build candidate bundles (related entities)
- Determine research directions per bundle

**Output**: Connected candidate bundles with relationship graphs

#### 3. Initial Research Plan

**Input**: Connected candidate bundles

**Process**:
- Determine stage mode (full_entities_standard, full_entities_basic, etc.)
- Create stage structure (S1, S2, S3, etc.)
- Create sub-stages within each stage
- Generate agent instances for each sub-stage
- Apply slicing for parallel processing (people, products)
- **NO SOURCES YET** - this is the skeleton

**Output**: `InitialResearchPlan` with stages, sub-stages, and agent instances

#### 4. Source Expansion

**Input**: Initial research plan, candidate bundles

**Process**:
- Discover additional sources (competitors, research papers, news)
- Curate domain catalogs (official sources)
- Match sources to agent instances based on objectives

**Output**: Expanded source lists per agent instance

#### 5. Final Research Plan

**Input**: Initial research plan, expanded sources

**Process**:
- Attach starter sources to each agent instance
- Prioritize source assignments (official > scholarly > press)
- Respect stage dependencies and context flow
- Validate source relevance

**Output**: `ResearchMissionPlanFinal` with complete source assignments

#### 6. Research Mission Execution

**Input**: Final research plan

**Process**:
- Execute stages in dependency order
- Run sub-stages (parallel where possible)
- Execute agent instances with assigned sources
- Collect outputs and artifacts
- Track progress and logs

**Output**: Mission outputs, stage outputs, agent outputs, logs

### Research Plan Structure

A research plan consists of:

- **Mission ID**: Unique identifier
- **Stage Mode**: Determines available stages and agents
- **Mission Objectives**: High-level goals
- **Stages**: Ordered research phases
  - **Stage ID**: S1, S2, S3, etc.
  - **Dependencies**: Which stages must complete first
  - **Sub-Stages**: Granular work units within a stage
    - **Sub-Stage ID**: S1.1, S1.2, etc.
    - **Agent Instances**: Specific agent executions
      - **Instance ID**: Deterministic format
      - **Agent Type**: BusinessIdentityAndLeadershipAgent, ProductSpecAgent, etc.
      - **Slice**: Optional slicing for parallel processing
      - **Objectives**: What this instance should accomplish
      - **Starter Sources**: URLs to begin research
      - **Tools**: Available tools for this instance

### Current Agent Types

- **BusinessIdentityAndLeadershipAgent**: Company identity, leadership, structure
- **PersonBioAndAffiliationsAgent**: Person biographies and affiliations
- **ProductSpecAgent**: Product specifications and details
- **EcosystemMapperAgent**: Competitive landscape and ecosystem
- **CaseStudyHarvestAgent**: Evidence discovery and case studies
- **CompoundResearchAgent**: Compound research and properties
- (More agent types can be created dynamically)

---

## Final Form Vision

### 1. FastAPI Server

**Goal**: Expose the research system through a REST API

**Features**:
- Run entire workflows from API endpoints
- Execute specific graphs independently
- Resume workflows from any `thread_id`, `checkpoint_id`, or `checkpoint_ns`
- Use LangSmith SDK and LangGraph's built-in graph state features
- WebSocket support for real-time progress updates
- Authentication and authorization
- Rate limiting and quota management

**Endpoints** (planned):
- `POST /research/missions` - Start a new research mission
- `GET /research/missions/{mission_id}` - Get mission status
- `POST /research/missions/{mission_id}/resume` - Resume from checkpoint
- `GET /research/graphs` - List available graphs
- `POST /research/graphs/{graph_name}/execute` - Execute specific graph
- `GET /research/checkpoints/{checkpoint_id}` - Get checkpoint state

### 2. Beanie Models for MongoDB

**Goal**: Replace fragile Pydantic models with robust Beanie ODM models

**Benefits**:
- Type-safe database operations
- Automatic validation
- Relationship management
- Migration support
- Better error handling

**Models to Convert**:
- ResearchPlan models
- ResearchRun models
- Candidate models
- Source models
- AgentInstance models
- Output models

**API Integration**: Beanie models exposed through FastAPI endpoints

### 3. Robust Memory Operations with LangMem

**Goal**: Implement episodic, semantic, and procedural memory

**Memory Types**:

- **Episodic Memory**: 
  - Store specific research runs and their outcomes
  - Remember what worked and what didn't
  - Track source quality and reliability
  - Learn from human feedback

- **Semantic Memory**:
  - Store learned facts about entities
  - Maintain knowledge graph relationships
  - Remember domain patterns and heuristics
  - Build entity profiles over time

- **Procedural Memory**:
  - Remember successful research strategies
  - Learn optimal agent configurations
  - Remember effective source discovery patterns
  - Store workflow optimizations

**Memory Operations**:
- **Retrieval**: Query past research, entity knowledge, strategies
- **Forgetting**: Prune outdated or low-quality memories
- **Updating**: Refine memories based on new evidence
- **Using**: Apply memories to improve current research

**Integration Points**:
- Before research: Query knowledge graph and past runs
- During research: Store findings and learnings
- After research: Update memories with outcomes
- Human review: Incorporate human feedback into memories

### 4. Neo4j-Backed GraphQL API

**Goal**: Build a biotech knowledge graph from research

**Components**:

- **Neo4j Database**: Store entities, relationships, and properties
- **GraphQL API**: Query and mutate the knowledge graph
- **Entity Types**: Organizations, People, Products, Compounds, Research, Documents, Chunks
- **Relationships**: Works_For, Develops, Researches, Cites, Contains, etc.

**Re-implementation Required**:
- **Extraction Graph**: Currently extracts entities but doesn't store in Neo4j
- New extraction graph should:
  - Extract entities from research outputs
  - Create/update Neo4j nodes
  - Create/update relationships
  - Link to source documents and chunks
  - Handle deduplication and merging

**GraphQL Schema** (planned):
```graphql
type Organization {
  id: ID!
  name: String!
  description: String
  website: String
  products: [Product!]!
  people: [Person!]!
  research: [Research!]!
}

type Person {
  id: ID!
  name: String!
  affiliations: [Organization!]!
  research: [Research!]!
}

type Product {
  id: ID!
  name: String!
  organization: Organization!
  specifications: JSON
  evidence: [Evidence!]!
}

type Document {
  id: ID!
  url: String!
  title: String
  chunks: [Chunk!]!
  entities: [Entity!]!
}

type Chunk {
  id: ID!
  text: String!
  document: Document!
  entities: [Entity!]!
}
```

### 5. Docling Integration

**Goal**: Transform research documents into embeddings and store in knowledge graph

**Docling Features**:
- Document conversion (PDF, DOCX, HTML, etc. → structured format)
- Text extraction and cleaning
- Table and figure extraction
- Metadata extraction

**Integration Strategy**:
- **Document Type**: Store converted documents in knowledge graph
- **Chunk Type**: Store document chunks with embeddings
- **Embedding Strategy**: 
  - Generate embeddings for chunks
  - Store embeddings for semantic search
  - Link chunks to extracted entities
- **RAG Integration**: Use chunks for retrieval-augmented generation

**Workflow**:
1. Agent discovers document URL
2. Docling converts document to structured format
3. Chunk document into semantic units
4. Generate embeddings for chunks
5. Store Document and Chunk nodes in Neo4j
6. Link chunks to relevant entities
7. Use chunks in future research via RAG

### 6. React Frontend

**Goal**: Interactive interface for the research system

**Features**:

- **Workflow Management**:
  - Start new research missions
  - View mission status and progress
  - Resume paused missions
  - Cancel running missions

- **Coordinator Agent Interface**:
  - Chat with coordinator agent
  - Ask coordinator to kick off research workflows
  - Get recommendations and suggestions
  - Review and approve research plans

- **Research Exploration**:
  - Browse research missions and results
  - Explore knowledge graph (visual graph view)
  - Search entities, documents, and research
  - View source provenance and evidence

- **Human-in-the-Loop**:
  - Review and approve research plans
  - Provide feedback on research quality
  - Correct entity extractions
  - Validate relationships

- **Memory Management**:
  - View learned memories
  - Provide feedback to improve memories
  - Review and prune memories
  - See memory impact on research

**Technology Stack** (planned):
- React with TypeScript
- GraphQL client (Apollo or Relay)
- State management (Redux or Zustand)
- UI framework (Material-UI or Tailwind CSS)
- Graph visualization (Cytoscape.js or vis.js)

---

## Special Considerations

### Memory is Critical

**Why**: The system must learn from experiences to improve research quality over time.

**Requirements**:
- **Before research starts**: Query knowledge graph and past research runs
  - What do we already know about these entities?
  - What research strategies worked before?
  - What sources were reliable?
  - What patterns should we follow?

- **During research**: Store findings and learnings
  - What did we discover?
  - What sources were useful?
  - What strategies worked?
  - What errors occurred?

- **After research**: Update memories with outcomes
  - Incorporate research results
  - Update entity knowledge
  - Refine strategies
  - Store human feedback

- **Memory retrieval**: Use memories to improve current research
  - Apply learned strategies
  - Avoid past mistakes
  - Leverage known facts
  - Use proven source patterns

**Implementation**:
- LangMem for memory operations
- Integration with knowledge graph
- Human feedback loops
- Memory quality metrics

### Human-in-the-Loop

**Why**: Human oversight ensures quality, correctness, and alignment with goals.

**Integration Points**:

1. **Research Plan Review**:
   - Human reviews initial research plan
   - Approves or modifies stages and agents
   - Adjusts source assignments
   - Sets priorities and constraints

2. **Entity Validation**:
   - Human validates extracted entities
   - Corrects misclassifications
   - Merges duplicate entities
   - Adds missing relationships

3. **Source Quality**:
   - Human rates source quality
   - Flags unreliable sources
   - Adds missing sources
   - Curates source catalogs

4. **Research Feedback**:
   - Human reviews research outputs
   - Provides quality ratings
   - Suggests improvements
   - Corrects errors

5. **Memory Feedback**:
   - Human reviews learned memories
   - Validates entity knowledge
   - Approves strategy learnings
   - Prunes incorrect memories

**UI Requirements**:
- Clear approval/rejection interfaces
- Easy feedback mechanisms
- Visual diff views for changes
- Audit trails for human actions

### File System Organization

**Why**: Well-organized file structure enables maintainability, discoverability, and AI-assisted development.

**Principles**:
- **Feature-based organization**: Group related code by feature
- **Clear separation of concerns**: Models, graphs, tools, prompts, etc.
- **Consistent naming**: Follow established conventions
- **Documentation co-location**: Keep docs near code
- **Spec-driven structure**: Align with SDD spec organization

**Current Structure** (to be refined):
```
human_upgrade/
  graphs/              # LangGraph workflow definitions
  agents/              # Agent implementations
  tools/               # Agent tools
  prompts/             # Prompt templates
  structured_outputs/  # Pydantic models for outputs
  reducers/            # State reducers
  outputs/             # Output formatters
```

**Target Structure** (aligned with SDD):
```
human_upgrade/
  specs/               # Feature specifications
  graphs/              # Workflow implementations
  agents/              # Agent implementations
  tools/               # Tool implementations
  models/              # Beanie models
  api/                 # FastAPI routes
  memory/              # Memory operations
  knowledge_graph/     # Neo4j/GraphQL integration
  frontend/            # React application
```

### Linear Integration

**Goal**: Track specifications and development through Linear issues

**Integration Points**:
- Link Linear issues to spec folders
- Create Linear issues from spec tasks
- Reference specs in Linear descriptions
- Update Linear issues from spec changelogs
- Sync Linear labels with spec categories

**Workflow**:
1. Create Linear issue for feature
2. Use Linear issue ID in spec files
3. Create Linear sub-tasks from `tasks.md`
4. Link PRs to Linear issues
5. Update Linear status from spec progress

---

## Implementation Roadmap 

## TOTAL IMPLEMENTATION TIME 2 Months 

### Phase 1: Foundation 

- [ ] Set up SDD structure and `.cursor` directory
- [ ] Convert Pydantic models to Beanie
- [ ] Implement basic FastAPI server
- [ ] Set up Neo4j and basic GraphQL schema
- [ ] Implement basic memory operations (LangMem)

### Phase 2: Core Features 
- [ ] Complete FastAPI endpoints for all graphs
- [ ] Re-implement extraction graph with Neo4j storage
- [ ] Integrate Docling for document processing
- [ ] Build comprehensive memory system
- [ ] Implement human-in-the-loop interfaces

### Phase 3: Knowledge Graph 

- [ ] Complete GraphQL API
- [ ] Build entity extraction and linking
- [ ] Implement document and chunk storage
- [ ] Create embedding pipeline
- [ ] Build RAG integration

### Phase 4: Frontend 

- [ ] Build React application
- [ ] Implement coordinator agent interface
- [ ] Create knowledge graph visualization
- [ ] Build research exploration UI
- [ ] Implement human-in-the-loop workflows

### Phase 5: Optimization

- [ ] Optimize memory retrieval and usage
- [ ] Improve research quality through learning
- [ ] Enhance human-in-the-loop efficiency
- [ ] Scale system for production use
- [ ] Continuous improvement based on usage

---

## Success Metrics

### Research Quality
- Entity extraction accuracy
- Source reliability scores
- Research completeness
- Human approval rates

### System Performance
- Research mission completion time
- Memory retrieval speed
- API response times
- Knowledge graph query performance

### User Experience
- Human-in-the-loop efficiency
- Frontend usability
- Coordinator agent helpfulness
- Research discovery success

### Learning & Improvement
- Memory hit rates
- Strategy reuse frequency
- Error reduction over time
- Human feedback incorporation

---

## Current Project State Summary

### What Works
- ✅ Multi-graph LangGraph workflow
- ✅ Entity candidate discovery
- ✅ Connected candidate bundling
- ✅ Research plan creation (initial and final)
- ✅ Research mission execution
- ✅ Stage and sub-stage orchestration
- ✅ Agent instance execution
- ✅ Source expansion

### What Needs Work
- ⚠️ Pydantic models (fragile, need Beanie)
- ⚠️ No persistent memory system
- ⚠️ No API layer
- ⚠️ No knowledge graph storage
- ⚠️ No document conversion
- ⚠️ No frontend
- ⚠️ Limited human-in-the-loop
- ⚠️ No learning from past research

### Immediate Priorities
1. Set up SDD structure and context engineering
2. Convert to Beanie models
3. Implement basic FastAPI server
4. Set up Neo4j and begin entity storage
5. Integrate LangMem for memory operations

---

*This document is a living specification. Update it as the project evolves.*
