## Entity Research Graphs – Direction Agents & Bundle Orchestration

### Scope and Purpose

- **Graph/agent module**: `human_upgrade/entity_research_graphs.py`
- **Primary role**:
  - Take one or more **Entity Research Direction Bundles** (`EntityBundlesListFinal` / `EntityBundleDirectionsFinal`) produced by the candidates + directions graph.
  - For each bundle and each active **direction type** (`GUEST`, `BUSINESS`, `PRODUCT`, `COMPOUND`, `PLATFORM`):
    - Run a **direction research agent** that:
      - Uses **web search tools** (Tavily + Wikipedia) for evidence.
      - Uses **file system tools** for checkpoints and context management.
      - Uses a **think tool** for explicit intermediate reasoning.
    - Accumulates **checkpoint reports** and finally synthesizes a **final report** per direction into the filesystem.
  - At the bundle level, orchestrate running all directions, collect final reports, and expose them to later stages (e.g., extraction/GraphQL seeding).

This module is the **core research workhorse**: it turns abstract research directions into concrete, evidence‑backed reports.

---

### Key Files and Subsystems

- **This graph/agent definition**
  - `human_upgrade/entity_research_graphs.py`
    - Defines:
      - `EntityIntelResearchBundleState` – bundle‑level LangGraph state.
      - `DirectionAgentState` – direction‑level agent state.
      - Middleware, tools list, and direction agent:
        - `direction_agent_middlewares`
        - `ALL_RESEARCH_TOOLS`
        - `build_direction_agent(...)`
        - `DirectionAgent` (process‑wide compiled agent)
      - Bundle orchestration subgraph:
        - `build_direction_queue(...)`
        - `select_direction_plan(...)`
        - `make_bundle_research_graph(config: RunnableConfig) -> CompiledStateGraph`

- **Structured outputs / plans**
  - `human_upgrade/structured_outputs/research_direction_outputs.py`
    - `EntityBundleDirectionsFinal`
    - Direction finals:
      - `GuestDirectionOutputFinal`
      - `BusinessDirectionOutputFinal`
      - `ProductsDirectionOutputFinal`
      - `CompoundsDirectionOutputFinal`
      - `PlatformsDirectionOutputFinal`
    - These are what the direction agent actually executes, with deterministic `requiredFields`.

- **File system tools (research agent workspace)**
  - `human_upgrade/tools/file_system_tools.py`
    - Tools exposed to the direction agent (subset used here):
      - `agent_write_file`
      - `agent_edit_file`
      - (Others exist: `agent_read_file`, `agent_delete_file`, `agent_search_files`, `agent_list_outputs`, but some are commented out in this module.)
  - `agent_write_file` and `agent_edit_file` are included in:
    - `RESEARCH_FILESYSTEM_TOOLS` – for direction‑level research.
    - `ALL_FILESYSTEM_TOOLS` – broader set (write, delete, search, list outputs) if needed.
  - Lower‑level filesystem helpers:
    - `research_agent.agent_tools.file_system_functions`:
      - `write_file`
      - `sanitize_path_component`
      - `BASE_DIR`
      - `read_file`, `write_file as fs_write_file` (for final report path handling).

- **Think tool**
  - `human_upgrade/tools/think_tool.py`
    - Imported as `think_tool` (not directly wired into `ALL_RESEARCH_TOOLS` in this snippet but part of the broader tool ecosystem).
    - Produces **structured thoughts** that are stored in `DirectionAgentState["thoughts"]`.
    - Allows explicit meta‑reasoning steps to be captured in the state and persisted via checkpoints.

- **Web search tools (research type)**
  - `human_upgrade/tools/web_search_tools.py`
    - Research‑oriented Tavily tools (with step counting and Command updates):
      - `tavily_search_research`
      - `tavily_extract_research`
      - `tavily_map_research`
    - Wikipedia tool:
      - `wiki_tool` (async `wiki_search_tool` wrapper).
  - These are **wired into `ALL_RESEARCH_TOOLS`** and made available to the direction agent via `ToolNode`:
    - The agent calls them to:
      - Search the web for evidence.
      - Extract structured content from URLs.
      - Map internal links from authoritative sites.
    - Each research tool:
      - Increments `steps_taken` in the agent state.
      - Emits a `ToolMessage` with formatted content back into the conversation history.

