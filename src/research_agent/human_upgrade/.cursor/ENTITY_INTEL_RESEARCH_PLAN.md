# Entity Intel Research Agent Plan

## 🎯 Key Architectural Innovation

**Context Summarization Inside Tools, Not in Separate Nodes**

This plan implements a novel architecture where context management happens **inside the `agent_write_file()` tool**, triggered automatically by the natural checkpoint of completing research and writing output.

**Why This Matters:**

- ✅ Simpler graph: `research_llm(state) ↔ tool_node(state)` cycle only
- ✅ No conditional edges for summarization but conditional edges for whether to continue tool calling or not. Guided by prompts and messages
- ✅ Automatic: No conditional edges for summarization
- ✅ Atomic: Parallel tool calls ensure todo completion + file write + context reset happen together
- ✅ Natural: Tied to research completion (writing output)

**Agent Behavior:**
When research is complete, agent makes **parallel tool calls**:

1. `todo_update(status="completed", notes="...")`
2. `agent_write_file(filename, content, description)` ← **This triggers context reset inside the tool**

The file write tool invokes a summarization LLM, clears old messages, inserts a summary, and the agent continues with fresh context.

---

## Workflow Understanding

### Current State (Completed)

1. **Seed Extraction Node** → Extracts candidate entities from episode summary
2. **Candidate Sources Node** → Web searches and ranks candidate sources for each entity
3. **Research Directions Node** → Generates structured `EntitiesResearchDirections` with bundles containing:
   - `GuestDueDiligenceDirections` (3 directions per guest)
   - `BusinessDueDiligenceDirections` (4 directions per business)
   - `ProductResearchDirections` (3-4 directions per product)
   - `CompoundNormalizationDirections` (1-2 directions per compound)
   - `PlatformResearchDirections` (1-2 directions per platform)

### New Research Phase (To Build)

The research directions output becomes the input to a **brand new LangGraph** that will:

1. **Convert research directions to executable todos** (via LLM generation)
2. **Execute research agent loops** with tool-calling for each todo
3. **Write structured outputs** to filesystem and graph state
4. **Update todos and summarize** at checkpoints to manage context
5. **Move to next todo** with clean slate
6. **Run with bounded parallelism** using semaphores

---

## Architecture Design

### 1. New Graph: EntityIntelResearchGraph

This will be a **separate graph** from the current candidate/directions graph, with its own state management.

#### State Definition: `EntityIntelResearchState`

```python
class EntityIntelResearchState(TypedDict):
    """State for the research execution phase."""

    # Input from previous graph
    episode: Dict[str, Any]  # Episode metadata (ID, URL, etc.)
    research_directions: EntitiesResearchDirections  # From directions node
    candidate_sources: Dict[str, Any]  # Ranked sources from candidate node

    # Research execution state
    todo_list: Dict[str, Any]  # TodoList model serialized
    current_todo_id: Optional[str]  # Currently active todo
    completed_research: List[Dict[str, Any]]  # Completed research outputs

    # Agent communication
    messages: Annotated[Sequence[BaseMessage], operator.add]  # Conversation history

    # Checkpointing
    checkpoint_count: int  # Number of checkpoints hit
    total_todos: int
    completed_todos: int

    # Output artifacts
    research_outputs: List[Dict[str, Any]]  # Structured research per direction
    output_directory: str  # Where files are being written
```

**Key State Features:**

- `messages` uses `operator.add` to constantly append without replacement
- `todo_list` tracks all todos with status, notes, timestamps
- `checkpoint_count` triggers context summarization
- Separates completed research from in-progress work

---

### 2. Todo Generation Strategy

#### Approach: Dedicated LLM Call (Recommended)

**Why LLM over function?**

- Research directions have nuanced objectives and acceptance criteria
- Need intelligent breakdown of complex directions into actionable steps
- Edge cases (optional directions, conditional requirements) are common
- LLM can generate better task descriptions and priorities

#### Todo Generation Node: `generate_todos_node`

**Input:** `EntitiesResearchDirections` from state

**Process:**

1. Extract all research directions from all bundles
2. Flatten into list with metadata (bundle ID, entity type, entity name)
3. Invoke LLM with specialized prompt to generate `TodoList`
4. LLM generates todos following convention:

   ```
   {bundleId}_{entityType}_{entityName_slug}_{directionKey}

   Examples:
   - guest_ilan_sobel_001_roleAffiliationConfirmation
   - guest_ilan_sobel_001_biz_bioharvest_businessIdentityOverview
   - guest_ilan_sobel_001_prod_vinia_productCanonicalIdentity
   ```

**Output:** Updates `state["todo_list"]` with complete TodoList

