"""
Agent-Facing File System Tools

These tools wrap the low-level file system functions and provide
a clean interface for the agent to interact with its workspace.

All paths are automatically scoped and sanitized to prevent:
- Path traversal attacks
- Windows-invalid characters
- Collisions between agents
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
    write_file,
    read_file,
    edit_file,
    delete_file,
    list_directory,
    search_files,
    sanitize_path_component,
    BASE_DIR,
)


# ============================================================
# WORKSPACE HELPERS
# ============================================================

def _get_state_value(runtime: ToolRuntime, key: str, default: str = "") -> str:
    """Get a state value, sanitizing it for use in paths."""
    value = runtime.state.get(key, default)
    if not isinstance(value, str):
        if value is None:
            return default
        value = str(value)
    
    # CRITICAL: Always sanitize values from state
    # This handles both new runs AND old checkpoints with invalid characters
    return sanitize_path_component(value)


def _get_workspace_components(runtime: ToolRuntime) -> tuple[str, str, str]:
    """
    Get the workspace path components from runtime state.
    
    Returns:
        Tuple of (bundle_id, direction_type, run_id)
        All components are sanitized and guaranteed Windows-safe.
    """
    bundle_id = _get_state_value(runtime, "bundle_id")
    direction_type = _get_state_value(runtime, "direction_type")
    run_id = _get_state_value(runtime, "run_id")
    
    # Validate that we have all required components
    if not bundle_id:
        raise ValueError("Missing bundle_id in runtime state")
    if not direction_type:
        raise ValueError("Missing direction_type in runtime state")
    if not run_id:
        raise ValueError("Missing run_id in runtime state")
    
    # Log if we had to sanitize (indicates old checkpoint with invalid chars)
    raw_run_id = runtime.state.get("run_id", "")
    if ":" in str(raw_run_id) or "<" in str(raw_run_id) or ">" in str(raw_run_id):
        logger.warning(
            "⚠️  Sanitized workspace path from checkpoint (had invalid Windows chars): "
            "bundle_id=%s, direction_type=%s, run_id='%s' -> '%s'",
            bundle_id, direction_type, raw_run_id, run_id
        )
    
    logger.debug(
        "Workspace: bundle_id=%s, direction_type=%s, run_id=%s",
        bundle_id, direction_type, run_id
    )
    
    return bundle_id, direction_type, run_id


def _build_file_path(runtime: ToolRuntime, filename: str) -> tuple[str, str, str, str]:
    """
    Build the full file path components from runtime state + filename.
    
    Args:
        runtime: Tool runtime with state
        filename: Workspace-relative filename from the agent
        
    Returns:
        Tuple of (bundle_id, direction_type, run_id, filename)
        All components are sanitized.
    """
    bundle_id, direction_type, run_id = _get_workspace_components(runtime)
    
    # Clean up the filename
    filename = filename.strip().lstrip("/").replace("\\", "/")
    if not filename:
        raise ValueError("filename cannot be empty")
    
    # Sanitize each part of the filename (handles nested paths)
    filename_parts = [sanitize_path_component(p) for p in filename.split("/") if p]
    clean_filename = "/".join(filename_parts)
    
    return bundle_id, direction_type, run_id, clean_filename


def _inc_steps(runtime: ToolRuntime) -> int:
    """Increment and return the step counter."""
    return int(runtime.state.get("steps_taken", 0) or 0) + 1


async def _list_workspace_files(runtime: ToolRuntime) -> List[Dict[str, Any]]:
    """
    Get a list of all files in the current workspace.
    
    Returns:
        List of dicts with file info
    """
    try:
        bundle_id, direction_type, run_id = _get_workspace_components(runtime)
        paths = await list_directory(bundle_id, direction_type, run_id)
    except Exception:
        return []
    
    files = []
    for p in paths:
        try:
            files.append({
                "name": p.name,
                "path": str(p.relative_to(BASE_DIR)),
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else None,
            })
        except Exception:
            continue
    
    return files


def _require_description(description: str) -> None:
    """Validate that description is useful."""
    d = (description or "").strip()
    if len(d) < 25:
        raise ValueError("description must be at least 25 characters")
    
    vague_words = {"notes", "summary", "file", "report", "temp", "output"}
    if d.lower() in vague_words:
        raise ValueError("description is too vague - describe what's inside and what it covers")


# ============================================================
# TYPE DEFINITIONS
# ============================================================

FieldStatus = Literal["todo", "in_progress", "done", "not_found"]


def _safe_status(x: Optional[str]) -> Optional[FieldStatus]:
    """Validate field status."""
    if x in ("todo", "in_progress", "done", "not_found"):
        return x  # type: ignore
    return None


def _ensure_rfs_entry(existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Ensure required_fields_status entry has correct structure."""
    base = {"status": "todo", "evidence_files": [], "notes": ""}
    if not isinstance(existing, dict):
        return dict(base)
    
    out = dict(base)
    out.update({k: v for k, v in existing.items() if k in base})
    
    if not isinstance(out.get("evidence_files"), list):
        out["evidence_files"] = []
    
    return out


