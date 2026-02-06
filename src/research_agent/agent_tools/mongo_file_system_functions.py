from __future__ import annotations
from pathlib import Path
import aiofiles
from research_agent.agent_tools.file_system_functions import (
    BASE_DIR,
    sanitize_path_component,
)


### MONGO FILE SYSTEM FUNCTIONS ### 


def _split_mongo_relpath(mongo_relpath: str) -> list[str]:
    """
    Split a Mongo-stored relative path into components, handling:
    - Windows backslashes
    - forward slashes
    - accidental leading/trailing separators
    """
    if not mongo_relpath or not mongo_relpath.strip():
        raise ValueError("mongo_relpath cannot be empty")

    # Normalize separators to '/'
    normalized = mongo_relpath.strip().replace("\\", "/")

    # Remove leading "./" and leading/trailing "/"
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.strip("/")

    parts = [p for p in normalized.split("/") if p and p != "."]
    return parts


def resolve_mongo_workspace_path(mongo_relpath: str) -> Path:
    """
    Resolve a mongo file_path that is stored RELATIVE to BASE_DIR.

    Example mongo_relpath:
      "ilan_sobel_bioharvest\\COMPOUND\\ilan_sobel_bioharvest_COMPOUND\\checkpoints\\final_report.txt"

    Returns:
      Absolute Path within BASE_DIR

    Raises:
      ValueError if traversal outside BASE_DIR is attempted
    """
    parts = _split_mongo_relpath(mongo_relpath)

    # Sanitize each component as a Windows-safe filename/dir name
    safe_parts = [sanitize_path_component(p) for p in parts]

    # Build absolute path
    abs_path = (BASE_DIR / Path(*safe_parts)).resolve()

    # Prevent traversal outside BASE_DIR
    try:
        abs_path.relative_to(BASE_DIR.resolve())
    except ValueError:
        raise ValueError(
            f"Security error: Path '{abs_path}' is outside BASE_DIR '{BASE_DIR}'"
        )

    return abs_path


async def read_file_from_mongo_path(mongo_relpath: str) -> str:
    """
    Read a file whose path is stored in Mongo as a relative path under BASE_DIR.

    Usage:
      txt = await read_file_from_mongo_path(
          r"ilan_sobel_bioharvest\COMPOUND\ilan_sobel_bioharvest_COMPOUND\checkpoints\final_report.txt"
      )
    """
    filepath = resolve_mongo_workspace_path(mongo_relpath)

    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
        return await f.read()