# Research Execution Architecture Analysis

## 🎯 The Problem

After `research_directions_node` generates `EntitiesResearchDirections`, we need to decide **how to execute the research**.

### Data Structure Recap

```
EntitiesResearchDirections
├── bundles: List[EntityBundleResearchDirections]
    ├── bundleId: str
    ├── guestDirections: GuestDueDiligenceDirections (3 directions)
    ├── businessDirections: List[BusinessDueDiligenceDirections] (4 directions each)
    ├── productDirections: List[ProductResearchDirections] (3-4 directions each)
    ├── compoundDirections: List[CompoundNormalizationDirections] (1-2 directions each)
    └── platformDirections: List[PlatformResearchDirections] (1-2 directions each)
```

### Scale Analysis

**Typical Episode:**

- 1 guest → 3 directions
- 2 businesses → 8 directions (4 each)
- 4 products → 12-16 directions (3-4 each)
- 6 compounds → 6-12 directions (1-2 each)
- 1 platform → 1-2 directions

**Total per bundle: ~30-41 research directions**

**With 2 guests: 60-82 directions per episode**

---

## 📊 Architecture Options

### Option 1: One Graph Per Individual ResearchDirection ❌

**Granularity:** Finest (1 direction = 1 graph invocation)

**Implementation:**

```python
# For each direction in each bundle:
for bundle in research_directions.bundles:
    # Guest directions (3 invocations)
    for direction in [bundle.guestDirections.roleAffiliation, ...]:
        todo_list = TodoList(todos=[create_todo_from_direction(direction)])
        await research_graph.ainvoke({
            "todo_list": todo_list,
            "direction": direction,
            ...
        })

    # Business directions (4 invocations per business)
    for biz in bundle.businessDirections:
        for direction in [biz.businessIdentityOverview, ...]:
            # ... invoke graph
```

**Pros:**

- ✅ Simple isolation
- ✅ Easy error recovery (1 direction fails, others continue)
- ✅ Easy to parallelize

**Cons:**

- ❌ **60-82 graph invocations per episode** (massive overhead)
- ❌ No context sharing between related directions
- ❌ Checkpoint/summarization overhead wasted (1 todo = instant completion)
- ❌ High LangSmith costs (1 trace per direction)
- ❌ Lost opportunity to leverage related entity context

**Verdict:** ❌ **Too fine-grained, excessive overhead**

---

### Option 2: One Graph Per Entity Type Across All Entities ❌

**Granularity:** Entity type level (all businesses across all bundles in 1 graph)

**Implementation:**

```python
# Collect all business directions from all bundles
all_business_directions = []
for bundle in research_directions.bundles:
    all_business_directions.extend(bundle.businessDirections)

# Create mega todo list with ALL businesses
todo_list = create_todos_for_businesses(all_business_directions)

# One graph invocation for ALL businesses
await research_graph.ainvoke({
    "todo_list": todo_list,
    "directions": all_business_directions,
    ...
})

# Repeat for products, compounds, platforms, guests
```

**Pros:**

- ✅ Very few graph invocations (5 per episode: guest, business, product, compound, platform)
- ✅ Context sharing within entity type

**Cons:**

- ❌ Loses bundle relationships (guest → their business → their product)
- ❌ One failure affects entire entity type
- ❌ Very long-running graphs (10-20+ todos per graph)
- ❌ Context mixing between unrelated bundles

**Verdict:** ❌ **Too coarse-grained, loses relationships**

---

### Option 3: One Graph Per Entity Instance 🤔

**Granularity:** Entity instance level (1 business = 1 graph with 4 todos)

**Implementation:**

```python
for bundle in research_directions.bundles:
    # Guest (1 invocation with 3 todos)
    guest_todo_list = create_todos_from_guest_directions(bundle.guestDirections)
    await research_graph.ainvoke({
        "todo_list": guest_todo_list,
        "directions": bundle.guestDirections,
        ...
    })

    # Each business (1 invocation per business with 4 todos)
    for biz_directions in bundle.businessDirections:
        biz_todo_list = create_todos_from_business_directions(biz_directions)
        await research_graph.ainvoke({
            "todo_list": biz_todo_list,
            "directions": biz_directions,
            ...
        })

    # Each product (1 invocation per product with 3-4 todos)
    for prod_directions in bundle.productDirections:
        # ... invoke graph
```

**Invocation Count:**