# ============================================================
# AGENT TOOLS
# ============================================================

@tool(
    description="Write content to a file in the agent workspace.",
    parse_docstring=False
)
async def agent_write_file(
    runtime: ToolRuntime,
    filename: Annotated[
        str,
        "Workspace-relative path for the output file (e.g., 'checkpoints/trials_safety.txt'). "
        "Avoid absolute paths. Use forward slashes for subdirectories."
    ],
    content: Annotated[
        str,
        "Plain-text content to write. For reports, include citations and URLs under claims."
    ],
    description: Annotated[
        str,
        "Detailed description (>=25 chars): what this file contains, which fields it covers, "
        "key evidence sources, and what's missing or uncertain."
    ],
    bundle_id: Annotated[
        str,
        "Optional: bundle_id override (normally inferred from runtime state)."
    ] = "",
    entity_key: Annotated[
        str,
        "Optional: stable key for the entity/section (used for indexing)."
    ] = "",
    covered_fields: Annotated[
        Optional[List[str]],
        "List of requiredFields covered by this file. Auto-updates the research ledger."
    ] = None,
    field_statuses: Annotated[
        Optional[Dict[str, FieldStatus]],
        "Optional status overrides per field (e.g., {'founder_bio': 'not_found'})."
    ] = None,
    field_notes: Annotated[
        Optional[Dict[str, str]],
        "Optional notes per field (<=280 chars) for the ledger."
    ] = None,
    mark_as_key_file: Annotated[
        bool,
        "If true, mark this file as a key checkpoint in the context index."
    ] = True,
) -> Command:
    """
    Write content to a file in the agent's scoped workspace.
    
    This tool automatically:
    - Sanitizes all path components for Windows safety
    - Creates parent directories as needed
    - Records the file reference in state
    - Updates the required_fields_status ledger
    - Updates the context_index for the agent
    """
    try:
        steps = _inc_steps(runtime)
        _require_description(description)
        
        # Build sanitized file path components
        bundle_id_comp, direction_type_comp, run_id_comp, filename_comp = _build_file_path(
            runtime, filename
        )
        
        # Log what we're doing
        logger.info(
            f"📝 WRITE FILE [{steps}]: {bundle_id_comp}/{direction_type_comp}/"
            f"{run_id_comp}/{filename_comp} - {description[:80]}"
        )
        
        # Write the file using the new API
        try:
            filepath = await write_file(
                bundle_id_comp,
                direction_type_comp,
                run_id_comp,
                filename_comp,
                content=content
            )
            
            # Calculate relative path for state storage
            relative_path = str(filepath.relative_to(BASE_DIR))
            
            logger.info(f"✅ WRITE FILE complete: {relative_path}")
            status = "success"
            error = None
            
        except Exception as e:
            logger.error(f"❌ WRITE FILE failed: {e}", exc_info=True)
            status = "error"
            error = str(e)
            relative_path = f"{bundle_id_comp}/{direction_type_comp}/{run_id_comp}/{filename_comp}"
        
        # Build state updates
        state_updates: Dict[str, Any] = {"steps_taken": steps}
        
        if status == "success":
            # Create file reference
            file_ref = FileReference(
                file_path=relative_path,
                description=description,
                bundle_id=runtime.state.get("bundle_id") or bundle_id,
                entity_key=entity_key,
            )
            
            # Add to file_refs list
            state_updates["file_refs"] = [file_ref]
            state_updates["last_file_ref"] = file_ref
            state_updates["last_file_event"] = {
                "op": "write",
                "file_path": relative_path,
                "description": description,
                "entity_key": entity_key,
                "covered_fields": covered_fields or [],
            }
            
            # Update required_fields_status ledger
            rfs: Dict[str, Any] = dict(runtime.state.get("required_fields_status") or {})
            cf = [f.strip() for f in (covered_fields or []) if isinstance(f, str) and f.strip()]
            statuses = field_statuses or {}
            notes_map = field_notes or {}
            
            for field in cf:
                entry = _ensure_rfs_entry(rfs.get(field))
                
                # Add file to evidence_files (deduplicated)
                ev = list(entry.get("evidence_files") or [])
                if relative_path not in ev:
                    ev.append(relative_path)
                entry["evidence_files"] = ev
                
                # Set status
                s_override = _safe_status(statuses.get(field)) if isinstance(statuses, dict) else None
                entry["status"] = s_override or "done"
                
                # Set notes
                if isinstance(notes_map, dict) and field in notes_map:
                    entry["notes"] = (notes_map[field] or "")[:280]
                
                rfs[field] = entry
            
            if cf:
                state_updates["required_fields_status"] = rfs
            
            # Update context_index
            ctx = dict(runtime.state.get("context_index") or {})
            ctx["latest_checkpoint"] = relative_path
            if mark_as_key_file:
                kf = list(ctx.get("key_files") or [])
                if relative_path not in kf:
                    kf.append(relative_path)
                ctx["key_files"] = kf[-25:]  # Keep last 25
            state_updates["context_index"] = ctx
        
        # Refresh workspace file listing
        workspace_files = await _list_workspace_files(runtime)
        state_updates["workspace_files"] = workspace_files
        
        # Build tool response
        if status == "success":
            covered_preview = ", ".join((covered_fields or [])[:8]) if covered_fields else "(none)"
            tool_content = (
                f"✅ File written: '{filename}'\n"
                f"Path: {relative_path}\n"
                f"Size: {len(content.encode('utf-8'))} bytes\n"
                f"Description: {description}\n"
                f"Covered fields: {covered_preview}"
            )
        else:
            tool_content = f"❌ ERROR: failed to write '{filename}': {error}"
        
        state_updates["messages"] = [
            ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)
        ]
        
        return Command(update=state_updates)
    
    except Exception as e:
        # Catch ALL errors and return as ToolMessage
        logger.error(f"❌ WRITE FILE exception: {e}", exc_info=True)
        return Command(
            update={
                "steps_taken": int(runtime.state.get("steps_taken", 0) or 0) + 1,
                "messages": [
                    ToolMessage(
                        content=f"❌ ERROR: failed to write '{filename}': {str(e)}",
                        tool_call_id=runtime.tool_call_id
                    )
                ],
            }
        )


