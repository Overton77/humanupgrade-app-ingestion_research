# Issue Analysis Report: File Paths and Agent Prompting

## Executive Summary

Two critical issues identified:
1. **File Path Construction Error**: Workspace paths are being duplicated and include Windows absolute paths in the middle
2. **Agent Waiting for Input**: Agent may not be starting automatically due to missing initial user message

---

## Issue #1: File Path Construction Problem

### Problem Description

The generated file path shows:
```
ingestion\agent_instances_current\C_\Users\Pinda\Proyectos\humanupgradeapp\ingestion\agent_instances_current\mission_onethousandroads_001_simplified\S1\S1.1\BusinessIdentityAndLeadershipAgent_BusinessIdentityAndLeadershipAgent_S1_S1.1_single\checkpoint_request_identity_leadership.md
```

**Expected path should be:**
```
ingestion\agent_instances_current\mission_onethousandroads_001_simplified\S1\S1.1\BusinessIdentityAndLeadershipAgent_BusinessIdentityAndLeadershipAgent_S1_S1.1_single\checkpoint_request_identity_leadership.md
```

### Root Cause Analysis

**Step 1: Workspace Creation** (`worker.py:178-184`)
```python
workspace = workspace_for(
    mission_id,
    stage_id,
    f"{sub_stage_id}",
    f"{inst.agent_type}_{inst.instance_id}",
)
workspace_root = str(workspace)
```

**Step 2: `workspace_for()` Returns Absolute Path** (`agent_workspace_root_helpers.py:97-101`)
```python
def workspace_for(*parts: str) -> Path:
    safe = [sanitize(p) for p in parts if p]
    p = BASE_DIR.joinpath(*safe)  # Returns ABSOLUTE Path
    p.mkdir(parents=True, exist_ok=True)
    return p
```

**Problem**: `BASE_DIR.joinpath(*safe)` creates an **absolute Path** like:
```
C:\Users\Pinda\Proyectos\humanupgradeapp\ingestion\agent_instances_current\mission_onethousandroads_001_simplified\S1\S1.1\...
```

**Step 3: Absolute Path Converted to String** (`worker.py:184`)
```python
workspace_root = str(workspace)  # Full absolute path string
```

**Step 4: Absolute Path Treated as Relative Components** (`file_system_tools.py:67-89`)
```python
def _rel_parts_from_ws_and_filename(workspace_root: str, filename: str) -> List[str]:
    root = (workspace_root or "").strip().replace("\\", "/").strip("/")
    # ... splits by "/" and treats each part as a component
    root_parts = [sanitize_path_component(p) for p in root.split("/") if p]
```

**Problem**: When `workspace_root` is `"C:\Users\Pinda\Proyectos\..."`, splitting by `/` after replacing `\` with `/` creates components:
- `C:`
- `Users`
- `Pinda`
- `Proyectos`
- `humanupgradeapp`
- `ingestion`
- `agent_instances_current`
- `mission_onethousandroads_001_simplified`
- ...

**Step 5: Components Rebuilt Under BASE_DIR** (`file_system_functions.py:107-135`)
```python
def resolve_workspace_path(*components: str) -> Path:
    relative_path = build_workspace_path(*components)  # Sanitizes each component
    absolute_path = (BASE_DIR / relative_path).resolve()  # Rebuilds under BASE_DIR
```

**Result**: Creates path like:
```
BASE_DIR/C_/Users/Pinda/Proyectos/.../agent_instances_current/.../filename
```

### Impact

- Files are written to incorrect locations
- Paths include Windows drive letters (`C_`) in the middle
- Path duplication (BASE_DIR appears twice in the path)
- File references stored in state will have incorrect paths
- Downstream file reading operations will fail

### Solution Plan

**Option A: Store Relative Path (Recommended)**
1. Modify `workspace_for()` to return a relative path string instead of absolute Path
2. Or create a new helper `workspace_root_for()` that returns relative string
3. Ensure `workspace_root` is always relative to `BASE_DIR`

**Option B: Fix Path Parsing**
1. Detect if `workspace_root` is absolute
2. Convert to relative before processing
3. More complex, less clean

**Recommended Implementation:**
```python
# In agent_workspace_root_helpers.py
def workspace_root_for(*parts: str) -> str:
    """
    Returns workspace root as relative path string (relative to BASE_DIR).
    Use this instead of workspace_for() when you need a string for state.
    """
    safe = [sanitize(p) for p in parts if p]
    return "/".join(safe)  # Return relative path string

