from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langgraph.types import Command

from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference
from research_agent.agent_tools.filesystem_tools import (
    write_file as fs_write_file,
    read_file as fs_read_file,
    edit_file as fs_edit_file,
    delete_file as fs_delete_file,
    search_directory as fs_search_directory,
    search_files as fs_search_files,
)

# ============================================================
# Workspace layout
# ============================================================
# BASE_DIR is defined in your filesystem_tools module as:
#   BASE_DIR = Path.cwd() / "agent_files_current"
#
# Per-agent workspace root:
#   agent_files_current/<bundle_id>/<direction_type>/<run_id>/
#
# This ensures:
# - directions never collide
# - concurrent agents never overwrite each other
# - dynamic prompt can list files for this agent only
# ============================================================


# -----------------------------
# Workspace helpers
# -----------------------------

def _require_state_str(runtime: ToolRuntime, key: str) -> str:
    v = runtime.state.get(key)
    if not isinstance(v, str) or not v:
        raise ValueError(f"Missing/invalid runtime.state['{key}']")
    return v

def _workspace_root(runtime: ToolRuntime) -> Path:
    bundle_id = _require_state_str(runtime, "bundle_id")
    direction_type = _require_state_str(runtime, "direction_type")
    run_id = _require_state_str(runtime, "run_id")
    # IMPORTANT: this is a path RELATIVE to BASE_DIR used by fs_* tools.
    return Path(bundle_id) / direction_type / run_id

def _scoped_filename(runtime: ToolRuntime, filename: str) -> str:
    """
    Returns a string path *relative to BASE_DIR* that is scoped per agent.
    The model passes "filename" relative to agent workspace root; we scope it.
    """
    filename = filename.strip().lstrip("/").replace("\\", "/")
    if not filename:
        raise ValueError("filename cannot be empty")
    return str(_workspace_root(runtime) / filename)

def _inc_steps(runtime: ToolRuntime) -> int:
    steps = int(runtime.state.get("steps_taken", 0) or 0) + 1
    runtime.state["steps_taken"] = steps
    return steps

def _ensure_file_refs_list(runtime: ToolRuntime) -> List[Any]:
    file_refs = runtime.state.get("file_refs")
    if file_refs is None:
        runtime.state["file_refs"] = []
        return runtime.state["file_refs"]
    if not isinstance(file_refs, list):
        raise TypeError(f'runtime.state["file_refs"] must be a list, got {type(file_refs)}')
    return file_refs

async def _list_workspace_files(runtime: ToolRuntime) -> List[Dict[str, Any]]:
    """
    Returns a compact listing you can optionally inject in dynamic prompts:
      [{"path": "...", "size": 123, "is_dir": False}, ...]
    """
    root = _workspace_root(runtime)
    try:
        paths = await fs_search_directory(root)
    except Exception:
        # If folder doesn't exist yet, treat as empty.
        return []
    out: List[Dict[str, Any]] = []
    for p in paths:
        try:
            out.append(
                {
                    "name": p.name,
                    "path": str((root / p.name).as_posix()),
                    "is_dir": p.is_dir(),
                    "size": (p.stat().st_size if p.is_file() else None),
                }
            )
        except Exception:
            # Skip weird filesystem edge cases
            continue
    return out

def _require_description_for_reports(description: str) -> None:
    """
    Enforce your “description must be very useful” rule.
    Keep it minimal but strong (no vague 'notes' or 'summary').
    """
    d = (description or "").strip()
    if len(d) < 25:
        raise ValueError("description is required and must be detailed (>= 25 chars).")
    vague = {"notes", "summary", "file", "report", "temp", "output"}
    if d.lower() in vague:
        raise ValueError("description is too vague; describe exactly what is inside and what fields are covered.")


# ============================================================
# Tools (Command-based state updates)
# ============================================================

