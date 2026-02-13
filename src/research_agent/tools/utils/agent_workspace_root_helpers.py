from __future__ import annotations

from pathlib import Path
from typing import List
from research_agent.agent_tools.file_system_functions import (
    BASE_DIR,
    sanitize_path_component,
    resolve_workspace_path,   
)
from research_agent.agent_tools.mongo_file_system_functions import (
    read_file_from_mongo_path,
)
from research_agent.human_upgrade.structured_outputs.file_outputs import ( 
    FileReference 
)  
import re 


def _workspace_root_components(workspace_root: str) -> List[str]:
    """
    Convert a workspace_root like:
      "mission123/S1/S1.2_people/PersonBioAndAffiliationsAgent_inst123"
    into sanitized path components.
    
    Handles both relative and absolute paths (defensive programming).
    """
    if not workspace_root or not isinstance(workspace_root, str):
        return ["_missing_workspace"]
    
    root = workspace_root.strip().replace("\\", "/").strip("/")
    if not root:
        return ["_missing_workspace"]
    
    # If absolute path (Windows: C:/ or Unix: /), try to extract relative part
    if root.startswith("/") or (len(root) > 1 and root[1] == ":"):
        try:
            abs_path = Path(root)
            try:
                # Try to get relative to BASE_DIR
                rel_path = abs_path.relative_to(BASE_DIR.resolve())
                root = str(rel_path).replace("\\", "/")
            except ValueError:
                # Path not under BASE_DIR, find BASE_DIR name and take after it
                parts = [p for p in root.split("/") if p]
                base_name = BASE_DIR.name
                if base_name in parts:
                    idx = parts.index(base_name)
                    root = "/".join(parts[idx + 1:]) if idx + 1 < len(parts) else ""
                else:
                    # Fallback: take last few components
                    root = "/".join(parts[-4:]) if len(parts) >= 4 else "/".join(parts)
        except Exception:
            return ["_missing_workspace"]
    
    parts = [p for p in root.split("/") if p]
    sanitized = [sanitize_path_component(p) for p in parts if p]
    return sanitized if sanitized else ["_missing_workspace"]


def _build_scoped_path(workspace_root: str, filename: str) -> Path:
    """
    Build absolute path under BASE_DIR using workspace_root + filename.
    Filename may include subdirs; everything sanitized.
    """
    root_parts = _workspace_root_components(workspace_root)

    fn = (filename or "").strip().replace("\\", "/").lstrip("/")
    if not fn:
        raise ValueError("filename cannot be empty")

    fn_parts = [sanitize_path_component(p) for p in fn.split("/") if p]
    if not fn_parts:
        raise ValueError("filename resolves to empty after sanitization")

    # Use existing security resolver (prevents traversal)
    return resolve_workspace_path(*root_parts, *fn_parts)


def _relative_to_base(p: Path) -> str:
    return str(p.relative_to(BASE_DIR)).replace("\\", "/")


async def _concat_agent_files(file_refs: List[FileReference]) -> str:
    """
    Reads every file referenced in file_refs and concatenates them into one block
    with separators, including file metadata (description, agent_type, source).
    
    Uses read_file_from_mongo_path since file_path is stored relative to BASE_DIR.
    The file_path in FileReference is a workspace-relative path (relative to BASE_DIR),
    which read_file_from_mongo_path handles correctly by splitting and sanitizing.
    """
    parts: List[str] = []
    for i, ref in enumerate(file_refs, start=1):
        file_path = ref.file_path
        agent_type = getattr(ref, "agent_type", "UnknownAgent")
        description = getattr(ref, "description", "")
        source = getattr(ref, "source", "")
        
        parts.append(f"\n\n===== FILE {i}: {file_path} =====")
        parts.append(f"AGENT_TYPE: {agent_type}")
        if description:
            parts.append(f"DESCRIPTION: {description}")
        if source:
            parts.append(f"SOURCE: {source}")
        parts.append("---")
        
        try:
            # file_path is stored as a relative path string (e.g., "mission123/S1/.../file.txt")
            # read_file_from_mongo_path handles splitting and sanitizing this correctly
            content = await read_file_from_mongo_path(file_path)
            parts.append(content)
        except Exception as e:
            parts.append(f"[ERROR READING FILE: {e}]")
    
    return "\n".join(parts).strip()



def sanitize(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s)
    return s[:120] if len(s) > 120 else s

def workspace_for(*parts: str) -> Path:
    """
    Create workspace directory and return absolute Path.
    Use this when you need to create the directory or work with Path objects.
    """
    safe = [sanitize(p) for p in parts if p]
    p = BASE_DIR.joinpath(*safe)
    p.mkdir(parents=True, exist_ok=True)
    return p

def workspace_root_for(*parts: str) -> str:
    """
    Returns workspace root as relative path string (relative to BASE_DIR).
    Use this when you need a string for state.workspace_root.
    
    This ensures workspace_root is always relative, preventing path duplication
    when used in file_system_tools.
    """
    safe = [sanitize(p) for p in parts if p]
    # Also ensure the directory exists
    p = BASE_DIR.joinpath(*safe)
    p.mkdir(parents=True, exist_ok=True)
    # Return relative path string
    return "/".join(safe)