- **Web search summarization + formatting**
  - `human_upgrade/tools/utils/web_search_helpers.py`
    - `summarize_tavily_web_search(search_results: str, model: ChatOpenAI) -> TavilyResultsSummary`
      - Uses `create_agent` with `response_format=ProviderStrategy(TavilyResultsSummary)` and a dedicated summary prompt (`TAVILY_SUMMARY_PROMPT`).
      - Returns a structured `TavilyResultsSummary` object:
        - `summary: str`
        - `citations: List[TavilyCitation]` (title, URL, optional dates/scores, etc.).
      - Saves the summary JSON via `save_json_artifact`.
    - `summarize_tavily_extract(extract_results: str, model: ChatOpenAI) -> TavilyResultsSummary`
      - Same pattern but for Tavily **extract** outputs.
    - `format_tavily_summary_results(summary: TavilyResultsSummary) -> str`
      - Converts the structured summary + citations into a **compact, human‑readable string**:
        - Header.
        - Summary body.
        - A short list of citations with titles, URLs, optional published date and score.
  - The research tools in `web_search_tools.py` call these helpers to:
    - **Summarize and compress raw Tavily results** into a structured summary.
    - Then **format to a concise text block** that is written into the agent’s messages.
  - This two‑step pattern (summarize → format) is the **primary mechanism for context compression** of web search results in the direction agent.

- **Persistence / checkpoints**
  - `human_upgrade/persistence/checkpointer_and_store.py`
    - `get_persistence()` returns `(store, checkpointer)` used for:
      - Direction agent graph (`build_direction_agent`).
      - Bundle subgraph (`make_bundle_research_graph`).
  - `human_upgrade/utils/graph_namespaces.py`
    - `with_checkpoint_ns`, `ns_direction`, `ns_bundle`:
      - Provide **per‑bundle** and **per‑direction** checkpoint namespaces so threads/checkpoints can be isolated and resumed/forked.

- **Analysis + rules context**
  - `.cursor/analysis/*.md` (this file and `entity_candidates_research_directions.md`):
    - Living architecture docs used to later derive:
      - `.cursor/rules` files.
      - Agent definitions (for Cursor/LangSmith).
      - Implementation issues/milestones (e.g., API endpoints).

---

### DirectionAgentState – Direction‑Level Research State

**State schema**: `DirectionAgentState(AgentState)` (TypedDict‑like with reducers).

- **Identity / plan**
  - `direction_type: DirectionType` – `"GUEST" | "BUSINESS" | "PRODUCT" | "COMPOUND" | "PLATFORM"`.
  - `bundle_id: str` – unique identifier per bundle (e.g., guest + episode).
  - `run_id: str` – per‑direction identifier (`bundleId_directionType`).
  - `plan: Dict[str, Any]`
    - `{"chosen": {...}, "required_fields": [...]}` derived from `EntityBundleDirectionsFinal`.
  - `episode: Dict[str, Any]` – per‑episode context (URL, metadata, etc.).

- **Counters / progress**
  - `steps_taken: int` – incremented by tools (web search, etc.) and used in logging.

- **Accumulators with reducers**
  - `file_refs: Annotated[List[FileReference], operator.add]`
    - References to checkpoint and final report files written by filesystem tools and final synthesis.
  - `research_notes: Annotated[List[str], operator.add]`
    - Free‑form notes about progress, warnings, errors, etc.
  - `thoughts: Annotated[List[str], operator.add]`
    - Meta‑reasoning outputs from `think_tool`.

- **Final output**
  - `final_report: Optional[Union[FileReference, str]]`
    - Typically a `FileReference` pointing to the synthesized final report on disk.
    - Written by `write_final_report_and_update_state`.

- **Convenience state for prompting/debug**
  - `last_file_event: Optional[LastFileEvent]`
    - Overwrite‑only metadata about most recent file operation (write/edit/delete/list/search).
  - `workspace_files: Annotated[List[WorkspaceFile], operator.add]`
    - Snapshots of agent workspace files/dirs (names, paths, sizes).
  - `required_fields_status: Dict[str, RequiredFieldEntry]`
    - Tracks progress against deterministic `requiredFields` for the direction:
      - `status: FieldStatus ("todo" | "in_progress" | "done" | "not_found")`
      - `evidence_files: List[str]`
      - `notes: str`
  - `open_questions: List[str]`
  - `current_focus: CurrentFocus` – which entity/field the agent is currently working on.
  - `context_index: ContextIndex` – high‑level context summary (latest checkpoint, key files).
  - `last_plan: str` – compact plan string to inject into prompts.

---

### Direction Agent Middleware Pipeline

The direction agent uses **LangChain Agent middleware** to control prompting, summarize history, and run a final synthesis step.