@tool(description="Write content to a file in the agent workspace.", parse_docstring=False)
async def agent_write_file(
    runtime: ToolRuntime,
    filename: str,
    content: str,
    description: str,
    bundle_id: str = "",
    entity_key: str = "",
) -> Command:
    """
    Writes content to a file under the agent's scoped workspace directory.
    Records FileReference in state, and returns a ToolMessage + state updates.
    """
    steps = _inc_steps(runtime)
    _require_description_for_reports(description)

    # Scope path per agent workspace
    scoped = _scoped_filename(runtime, filename)
    desc_text = f" - {description}" if description else ""
    logger.info(f"📝 WRITE FILE [{steps}]: {scoped}{desc_text}")

    status = "success"
    err: Optional[str] = None
    try:
        filepath = await fs_write_file(scoped, content)
        logger.info(f"✅ WRITE FILE complete: {filepath}")
    except Exception as e:
        status = "error"
        err = str(e)
        logger.error(f"❌ WRITE FILE failed: {e}")

    # FileReference should store the scoped path so any agent can locate it deterministically.
    # Prefer the runtime.state bundle_id if not passed.
    state_bundle_id = runtime.state.get("bundle_id") or bundle_id

    file_ref = FileReference(
        file_path=scoped,              # scoped relative-to-BASE_DIR path
        description=description,
        bundle_id=state_bundle_id,
        entity_key=entity_key,
    )

    file_refs = _ensure_file_refs_list(runtime)
    if status == "success":
        file_refs.append(file_ref)
        runtime.state["last_file_ref"] = file_ref  # handy for prompts
        runtime.state["last_file_event"] = {
            "op": "write",
            "file_path": scoped,
            "description": description,
            "entity_key": entity_key,
        }

    # Optional: cache workspace listing for dynamic prompts
    workspace_files = await _list_workspace_files(runtime)
    runtime.state["workspace_files"] = workspace_files

    # Craft tool-visible response content
    if status == "success":
        tool_content = (
            f"OK: wrote file '{scoped}'.\n"
            f"Description: {description}\n"
            f"Bytes: {len(content.encode('utf-8'))}\n"
            f"Tip: Use agent_read_file('{filename}') to read it (filename is workspace-relative)."
        )
    else:
        tool_content = f"ERROR: failed to write '{scoped}': {err}"

    return Command(
        update={
            "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
            "file_refs": file_refs,
            "last_file_ref": runtime.state.get("last_file_ref"),
            "last_file_event": runtime.state.get("last_file_event"),
            "workspace_files": workspace_files,
            "steps_taken": steps,
        }
    )


@tool(description="Read content from a file in the agent workspace.", parse_docstring=False)
async def agent_read_file(runtime: ToolRuntime, filename: str) -> Command:
    steps = _inc_steps(runtime)
    scoped = _scoped_filename(runtime, filename)
    logger.info(f"📖 READ FILE [{steps}]: {scoped}")

    try:
        content = await fs_read_file(scoped)
        logger.info(f"✅ READ FILE complete: {scoped}")
        tool_content = content
    except Exception as e:
        logger.error(f"❌ READ FILE failed: {e}")
        tool_content = f"ERROR: {e}"

    return Command(
        update={
            "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
            "steps_taken": steps,
        }
    )


@tool(description="Edit a file by finding and replacing text.", parse_docstring=False)
async def agent_edit_file(
    runtime: ToolRuntime,
    filename: str,
    find_text: str,
    replace_text: str,
    count: int = -1,
) -> Command:
    steps = _inc_steps(runtime)
    scoped = _scoped_filename(runtime, filename)
    logger.info(f"✏️  EDIT FILE [{steps}]: {scoped}")

    status = "success"
    err: Optional[str] = None
    try:
        filepath = await fs_edit_file(scoped, find_text, replace_text, count)
        logger.info(f"✅ EDIT FILE complete: {filepath}")
    except Exception as e:
        status = "error"
        err = str(e)
        logger.error(f"❌ EDIT FILE failed: {e}")

    # Optional: refresh workspace listing
    workspace_files = await _list_workspace_files(runtime)
    runtime.state["workspace_files"] = workspace_files

    if status == "success":
        runtime.state["last_file_event"] = {
            "op": "edit",
            "file_path": scoped,
            "find_text_preview": (find_text[:80] + "..." if len(find_text) > 80 else find_text),
        }
        tool_content = f"OK: edited file '{scoped}'. Replacements: {'all' if count == -1 else count}."
    else:
        tool_content = f"ERROR: failed to edit '{scoped}': {err}"

    return Command(
        update={
            "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
            "last_file_event": runtime.state.get("last_file_event"),
            "workspace_files": workspace_files,
            "steps_taken": steps,
        }
    )


@tool(description="Delete a file from the agent workspace.", parse_docstring=False)
async def agent_delete_file(runtime: ToolRuntime, filename: str) -> Command:
    steps = _inc_steps(runtime)
    scoped = _scoped_filename(runtime, filename)
    logger.info(f"🗑️  DELETE FILE [{steps}]: {scoped}")

    try:
        deleted = await fs_delete_file(scoped)
        if deleted:
            logger.info(f"✅ DELETE FILE complete: {scoped}")
            tool_content = f"OK: deleted '{scoped}'."
        else:
            tool_content = f"NOT FOUND: '{scoped}'."
    except Exception as e:
        logger.error(f"❌ DELETE FILE failed: {e}")
        tool_content = f"ERROR: failed to delete '{scoped}': {e}"

    workspace_files = await _list_workspace_files(runtime)
    runtime.state["workspace_files"] = workspace_files
    runtime.state["last_file_event"] = {"op": "delete", "file_path": scoped}

    return Command(
        update={
            "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
            "workspace_files": workspace_files,
            "last_file_event": runtime.state.get("last_file_event"),
            "steps_taken": steps,
        }
    )


