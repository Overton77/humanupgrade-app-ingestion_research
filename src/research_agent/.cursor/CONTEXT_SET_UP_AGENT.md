# Context Engineering & Specification-Driven Development Setup

This document defines how we use **Specification-Driven Development (SDD)** and **Cursor's native context engineering features** to build and maintain the research agent and ingestion pipeline.

---

## Table of Contents

1. [Specification-Driven Development Principles](#specification-driven-development-principles)
2. [Cursor Native Context Engineering](#cursor-native-context-engineering)
3. [Directory Structure & File Types](#directory-structure--file-types)
4. [How to Use SDD in This Project](#how-to-use-sdd-in-this-project)
5. [Context Engineering Best Practices](#context-engineering-best-practices)

---

## Specification-Driven Development Principles

### Core Philosophy

**Specs are the source of truth**: Code, tests, and documentation are derived artifacts. All behavior must be justified by an explicit specification.

### Key Principles

1. **Machine-readable specs**: Structured, versioned, diffable formats (Markdown with conventions, YAML/JSON, OpenAPI, GraphQL SDL) optimized for retrieval and regeneration.

2. **Spec → code workflow**: Changes begin with spec updates; AI generates or updates interfaces, implementations, tests, and migrations from specs.

3. **Explicit intent & constraints**: Specs define invariants, pre/post-conditions, failure modes, non-goals, performance, security, and compliance rules.

4. **Optimal context engineering**: Specs act as compressed, authoritative context that bounds AI behavior and prevents drift or hallucination.

5. **Contract-driven interfaces**: APIs, data models, and module boundaries are defined declaratively and enforced across the codebase.

6. **Spec-driven testing**: Tests are generated from specs (property, contract, regression); spec changes imply test regeneration.

7. **Versioned intent evolution**: Spec diffs represent behavioral change; breaking changes, migrations, and rollouts are explicitly modeled.

8. **Planning via specs**: Roadmaps, tasks, and refactors are expressed as spec deltas rather than tickets or ad-hoc instructions.

9. **Agent-native design**: Specs enable multiple AI agents to coordinate, resume work, validate assumptions, and self-correct.

10. **Human–AI boundary**: Humans define intent, tradeoffs, and constraints; AI executes expansion, implementation, refactoring, and enforcement.

---

## Cursor Native Context Engineering

### Overview

Cursor provides built-in context engineering features through the `.cursor` directory. This directory contains structured context that guides AI behavior, enforces conventions, and enables deterministic development workflows.

### Core Components

#### 1. AGENTS.md (Repository Constitution)

**Location**: Root of repository or `.cursor/AGENTS.md`

**Purpose**: The canonical high-level brief that defines:
- What the repository is
- Core invariants and non-negotiables
- Definition of Done
- Vocabulary anchors
- System architecture boundaries

**How Cursor uses it**: Cursor reads this as stable context for all conversations about the repository. It should remain correct for months.

**What belongs here**:
- Domain vocabulary at a high level
- System architecture boundaries (web → API → agents)
- Global non-functional constraints (privacy, provenance)
- Done criteria

**What does NOT belong here**:
- Feature-specific requirements
- Design diagrams for specific subsystems
- One-off implementation notes

#### 2. .cursor/rules/ (Persistent Constraints)

**Purpose**: Rules are ALWAYS constraints and conventions. They prevent drift, hallucinated architecture, and inconsistent patterns.

**Key principle**: Rules should be:
- Modular (one purpose each)
- Short and focused
- Scoped with globs when possible
- Stable (avoid details that change weekly)

**Types of rules**:
- `alwaysApply: true` → Global invariants (glossary, quality, privacy)
- `globs: [...]` → Only apply in certain folders (API, agents, frontend)

**Rule file format**: `.mdc` (Markdown with Cursor metadata)

**Example rule structure**:
```markdown
---
alwaysApply: true
# OR
globs: ["**/api/**", "**/routes/**"]
---

# Rule Title

Rule content explaining the constraint...
```

**Common rule categories**:
- **00-glossary.mdc**: Canonical vocabulary (Organization, Chunk, EvidenceReport, AgentRunId)
- **10-architecture.mdc**: System boundaries and architectural constraints
- **20-quality-bar.mdc**: Testing and verification requirements
- **30-security-privacy.mdc**: Security and privacy constraints
- **40-data-graph.mdc**: Graph database conventions (Neo4j, relationships)
- **50-api-contracts.mdc**: API design and contract requirements
- **60-agents-runtime.mdc**: Agent tool behavior and runtime standards

#### 3. .cursor/commands/ (Phase-Gated Workflows)

**Purpose**: Commands are repeatable workflows invoked explicitly via slash commands (e.g., `/sdd.specify`, `/sdd.plan`).

**How they work**: Commands orchestrate file creation and enforce output structure. Commands are NOT the specs themselves; they create and maintain spec files.

**Command design rules**:
1. Read required inputs (existing spec files)
2. Produce specific output files
3. Refuse to skip steps (no planning before requirements exist)
4. End with "next command to run"

**Standard SDD commands**:

- **sdd.specify.md**: Creates/updates `specs/<slug>/00-requirements/` files
  - Requirements, acceptance criteria, personas, out-of-scope
  - No design decisions allowed

- **sdd.plan.md**: Creates/updates `specs/<slug>/01-design/` files
  - Architecture, data model, API contracts, failure modes, alternatives
  - Explicit boundary and data ownership required

- **sdd.tasks.md**: Creates/updates `specs/<slug>/02-tasks/tasks.md`
  - Atomic tasks with verification steps
  - Ordered by dependency

- **sdd.tests.md**: Creates/updates `specs/<slug>/03-tests/` files
  - Test plan and traceability matrix
  - Maps acceptance criteria to tests

- **sdd.ops.md**: Creates/updates `specs/<slug>/04-ops/` files
  - Rollout plan, migrations, observability, runbook
  - Feature flags and monitoring signals

- **sdd.implement.md**: Implements tasks from `02-tasks/tasks.md`
  - One task at a time
  - Runs verification steps
  - Updates changelog when behavior deviates

- **sdd.check.md**: Validates all spec phase files
  - Pass/fail checklist
  - Used before implementation, PR merge, or release

- **adr.new.md**: Creates Architecture Decision Records
  - For repo-wide decisions affecting multiple features

#### 4. .cursor/skills/ (Reusable Micro-Procedures)

**Purpose**: Skills are reusable cognitive tools and checklists, not gates. Use them for consistent review criteria and standard rubrics.

**When to use**:
- Consistent review criteria needed
- Standard rubrics to apply repeatedly

**Example skills**:
- **sdd-spec-quality.md**: Ensures requirements are complete
- **sdd-nfr-checklist.md**: Captures performance/security/reliability
- **evidence-provenance-rubric.md**: For agent tools creating Chunks or claims
- **neo4j-cypher-playbook.md**: For writing Cypher or defining graph query APIs
- **api-contract-discipline.md**: For adding endpoints or modifying response shapes

#### 5. .cursor/subagents/ (Specialized Reviewers)

**Purpose**: Specialized roles that run in parallel, reduce context pollution, and provide independent checks.

**When to spawn**:
- After `/sdd.specify`: `requirements-reviewer` + `security-privacy-reviewer`
- After `/sdd.plan`: `design-reviewer` + `security-privacy-reviewer`
- After `/sdd.tasks`: `test-planner`
- Before merge: `sdd.check` + `security-privacy-reviewer`

**Expected outputs**:
- Specific missing items
- Concrete edits to make in spec docs
- Risk list with mitigations

---

## Directory Structure & File Types

### Standard SDD Spec Structure

```
specs/
  _templates/          # Starting point templates
    00-requirements/
    01-design/
    02-tasks/
    03-tests/
    04-ops/
    05-changelog/
  
  <feature-slug>/      # Each feature gets its own folder
    00-requirements/
      README.md
      personas.md
      requirements.md
      acceptance-criteria.md
      out-of-scope.md
    
    01-design/
      README.md
      architecture.md
      data-model.md
      api-contracts.md
      consistency-failure-modes.md
      alternatives-considered.md
    
    02-tasks/
      README.md
      tasks.md
    
    03-tests/
      README.md
      test-plan.md
      traceability-matrix.md
    
    04-ops/
      README.md
      rollout.md
      migrations-backfill.md
      observability.md
      runbook.md
    
    05-changelog/
      README.md
      changelog.md
```

### File Type Conventions

#### .mdc Files (Markdown with Cursor Metadata)

**Purpose**: Rules and context files with application and file matching rules.

**Format**:
```markdown
---
alwaysApply: true
# OR
globs: ["**/*.py", "**/api/**"]
---

# Content here
```

**Use cases**:
- Rules that apply to specific file patterns
- Context that should be automatically included when editing matching files

#### .md Files (Standard Markdown)

**Purpose**: Specifications, documentation, and context files.

**Use cases**:
- All spec files (requirements, design, tasks, tests, ops)
- Commands, skills, subagents
- ADRs (Architecture Decision Records)
- General documentation

#### Other Important Files

- **YAML/JSON**: For structured data (OpenAPI specs, configuration)
- **GraphQL SDL**: For GraphQL schema definitions
- **Python/TypeScript**: Code implementations (derived from specs)

---

## How to Use SDD in This Project

### Workflow: Idea → Shipped Feature

1. **Requirements Phase** (`/sdd.specify`)
   - Define what we're building, who it's for, acceptance criteria
   - Output: `specs/<feature>/00-requirements/`

2. **Design Phase** (`/sdd.plan`)
   - Define how it works, architecture, data model, API contracts
   - Output: `specs/<feature>/01-design/`

3. **Tasks Phase** (`/sdd.tasks`)
   - Break down into atomic work units with verification
   - Output: `specs/<feature>/02-tasks/tasks.md`

4. **Tests Phase** (`/sdd.tests`)
   - Create test plan and traceability matrix
   - Output: `specs/<feature>/03-tests/`

5. **Ops Phase** (`/sdd.ops`)
   - Plan rollout, migrations, observability
   - Output: `specs/<feature>/04-ops/`

6. **Implementation Phase** (`/sdd.implement`)
   - Execute tasks one at a time
   - Run verification steps
   - Update changelog for deviations

7. **Validation Phase** (`/sdd.check`)
   - Verify all phases are complete
   - Check before PR merge or release

### Integration with Linear

**Tracking specifications through Linear issues**:
- Link Linear issues to spec folders
- Use Linear issue IDs in spec changelogs
- Reference specs in Linear issue descriptions
- Create Linear issues from spec tasks

**Example workflow**:
1. Create Linear issue for new feature
2. Use `/sdd.specify` with Linear issue ID in notes
3. Reference Linear issue in spec files
4. Create Linear sub-tasks from `tasks.md`
5. Link PR to Linear issue and spec folder

### Context Usage Rules

#### Semantic Search vs @Mentions

- **Discover**: Use semantic search to find code ("where do we create Chunk nodes?")
- **Lock**: Use `@mentions` to pin specific files during implementation

#### During Implementation

Always mention:
- `@specs/<slug>/00-requirements/acceptance-criteria.md`
- `@specs/<slug>/01-design/*`
- `@specs/<slug>/02-tasks/tasks.md`

This prevents "implementation drift" from specifications.

#### File Organization

- Keep specs organized by feature slug
- Use consistent naming conventions
- Maintain changelogs for spec evolution
- Link related specs together

---

## Context Engineering Best Practices

### 1. Keep Context Compressed and Authoritative

- **Specs should be the single source of truth**
- Avoid duplicating information across files
- Reference rather than copy when possible
- Keep specs focused and concise

### 2. Version and Diff Specifications

- Use version control for all spec files
- Review spec diffs as carefully as code diffs
- Spec changes should trigger test regeneration
- Document breaking changes explicitly

### 3. Make Context Retrievable

- Use clear, consistent naming
- Organize by feature/domain
- Include cross-references
- Maintain indexes when helpful

### 4. Enforce Constraints Through Rules

- Use `.mdc` rules for architectural constraints
- Apply rules with appropriate scope (global vs. scoped)
- Review and update rules periodically
- Document rule rationale

### 5. Use Commands for Deterministic Workflows

- Follow the SDD command sequence
- Don't skip phases
- Validate with `/sdd.check` before proceeding
- Document deviations in changelog

### 6. Leverage Subagents for Parallel Review

- Spawn specialized reviewers at appropriate phases
- Use subagents to catch issues early
- Incorporate subagent feedback into specs
- Maintain subagent definitions

### 7. Maintain Traceability

- Link acceptance criteria to tests
- Map design decisions to implementations
- Track spec evolution in changelogs
- Connect Linear issues to specs

### 8. Human-AI Collaboration Boundaries

**Humans define**:
- Intent and requirements
- Tradeoffs and constraints
- Architectural decisions
- Non-functional requirements

**AI executes**:
- Spec expansion and refinement
- Code generation from specs
- Test generation
- Documentation updates
- Refactoring within constraints

### 9. Prevent Drift

- Always reference specs during implementation
- Run `/sdd.check` before merging
- Update specs when requirements change
- Document deviations in changelog

### 10. Optimize for AI Understanding

- Use structured formats (Markdown with conventions)
- Include examples and patterns
- Define vocabulary explicitly
- Provide context hierarchies (high-level → detailed)

---

## Success Criteria

You know the SDD and context engineering setup is working when:

1. ✅ New features start with `/sdd.specify` and end with `/sdd.ops` + `/sdd.implement`
2. ✅ Code changes always reference a feature spec folder
3. ✅ Every major change has traceability to acceptance criteria
4. ✅ Security/privacy issues are caught in spec phase, not production
5. ✅ AI agents can coordinate and resume work using specs
6. ✅ Spec diffs clearly show behavioral changes
7. ✅ Tests are generated from specs and stay in sync
8. ✅ Context is compressed and authoritative (no duplication)
9. ✅ Rules prevent architectural drift
10. ✅ Commands enforce deterministic workflows

---

## Additional Resources

- **SDD Specification System Manual**: `.cursor/cursor_setup/SDD_Specification_System_Manual.md`
- **Cursor Native Operating Manual**: `.cursor/cursor_setup/Cursor_Native_Operating_Manual.md`
- **Master Layout**: `.cursor/cursor_setup/master_layout.md`
- **Agents Brief**: `.cursor/cursor_setup/Agents.md`

---

## Notes for This Project

### Research Agent Specific Considerations

- **Graph workflows**: Specs should define LangGraph state structures and node behaviors
- **Agent types**: Document agent types, tools, and capabilities in specs
- **Memory operations**: Spec episodic, semantic, and procedural memory usage
- **Knowledge graph**: Define Neo4j node types, relationships, and GraphQL schema in specs
- **Human-in-the-loop**: Document approval gates and review points in specs
- **Source provenance**: Enforce evidence and source tracking in all agent specs

### Integration Points

- **FastAPI server**: API contracts should be defined in `01-design/api-contracts.md`
- **Beanie models**: Data models should be specified before implementation
- **LangMem**: Memory operations should be specified with retrieval/forgetting strategies
- **Docling**: Document conversion strategies should be in design specs
- **React frontend**: UI requirements should reference API contracts from backend specs

---

*This document is a living specification. Update it as practices evolve.*