**Prompt Design:**

```python
GENERATE_TODOS_PROMPT = """
You are a todo list generator for entity due diligence research.

Given the research directions below, generate a complete todo list with one todo per research direction.

REQUIREMENTS:
1. Each todo must have:
   - id: Following convention {bundleId}_{entityType}_{entityNameSlug}_{directionKey}
   - description: Clear, actionable task description (50-100 words)
   - entityType: One of PERSON, BUSINESS, PRODUCT, COMPOUND, PLATFORM
   - entityName: Canonical entity name
   - priority: Map from direction priority (HIGH, MEDIUM, LOW)
   - status: Always 'pending' for new todos

2. Description should include:
   - What to research/extract
   - Key fields to populate
   - Source priorities
   - Acceptance criteria

3. Maintain bundle grouping for clarity

OUTPUT: Complete TodoList model with all todos
"""
```

**Model:**

```python
# Uses existing TodoList and TodoItem from entity_intel_output_models.py
# Structured output ensures valid todo generation
```

---

### 3. Research Agent Node: `research_agent_node`

This is the **core agent loop** that executes research for each todo.

#### Agent Behavior

**Loop Structure:**

1. Get next pending todo (highest priority first)
2. Mark todo as `in_progress`
3. Execute research using tool calls (web search, extraction, etc.)
4. **When research is complete, make PARALLEL tool calls:**
   - `todo_update(todo_id, status="completed", notes="...")`
   - `agent_write_file(filename, content, description)` - **This triggers automatic context reset**
5. Inside `agent_write_file()` tool execution:
   - Write structured output to filesystem
   - Invoke summarization LLM to create concise summary of work done
   - Clear old messages and insert summary (automatic context management)
   - Update state with completed research metadata
6. Agent receives fresh context with summary and automatically continues to next todo
7. Repeat from step 1 until all todos complete

**Key Architectural Points:**

- **research_llm(state)** → **tool_node(state)** cycle back and forth
- File write operation **automatically triggers context reset** (no separate summarization node)
- Agent uses **parallel tool calling** to atomically complete todo + write output
- Context summarization happens **inside the tool**, not in a separate graph node

---

#### Agent Loop Architecture

**The Core Cycle:**

```
┌─────────────────────────────────────────────────────────────┐
│                    research_agent_node                       │
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │              │         │              │                 │
│  │ research_llm │────────▶│  tool_node   │                 │
│  │   (state)    │         │   (state)    │                 │
│  │              │         │              │                 │
│  └──────┬───────┘         └──────┬───────┘                 │
│         │                        │                         │
│         │                        │ Tools access state      │
│         │                        │ via ToolRuntime         │
│         │                        │                         │
│         │                        │ agent_write_file()      │
│         │                        │ triggers context reset  │
│         │                        │                         │
│         └────────────────────────┘                         │
│              Loop continues                                │
└─────────────────────────────────────────────────────────────┘
```

**State Access in Tools:**

Every `@tool` decorated function receives `ToolRuntime` via injection:

```python
@tool
async def some_tool(
    param: str,
    *,
    runtime: Annotated[ToolRuntime, InjectedToolArg]
) -> str:
    # Access entire graph state
    state = runtime.values

    # Read state
    current_todo = state.get("current_todo_id")

    # Modify state
    state["some_key"] = "some_value"

    # State updates persist across tool calls
    return "Result"
```

**Why This Architecture Works:**

1. **Stateful Tools**: Tools can read and write graph state directly
2. **Automatic Context Management**: File writes trigger summarization inside the tool
3. **Simple Graph**: Just research_agent → research_agent loop (no conditional edges for summarization)
4. **Atomic Operations**: Parallel tool calls ensure todo completion + file write happen together

---

#### Tools Available to Agent

**Web Search Tools:**

- `tavily_search_research()` - Web search with summaries
- `tavily_extract_research()` - Extract content from specific URLs
- `firecrawl_scrape()` - Scrape and convert to markdown
- `firecrawl_map()` - Map website structure
- `wikipedia_search()` - Wikipedia queries for disambiguation

**File System Tools:**

- `agent_write_file()` - Write structured JSON/text files
- `agent_read_file()` - Read previously written files
- `agent_list_files()` - List files in output directory

**Todo List Tools:**

- `todo_read()` - Read todo list (optionally filter by status)
- `todo_update()` - Update todo status and notes
- `todo_get_next()` - Get next pending todo

**Tool Implementation with ToolRuntime:**

All tools will use `ToolRuntime` injected via `runtime_values` to access and update graph state:

```python
from langchain.tools import tool, ToolRuntime

@tool
async def todo_update(
    todo_id: str,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    *,
    runtime: Annotated[ToolRuntime, InjectedToolArg]
) -> str:
    """Update a todo's status and/or add notes."""
    state = runtime.values
    todo_list_dict = state.get("todo_list", {})

    # Update todo
    result = update_todo_function(todo_list_dict, todo_id, status, notes)

    # Update state
    state["todo_list"] = result["todo_list"]

    # Track steps
    if "steps_taken" in state:
        state["steps_taken"].append({
            "action": "todo_update",
            "todo_id": todo_id,
            "status": status,
            "timestamp": datetime.now().isoformat()
        })

    return result["message"]
```

**File Writing Tool with Context Management:**

```python
@tool
async def agent_write_file(
    filename: str,
    content: str,
    description: str,
    *,
    runtime: Annotated[ToolRuntime, InjectedToolArg]
) -> str:
    """
    Write research output to file system.

    **IMPORTANT:** This tool automatically triggers context summarization
    after writing the file to manage memory and prevent token overflow.
    """
    state = runtime.values
    output_dir = state["output_directory"]
    current_todo_id = state.get("current_todo_id")

    # 1. Write file to disk
    filepath = await write_file_to_dir(output_dir, filename, content)

    # 2. Update state with completed research metadata
    state["completed_research"].append({
        "filename": filename,
        "filepath": filepath,
        "description": description,
        "todo_id": current_todo_id,
        "timestamp": datetime.now().isoformat()
    })

    state["completed_todos"] = state.get("completed_todos", 0) + 1

    # 3. CONTEXT MANAGEMENT: Summarize and reset messages
    # This happens automatically every time a file is written (natural checkpoint)
    current_messages = state.get("messages", [])

    if len(current_messages) > 10:  # If we have enough history to summarize
        # Invoke summarization LLM
        summary_llm = ChatOpenAI(model="gpt-4o-mini")

        summary_prompt = f"""
        Summarize the research work that was just completed in 2-3 sentences:

        Todo: {current_todo_id}
        Output: {description}
        Filename: {filename}

        Recent messages (last 10):
        {format_recent_messages(current_messages[-10:])}

        Create a brief summary for context continuity.
        """

        summary_response = await summary_llm.ainvoke(summary_prompt)
        summary_text = summary_response.content

        # Create summary message
        summary_message = SystemMessage(
            content=f"[RESEARCH CHECKPOINT]\n{summary_text}\n\nContext reset. Ready for next todo."
        )

        # Clear messages, keep only: system prompt + summary
        system_prompt = current_messages[0] if current_messages else None
        if system_prompt:
            state["messages"] = [system_prompt, summary_message]
        else:
            state["messages"] = [summary_message]

        # Increment checkpoint counter
        state["checkpoint_count"] = state.get("checkpoint_count", 0) + 1

    return f"✅ Saved: {filepath}\n📝 Context summarized. Ready for next todo."
```

**Key Innovation:** Context management happens **inside the tool**, triggered by the natural checkpoint of completing research and writing output. No separate graph node needed!

---

#### Agent Prompts

**System Prompt: `RESEARCH_AGENT_SYSTEM_PROMPT`**

```python
RESEARCH_AGENT_SYSTEM_PROMPT = """
You are an expert entity due diligence research agent.

CURRENT DATE: {current_date}

YOUR MISSION:
Execute research tasks systematically to compile comprehensive, factual profiles of biotech entities (people, businesses, products, compounds, platforms).

WORKFLOW:
1. Read your todo list to see what needs to be done
2. Get the next pending todo (highest priority first)
3. Mark it as 'in_progress'
4. Execute thorough research using your tools:
   - Search for official sources first (company websites, official pages)
   - Fall back to reputable secondary sources (LinkedIn, Crunchbase, news)
   - Use Wikipedia only for disambiguation
5. Extract the specific fields listed in the todo
6. Compile findings into structured JSON

**7. WHEN RESEARCH IS COMPLETE, MAKE PARALLEL TOOL CALLS:**
   - Call `agent_write_file(filename, content, description)` to save your research
   - Call `todo_update(todo_id, status="completed", notes="...")` to mark completion
   - **You MUST call both tools in parallel in a single turn**

8. The file write will automatically trigger context summarization
9. Continue with the next todo (you'll receive a fresh context)

QUALITY STANDARDS:
- Prioritize official sources over secondary sources
- Always include source URLs in your outputs
- Extract exact data (prices, dates, names) - do not paraphrase
- If information is unavailable, note it explicitly
- For products: get ingredient lists, pricing, official descriptions
- For businesses: get legal name, website, leadership, founding date
- For people: get current role, affiliation, bio, LinkedIn

CONTEXT MANAGEMENT:
- Writing a file **automatically summarizes and resets your context**
- This prevents token overflow and keeps you focused
- After each todo completion, you start fresh with a clean slate
- Don't worry about context length - the system handles it for you

USE YOUR TOOLS EFFECTIVELY:
- tavily_search_research: Broad searches to find official sources
- tavily_extract_research: Extract content from specific URLs
- agent_write_file: Save structured JSON outputs
- todo_update: Track your progress
- todo_get_next: Know what to work on next
"""
```