- **`init_run_state` (@before_agent)**
  - Runs once per direction agent invocation.
  - Initializes:
    - `_initial_prompt_sent = False` (prompt latch).
    - `required_fields_status` entries (status `todo` for each required field).
    - `open_questions`, `current_focus`, `context_index`, `last_plan`.

- **`SummarizationMiddleware` (`summarizer`)**
  - Model: `gpt_5_mini`.
  - Trigger: `("tokens", 30_000)` – when history ~75% of 40k context.
  - Keep: `("tokens", 15_000)` – retain recent half of context.
  - Summary prompt: `SUMMARY_PROMPT` (research‑oriented).
  - Truncates input to ~12k tokens when summarizing.
  - Ensures long research loops stay within model limits while preserving key tool/LLM interactions.

- **`biotech_direction_dynamic_prompt` (@dynamic_prompt)**
  - Reads `DirectionAgentState` to decide **which system prompt to inject**:
    - If `_initial_prompt_sent` is `False`:
      - Uses `get_initial_research_prompt(...)` with:
        - `bundle_id`, `run_id`, `direction_type`, `plan`, `entity_context`, `max_web_tool_calls_hint`.
    - Otherwise:
      - Uses `get_reminder_research_prompt(...)` to provide a reminder context with state summary and next‑step guidance.

- **`latch_initial_prompt_after_first_model` (@after_model)**
  - After the first model call:
    - Sets `_initial_prompt_sent = True`.
  - Ensures the initial prompt is only used once; subsequent turns get reminder prompts.

- **`finalize_direction_report_after_agent` (@after_agent)**
  - Runs once after the agent completes its loop for a given direction.
  - Behavior:
    - Reads `file_refs` (checkpoint files).
    - If none exist:
      - Logs warning and returns a research note: *no final report generated*.
    - Otherwise:
      - Calls `generate_final_report_text(state)`:
        - Uses `gpt_5` with `_final_report_system_prompt` and `_concat_direction_files(file_refs)` to produce a synthesized final report text.
      - Calls `write_final_report_and_update_state(state, final_text)`:
        - Writes `final_report.txt` to a structured path:
          - `bundle_id / direction_type / run_id / final_report.txt` under `BASE_DIR`.
        - Creates a `FileReference` with path + description + `entity_key` (e.g., `"final_guest"`).
        - Returns updates:
          - `final_report` (overwrite).
          - `file_refs` (append final ref).
          - `research_notes` (append note).

The final middleware list used to construct the direction agent:

- `direction_agent_middlewares = [`
  - `init_run_state,`
  - `summarizer,`
  - `biotech_direction_dynamic_prompt,`
  - `latch_initial_prompt_after_first_model,`
  - `finalize_direction_report_after_agent,`
  - `]`

---

### Tools Used by the Direction Agent

**ALL_RESEARCH_TOOLS** (subset relevant here):

- **Web search & evidence tools (research type)**
  - `wiki_tool`
  - `tavily_search_research`
  - `tavily_extract_research`
  - `tavily_map_research`
  - All return either a `Command` with state updates or a formatted string, and internally:
    - Call Tavily API wrappers (`tavily_search`, `tavily_extract`, `tavily_map`).
    - Save raw results as JSON artifacts.
    - Summarize with `summarize_tavily_web_search` / `summarize_tavily_extract`.
    - Format summaries with `format_tavily_summary_results` for compact inclusion in `ToolMessage` content.
  - This pattern ensures the **agent sees compressed, citation‑rich summaries** instead of raw, verbose search payloads.

- **Filesystem tools**
  - `agent_write_file`
  - `agent_edit_file`
  - (In `ALL_FILESYSTEM_TOOLS`, also `agent_delete_file`, `agent_search_files`, `agent_list_outputs`.)
  - Used to:
    - Write intermediate **checkpoint reports** (e.g., per required field or sub‑topic).
    - Edit/update notes or context files.
    - (Optionally) search/list outputs within the agent workspace.

- **Think tool**
  - `think_tool` (imported but not explicitly listed in ALL_RESEARCH_TOOLS in this snippet; can be added if needed).
  - When used, emits **reflection/thought messages** that are recorded in `DirectionAgentState["thoughts"]`.

These tools are wrapped by **LangGraph `ToolNode`**, enabling the direction agent to invoke them as part of its step‑by‑step reasoning.

---

### Bundle‑Level Orchestration: EntityIntelResearchBundleState

**State schema**: `EntityIntelResearchBundleState(TypedDict, total=False)`.