# In worker.py
workspace_root = workspace_root_for(
    mission_id,
    stage_id,
    f"{sub_stage_id}",
    f"{inst.agent_type}_{inst.instance_id}",
)
```

---

## Issue #2: Agent Waiting for Input

### Problem Description

Agent appears to be waiting for user input when it should start working automatically with the provided context.

### Root Cause Analysis

**Step 1: Initial State Has Empty Messages** (`agent_instance_factory.py:370-386`)
```python
init_state: WorkerAgentState = {
    "messages": [],  # ⚠️ EMPTY MESSAGE LIST
    "agent_instance_plan": agent_instance_plan,
    "workspace_root": workspace_root,
    # ... other fields
}
```

**Step 2: Prompt Set via Dynamic Middleware** (`agent_instance_factory.py:269-280`)
```python
@dynamic_prompt
def worker_dynamic_prompt(request: ModelRequest) -> str:
    # Returns system prompt string
    return fn(s)  # build_initial_prompt or build_reminder_prompt
```

**Step 3: Prompt Contains "NOW:" Instruction** (`sub_agent_prompt_builders.py:467-469`)
```python
NOW:
If you need a plan, call think with 1–3 actions.
Otherwise, start with starter sources → then use the most surgical tool call (usually extract or map).
```

**Problem**: 
- `@dynamic_prompt` sets the **system prompt**, not a user message
- With empty `messages: []`, the agent has no user message to respond to
- LangChain agents typically need at least one `HumanMessage` to trigger execution
- The agent may be waiting for a user message before starting

### Impact

- Agent doesn't start working automatically
- Requires manual intervention or may timeout
- Poor user experience
- Unclear if agent is stuck or waiting

### Solution Plan

**Option A: Add Initial User Message (Recommended)**
```python
# In agent_instance_factory.py:run_worker_once
from langchain_core.messages import HumanMessage

init_state: WorkerAgentState = {
    "messages": [
        HumanMessage(content="Begin your research task. Use the starter sources and tools provided.")
    ],
    # ... rest of state
}
```

**Option B: Use System Message with Explicit Start**
- Modify prompt to be more explicit about auto-start
- Less reliable, depends on model behavior

**Option C: Check LangChain Agent Behavior**
- Verify if `create_agent` with `@dynamic_prompt` requires initial message
- May need to check LangChain documentation for expected pattern

**Recommended Implementation:**
Add a simple, clear user message that triggers the agent to start:
```python
init_state: WorkerAgentState = {
    "messages": [
        HumanMessage(content="Start your research task now.")
    ],
    # ... rest of state
}
```

---

## Additional Observations

### Workspace Root in Prompt

The prompt includes the full absolute path in the workspace description:
```python
f"Your file workspace root: Your filenames will be relative to this. Workspace: {state.get('workspace_root', '')}\n"
```

This will show the agent the full Windows path, which is confusing. After fixing Issue #1, this will show the correct relative path.

### Seed Context Not Used

The `seed_context` is stored in state but doesn't appear to be used in the prompt. The prompt builder accesses `starter_sources` directly from the plan, which is fine, but the seed_context could be leveraged for additional context injection.

---

## Priority & Implementation Order

1. **HIGH PRIORITY**: Fix Issue #1 (File Paths)
   - Blocks file operations
   - Causes incorrect file storage
   - Breaks downstream file reading

2. **HIGH PRIORITY**: Fix Issue #2 (Agent Prompting)
   - Blocks agent execution
   - Causes user confusion
   - May cause timeouts

3. **LOW PRIORITY**: Clean up workspace_root display in prompt
   - Cosmetic issue
   - Will be fixed automatically when Issue #1 is resolved

---

## Testing Plan

After fixes:

1. **Path Testing**:
   - Verify files are written to correct location
   - Check `file_refs` in state have correct relative paths
   - Verify file reading works with stored paths

2. **Agent Execution Testing**:
   - Verify agent starts automatically
   - Check agent uses starter sources
   - Verify agent creates checkpoint files

3. **Integration Testing**:
   - Run full mission workflow
   - Verify file paths in final reports
   - Check file references are correct

---

## Files Requiring Changes

1. `ingestion/src/research_agent/human_upgrade/tools/utils/agent_workspace_root_helpers.py`
   - Add `workspace_root_for()` function

2. `ingestion/src/research_agent/mission_queue/worker.py`
   - Change `workspace_for()` to `workspace_root_for()`
   - Update `workspace_root = str(workspace)` to use new function

3. `ingestion/src/research_agent/human_upgrade/graphs/agent_instance_factory.py`
   - Add initial `HumanMessage` to `init_state["messages"]`

4. `ingestion/src/research_agent/human_upgrade/graphs/sub_stage_graph.py` (if exists)
   - Similar fix for workspace_root if used there

---

## Risk Assessment

**Low Risk**: Both fixes are straightforward and don't change core logic, only:
- Path representation (absolute → relative)
- Initial message list (empty → one message)

**Backward Compatibility**: 
- Existing file paths will need migration if any files were written with wrong paths
- New runs will work correctly immediately