@tool(description="List files and directories within the agent workspace.", parse_docstring=False)
async def agent_list_directory(runtime: ToolRuntime, subdir: Optional[str] = None) -> Command:
    steps = _inc_steps(runtime)

    root = _workspace_root(runtime)
    scoped_subdir = root / subdir if subdir else root
    logger.info(f"📂 LIST DIR [{steps}]: {scoped_subdir}")

    try:
        paths = await fs_search_directory(scoped_subdir)
        if not paths:
            tool_content = f"Directory is empty: {scoped_subdir}"
        else:
            files = [p for p in paths if p.is_file()]
            dirs = [p for p in paths if p.is_dir()]
            lines = [f"Contents of {scoped_subdir}:", ""]
            if dirs:
                lines.append("Directories:")
                for d in sorted(dirs):
                    lines.append(f"  📁 {d.name}/")
                lines.append("")
            if files:
                lines.append("Files:")
                for f in sorted(files):
                    size = f.stat().st_size
                    lines.append(f"  📄 {f.name} ({size} bytes)")
            tool_content = "\n".join(lines)
    except Exception as e:
        logger.error(f"❌ LIST DIR failed: {e}")
        tool_content = f"ERROR: {e}"

    workspace_files = await _list_workspace_files(runtime)
    runtime.state["workspace_files"] = workspace_files

    return Command(
        update={
            "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
            "workspace_files": workspace_files,
            "steps_taken": steps,
        }
    )


@tool(description="Search for files matching a glob pattern within the agent workspace.", parse_docstring=False)
async def agent_search_files(runtime: ToolRuntime, pattern: str, subdir: Optional[str] = None) -> Command:
    steps = _inc_steps(runtime)

    root = _workspace_root(runtime)
    scoped_subdir = root / subdir if subdir else root
    logger.info(f"🔍 SEARCH FILES [{steps}]: pattern='{pattern}' in {scoped_subdir}")

    try:
        paths = await fs_search_files(pattern, scoped_subdir)
        if not paths:
            tool_content = f"No files found matching pattern '{pattern}' in {scoped_subdir}"
        else:
            lines = [f"Found {len(paths)} file(s) matching '{pattern}' in {scoped_subdir}:", ""]
            for p in sorted(paths):
                # show path relative to BASE_DIR (agent_files_current)
                # NOTE: BASE_DIR lives in filesystem_tools; we avoid importing it here.
                lines.append(f"  📄 {p.as_posix()}")
            tool_content = "\n".join(lines)
    except Exception as e:
        logger.error(f"❌ SEARCH FILES failed: {e}")
        tool_content = f"ERROR: {e}"

    workspace_files = await _list_workspace_files(runtime)
    runtime.state["workspace_files"] = workspace_files

    return Command(
        update={
            "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
            "workspace_files": workspace_files,
            "steps_taken": steps,
        }
    )


@tool(
    description="List research outputs produced so far (file_refs + descriptions) for this agent run.",
    parse_docstring=False,
)
def agent_list_outputs(runtime: ToolRuntime) -> Command:
    """
    Returns a friendly string enumerating file_refs (path + description),
    plus optional workspace_files snapshot if present.
    """
    file_refs = runtime.state.get("file_refs") or []
    direction_type = runtime.state.get("direction_type", "UNKNOWN")
    bundle_id = runtime.state.get("bundle_id", "unknown")
    run_id = runtime.state.get("run_id", "unknown")

    lines: List[str] = []
    lines.append(f"Outputs for Bundle={bundle_id} Run={run_id} Direction={direction_type}")
    lines.append("")

    if not file_refs:
        lines.append("No file outputs recorded yet.")
    else:
        lines.append(f"File outputs ({len(file_refs)}):")
        for i, r in enumerate(file_refs, start=1):
            file_path = getattr(r, "file_path", None) or (r.get("file_path") if isinstance(r, dict) else "unknown")
            desc = getattr(r, "description", None) or (r.get("description") if isinstance(r, dict) else "")
            entity_key = getattr(r, "entity_key", None) or (r.get("entity_key") if isinstance(r, dict) else "")
            ek = f" ({entity_key})" if entity_key else ""
            if desc:
                lines.append(f"{i}. {file_path}{ek}\n   - {desc}")
            else:
                lines.append(f"{i}. {file_path}{ek}")

    # Optional: include workspace snapshot if present
    ws = runtime.state.get("workspace_files") or []
    if ws:
        lines.append("")
        lines.append(f"Workspace snapshot ({len(ws)} items, top-level):")
        for item in ws[:30]:
            name = item.get("name", "unknown")
            path = item.get("path", name)
            is_dir = bool(item.get("is_dir", False))
            size = item.get("size", None)
            if is_dir:
                lines.append(f"- 📁 {path}/")
            else:
                sz = f" ({size} bytes)" if isinstance(size, int) else ""
                lines.append(f"- 📄 {path}{sz}")
        if len(ws) > 30:
            lines.append(f"...and {len(ws) - 30} more.")

    content = "\n".join(lines)

    return Command(
        update={
            "messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)],
        }
    )