**Reminder Prompt (always injected with system prompt):**

```python
RESEARCH_AGENT_REMINDER_PROMPT = """
PROGRESS CHECK:
- Total todos: {total_todos}
- Completed: {completed_todos}
- Remaining: {remaining_todos}

CRITICAL REMINDERS:
1. Complete one todo fully before moving to the next
2. When research is complete, make PARALLEL tool calls:
   - agent_write_file(filename, full_research_output, description)
   - todo_update(todo_id, status="completed", notes="summary of findings")
3. The file write automatically resets your context (no action needed from you)
4. Use official sources whenever possible
5. Extract precise data, not summaries
6. Include all source URLs in your structured output

NEXT STEP:
- If just completed a todo: Get the next pending todo with todo_get_next()
- If working on a todo: Continue research or write final output

Remember: ALWAYS call agent_write_file() and todo_update() in PARALLEL when done!
"""
```

**Tool Use Prompt:**

```python
RESEARCH_AGENT_TOOL_INSTRUCTIONS = """
TOOL USAGE GUIDE:

🔍 SEARCH & EXTRACT:
- tavily_search_research(query): Find sources on the web
  Example: tavily_search_research("BioHarvest Sciences official website")

- tavily_extract_research(urls): Extract content from specific URLs
  Example: tavily_extract_research(["https://bioharvest.com/about"])

📝 FILE OPERATIONS:
- agent_write_file(filename, content, description): Save research output
  Example: agent_write_file(
      filename="bioharvest_identity.json",
      content=json.dumps(data),
      description="Business identity data for BioHarvest Sciences"
  )

✅ TODO MANAGEMENT:
- todo_read(status_filter): View todos (optionally filter by status)
  Example: todo_read(status_filter="pending")

- todo_get_next(): Get the next pending todo to work on
  Example: todo_get_next()

- todo_update(todo_id, status, notes): Update todo progress
  Example: todo_update(
      todo_id="biz_bioharvest_identity",
      status="completed",
      notes="Extracted all fields. Official website confirmed."
  )

WORKFLOW PATTERN:
1. todo_get_next() → See what to work on
2. todo_update(id, "in_progress") → Mark as started
3. tavily_search_research(...) → Find sources
4. tavily_extract_research(...) → Get detailed content
5. **PARALLEL TOOL CALLS when complete:**
   - agent_write_file(filename, full_output, description)
   - todo_update(id, "completed", notes)
6. Context automatically resets (via file write tool)
7. Repeat from step 1 with fresh context

**IMPORTANT:** Steps 5a and 5b must be called IN PARALLEL in the same turn!
The file write triggers automatic context summarization.
"""
```

---

### 4. Context Management & Summarization

**Challenge:** As the agent processes multiple todos, the message history grows large and can cause token overflow.

**Solution:** Automatic context summarization triggered by file writes (natural checkpoints)

#### Architecture: Summarization Inside Tools

**Key Innovation:** Context summarization happens **inside the `agent_write_file()` tool**, not in a separate graph node.

**Why this approach?**

1. ✅ **Natural Checkpoint**: Writing a file signals research completion
2. ✅ **Automatic**: No conditional edges or separate nodes needed
3. ✅ **Atomic**: File write + context reset happen together
4. ✅ **Simplified Graph**: research_llm ↔ tool_node cycle, that's it!

#### How It Works

**Graph Cycle:**

```
research_llm(state) → tool_node(state) → research_llm(state) → tool_node(state) → ...
                       ↑                                          ↑
                       |                                          |
                    Tools execute                          agent_write_file
                    (access state via                      triggers context
                     ToolRuntime)                          summarization
```

**When Agent Completes Research:**

1. Agent makes **parallel tool calls**:

   ```python
   # Both called in same turn
   agent_write_file("biz_bioharvest_identity.json", research_data, "Business identity")
   todo_update("biz_001_identity", status="completed", notes="All fields extracted")
   ```

