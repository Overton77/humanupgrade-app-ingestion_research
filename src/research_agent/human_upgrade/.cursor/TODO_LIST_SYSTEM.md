# TodoList System for Research Agents

## Overview

The TodoList system provides task tracking for research agents to maintain focus and progress through entity due diligence research directions.

## Architecture

### 1. **TodoList State Models** (`entity_fast_output_models.py`)

#### TodoItem

Individual task with:

- `id`: Unique identifier (e.g., `"biz_001_identity"`)
- `description`: What needs to be done
- `status`: `pending | in_progress | completed | blocked | skipped`
- `entityType`: Optional entity type (PERSON, BUSINESS, etc.)
- `entityName`: Optional entity name
- `priority`: HIGH | MEDIUM | LOW
- `notes`: Progress notes, findings, or blockers
- `createdAt`, `updatedAt`, `completedAt`: Timestamps

#### TodoList

Collection of todos with:

- `todos`: List of TodoItems
- `totalTodos`, `completedCount`, `inProgressCount`, `pendingCount`: Counters
- Methods:
  - `update_counts()`: Recalculate counters
  - `get_todo(id)`: Find specific todo
  - `add_todo(todo)`: Add new todo
  - `update_todo(id, status, notes)`: Update existing todo
  - `get_next_pending()`: Get next pending todo (highest priority first)

### 2. **Base Functions** (`agent_tools/todo_list_tools.py`)

Pure functions for todo list operations:

#### Core Operations

- `create_todo_list()`: Create empty todo list
- `add_todo(...)`: Add new todo item
- `update_todo(...)`: Update status/notes
- `get_todo(...)`: Retrieve specific todo
- `get_all_todos(...)`: Get all todos
- `get_todos_by_status(...)`: Filter by status
- `get_next_pending_todo(...)`: Get next task (priority-sorted)
- `format_todo_list(...)`: Format for display

#### Batch Operations

- `create_todos_from_directions(...)`: Initialize todo list from EntitiesResearchDirections

### 3. **LangChain Tools** (`entity_intel_fast.py`)

Runtime-injected tools for agent use:

#### todo_create

```python
todo_create(
    todo_id: str,
    description: str,
    entity_type: Optional[str] = None,
    entity_name: Optional[str] = None,
    priority: str = "MEDIUM",
) -> str
```

**What it does:**

- Creates new todo in `state["todo_list"]`
- Tracks steps taken
- Returns confirmation message

**Example:**

```python
todo_create(
    todo_id="biz_001_identity",
    description="Extract business identity and overview for BioHarvest Sciences",
    entity_type="BUSINESS",
    entity_name="BioHarvest Sciences",
    priority="HIGH"
)
```

#### todo_update

```python
todo_update(
    todo_id: str,
    status: Optional[str] = None,
    notes: Optional[str] = None,
) -> str
```

**What it does:**

- Updates existing todo status and/or adds notes
- Notes are appended (not replaced)
- Auto-sets `completedAt` when status → completed
- Updates `updatedAt` timestamp

**Example:**

```python
# Start working on a task
todo_update(
    todo_id="biz_001_identity",
    status="in_progress",
    notes="Searching for official website"
)

# Add progress notes
todo_update(
    todo_id="biz_001_identity",
    notes="Found official site: bioharvest.com. Extracting content..."
)

# Complete the task
todo_update(
    todo_id="biz_001_identity",
    status="completed",
    notes="Extracted: legal name, website, description, core products"
)
```

#### todo_read

```python
todo_read(
    status_filter: Optional[str] = None,
) -> str
```

**What it does:**

- Returns formatted todo list
- Optional filtering by status
- Shows summary with counts and grouped todos

**Example:**

```python
# Read all todos
todo_read()

# Read only pending
todo_read(status_filter="pending")

# Read completed
todo_read(status_filter="completed")
```

#### todo_get_next

```python
todo_get_next() -> str
```

**What it does:**

- Returns next pending todo (highest priority first)
- Useful for "what should I work on next?"
- Returns formatted details

**Example Output:**

```
🔴 Next Todo:
ID: biz_001_history
Description: Extract founding and key milestones for BioHarvest Sciences
Entity: [BUSINESS] BioHarvest Sciences
Priority: HIGH
```

## Usage Pattern: Entity Due Diligence

### Typical Research Flow

```python
# 1. Agent gets next task
next_todo = todo_get_next()
# Returns: "biz_001_identity - Extract business identity..."

# 2. Mark as in-progress
todo_update(
    todo_id="biz_001_identity",
    status="in_progress"
)

# 3. Do research
search_result = tavily_search_research("BioHarvest Sciences official website")

# 4. Add progress notes
todo_update(
    todo_id="biz_001_identity",
    notes="Found official website. Key info: biotech company, founded 2009..."
)

# 5. Extract and save
content = tavily_extract_research(["https://bioharvest.com/about"])
agent_write_file(
    filename="research/bioharvest_identity.json",
    content=structured_data,
    description="Business identity data"
)

# 6. Mark complete
todo_update(
    todo_id="biz_001_identity",
    status="completed",
    notes="All fields extracted and saved to file"
)

# 7. Get next task
next_todo = todo_get_next()
# Returns: "biz_001_history - Extract founding and key milestones..."
```

## Integration with Research Directions