- **Core fields**
  - `episode: Dict[str, Any]`
  - `bundle: EntityBundleDirectionsFinal`
  - `bundle_id: str`
  - `direction_queue: List[DirectionType]` – ordered list of directions to run.
  - `direction_index: int` – current index into `direction_queue`.

- **Accumulated outputs**
  - `file_refs: Annotated[List[FileReference], operator.add]`
    - Merged from all direction agent runs.
  - `structured_outputs: Annotated[List[BaseModel], operator.add]` – reserved for future if needed.
  - `final_reports: Annotated[List[FileReference], operator.add]`
    - Per‑direction `final_report` refs from each DirectionAgent invocation.

**Key bundle‑level nodes**

- `init_bundle_research_node(state) -> EntityIntelResearchBundleState`
  - Sets:
    - `bundle_id` from `state["bundle"].bundleId`.
    - `direction_queue` via `build_direction_queue(bundle)`.
    - `direction_index = 0`.

- `has_next_direction(state) -> Literal["run_direction", "done"]`
  - Simple guard: if `direction_index < len(direction_queue)` → `"run_direction"` else `"done"`.

- `run_direction_node(state, config) -> EntityIntelResearchBundleState`
  - Selects current `direction_type` from `direction_queue[direction_index]`.
  - Builds `plan = select_direction_plan(bundle, direction_type)`.
  - Computes `run_id = sanitize_path_component(f"{bundle_id}_{direction_type}")`.
  - Constructs initial `DirectionAgentState` with empty lists, zero `steps_taken`, etc.
  - Wraps `config` with per‑direction checkpoint namespace via:
    - `dir_cfg = with_checkpoint_ns(config, ns_direction(bundle_id, direction_type))`.
  - Invokes the direction agent:
    - `out = await direction_agent.ainvoke(direction_state, dir_cfg)`.
  - Extracts:
    - `merged_file_refs = out.get("file_refs", []) or []`.
    - `merged_notes = out.get("research_notes", []) or []`.
    - `final_report = out.get("final_report")`.
    - `steps = int(out.get("steps_taken", 0) or 0)`.
  - Returns bundle‑level delta:
    - `"file_refs": merged_file_refs`
    - `"final_reports": [final_report]` if it’s a `FileReference`.

- `advance_direction_index_node(state) -> EntityIntelResearchBundleState`
  - Increments `direction_index` by 1.

- `finalize_bundle_research_node(state) -> EntityIntelResearchBundleState`
  - Logs completion and returns `{}` (placeholder for potential bundle summary).

**Graph wiring** (inside `make_bundle_research_graph`):

- Nodes:
  - `"init_bundle"`, `"run_direction"`, `"advance_direction"`, `"finalize_bundle"`.
- Edges:
  - Entry: `START` → `"init_bundle"`.
  - Conditional:
    - `"init_bundle"` → `"run_direction"` or `"finalize_bundle"` via `has_next_direction`.
  - `"run_direction"` → `"advance_direction"`.
  - `"advance_direction"` → `"run_direction"` or `"finalize_bundle"` via `has_next_direction`.
  - `"finalize_bundle"` → `END`.
- Compiled with shared `checkpointer` and `store` from `get_persistence()`; per‑run separation is via checkpoint namespaces.

---

### How Web Search Compression Fits Into the Overall Flow

1. **DirectionAgent** decides to call a web search tool (e.g. `tavily_search_research`) to gather evidence for one or more required fields.
2. The tool:
   - Calls Tavily (`tavily_search` / `tavily_extract` / `tavily_map`).
   - Saves raw results as JSON artifacts.
   - Uses `summarize_tavily_web_search` or `summarize_tavily_extract` to:
     - Run a **secondary summarization agent** (`create_agent + ProviderStrategy(TavilyResultsSummary)`) that transforms raw HTML/snippets into structured `summary + citations`.
   - Uses `format_tavily_summary_results` to turn the structured summary into a short, readable string.
   - Returns a `Command` that:
     - Increments `steps_taken`.
     - Appends a `ToolMessage` containing the **formatted summary** (not raw results) into the direction agent’s message history.
3. SummarizationMiddleware later compresses the accumulated conversation further as needed.

Combined effect:

- Web results are **double‑compressed**:
  - First by Tavily’s own retrieval.
  - Then by the summarization agent in `web_search_helpers`.
  - Finally, by the direction agent’s `SummarizationMiddleware` if the context grows too large.
- The agent sees:
  - A clean, reference‑rich narrative with citations.
  - A manageable number of tokens, even across many tool calls.