2. **Inside `agent_write_file()` execution:**

   ```python
   # Write file to disk
   filepath = await write_file_to_dir(output_dir, filename, content)

   # Update completed research tracking
   state["completed_research"].append(metadata)

   # CONTEXT SUMMARIZATION
   if len(state["messages"]) > 10:
       # Invoke summarization LLM
       summary = await summarization_llm.ainvoke(
           f"Summarize: Just completed {todo_id}, saved to {filename}..."
       )

       # Clear messages, insert summary
       state["messages"] = [
           state["messages"][0],  # System prompt
           SystemMessage(content=f"[CHECKPOINT] {summary}")
       ]

       state["checkpoint_count"] += 1
   ```

3. Agent receives **fresh context** with summary in next iteration

#### Summarization Prompt (Used Inside Tool)

```python
CONTEXT_SUMMARIZATION_PROMPT = """
Summarize the research work that was just completed in 2-3 concise sentences:

Todo ID: {todo_id}
Entity: {entity_name} ({entity_type})
Output File: {filename}
Description: {description}

Recent conversation (last 10 messages):
{recent_messages}

Create a brief summary capturing:
- What was researched
- Key findings
- Any blockers or issues

This will replace the detailed message history for memory management.
"""
```

#### Implementation Inside agent_write_file Tool

See the complete implementation in the "Tool Implementation with ToolRuntime" section above. Key points:

- **ToolRuntime access**: `runtime.values` gives direct state access
- **Automatic summarization**: Happens when message count exceeds threshold
- **No separate node needed**: All logic contained in the tool
- **State updates**: Messages cleared, summary inserted, checkpoint incremented

#### Benefits of This Approach

1. **Seamless**: No manual triggering of summarization
2. **Efficient**: Tied to natural checkpoints (file writes)
3. **Simple Graph**: No conditional edges for summarization needed
4. **Robust**: Can't forget to summarize - it's automatic
5. **Stateful**: Tools have full access to graph state via ToolRuntime

---

### 5. Graph Flow Design

**Simplified Architecture:** No separate summarization node needed!

```python
from langgraph.graph import StateGraph, START, END

# Build the research graph
research_graph = StateGraph(EntityIntelResearchState)

# Add nodes
research_graph.add_node("generate_todos", generate_todos_node)
research_graph.add_node("research_agent", research_agent_node)
research_graph.add_node("finalize_output", finalize_output_node)

# Define edges
research_graph.add_edge(START, "generate_todos")
research_graph.add_edge("generate_todos", "research_agent")

# Simple conditional edge: continue or finalize
research_graph.add_conditional_edges(
    "research_agent",
    should_continue_or_finalize,
    {
        "continue": "research_agent",  # Loop back for next todo
        "finalize": "finalize_output"  # All todos done
    }
)

research_graph.add_edge("finalize_output", END)

# Compile
entity_intel_research_graph = research_graph.compile()
```

**Note:** The graph is much simpler because context summarization happens automatically inside the `agent_write_file()` tool!

#### Conditional Logic: `should_continue_or_finalize`

```python
def should_continue_or_finalize(state: EntityIntelResearchState) -> str:
    """Determine next step after research agent iteration."""

    # Check if all todos are complete
    todo_list = TodoList(**state["todo_list"])

    if todo_list.pendingCount == 0:
        return "finalize"  # All done, create final artifacts
    else:
        return "continue"  # More todos remaining, keep going
```

**That's it!** No need to check for summarization triggers - it happens automatically.

#### Research Agent Node Implementation

The research agent node is a simple LLM + tool cycle:

```python
async def research_agent_node(state: EntityIntelResearchState) -> Dict[str, Any]:
    """
    Core research agent that executes todos using tools.

    This node cycles between:
    - research_llm(state): Agent decides what tools to call
    - tool_node(state): Tools execute with state access via ToolRuntime

    Context summarization happens automatically inside agent_write_file tool.
    """

    # Build research LLM with tools
    research_llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Bind tools with runtime state access
    tools_with_runtime = [
        todo_read,
        todo_update,
        todo_get_next,
        tavily_search_research,
        tavily_extract_research,
        agent_write_file,  # This tool handles context summarization!
        # ... other tools
    ]

    # Create agent
    research_agent = research_llm.bind_tools(tools_with_runtime)

    # Build messages for this iteration
    messages = state["messages"] if state["messages"] else []

    # Add system prompt if first iteration
    if not messages:
        system_prompt = SystemMessage(content=RESEARCH_AGENT_SYSTEM_PROMPT.format(
            current_date=datetime.now().strftime("%B %d, %Y")
        ))
        messages = [system_prompt]

    # Always add reminder prompt
    reminder = HumanMessage(content=RESEARCH_AGENT_REMINDER_PROMPT.format(
        total_todos=state["total_todos"],
        completed_todos=state["completed_todos"],
        remaining_todos=state["total_todos"] - state["completed_todos"]
    ))

    # Invoke agent
    response = await research_agent.ainvoke(messages + [reminder])

    # If tool calls, execute them
    if response.tool_calls:
        # Tool execution happens in tool_node
        # Tools access state via ToolRuntime and can modify it
        # agent_write_file will automatically trigger summarization
        return {"messages": [response]}

    # No tool calls, agent is done or stuck
    return {"messages": [response]}
```