### Automatic Todo Creation

The `create_todos_from_directions()` function automatically generates todos from research directions:

```python
# After research directions are generated:
research_directions = state["research_directions"]

# Create todos
todo_list = create_todos_from_directions(research_directions.model_dump())

# Save to state
state["todo_list"] = todo_list

# Now agent can use todo tools to track progress!
```

### Todo ID Convention

Todos created from directions follow this pattern:

```
{bundleId}_{entityType}{index}_{directionKey}

Examples:
- guest_ilan_sobel_biz0_001_guest_roleAffiliationConfirmation
- guest_ilan_sobel_biz0_001_biz0_businessIdentityOverview
- guest_ilan_sobel_biz0_001_prod0_productCanonicalIdentity
```

## State Management

### Todo List in State

The todo list lives in `state["todo_list"]` as a dict:

```python
{
    "todos": [
        {
            "id": "biz_001_identity",
            "description": "Extract business identity...",
            "status": "completed",
            "entityType": "BUSINESS",
            "entityName": "BioHarvest Sciences",
            "priority": "HIGH",
            "notes": "Extracted all fields...",
            "createdAt": "2026-01-14T10:30:00",
            "updatedAt": "2026-01-14T10:45:00",
            "completedAt": "2026-01-14T10:45:00"
        },
        // ... more todos
    ],
    "totalTodos": 15,
    "completedCount": 3,
    "inProgressCount": 1,
    "pendingCount": 11
}
```

### Persistence

Todos are stored in graph state and survive across node executions. For long-term persistence:

1. **Save to file**: Use `agent_write_file` to save todo list snapshots
2. **State checkpoints**: LangGraph automatically checkpoints state
3. **Final artifact**: Save completed todo list as research session record

## Benefits

### 1. **Focus & Structure**

- Agent always knows what to work on next
- Clear priorities (HIGH → MEDIUM → LOW)
- Prevents redundant work

### 2. **Progress Tracking**

- See completion percentage
- Identify blockers
- Monitor which entities are complete

### 3. **Context Management**

- Notes capture findings per task
- File references link to saved research
- History of what was done and when

### 4. **Debuggability**

- Todo status shows where agent got stuck
- Notes reveal reasoning and findings
- Timeline via timestamps

### 5. **Resumability**

- Can stop and resume research
- Next pending todo picks up where left off
- State persists across runs

## Example: Complete Research Session

```python
# Initial state after research directions generated
todo_read()
# Output:
# Total: 15
# Completed: 0
# In Progress: 0
# Pending: 15

# Start research
todo_get_next()
# 🔴 Next Todo: biz_001_identity

todo_update("biz_001_identity", status="in_progress")

# ... do research, save files ...

todo_update("biz_001_identity", status="completed",
    notes="Extracted all fields. Saved to research/bioharvest_identity.json")

# Continue
todo_get_next()
# 🔴 Next Todo: biz_001_history

# ... repeat for all todos ...

# Final status
todo_read()
# Output:
# Total: 15
# Completed: 13
# In Progress: 0
# Pending: 2
# Blocked: 0

# Blocked tasks need attention
todo_read(status_filter="blocked")
# Shows any tasks that hit issues
```

## Advanced Patterns

### Conditional Todos

```python
# Mark as skipped if not applicable
todo_update(
    todo_id="prod_003_variants",
    status="skipped",
    notes="Product has no variants, single SKU only"
)
```

### Blocking Issues

```python
# Mark as blocked when stuck
todo_update(
    todo_id="biz_001_history",
    status="blocked",
    notes="Official history page requires login. Need alternative source."
)
```

### Parallel Processing

For future parallel subgraphs:

```python
# Get all pending HIGH priority todos
high_priority_pending = [
    t for t in get_all_todos(todo_list)
    if t["status"] == "pending" and t["priority"] == "HIGH"
]

# Assign to parallel subgraphs
# Each subgraph updates its assigned todos independently
```

## Tool Collection

```python
TODO_TOOLS = [
    todo_create,      # Create new todo
    todo_update,      # Update status/notes
    todo_read,        # Read todo list
    todo_get_next,    # Get next pending
]

ALL_RESEARCH_TOOLS = [
    # Web search tools...
    # Filesystem tools...
] + TODO_TOOLS
```

## Future Enhancements

### Potential Additions

1. **Dependencies**: Todo A must complete before Todo B
2. **Subtasks**: Break complex todos into smaller steps
3. **Time Estimates**: Track expected vs actual duration
4. **Auto-create from failures**: If research fails, create follow-up todo
5. **Priority recalculation**: Adjust priorities based on findings
6. **Completion validation**: Check acceptance criteria before marking complete

### Integration Ideas

1. **Dashboard**: Real-time todo progress visualization
2. **Notifications**: Alert when todos blocked or completed
3. **Analytics**: Success rates, bottlenecks, time per entity type
4. **Templates**: Pre-defined todo structures for common entity types
5. **Collaboration**: Multiple agents working on shared todo list

## Summary

The TodoList system provides:

- ✅ Structured task tracking
- ✅ Progress monitoring
- ✅ Context preservation
- ✅ Agent focus & efficiency
- ✅ Debuggability & resumability

It transforms a research agent from "try to remember what to do" into "systematic execution of well-defined tasks with full tracking."