This design is critical to make long‑running research over multiple entities/directions feasible within `gpt_5_mini` and `gpt_5` context limits.

---

### Integration Notes and Future API/Rules Hooks

- **Invocation from FastAPI / LangSmith**
  - `make_bundle_research_graph(config)` returns a `CompiledStateGraph` ready to be:
    - Called directly via `.ainvoke(initial_state, config)`.
    - Or instrumented via LangSmith with thread IDs and checkpoint namespaces (`ns_bundle`, `ns_direction`).
  - External API can:
    - Provide `bundle` (`EntityBundleDirectionsFinal`) + `episode` in the initial state.
    - Set `config.configurable["checkpoint_ns"]` and/or `thread_id` to support pause/resume/fork.

- **Filesystem layout**
  - All checkpoint and final reports are written under `BASE_DIR` using sanitized path components:
    - `bundle_id` / `direction_type` / `run_id` / `filename`.
  - `FileReference.file_path` stores **relative paths** (relative to `BASE_DIR`) for durability and easier migration.

- **.cursor context**
  - This analysis doc and the one for **candidates + directions** live in:
    - `ingestion/src/research_agent/.cursor/analysis/`
  - Intended future usage:
    - Generate `.cursor/rules` entries describing:
      - How and when to invoke `make_bundle_research_graph`.
      - What inputs/outputs look like for each direction.
    - Seed a project plan for:
      - FastAPI endpoints (per graph + full workflow).
      - LangSmith integration (thread listing, checkpoint resume/fork).
      - Observability dashboards (artifacts, logs, seed provenance).

---

### Think Tool Integration Strategy (Current Gap and Next Step)

- **Current state**
  - `think_tool` is implemented in `human_upgrade/tools/think_tool.py` and:
    - Produces a **compact plan text** (`FOCUS`, `TARGET_FIELDS`, `NEXT_ACTIONS`, `OPEN_QUESTIONS`).
    - Updates:
      - `DirectionAgentState["thoughts"]`
      - `DirectionAgentState["last_plan"]`
      - `DirectionAgentState["required_fields_status"]`
      - `DirectionAgentState["current_focus"]`
      - `DirectionAgentState["open_questions"]`
    - Emits a `ToolMessage` so its plan is in the transcript.
  - The **prompt builders** in `human_upgrade/prompts/research_prompt_builders.py` rely heavily on this:
    - `get_initial_research_prompt` instructs the agent that the **first action must be `think_tool`** and frames the default workflow as `think_tool → tavily_search_research → tavily_extract_research → agent_write_file`.
    - `get_reminder_research_prompt` reads:
      - `last_plan` and/or latest entry in `thoughts` (via `_recent_thought`).
      - `required_fields_status` (via `_format_required_fields_status_compact`).
      - `current_focus` and recent `file_refs`.
    - Together, they implement a **reminder‑style prompting strategy** that:
      - Injects the latest plan and ledger state into each reminder prompt.
      - Uses `think_tool` as the primary primitive for **course correction and next‑step selection**.

- **Gap**
  - In the current `entity_research_graphs.py`, `think_tool` is **imported** but not yet wired into:
    - `RESEARCH_FILESYSTEM_TOOLS`
    - `ALL_RESEARCH_TOOLS`
  - As a result, the direction agent:
    - Cannot actually call `think_tool`, even though the prompts explicitly instruct it to do so.
    - Loses the intended tight feedback loop between:
      - Planning (`think_tool`).
      - Execution (`tavily_*` + filesystem tools).
      - Prompting (`get_initial_research_prompt` / `get_reminder_research_prompt`).

- **Intended fix (future code change, not yet applied)**
  - Update `ALL_RESEARCH_TOOLS` in `entity_research_graphs.py` to include `think_tool`, for example:
    - `ALL_RESEARCH_TOOLS = [wiki_tool, tavily_search_research, tavily_extract_research, tavily_map_research, think_tool] + RESEARCH_FILESYSTEM_TOOLS`
  - Optionally, also expose `think_tool` in a dedicated `PLANNING_TOOLS` list for clarity, but keep it in `ALL_RESEARCH_TOOLS` so the agent can call it.
  - Once added, the loop described in the prompts becomes **executable**:
    - First step: `think_tool` (plan + ledger update).
    - Subsequent steps: web search + extract + filesystem writes.
    - Reminder prompts: inject `last_plan`, ledger, focus, and recent files to keep the agent on track.

This section documents the **expected design** so that future implementation work can safely align the tools list with the prompt strategy without re‑deriving the intent.


