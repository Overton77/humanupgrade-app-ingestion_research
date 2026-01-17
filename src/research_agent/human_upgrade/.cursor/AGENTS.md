# Human Upgrade Research & Ingestion Agent

## Overview

This is a sophisticated **LangGraph-based research and ingestion pipeline** for Human Upgrade podcast episodes. The system processes podcast episodes to extract, research, and structure information about biotech entities (people, businesses, products, compounds, platforms) and generate comprehensive episode reports.

## Development Resources

### LangChain Ecosystem Support

When working with LangChain, LangGraph, and LangSmith:

- **Use the `docs-langchain` MCP server** for:

  - API references and documentation lookups
  - Code examples and implementation patterns
  - Feature explanations and best practices
  - Specific LangChain/LangGraph/LangSmith guides

- **Use web search** for:
  - Latest updates and changes to LangChain ecosystem
  - Community solutions and discussions
  - Blog posts and tutorials
  - Release notes and migration guides

These resources should be consulted frequently as LangChain-related questions are expected to come up often during development.

## Architecture Goals

### High-Level Capabilities

- **Persistent Memory**: Langmem or AWS integration to track previously ingested entities and past research runs
- **AWS AgentCore Runtime Deployment**: Production-ready deployment on AWS infrastructure
- **Service-Callable**: Exposable as a service API for other parts of the system to invoke

### Current State

- **~1200 episodes** already stored in MongoDB database
- **Transcripts** stored in AWS S3 bucket
- **Current Phase**: Candidate ranking + entity research directions implementation
- **Location**: New version being built in `ingestion/src/research_agent/human_upgrade/`

## Complete Workflow Pipeline

### Phase 1: Entity Due Diligence

#### 1.1 Input

- **Batch of episodes** sent into LangGraph workflow
- Each episode includes web page summaries with guest and product information

#### 1.2 Candidate Identification

- Extract potential entities from web page summaries:
  - Guest information
  - Product mentions
  - Company/business references
  - Compound/substance mentions
  - Platform references

#### 1.3 Web Search & Ranking

- Enrich candidates with web search data
- Rank candidates by:
  - Importance/relevance to episode
  - Research value
  - Novelty (not previously researched)

#### 1.4 Research Directions Generation

- Convert ranked candidates into specific, actionable research questions
- Generate targeted due diligence queries for each entity type

#### 1.5 Parallel Research Execution

- **Implementation**: SubGraph or separate Graph
- Execute research in parallel for performance
- Each entity gets thorough due diligence investigation

#### 1.6 Structured Output Collection

- Collect complete entity profiles with all required fields:
  - **Business**: Company information, products, leadership
  - **People**: Credentials, expertise, affiliations
  - **Products**: Features, benefits, evidence
  - **Compounds**: Mechanisms, research, safety
  - **Platforms**: Technology, use cases, adoption

#### 1.7 Persistence Layer

- **MongoDB**: Save structured entity data via GraphQL API
- **AWS Knowledge Base**: Embed entity overviews and descriptions in vector stores for semantic search

---

### Phase 2: Episode Transcript Analysis & Report Generation

#### 2.1 Transcript Processing

- Minimally summarize the full episode transcript
- Identify key themes and topics

#### 2.2 High-Value Research Directions

Generate research questions for:

- **Claims Verification**: Fact-check statements made in episode
- **Mechanism Understanding**: Deep dive into biological/technical mechanisms discussed
- **Case Study Identification**: Find supporting evidence and real-world examples

#### 2.3 Structure Development

**Decision Point**: Choose approach based on content

- **Option A**: Outline → Research Directions
- **Option B**: Research Directions → Outline

#### 2.4 Research Compilation

- Execute transcript-level research
- Compile findings from all research directions
- Integrate entity research from Phase 1

#### 2.5 Final Report Generation

Create comprehensive episode report that:

- **Ties in entity research** from Phase 1 for contextual richness
- **Is embeddable** in vector store for semantic search
- **Is frontend-ready** for user consumption
- **Contains actionable information**: verified claims, explained mechanisms, supporting evidence

#### 2.6 Embedding & Storage

- Store complete report in AWS Knowledge Base
- Enable semantic search across all episode reports

---

## Key Design Considerations

### Performance

- **Parallel execution** for entity research to maximize throughput
- **Batch processing** of episodes for efficiency
- **SubGraph architecture** for modular, parallelizable research execution

### Integration

- Leverage existing tools in `research_agent` folder
- Integrate with existing MongoDB schema via GraphQL API
- AWS services integration (S3, Knowledge Base, AgentCore Runtime)

### Data Flow

1. **Entity-First Approach**: Complete entity due diligence before transcript analysis
2. **Context Enrichment**: Use entity research to enhance transcript report quality
3. **Dual Persistence**: Structured data (MongoDB) + vector embeddings (AWS Knowledge Base)

### Modularity

- **Phase separation**: Clear boundary between entity and transcript processing
- **Reusable components**: Research tools, prompts, output models
- **Structured outputs**: Well-defined schemas at each stage for reliability

---

## Entity Types

The system handles five primary entity types:

1. **Business/Company**: Organizations mentioned or featured
2. **People**: Guests, researchers, experts discussed
3. **Products**: Commercial products, services, or offerings
4. **Compounds**: Chemical compounds, supplements, drugs, biologics
5. **Platforms**: Technologies, methodologies, frameworks, systems

---

## Output Artifacts

### Per Episode

- **Entity Profiles**: Complete structured data for each identified entity
- **Episode Report**: Comprehensive analysis with verified claims and explained mechanisms
- **Vector Embeddings**: Searchable representations in AWS Knowledge Base

### System-Wide

- **Memory State**: Tracking of all ingested entities and completed research
- **Research History**: Record of past research runs for deduplication
- **Knowledge Graph**: Relationships between entities, episodes, and concepts

---

## Next Steps

Current implementation status: **Candidate ranking + entity research directions phase**

Remaining work:

- [ ] Complete research directions generation
- [ ] Implement parallel research SubGraph
- [ ] Build structured output collection
- [ ] Integrate MongoDB persistence via GraphQL
- [ ] Implement AWS Knowledge Base embeddings
- [ ] Build transcript analysis pipeline (Phase 2)
- [ ] Implement memory/state management (Langmem/AWS)
- [ ] Deploy to AWS AgentCore Runtime
- [ ] Create service API for external invocation
