# common/artifacts.py

import json
import os
import uuid
from datetime import datetime
from typing import Any, Union, Mapping

import aiofiles
import aiofiles.os
import logging

PathLike = Union[str, os.PathLike]

logger = logging.getLogger(__name__)


async def ensure_directory_exists(path: PathLike) -> None:
    """
    Ensure a directory exists, creating it if necessary.

    `path` can be either a directory path or a full file path.
    If it's a file path, we use its parent directory.
    """
    # Accept both dir paths and file paths
    path_str = os.fspath(path)
    dir_path = path_str if os.path.isdir(path_str) else os.path.dirname(path_str)

    if not dir_path:
        return

    try:
        await aiofiles.os.makedirs(dir_path, exist_ok=True)
    except Exception as e:
        logger.warning(f"Could not create directory {dir_path}: {e}")


def _build_artifact_filename(
    artifact_type: str,
    suffix: str = "",
    extension: str = "json",
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = str(uuid.uuid4())[:8]

    filename = f"{artifact_type}_{timestamp}_{short_uuid}"
    if suffix:
        filename += f"_{suffix}"
    return f"{filename}.{extension}"


def _normalize_json_data(data: Any) -> Mapping[str, Any]:
    """
    Convert various object types into JSON-serializable dicts.
    """
    if hasattr(data, "model_dump"):  # Pydantic v2
        return data.model_dump()
    if hasattr(data, "dict"):  # Pydantic v1 or similar
        return data.dict()  # type: ignore[no-any-return]
    if isinstance(data, dict):
        return data
    # Fallback: store string representation
    return {"content": str(data)}


async def save_json_artifact(
    data: Any,
    base_dir: PathLike,
    direction_id: str,
    artifact_type: str,
    suffix: str = "",
) -> str:
    """
    Save a JSON artifact to disk with structured naming.

    Args:
        data: Data to serialize (dict, Pydantic model, or JSON-serializable object)
        base_dir: Root directory for this kind of artifact (e.g., 'entity_intel_outputs')
        direction_id: The research direction ID
        artifact_type: Type of artifact (e.g., 'tavily_search', 'llm_response')
        suffix: Optional suffix for additional context

    Returns:
        The file path where the artifact was saved, or "" on failure.
    """
    filename = _build_artifact_filename(
        artifact_type=artifact_type,
        suffix=suffix,
        extension="json",
    )

    filepath = os.path.join(os.fspath(base_dir), direction_id, filename)

    await ensure_directory_exists(filepath)

    json_data = _normalize_json_data(data)

    try:
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(
                json.dumps(
                    json_data,
                    indent=2,
                    default=str,
                    ensure_ascii=False,
                )
            )
        logger.debug(f"Saved JSON artifact: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save JSON artifact {filepath}: {e}")
        return ""


async def save_text_artifact(
    content: str,
    base_dir: PathLike,
    direction_id: str,
    artifact_type: str,
    suffix: str = "",
) -> str:
    """
    Save a text artifact to disk.

    Args:
        content: Text content to save
        base_dir: Root directory for this kind of artifact (e.g., 'evidence_research_outputs')
        direction_id: The research direction ID
        artifact_type: Type of artifact (e.g., 'full_transcript', 'notes')
        suffix: Optional suffix

    Returns:
        The file path where the artifact was saved, or "" on failure.
    """
    filename = _build_artifact_filename(
        artifact_type=artifact_type,
        suffix=suffix,
        extension="txt",
    )

    filepath = os.path.join(os.fspath(base_dir), direction_id, filename)

    await ensure_directory_exists(filepath)

    try:
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)
        logger.debug(f"Saved text artifact: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save text artifact {filepath}: {e}")
        return ""
