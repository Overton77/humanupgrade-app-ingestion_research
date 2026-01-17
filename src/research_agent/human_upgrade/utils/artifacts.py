from datetime import datetime 
import os
import uuid
import json
import aiofiles
from typing import Any

from research_agent.human_upgrade.logger import logger



ENTITY_INTEL_OUTPUT_DIR = "newest_research_outputs" 



def get_current_date_string() -> str:
    """Returns a clean, human-readable date string for prompts."""
    return datetime.now().strftime("%B %d, %Y") 


# ============================================================================
# FILE SAVING UTILITIES
# ============================================================================

def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by replacing invalid Windows characters.
    
    Windows doesn't allow: < > : " / \ | ? *
    Also replace other potentially problematic characters like = and &
    """
    # Replace invalid Windows filename characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Replace other problematic characters
    filename = filename.replace('=', '_eq_')
    filename = filename.replace('&', '_and_')
    
    # Remove leading/trailing dots and spaces (Windows doesn't allow these)
    filename = filename.strip('. ')
    
    # Remove multiple consecutive underscores
    while '__' in filename:
        filename = filename.replace('__', '_')
    
    return filename


async def ensure_directory_exists(path: str) -> None:
    """Ensure a directory exists, creating it if necessary."""
    dir_path = os.path.dirname(path)
    if dir_path:
        try:
            await aiofiles.os.makedirs(dir_path, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create directory {dir_path}: {e}")


async def save_json_artifact(
    data: Any,
    direction_id: str,
    artifact_type: str,
    suffix: str = "",
) -> str:
    """Save a JSON artifact to disk with structured naming."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = str(uuid.uuid4())[:8]
    
    filename = f"{artifact_type}_{timestamp}_{short_uuid}"
    if suffix:
        filename += f"_{sanitize_filename(suffix)}"
    filename = sanitize_filename(filename) + ".json"
    
    filepath = os.path.join(ENTITY_INTEL_OUTPUT_DIR, direction_id, filename)
    
    await ensure_directory_exists(filepath)
    
    # Convert to JSON-serializable format
    if hasattr(data, "model_dump"):
        json_data = data.model_dump()
    elif hasattr(data, "dict"):
        json_data = data.dict()
    elif isinstance(data, dict):
        json_data = data
    else:
        json_data = {"content": str(data)}
    
    try:
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(json.dumps(json_data, indent=2, default=str, ensure_ascii=False))
        logger.debug(f"Saved artifact: {filepath}")
    except Exception as e:
        logger.error(f"Failed to save artifact {filepath}: {e}")
        return ""
    
    return filepath


async def save_text_artifact(
    content: str,
    direction_id: str,
    artifact_type: str,
    suffix: str = "",
) -> str:
    """Save a text artifact to disk."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = str(uuid.uuid4())[:8]
    
    filename = f"{artifact_type}_{timestamp}_{short_uuid}"
    if suffix:
        filename += f"_{sanitize_filename(suffix)}"
    filename = sanitize_filename(filename) + ".txt"
    
    filepath = os.path.join(ENTITY_INTEL_OUTPUT_DIR, direction_id, filename)
    
    await ensure_directory_exists(filepath)
    
    try:
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)
        logger.debug(f"Saved text artifact: {filepath}")
    except Exception as e:
        logger.error(f"Failed to save text artifact {filepath}: {e}")
        return ""
    
    return filepath