---

### 6. Bounded Parallelism Strategy

**Challenge:** Processing all bundles sequentially is slow. Need parallelism with resource limits.

**Solution:** Run multiple graph instances in parallel with semaphore

#### Parallel Execution Controller

```python
import asyncio
from typing import List

async def execute_research_with_parallelism(
    all_bundles: List[EntityBundleResearchDirections],
    episode: Dict[str, Any],
    candidate_sources: Dict[str, Any],
    max_concurrent: int = 3
) -> List[Dict[str, Any]]:
    """
    Execute research for all bundles with bounded parallelism.

    Args:
        all_bundles: All research direction bundles
        episode: Episode metadata
        candidate_sources: Ranked candidate sources
        max_concurrent: Maximum concurrent graph executions

    Returns:
        List of research outputs for all bundles
    """

    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_bundle(bundle: EntityBundleResearchDirections):
        """Execute research for a single bundle."""
        async with semaphore:
            logger.info(f"Starting research for bundle: {bundle.bundleId}")

            # Create initial state for this bundle
            initial_state = {
                "episode": episode,
                "research_directions": EntitiesResearchDirections(
                    bundles=[bundle],  # Single bundle
                    totalDirections=count_directions_in_bundle(bundle)
                ),
                "candidate_sources": candidate_sources,
                "todo_list": {},  # Will be populated by generate_todos_node
                "current_todo_id": None,
                "completed_research": [],
                "messages": [],
                "checkpoint_count": 0,
                "total_todos": 0,
                "completed_todos": 0,
                "research_outputs": [],
                "output_directory": f"entity_intel_outputs/{bundle.bundleId}"
            }

            # Invoke research graph
            result = await entity_intel_research_graph.ainvoke(initial_state)

            logger.info(f"Completed research for bundle: {bundle.bundleId}")
            return result["research_outputs"]

    # Execute all bundles in parallel (bounded by semaphore)
    tasks = [execute_bundle(bundle) for bundle in all_bundles]
    results = await asyncio.gather(*tasks)

    # Flatten results
    all_outputs = []
    for bundle_outputs in results:
        all_outputs.extend(bundle_outputs)

    return all_outputs
```

#### Integration with Main Graph

The main candidate/directions graph will invoke the parallel executor:

```python
async def parallel_research_orchestrator_node(state: EntityIntelCandidateAndResearchDirectionState):
    """
    Orchestrates parallel research execution for all bundles.
    This node is added to the main graph after research_directions_node.
    """

    research_directions = state["research_directions"]
    episode = state["episode"]
    candidate_sources = state["candidate_sources"]

    # Execute research in parallel
    all_research_outputs = await execute_research_with_parallelism(
        all_bundles=research_directions.bundles,
        episode=episode,
        candidate_sources=candidate_sources,
        max_concurrent=3  # Adjust based on rate limits and resources
    )

    return {
        "entity_research_outputs": all_research_outputs
    }
```

---

### 7. Finalization & Output

#### Finalize Output Node: `finalize_output_node`

**Purpose:** Aggregate all research outputs and create final artifacts

```python
async def finalize_output_node(state: EntityIntelResearchState) -> Dict[str, Any]:
    """
    Finalize research outputs and create summary artifacts.
    """

    bundle_id = state["research_directions"].bundles[0].bundleId
    output_dir = state["output_directory"]

    # Aggregate all research outputs
    all_outputs = {
        "bundleId": bundle_id,
        "episode": state["episode"],
        "researchDirections": state["research_directions"].model_dump(),
        "todoList": state["todo_list"],
        "completedResearch": state["completed_research"],
        "researchOutputs": state["research_outputs"],
        "checkpointCount": state["checkpoint_count"],
        "totalTodos": state["total_todos"],
        "completedTodos": state["completed_todos"]
    }

    # Save master output file
    master_file = os.path.join(output_dir, "research_complete.json")
    async with aiofiles.open(master_file, "w") as f:
        await f.write(json.dumps(all_outputs, indent=2, default=str))

    logger.info(f"Research complete for bundle {bundle_id}. Outputs saved to {output_dir}")

    return {
        "research_outputs": state["research_outputs"]
    }
```