- 1 guest = 1 invocation
- 2 businesses = 2 invocations
- 4 products = 4 invocations
- 6 compounds = 6 invocations
- 1 platform = 1 invocation
  **Total: ~14 invocations per bundle**

**Pros:**

- ✅ Good balance of granularity
- ✅ Entity-focused (all research for BioHarvest in one graph)
- ✅ Good checkpoint utilization (3-4 todos per graph)
- ✅ Reasonable invocation count
- ✅ Easy error recovery per entity

**Cons:**

- ⚠️ Still ~14-20 invocations per bundle
- ⚠️ Loses cross-entity context (product research can't use business context easily)
- ⚠️ Need to manage compound-product relationships carefully

**Verdict:** 🤔 **Balanced, but still many invocations**

---

### Option 4: One Graph Per Bundle ✅ **RECOMMENDED**

**Granularity:** Bundle level (1 guest + all their businesses/products/compounds/platforms)

**Implementation:**

```python
for bundle in research_directions.bundles:
    # Create comprehensive todo list for entire bundle
    todo_list = create_todos_from_bundle(bundle)  # ~30-41 todos

    # Single graph invocation for entire bundle
    await research_graph.ainvoke({
        "todo_list": todo_list,
        "bundle": bundle,
        "episode": episode,
        ...
    })
```

**Invocation Count:**

- 1-2 bundles per episode = **1-2 invocations per episode** ✨

**Pros:**

- ✅ **Minimal invocations** (1-2 per episode)
- ✅ **Context sharing** across related entities (guest → business → product)
- ✅ **Natural relationships preserved** (compounds linked to products, products to businesses)
- ✅ **Efficient checkpointing** (every 5 todos = context reset)
- ✅ **Agent can reuse research** (business website for product research)
- ✅ **Lower LangSmith costs** (fewer traces)
- ✅ **Simpler orchestration code**

**Cons:**

- ⚠️ Long-running graphs (30-41 todos per bundle = ~20-30 minutes)
- ⚠️ One failure affects entire bundle (mitigated by todo status tracking)
- ⚠️ Need good checkpoint/summarization (already built!)

**Handling Long-Running Graphs:**

- ✅ **Context summarization** every 5 todos (already designed)
- ✅ **Progress tracking** via todo list in state
- ✅ **Resumability** via LangGraph checkpoints
- ✅ **Partial outputs** (files written incrementally)

**Verdict:** ✅ **BEST OPTION - Natural, efficient, leverages context**

---

## 🏗️ Recommended Implementation: Option 4

### Architecture Flow

```
research_directions_node
    ↓
    └─ research_directions: EntitiesResearchDirections
            ↓
            └─ bundles: [Bundle1, Bundle2]
                     ↓
                     ├─ Bundle1 → EntityIntelResearchGraph (30-41 todos)
                     └─ Bundle2 → EntityIntelResearchGraph (30-41 todos)
                              ↓
                              Parallel execution with semaphore
```

### State Structure for Option 4

```python
class EntityIntelResearchState(TypedDict):
    """State for researching ONE complete bundle."""

    # Input
    episode: Dict[str, Any]
    bundle: EntityBundleResearchDirections  # The entire bundle
    candidate_sources: CandidateSourcesConnected  # For context

    # Todo tracking
    todo_list: Dict[str, Any]  # TodoList with ALL todos for bundle
    current_todo_id: Optional[str]

    # Agent loop
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # Outputs
    completed_research: List[Dict[str, Any]]
    file_refs: Annotated[List[FileReference], operator.add]

    # Checkpointing
    checkpoint_count: int
    total_todos: int
    completed_todos: int

    # Output directory
    output_directory: str  # e.g., "entity_intel_outputs/guest_ilan_sobel_001"
```

### Todo List Generation Strategy

**Instead of an LLM call, use a deterministic function:**

Why? Because the mapping from `EntityBundleResearchDirections` to todos is **completely deterministic**:

- `GuestDueDiligenceDirections` has exactly 3 fixed fields
- `BusinessDueDiligenceDirections` has exactly 4 fixed fields
- etc.

```python
def create_todos_from_bundle(bundle: EntityBundleResearchDirections) -> TodoList:
    """
    Create a complete todo list from a bundle's research directions.

    Deterministic mapping: each ResearchDirection field becomes 1 todo.
    """
    todos = []

    # Guest todos (always 3)
    guest_dirs = bundle.guestDirections
    todos.extend([
        create_todo_from_direction(
            f"{bundle.bundleId}_guest_roleAffiliation",
            guest_dirs.roleAffiliationConfirmation,
            "PERSON",
            guest_dirs.guestCanonicalName
        ),
        create_todo_from_direction(
            f"{bundle.bundleId}_guest_bio",
            guest_dirs.bioExtraction,
            "PERSON",
            guest_dirs.guestCanonicalName
        ),
        create_todo_from_direction(
            f"{bundle.bundleId}_guest_profiles",
            guest_dirs.canonicalProfileSources,
            "PERSON",
            guest_dirs.guestCanonicalName
        ),
    ])

    # Business todos (4 per business)
    for i, biz_dirs in enumerate(bundle.businessDirections):
        biz_prefix = f"{bundle.bundleId}_biz{i}"
        todos.extend([
            create_todo_from_direction(
                f"{biz_prefix}_identity",
                biz_dirs.businessIdentityOverview,
                "BUSINESS",
                biz_dirs.businessCanonicalName
            ),
            create_todo_from_direction(
                f"{biz_prefix}_history",
                biz_dirs.historyTimeline,
                "BUSINESS",
                biz_dirs.businessCanonicalName
            ),
            create_todo_from_direction(
                f"{biz_prefix}_executives",
                biz_dirs.executivesKeyPeople,
                "BUSINESS",
                biz_dirs.businessCanonicalName
            ),
            create_todo_from_direction(
                f"{biz_prefix}_brands",
                biz_dirs.brandProductLineMap,
                "BUSINESS",
                biz_dirs.businessCanonicalName
            ),
        ])

    # Similar for products, compounds, platforms...

    todo_list = TodoList(todos=todos)
    todo_list.update_counts()

    return todo_list


def create_todo_from_direction(
    todo_id: str,
    direction: ResearchDirection,
    entity_type: str,
    entity_name: str
) -> TodoItem:
    """Create a todo item from a research direction."""
    return TodoItem(
        id=todo_id,
        description=f"{direction.objective}\n\nFields to extract: {', '.join(direction.fieldsToExtract)}\n\nAcceptance criteria: {'; '.join(direction.acceptanceCriteria)}",
        status="pending",
        entityType=entity_type,
        entityName=entity_name,
        priority=direction.priority,
    )
```

**Why Deterministic > LLM?**

- ✅ Faster (no LLM call)
- ✅ Cheaper (no tokens)
- ✅ More reliable (no hallucination)
- ✅ Easier to test
- ✅ Completely predictable structure

---

### Graph Implementation for Option 4

```python
# In entity_candidates_research_directions_graph.py

async def generate_bundle_todos_node(state: EntityIntelResearchState) -> Dict[str, Any]:
    """
    Generate complete todo list for a bundle.
    Deterministic function - no LLM needed.
    """
    bundle = state["bundle"]

    # Deterministic todo generation
    todo_list = create_todos_from_bundle(bundle)

    logger.info(
        f"✅ Generated {todo_list.totalTodos} todos for bundle {bundle.bundleId}"
    )

    return {
        "todo_list": todo_list.model_dump(),
        "total_todos": todo_list.totalTodos,
        "completed_todos": 0,
    }


async def research_agent_node(state: EntityIntelResearchState) -> Dict[str, Any]:
    """
    Main research agent that cycles through todos.
    Uses research_llm ↔ tool_node cycle.
    """
    # Build agent with tools
    research_llm = ChatOpenAI(model="gpt-4o", temperature=0)

    tools_with_runtime = [
        todo_read,
        todo_update,
        todo_get_next,
        tavily_search_research,
        tavily_extract_research,
        agent_write_file,  # Triggers context summarization
        # ... other tools
    ]

    # Bind tools with runtime state injection
    bound_tools = [tool.bind_tools(runtime_values=lambda: state) for tool in tools_with_runtime]
    agent = research_llm.bind_tools(bound_tools)

    # Build messages
    messages = state.get("messages", [])

    if not messages:
        # First iteration: add system prompt
        system_prompt = SystemMessage(content=RESEARCH_AGENT_SYSTEM_PROMPT)
        messages = [system_prompt]

    # Always add reminder
    reminder = HumanMessage(content=RESEARCH_AGENT_REMINDER_PROMPT.format(
        total_todos=state["total_todos"],
        completed_todos=state["completed_todos"],
        remaining_todos=state["total_todos"] - state["completed_todos"]
    ))

    # Invoke agent
    response = await agent.ainvoke(messages + [reminder])

    # Return with message appended
    return {"messages": [response]}


def should_continue(state: EntityIntelResearchState) -> str:
    """Check if research is complete."""
    todo_list = TodoList(**state["todo_list"])

    if todo_list.pendingCount == 0 and todo_list.inProgressCount == 0:
        return "finalize"
    else:
        return "continue"


# Build graph
research_graph_builder = StateGraph(EntityIntelResearchState)

research_graph_builder.add_node("generate_todos", generate_bundle_todos_node)
research_graph_builder.add_node("research_agent", research_agent_node)
research_graph_builder.add_node("finalize", finalize_output_node)

research_graph_builder.set_entry_point("generate_todos")
research_graph_builder.add_edge("generate_todos", "research_agent")

research_graph_builder.add_conditional_edges(
    "research_agent",
    should_continue,
    {
        "continue": "research_agent",
        "finalize": "finalize"
    }
)

research_graph_builder.add_edge("finalize", END)

research_graph = research_graph_builder.compile()
```

### Parallel Execution with Semaphore

```python
async def execute_all_bundles(
    research_directions: EntitiesResearchDirections,
    episode: Dict[str, Any],
    candidate_sources: CandidateSourcesConnected,
    max_concurrent: int = 2  # Conservative for long-running graphs
) -> List[Dict[str, Any]]:
    """Execute research for all bundles in parallel with bounded concurrency."""

    semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_bundle(bundle: EntityBundleResearchDirections):
        async with semaphore:
            logger.info(f"🚀 Starting research for bundle: {bundle.bundleId}")

            initial_state = {
                "episode": episode,
                "bundle": bundle,
                "candidate_sources": candidate_sources,
                "todo_list": {},
                "current_todo_id": None,
                "completed_research": [],
                "messages": [],
                "file_refs": [],
                "checkpoint_count": 0,
                "total_todos": 0,
                "completed_todos": 0,
                "output_directory": f"entity_intel_outputs/{bundle.bundleId}"
            }

            result = await research_graph.ainvoke(initial_state)

            logger.info(f"✅ Completed bundle: {bundle.bundleId}")
            return result

    # Execute all bundles in parallel
    tasks = [execute_bundle(bundle) for bundle in research_directions.bundles]
    results = await asyncio.gather(*tasks)

    return results
```

---

## 🎬 Complete Flow

```
Episode URL
    ↓
[seed_extraction_node]
    ↓
[candidate_sources_node]
    ↓
[research_directions_node]
    ↓
research_directions: EntitiesResearchDirections
    └── bundles: [Bundle1, Bundle2]
            ↓
┌───────────────────────────────────────┐
│  Parallel Bundle Execution (max=2)   │
├───────────────────────────────────────┤
│  Bundle1 → research_graph:            │
│    - generate_todos (30 todos)        │
│    - research_agent (loop)            │
│      ↻ research_llm ↔ tool_node       │
│      ↻ todo 1 → write file → reset    │
│      ↻ todo 2 → write file → reset    │
│      ↻ ... (30 iterations)            │
│    - finalize                          │
├───────────────────────────────────────┤
│  Bundle2 → research_graph:            │
│    - generate_todos (35 todos)        │
│    - research_agent (loop)            │
│      ↻ research_llm ↔ tool_node       │
│      ↻ ... (35 iterations)            │
│    - finalize                          │
└───────────────────────────────────────┘
    ↓
All research outputs combined
```

---

## 📝 Summary & Recommendation

### ✅ Use Option 4: One Graph Per Bundle

**Reasons:**

1. **Fewest invocations** (1-2 per episode vs 14-82)
2. **Natural entity relationships** preserved
3. **Context sharing** between related entities
4. **Efficient checkpointing** (automatic every 5 todos)
5. **Simplest orchestration** code
6. **Lower costs** (fewer LangSmith traces)

**Implementation:**

1. **Deterministic todo generation** (no LLM needed)
2. **Single research graph** per bundle
3. **Parallel bundle execution** with semaphore
4. **Automatic context management** in agent_write_file

**Next Steps:**

1. Implement `create_todos_from_bundle()` deterministic function
2. Create `EntityIntelResearchState` TypedDict
3. Build `research_graph` with generate_todos → research_agent → finalize
4. Implement parallel executor with semaphore
5. Test with single bundle, then multiple bundles