@tool(
    description="Read content from a file in the agent workspace.",
    parse_docstring=False
)
async def agent_read_file(
    runtime: ToolRuntime,
    filename: Annotated[str, "Workspace-relative path to read"]
) -> Command:
    """Read a file from the agent's workspace."""
    try:
        steps = _inc_steps(runtime)
        
        # Build file path
        bundle_id, direction_type, run_id, filename_comp = _build_file_path(runtime, filename)
        
        logger.info(
            f"📖 READ FILE [{steps}]: {bundle_id}/{direction_type}/{run_id}/{filename_comp}"
        )
        
        # Read the file
        try:
            content = await read_file(bundle_id, direction_type, run_id, filename_comp)
            logger.info(f"✅ READ FILE complete: {filename}")
            tool_content = content
        except Exception as e:
            logger.error(f"❌ READ FILE failed: {e}")
            tool_content = f"❌ ERROR: {e}"
        
        return Command(
            update={
                "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
                "steps_taken": steps,
            }
        )
    
    except Exception as e:
        logger.error(f"❌ READ FILE exception: {e}", exc_info=True)
        return Command(
            update={
                "steps_taken": int(runtime.state.get("steps_taken", 0) or 0) + 1,
                "messages": [
                    ToolMessage(
                        content=f"❌ ERROR: failed to read '{filename}': {str(e)}",
                        tool_call_id=runtime.tool_call_id
                    )
                ],
            }
        )


