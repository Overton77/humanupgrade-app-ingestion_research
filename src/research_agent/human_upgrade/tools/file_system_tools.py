"""
Agent-Facing File System Tools (Workspace-Scoped, Minimal)

- Everything is scoped under runtime.state["workspace_root"] (set per agent instance).
- Filenames are workspace-relative (may include subdirs, forward slashes).
- All path components are sanitized for Windows safety.
- No bundle/run/direction legacy.
- Tools update state via Command: messages + file_refs + progress_ledger + outputs_by_substage.

Expected runtime.state keys:
- workspace_root: str (required; deterministic per agent instance)
- agent_instance_plan: AgentInstancePlanWithSources (optional but recommended)
- agent_type: str (optional; used for FileReference.agent_type fallback)
- sub_stage_id: str (optional; enables outputs_by_substage fan-in)

State fields written/updated:
- steps_taken (int)
- file_refs (list delta)
- last_file_ref (overwrite)
- progress_ledger (overwrite dict)
- outputs_by_substage (overwrite dict[str, list[FileReference|str]])
- messages (list delta)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Literal, Annotated

from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langgraph.types import Command

from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference
from research_agent.agent_tools.file_system_functions import (
    BASE_DIR,
    sanitize_path_component,
    resolve_workspace_path,  # security: prevents traversal
    write_file,
    read_file,
    edit_file,
)

# ---------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------

LedgerStatus = Literal["todo", "in_progress", "done", "blocked", "not_found"]


# ---------------------------------------------------------------------
# Tiny helpers (keep minimal)
# ---------------------------------------------------------------------

def _steps(runtime: ToolRuntime) -> int:
    return int(runtime.state.get("steps_taken", 0) or 0) + 1


def _ws_root(runtime: ToolRuntime) -> str:
    ws = runtime.state.get("workspace_root")
    if isinstance(ws, str) and ws.strip():
        return ws
    return "agent_outputs/_missing_workspace"


def _rel_parts_from_ws_and_filename(workspace_root: str, filename: str) -> List[str]:
    """
    Build sanitized BASE_DIR-relative path parts from workspace_root + filename.
    Uses resolve_workspace_path for traversal safety.
    Returns relative parts (split on '/').
    """
    # workspace root components
    root = (workspace_root or "").strip().replace("\\", "/").strip("/")
    root_parts = [sanitize_path_component(p) for p in root.split("/") if p] or ["_missing_workspace"]

    # filename components
    fn = (filename or "").strip().replace("\\", "/").lstrip("/")
    if not fn:
        raise ValueError("filename cannot be empty")
    fn_parts = [sanitize_path_component(p) for p in fn.split("/") if p]
    if not fn_parts:
        raise ValueError("filename resolves to empty after sanitization")

    # security: ensure final path is inside BASE_DIR
    abs_path: Path = resolve_workspace_path(*root_parts, *fn_parts)

    rel = str(abs_path.relative_to(BASE_DIR)).replace("\\", "/")
    return [p for p in rel.split("/") if p]


def _make_file_ref(runtime: ToolRuntime, rel_path: str, description: str) -> FileReference:
    """
    New FileReference (4 fields): file_path, agent_type, description, source.
    """
    plan = runtime.state.get("agent_instance_plan")

    agent_type = ""
    source = ""

    try:
        if plan is not None:
            agent_type = str(getattr(plan, "agent_type", "") or "")
            source = str(getattr(plan, "instance_id", "") or "")
    except Exception:
        agent_type = ""
        source = ""

    if not agent_type:
        at = runtime.state.get("agent_type")
        agent_type = str(at) if isinstance(at, str) else ""

    if not source:
        source = "unknown_instance"

    return FileReference(
        file_path=rel_path,
        agent_type=agent_type or "UnknownAgent",
        description=(description or "").strip() or "Workspace file written by agent.",
        source=source,
    )


def _ledger(runtime: ToolRuntime) -> Dict[str, Dict[str, Any]]:
    x = runtime.state.get("progress_ledger")
    return dict(x) if isinstance(x, dict) else {}


def _ledger_apply(
    ledger: Dict[str, Dict[str, Any]],
    *,
    keys: List[str],
    status: LedgerStatus,
    evidence_file: Optional[str],
    notes: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    for raw in keys:
        k = (raw or "").strip()
        if not k:
            continue
        entry = dict(ledger.get(k) or {"status": "todo", "evidence_files": [], "notes": ""})
        entry["status"] = status
        if notes is not None:
            entry["notes"] = (notes or "").strip()[:400]
        if evidence_file:
            ev = list(entry.get("evidence_files") or [])
            if evidence_file not in ev:
                ev.append(evidence_file)
            entry["evidence_files"] = ev
        ledger[k] = entry
    return ledger


def _append_to_substage_outputs(runtime: ToolRuntime, item: Any) -> Optional[Dict[str, Any]]:
    """
    If sub_stage_id is present, append `item` to outputs_by_substage[sub_stage_id].
    Returns dict patch or None.
    """
    sid = runtime.state.get("sub_stage_id")
    if not isinstance(sid, str) or not sid.strip():
        return None
    outputs = runtime.state.get("outputs_by_substage")
    out_map: Dict[str, List[Any]] = dict(outputs) if isinstance(outputs, dict) else {}
    cur = list(out_map.get(sid) or [])
    cur.append(item)
    out_map[sid] = cur
    return {"outputs_by_substage": out_map}


# ---------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------

@tool(description="Write content to a file in this agent instance's workspace.", parse_docstring=False)
async def agent_write_file(
    runtime: ToolRuntime,
    filename: Annotated[str, "Workspace-relative filename (may include subdirs). Example: 'checkpoints/identity.md'"],
    content: Annotated[str, "Text content to write."],
    description: Annotated[str, "Short description of what this file contains."],
    artifact_keys: Annotated[Optional[List[str]], "Optional artifact keys satisfied by this file."] = None,
    objective_keys: Annotated[Optional[List[str]], "Optional objective keys satisfied by this file."] = None,
    ledger_status: Annotated[LedgerStatus, "Ledger status to set for provided keys."] = "done",
    ledger_notes: Annotated[Optional[str], "Optional notes to store in progress_ledger entries."] = None,
    emit_to_substage_outputs: Annotated[bool, "If true, append FileReference to outputs_by_substage[sub_stage_id]."] = True,
) -> Command:
    s = _steps(runtime)
    ws = _ws_root(runtime)
    updates: Dict[str, Any] = {"steps_taken": s}

    try:
        rel_parts = _rel_parts_from_ws_and_filename(ws, filename)
        await write_file(*rel_parts, content=content)

        rel_path = "/".join(rel_parts)
        file_ref = _make_file_ref(runtime, rel_path, description)

        # state updates
        updates["file_refs"] = [file_ref]
        updates["last_file_ref"] = file_ref

        # ledger
        keys: List[str] = []
        for k in (artifact_keys or []):
            if isinstance(k, str) and k.strip():
                keys.append(k.strip())
        for k in (objective_keys or []):
            if isinstance(k, str) and k.strip():
                keys.append(k.strip())
        if keys:
            led = _ledger(runtime)
            updates["progress_ledger"] = _ledger_apply(
                led,
                keys=keys,
                status=ledger_status,
                evidence_file=rel_path,
                notes=ledger_notes,
            )

        # outputs_by_substage
        if emit_to_substage_outputs:
            patch = _append_to_substage_outputs(runtime, file_ref)
            if patch:
                updates.update(patch)

        msg = f"✅ Wrote: {rel_path}"
        updates["messages"] = [ToolMessage(content=msg, tool_call_id=runtime.tool_call_id)]
        logger.info(f"📝 WRITE [{s}] {rel_path}")
        return Command(update=updates)

    except Exception as e:
        msg = f"❌ WRITE failed for '{filename}': {e}"
        updates["messages"] = [ToolMessage(content=msg, tool_call_id=runtime.tool_call_id)]
        logger.error(msg, exc_info=True)
        return Command(update=updates)


@tool(description="Read a file from this agent instance's workspace.", parse_docstring=False)
async def agent_read_file(
    runtime: ToolRuntime,
    filename: Annotated[str, "Workspace-relative filename to read."],
) -> Command:
    s = _steps(runtime)
    ws = _ws_root(runtime)

    try:
        rel_parts = _rel_parts_from_ws_and_filename(ws, filename)
        content = await read_file(*rel_parts)

        logger.info(f"📖 READ [{s}] {'/'.join(rel_parts)}")
        return Command(
            update={
                "steps_taken": s,
                "messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)],
            }
        )

    except Exception as e:
        msg = f"❌ READ failed for '{filename}': {e}"
        logger.error(msg, exc_info=True)
        return Command(
            update={
                "steps_taken": s,
                "messages": [ToolMessage(content=msg, tool_call_id=runtime.tool_call_id)],
            }
        )


@tool(description="Edit a file in this agent instance's workspace via find/replace.", parse_docstring=False)
async def agent_edit_file(
    runtime: ToolRuntime,
    filename: Annotated[str, "Workspace-relative filename to edit."],
    find_text: Annotated[str, "Text to find."],
    replace_text: Annotated[str, "Replacement text."],
    count: Annotated[int, "Number of replacements (-1 = all)."] = -1,
    emit_to_substage_outputs: Annotated[bool, "If true, append a short edit note to outputs_by_substage."] = False,
) -> Command:
    s = _steps(runtime)
    ws = _ws_root(runtime)
    updates: Dict[str, Any] = {"steps_taken": s}

    try:
        rel_parts = _rel_parts_from_ws_and_filename(ws, filename)
        await edit_file(*rel_parts, find_text=find_text, replace_text=replace_text, count=count)
        rel_path = "/".join(rel_parts)

        msg = f"✅ Edited: {rel_path} (replacements={'all' if count == -1 else count})"
        updates["messages"] = [ToolMessage(content=msg, tool_call_id=runtime.tool_call_id)]

        if emit_to_substage_outputs:
            patch = _append_to_substage_outputs(runtime, msg)
            if patch:
                updates.update(patch)

        logger.info(f"✏️ EDIT [{s}] {rel_path}")
        return Command(update=updates)

    except Exception as e:
        msg = f"❌ EDIT failed for '{filename}': {e}"
        updates["messages"] = [ToolMessage(content=msg, tool_call_id=runtime.tool_call_id)]
        logger.error(msg, exc_info=True)
        return Command(update=updates)


@tool(description="Delete a file from this agent instance's workspace.", parse_docstring=False)
async def agent_delete_file(
    runtime: ToolRuntime,
    filename: Annotated[str, "Workspace-relative filename to delete."],
) -> Command:
    s = _steps(runtime)
    ws = _ws_root(runtime)

    try:
        rel_parts = _rel_parts_from_ws_and_filename(ws, filename)
        abs_path = resolve_workspace_path(*rel_parts)

        if abs_path.exists() and abs_path.is_file():
            abs_path.unlink()
            msg = f"✅ Deleted: {'/'.join(rel_parts)}"
            deleted = True
        else:
            msg = f"⚠️ Not found: {'/'.join(rel_parts)}"
            deleted = False

        logger.info(f"🗑️ DELETE [{s}] {'/'.join(rel_parts)} deleted={deleted}")
        return Command(
            update={
                "steps_taken": s,
                "messages": [ToolMessage(content=msg, tool_call_id=runtime.tool_call_id)],
            }
        )

    except Exception as e:
        msg = f"❌ DELETE failed for '{filename}': {e}"
        logger.error(msg, exc_info=True)
        return Command(
            update={
                "steps_taken": s,
                "messages": [ToolMessage(content=msg, tool_call_id=runtime.tool_call_id)],
            }
        )


@tool(description="List files in this agent instance's workspace (optionally within a subdir).", parse_docstring=False)
async def agent_list_directory(
    runtime: ToolRuntime,
    subdir: Annotated[Optional[str], "Optional subdirectory inside the workspace."] = None,
) -> Command:
    s = _steps(runtime)
    ws = _ws_root(runtime)

    try:
        # Build a safe directory path under workspace_root
        target = subdir.strip() if isinstance(subdir, str) else ""
        if not target:
            target = "."

        rel_parts = _rel_parts_from_ws_and_filename(ws, target)
        abs_path = resolve_workspace_path(*rel_parts)

        # If user passed ".", rel_parts includes "." sanitized out by our helper,
        # so abs_path may point to a file if target had a filename. Ensure dir:
        abs_dir = abs_path if abs_path.is_dir() else abs_path.parent

        if not abs_dir.exists():
            content = "(directory not found)"
        else:
            items = sorted(abs_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            if not items:
                content = "(empty)"
            else:
                lines: List[str] = []
                for p in items:
                    rp = str(p.relative_to(BASE_DIR)).replace("\\", "/")
                    if p.is_dir():
                        lines.append(f"📁 {rp}/")
                    else:
                        try:
                            lines.append(f"📄 {rp} ({p.stat().st_size} bytes)")
                        except Exception:
                            lines.append(f"📄 {rp}")
                content = "\n".join(lines)

        logger.info(f"📂 LIST [{s}] ws={ws} subdir={subdir or '.'}")
        return Command(
            update={
                "steps_taken": s,
                "messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)],
            }
        )

    except Exception as e:
        msg = f"❌ LIST failed: {e}"
        logger.error(msg, exc_info=True)
        return Command(
            update={
                "steps_taken": s,
                "messages": [ToolMessage(content=msg, tool_call_id=runtime.tool_call_id)],
            }
        )


@tool(description="Search files by glob pattern within this agent instance's workspace.", parse_docstring=False)
async def agent_search_files(
    runtime: ToolRuntime,
    pattern: Annotated[str, "Glob pattern (e.g. '*.md', '**/*.txt')."],
    subdir: Annotated[Optional[str], "Optional subdir inside workspace to constrain search."] = None,
) -> Command:
    s = _steps(runtime)
    ws = _ws_root(runtime)

    try:
        base = subdir.strip() if isinstance(subdir, str) else ""
        if not base:
            base = "."

        rel_parts = _rel_parts_from_ws_and_filename(ws, base)
        abs_path = resolve_workspace_path(*rel_parts)
        abs_dir = abs_path if abs_path.is_dir() else abs_path.parent

        if not abs_dir.exists():
            content = "(search root not found)"
        else:
            matches = sorted(abs_dir.glob(pattern))
            if not matches:
                content = "(no matches)"
            else:
                lines = []
                for p in matches:
                    try:
                        rp = str(p.relative_to(BASE_DIR)).replace("\\", "/")
                    except Exception:
                        rp = str(p)
                    lines.append(f"📄 {rp}")
                content = "\n".join(lines)

        logger.info(f"🔍 SEARCH [{s}] pattern={pattern} ws={ws} subdir={subdir or '.'}")
        return Command(
            update={
                "steps_taken": s,
                "messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)],
            }
        )

    except Exception as e:
        msg = f"❌ SEARCH failed: {e}"
        logger.error(msg, exc_info=True)
        return Command(
            update={
                "steps_taken": s,
                "messages": [ToolMessage(content=msg, tool_call_id=runtime.tool_call_id)],
            }
        )
