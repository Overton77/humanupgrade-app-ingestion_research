"""
Windows-Safe File System Functions for Agent Workspace

This module provides bulletproof file operations that:
1. Always sanitize paths to be Windows-safe
2. Create isolated workspaces per agent
3. Handle all edge cases gracefully
4. Never allow invalid characters in paths

Base directory: <project_root>/agent_files_current/
Workspace structure: <base>/<bundle_id>/<direction_type>/<run_id>/<files>
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional
import aiofiles


# ============================================================
# CONFIGURATION
# ============================================================

# Base directory for all agent files (relative to project root)
BASE_DIR: Path = Path.cwd() / "agent_instances_current"

# Windows-invalid characters that must be replaced
# < > : " | ? * are invalid in Windows filenames
# / \ are path separators (handled separately)
INVALID_CHARS_PATTERN = re.compile(r'[<>:"|?*]')

# Ensure base directory exists
BASE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# PATH SANITIZATION
# ============================================================

def sanitize_path_component(component: str) -> str:
    """
    Sanitize a single path component (file or directory name).
    
    Replaces ALL Windows-invalid characters with underscores.
    This is called on EVERY path component before use.
    
    Args:
        component: A file or directory name (not a full path)
        
    Returns:
        Sanitized component safe for Windows filesystems
        
    Example:
        >>> sanitize_path_component("bundle:GUEST")
        "bundle_GUEST"
        >>> sanitize_path_component('file<name>.txt')
        "file_name_.txt"
    """
    if not component:
        return ""
    
    # Replace invalid characters with underscores
    sanitized = INVALID_CHARS_PATTERN.sub('_', component)
    
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip().strip('.')
    
    # Ensure it's not empty after sanitization
    if not sanitized:
        sanitized = "unnamed"
    
    return sanitized


def build_workspace_path(*components: str) -> Path:
    """
    Build a path from components, sanitizing each one.
    
    This is the ONLY function that should be used to construct
    paths within the agent workspace. It guarantees Windows-safety.
    
    Args:
        *components: Path components (will be joined with /)
        
    Returns:
        Path object relative to BASE_DIR, fully sanitized
        
    Example:
        >>> build_workspace_path("bundle:id", "GUEST", "run:1", "file.txt")
        Path("bundle_id/GUEST/run_1/file.txt")
    """
    # Sanitize each component
    sanitized_components = [sanitize_path_component(c) for c in components if c]
    
    # Build path relative to BASE_DIR
    if not sanitized_components:
        return BASE_DIR
    
    # Join components
    relative_path = Path(*sanitized_components)
    
    return relative_path


def resolve_workspace_path(*components: str) -> Path:
    """
    Resolve a full absolute path within the workspace.
    
    This builds the path, sanitizes it, and returns the absolute path.
    Also validates that the path is within BASE_DIR (no traversal attacks).
    
    Args:
        *components: Path components to join
        
    Returns:
        Absolute Path object, guaranteed to be within BASE_DIR
        
    Raises:
        ValueError: If the resolved path would be outside BASE_DIR
    """
    relative_path = build_workspace_path(*components)
    absolute_path = (BASE_DIR / relative_path).resolve()
    
    # Security: prevent path traversal attacks
    try:
        absolute_path.relative_to(BASE_DIR.resolve())
    except ValueError:
        raise ValueError(
            f"Security error: Path '{absolute_path}' is outside "
            f"the allowed workspace directory '{BASE_DIR}'"
        )
    
    return absolute_path


# ============================================================
# FILE OPERATIONS
# ============================================================

async def write_file(*path_components: str, content: str) -> Path:
    """
    Write content to a file, creating directories as needed.
    
    All path components are sanitized automatically.
    
    Args:
        *path_components: Path components (will be joined and sanitized)
        content: Text content to write
        
    Returns:
        Absolute path of the written file
        
    Example:
        >>> await write_file("bundle_id", "GUEST", "run_1", "report.txt", content="Hello")
        Path("/abs/path/to/agent_files_current/bundle_id/GUEST/run_1/report.txt")
    """
    if not content or content is None:
        raise ValueError("Content cannot be empty or None")
    
    if not path_components:
        raise ValueError("Must provide at least one path component")
    
    filepath = resolve_workspace_path(*path_components)
    
    # Create parent directories
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Write file
    async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
        await f.write(content)
    
    return filepath


async def read_file(*path_components: str) -> str:
    """
    Read content from a file.
    
    All path components are sanitized automatically.
    
    Args:
        *path_components: Path components (will be joined and sanitized)
        
    Returns:
        File content as string
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not path_components:
        raise ValueError("Must provide at least one path component")
    
    filepath = resolve_workspace_path(*path_components)
    
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
        return await f.read()


async def edit_file(*path_components: str, find_text: str, replace_text: str, count: int = -1) -> Path:
    """
    Edit a file by finding and replacing text.
    
    Args:
        *path_components: Path components (will be joined and sanitized)
        find_text: Text to find
        replace_text: Text to replace with
        count: Number of replacements (-1 = all)
        
    Returns:
        Absolute path of the edited file
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not path_components:
        raise ValueError("Must provide at least one path component")
    
    # Read current content
    content = await read_file(*path_components)
    
    # Replace text
    new_content = content.replace(find_text, replace_text, count)
    
    # Write back
    filepath = await write_file(*path_components, content=new_content)
    
    return filepath


async def delete_file(*path_components: str) -> bool:
    """
    Delete a file.
    
    Args:
        *path_components: Path components (will be joined and sanitized)
        
    Returns:
        True if file was deleted, False if it didn't exist
    """
    if not path_components:
        raise ValueError("Must provide at least one path component")
    
    filepath = resolve_workspace_path(*path_components)
    
    if filepath.exists() and filepath.is_file():
        filepath.unlink()
        return True
    
    return False


async def list_directory(*path_components: str) -> List[Path]:
    """
    List all files and directories in a directory.
    
    Args:
        *path_components: Path components (empty = BASE_DIR)
        
    Returns:
        List of Path objects
        
    Raises:
        NotADirectoryError: If path is not a directory
    """
    dirpath = resolve_workspace_path(*path_components) if path_components else BASE_DIR
    
    if not dirpath.exists():
        return []
    
    if not dirpath.is_dir():
        raise NotADirectoryError(f"Not a directory: {dirpath}")
    
    return list(dirpath.iterdir())


async def search_files(pattern: str, *path_components: str) -> List[Path]:
    """
    Search for files matching a glob pattern.
    
    Args:
        pattern: Glob pattern (e.g., "*.txt", "**/*.md")
        *path_components: Directory components to search in (empty = BASE_DIR)
        
    Returns:
        List of matching Path objects
    """
    dirpath = resolve_workspace_path(*path_components) if path_components else BASE_DIR
    
    if not dirpath.exists() or not dirpath.is_dir():
        return []
    
    return list(dirpath.rglob(pattern))


# ============================================================
# WORKSPACE INFO
# ============================================================

def get_workspace_info(*path_components: str) -> dict:
    """
    Get information about a workspace path.
    
    Args:
        *path_components: Path components
        
    Returns:
        Dict with path info (exists, is_file, is_dir, size, etc.)
    """
    filepath = resolve_workspace_path(*path_components)
    
    info = {
        "path": str(filepath),
        "relative_path": str(filepath.relative_to(BASE_DIR)),
        "exists": filepath.exists(),
        "is_file": filepath.is_file() if filepath.exists() else False,
        "is_dir": filepath.is_dir() if filepath.exists() else False,
    }
    
    if filepath.is_file():
        info["size"] = filepath.stat().st_size
    
    return info