@tool(
    description="Edit a file by finding and replacing text.",
    parse_docstring=False
)
async def agent_edit_file(
    runtime: ToolRuntime,
    filename: Annotated[str, "Workspace-relative path to edit"],
    find_text: Annotated[str, "Text to find in the file"],
    replace_text: Annotated[str, "Text to replace with"],
    count: Annotated[int, "Number of replacements (-1 = all)"] = -1
) -> Command:
    """Edit a file by finding and replacing text."""
    try:
        steps = _inc_steps(runtime)
        
        # Build file path
        bundle_id, direction_type, run_id, filename_comp = _build_file_path(runtime, filename)
        
        logger.info(
            f"✏️  EDIT FILE [{steps}]: {bundle_id}/{direction_type}/{run_id}/{filename_comp}"
        )
        
        # Edit the file
        try:
            filepath = await edit_file(
                bundle_id, direction_type, run_id, filename_comp,
                find_text=find_text,
                replace_text=replace_text,
                count=count
            )
            relative_path = str(filepath.relative_to(BASE_DIR))
            logger.info(f"✅ EDIT FILE complete: {filename}")
            tool_content = f"✅ Edited '{filename}'. Replacements: {'all' if count == -1 else count}"
        except Exception as e:
            logger.error(f"❌ EDIT FILE failed: {e}")
            tool_content = f"❌ ERROR: {e}"
            relative_path = None
        
        # Refresh workspace listing
        workspace_files = await _list_workspace_files(runtime)
        
        state_updates: Dict[str, Any] = {
            "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
            "workspace_files": workspace_files,
            "steps_taken": steps,
        }
        
        if relative_path:
            state_updates["last_file_event"] = {
                "op": "edit",
                "file_path": relative_path,
                "find_text_preview": (find_text[:80] + "..." if len(find_text) > 80 else find_text),
            }
        
        return Command(update=state_updates)
    
    except Exception as e:
        logger.error(f"❌ EDIT FILE exception: {e}", exc_info=True)
        return Command(
            update={
                "steps_taken": int(runtime.state.get("steps_taken", 0) or 0) + 1,
                "messages": [
                    ToolMessage(
                        content=f"❌ ERROR: failed to edit '{filename}': {str(e)}",
                        tool_call_id=runtime.tool_call_id
                    )
                ],
            }
        )


@tool(
    description="Delete a file from the agent workspace.",
    parse_docstring=False
)
async def agent_delete_file(
    runtime: ToolRuntime,
    filename: Annotated[str, "Workspace-relative path to delete"]
) -> Command:
    """Delete a file from the agent's workspace."""
    try:
        steps = _inc_steps(runtime)
        
        # Build file path
        bundle_id, direction_type, run_id, filename_comp = _build_file_path(runtime, filename)
        
        logger.info(
            f"🗑️  DELETE FILE [{steps}]: {bundle_id}/{direction_type}/{run_id}/{filename_comp}"
        )
        
        # Delete the file
        try:
            deleted = await delete_file(bundle_id, direction_type, run_id, filename_comp)
            if deleted:
                logger.info(f"✅ DELETE FILE complete: {filename}")
                tool_content = f"✅ Deleted '{filename}'"
            else:
                tool_content = f"⚠️  File not found: '{filename}'"
        except Exception as e:
            logger.error(f"❌ DELETE FILE failed: {e}")
            tool_content = f"❌ ERROR: {e}"
        
        # Refresh workspace listing
        workspace_files = await _list_workspace_files(runtime)
        
        return Command(
            update={
                "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
                "workspace_files": workspace_files,
                "steps_taken": steps,
            }
        )
    
    except Exception as e:
        logger.error(f"❌ DELETE FILE exception: {e}", exc_info=True)
        return Command(
            update={
                "steps_taken": int(runtime.state.get("steps_taken", 0) or 0) + 1,
                "messages": [
                    ToolMessage(
                        content=f"❌ ERROR: failed to delete '{filename}': {str(e)}",
                        tool_call_id=runtime.tool_call_id
                    )
                ],
            }
        )


@tool(
    description="List all files in the agent workspace.",
    parse_docstring=False
)
async def agent_list_directory(
    runtime: ToolRuntime,
    subdir: Annotated[Optional[str], "Optional subdirectory to list"] = None
) -> Command:
    """List files and directories in the workspace."""
    try:
        steps = _inc_steps(runtime)
        
        # Build directory path
        bundle_id, direction_type, run_id = _get_workspace_components(runtime)
        
        if subdir:
            subdir_clean = sanitize_path_component(subdir)
            paths = await list_directory(bundle_id, direction_type, run_id, subdir_clean)
            location = f"workspace/{subdir_clean}"
        else:
            paths = await list_directory(bundle_id, direction_type, run_id)
            location = "workspace"
        
        logger.info(f"📂 LIST DIR [{steps}]: {location}")
        
        # Format output
        if not paths:
            tool_content = f"Directory is empty: {location}"
        else:
            files = [p for p in paths if p.is_file()]
            dirs = [p for p in paths if p.is_dir()]
            
            lines = [f"Contents of {location}:", ""]
            
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
        
        # Refresh workspace listing
        workspace_files = await _list_workspace_files(runtime)
        
        return Command(
            update={
                "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
                "workspace_files": workspace_files,
                "steps_taken": steps,
            }
        )
    
    except Exception as e:
        logger.error(f"❌ LIST DIR exception: {e}", exc_info=True)
        return Command(
            update={
                "steps_taken": int(runtime.state.get("steps_taken", 0) or 0) + 1,
                "messages": [
                    ToolMessage(
                        content=f"❌ ERROR: failed to list directory: {str(e)}",
                        tool_call_id=runtime.tool_call_id
                    )
                ],
            }
        )