#### Output Structure

Each bundle's research will produce:

```
entity_intel_outputs/
  {bundleId}/
    research_complete.json          # Master output
    guest_{name}_bio.json           # Guest research
    guest_{name}_profiles.json      # Guest profiles
    biz_{name}_identity.json        # Business identity
    biz_{name}_history.json         # Business history
    biz_{name}_executives.json      # Business executives
    biz_{name}_brands.json          # Business brands/products
    prod_{name}_identity.json       # Product identity
    prod_{name}_pricing.json        # Product pricing
    prod_{name}_ingredients.json    # Product ingredients
    compound_{name}_norm.json       # Compound normalization
    platform_{name}_overview.json   # Platform overview
```

---

## Implementation Phases

### Phase 1: State & Models (Week 1)

- [ ] Define `EntityIntelResearchState` TypedDict
- [ ] Ensure TodoList/TodoItem models are in `entity_intel_output_models.py`
- [ ] Add helper functions for todo list manipulation
- [ ] Write tests for state transitions

### Phase 2: Todo Generation (Week 1)

- [ ] Write `GENERATE_TODOS_PROMPT`
- [ ] Implement `generate_todos_node` with LLM invocation
- [ ] Test todo generation with sample research directions
- [ ] Validate todo ID conventions and completeness

### Phase 3: Tool Implementation (Week 2)

- [ ] Create `research_agent_tools.py` with all tools
- [ ] Implement ToolRuntime injection for state updates
- [ ] Implement web search tools (tavily, firecrawl, wikipedia)
- [ ] Implement file system tools (write, read, list)
- [ ] Implement todo tools (read, update, get_next)
- [ ] Write unit tests for each tool

### Phase 4: Research Agent Node (Week 2-3)

- [ ] Write agent system prompt (`RESEARCH_AGENT_SYSTEM_PROMPT`)
- [ ] Write agent tool instructions (`RESEARCH_AGENT_TOOL_INSTRUCTIONS`)
- [ ] Write agent reminder prompt (`RESEARCH_AGENT_REMINDER_PROMPT`)
- [ ] Implement `research_agent_node` with tool binding
- [ ] Test agent loop with single todo
- [ ] Test agent loop with multiple todos

### Phase 5: Context Management (Week 3)

- [ ] Write `CONTEXT_SUMMARIZATION_PROMPT` (used inside agent_write_file tool)
- [ ] Implement summarization logic inside `agent_write_file` tool
- [ ] Test automatic context reset after file writes
- [ ] Validate agent continues smoothly with fresh context after each todo
- [ ] Test message compression effectiveness

### Phase 6: Graph Construction (Week 3)

- [ ] Build `EntityIntelResearchGraph` with simplified node structure
- [ ] Implement conditional edge (`should_continue_or_finalize`) - much simpler!
- [ ] Implement `finalize_output_node`
- [ ] Test research_llm ↔ tool_node cycle
- [ ] Validate automatic context reset after file writes
- [ ] Test full graph flow end-to-end
- [ ] Validate output artifacts

### Phase 7: Bounded Parallelism (Week 4)

- [ ] Implement `execute_research_with_parallelism` with semaphore
- [ ] Integrate parallel executor with main candidate graph
- [ ] Test with multiple bundles
- [ ] Tune concurrency limits based on rate limits
- [ ] Monitor resource usage and errors

### Phase 8: Integration & Testing (Week 4)

- [ ] Integrate research graph with existing candidate/directions graph
- [ ] End-to-end testing with real episodes
- [ ] Performance benchmarking and optimization
- [ ] Error handling and retry logic
- [ ] Logging and observability improvements

### Phase 9: Observability & Monitoring (Week 5)

- [ ] Add LangSmith tracing for all graph executions
- [ ] Add metrics for todo completion rates
- [ ] Add alerting for failures and blockers
- [ ] Create dashboard for research progress
- [ ] Document operational runbooks

---

## Key Technical Notes

### 1. ToolRuntime State Updates

The `ToolRuntime` mechanism allows tools to directly update graph state:

```python
from langchain.tools import tool, ToolRuntime, InjectedToolArg
from typing_extensions import Annotated

@tool
async def example_tool(
    param: str,
    *,
    runtime: Annotated[ToolRuntime, InjectedToolArg]
) -> str:
    """Example tool with runtime injection."""
    # Access state
    state = runtime.values

    # Update state
    state["some_key"] = "some_value"

    # Return result
    return "Tool executed"
```

**Runtime injection happens via:**

```python
tools_with_runtime = [tool.bind(runtime_values=lambda: state) for tool in tools]
agent = create_agent(llm, tools_with_runtime, system_prompt)
```