@tool(
    description="Search for files matching a pattern in the workspace.",
    parse_docstring=False
)
async def agent_search_files(
    runtime: ToolRuntime,
    pattern: Annotated[str, "Glob pattern (e.g., '*.txt', '**/*.md')"],
    subdir: Annotated[Optional[str], "Optional subdirectory to search in"] = None
) -> Command:
    """Search for files matching a glob pattern."""
    try:
        steps = _inc_steps(runtime)
        
        # Build search path
        bundle_id, direction_type, run_id = _get_workspace_components(runtime)
        
        if subdir:
            subdir_clean = sanitize_path_component(subdir)
            paths = await search_files(pattern, bundle_id, direction_type, run_id, subdir_clean)
            location = f"workspace/{subdir_clean}"
        else:
            paths = await search_files(pattern, bundle_id, direction_type, run_id)
            location = "workspace"
        
        logger.info(f"🔍 SEARCH FILES [{steps}]: pattern='{pattern}' in {location}")
        
        # Format output
        if not paths:
            tool_content = f"No files found matching '{pattern}' in {location}"
        else:
            lines = [f"Found {len(paths)} file(s) matching '{pattern}' in {location}:", ""]
            for p in sorted(paths):
                lines.append(f"  📄 {p.relative_to(BASE_DIR)}")
            tool_content = "\n".join(lines)
        
        return Command(
            update={
                "messages": [ToolMessage(content=tool_content, tool_call_id=runtime.tool_call_id)],
                "steps_taken": steps,
            }
        )
    
    except Exception as e:
        logger.error(f"❌ SEARCH FILES exception: {e}", exc_info=True)
        return Command(
            update={
                "steps_taken": int(runtime.state.get("steps_taken", 0) or 0) + 1,
                "messages": [
                    ToolMessage(
                        content=f"❌ ERROR: failed to search files: {str(e)}",
                        tool_call_id=runtime.tool_call_id
                    )
                ],
            }
        )


@tool(
    description="List all research outputs produced so far by this agent.",
    parse_docstring=False
)
def agent_list_outputs(runtime: ToolRuntime) -> Command:
    """List all file outputs produced by this agent run."""
    try:
        file_refs = runtime.state.get("file_refs") or []
        direction_type = runtime.state.get("direction_type", "UNKNOWN")
        bundle_id = runtime.state.get("bundle_id", "unknown")
        run_id = runtime.state.get("run_id", "unknown")
        
        lines = [f"Outputs for Bundle={bundle_id} Run={run_id} Direction={direction_type}", ""]
        
        if not file_refs:
            lines.append("No file outputs recorded yet.")
        else:
            lines.append(f"File outputs ({len(file_refs)}):")
            for i, ref in enumerate(file_refs, start=1):
                file_path = getattr(ref, "file_path", None) or (
                    ref.get("file_path") if isinstance(ref, dict) else "unknown"
                )
                desc = getattr(ref, "description", None) or (
                    ref.get("description") if isinstance(ref, dict) else ""
                )
                entity_key = getattr(ref, "entity_key", None) or (
                    ref.get("entity_key") if isinstance(ref, dict) else ""
                )
                
                ek = f" ({entity_key})" if entity_key else ""
                if desc:
                    lines.append(f"{i}. {file_path}{ek}\n   - {desc}")
                else:
                    lines.append(f"{i}. {file_path}{ek}")
        
        # Include workspace snapshot
        ws = runtime.state.get("workspace_files") or []
        if ws:
            lines.append("")
            lines.append(f"Workspace snapshot ({len(ws)} items):")
            for item in ws[:30]:
                name = item.get("name", "unknown")
                is_dir = item.get("is_dir", False)
                size = item.get("size")
                
                if is_dir:
                    lines.append(f"- 📁 {name}/")
                else:
                    sz = f" ({size} bytes)" if isinstance(size, int) else ""
                    lines.append(f"- 📄 {name}{sz}")
            
            if len(ws) > 30:
                lines.append(f"...and {len(ws) - 30} more.")
        
        content = "\n".join(lines)
        
        return Command(
            update={
                "messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)],
            }
        )
    
    except Exception as e:
        logger.error(f"❌ LIST OUTPUTS exception: {e}", exc_info=True)
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"❌ ERROR: failed to list outputs: {str(e)}",
                        tool_call_id=runtime.tool_call_id
                    )
                ],
            }
        )