### 2. Message Accumulation with operator.add

```python
messages: Annotated[Sequence[BaseMessage], operator.add]
```

This ensures:

- New messages are **appended**, not replaced
- Conversation history builds up naturally
- Summarization can selectively clear/replace messages

### 3. Checkpoint Serialization

LangGraph automatically checkpoints state at each node. This enables:

- Resumability if execution fails
- Time-travel debugging
- State inspection at any point

### 4. Structured Output Validation

All LLM calls use structured outputs with Pydantic validation:

```python
todo_generation_llm = ChatOpenAI(model="gpt-4o").with_structured_output(TodoList)
```

This ensures:

- Type safety
- Schema validation
- Easier debugging

---

## Success Criteria

### Functional Requirements

- ✅ All research directions convert to actionable todos
- ✅ Agent systematically completes todos with tool calls
- ✅ Structured outputs saved to filesystem
- ✅ Context summarization prevents runaway token growth
- ✅ Bounded parallelism processes multiple bundles efficiently

### Quality Requirements

- ✅ Official sources prioritized over secondary sources
- ✅ Extracted data is precise and well-attributed
- ✅ Todos track progress accurately
- ✅ Agent handles missing information gracefully

### Performance Requirements

- ✅ Process 3-5 bundles in parallel
- ✅ Complete typical bundle (15 directions) in < 10 minutes
- ✅ Token usage stays under limits via summarization

### Observability Requirements

- ✅ Full LangSmith tracing for all executions
- ✅ Clear logging at each node
- ✅ Todo progress visible in real-time
- ✅ Failures and blockers captured

---

## Risk Mitigation

### Risk 1: Agent Gets Stuck in Loop

**Mitigation:**

- Max iterations per todo (e.g., 10 tool calls)
- Timeout per todo (e.g., 5 minutes)
- Auto-mark as "blocked" if stuck

### Risk 2: Rate Limits Hit

**Mitigation:**

- Semaphore limits concurrent requests
- Exponential backoff for retries
- Graceful degradation (skip optional todos)

### Risk 3: Context Window Overflow

**Mitigation:**

- **Automatic summarization inside agent_write_file tool** - happens after every completed todo
- Message pruning: keep only system prompt + summary after each file write
- Monitor token usage and adjust summarization threshold if needed
- No manual intervention required - fully automatic

### Risk 4: Hallucinated Outputs

**Mitigation:**

- Structured outputs with validation
- Source attribution required
- QA prompts asking for verification

### Risk 5: Incomplete Research

**Mitigation:**

- Acceptance criteria in todos
- Agent must confirm completion
- Human review for high-priority entities

---

## Future Enhancements

### Short-Term (Next Sprint)

1. Add validation checks for todo completion (acceptance criteria)
2. Implement retry logic for failed tool calls
3. Add human-in-the-loop for blocked todos
4. Create progress dashboard

### Medium-Term (Next Quarter)

1. Multi-agent collaboration (multiple agents per bundle)
2. Incremental updates (re-research outdated entities)
3. Cross-bundle deduplication (same entity in multiple episodes)
4. Quality scoring and auto-QA

### Long-Term (Next 6 Months)

1. Memory persistence (track all researched entities globally)
2. Learning from feedback (improve prompts based on corrections)
3. Auto-tuning of source priorities
4. Integration with claims validation pipeline

---

## Conclusion

This research agent system represents a **sophisticated, production-ready pipeline** for entity due diligence. Key innovations:

1. **Structured decomposition**: Research directions → Todos → Execution
2. **Automatic context management**: Summarization triggered inside `agent_write_file` tool - no separate graph node needed!
3. **Parallel tool calling**: Agent atomically completes todo + writes output in single turn
4. **Bounded parallelism**: Efficient processing without overwhelming resources
5. **State-aware tools**: ToolRuntime enables seamless state updates from within tools
6. **Simple graph architecture**: Just `research_llm(state) ↔ tool_node(state)` cycle
7. **Observability**: Full tracing and progress tracking

### The Key Architectural Insight

**Context summarization happens INSIDE the file write tool, not in a separate graph node.**

This elegant approach:

- ✅ Ties summarization to natural checkpoints (completing research)
- ✅ Eliminates complex conditional edges
- ✅ Ensures context reset never gets skipped
- ✅ Simplifies the graph to essential components
- ✅ Makes the system more maintainable and debuggable

By following this implementation plan, we'll build a robust system that can systematically research hundreds of entities across dozens of episodes with high quality and efficiency. The agent will maintain focus, manage its own memory automatically, and produce comprehensive structured outputs ready for database ingestion.
