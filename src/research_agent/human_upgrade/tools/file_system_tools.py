from langchain.tools import tool, ToolRuntime  
from typing import Optional  
from pathlib import Path  
from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference
from research_agent.human_upgrade.tools.utils.runtime_helpers import increment_steps 
from langgraph.types import Command
from langchain.messages import ToolMessage
from research_agent.human_upgrade.logger import logger  
from research_agent.agent_tools.filesystem_tools import (
    write_file as fs_write_file,
    read_file as fs_read_file,
    edit_file as fs_edit_file,
    delete_file as fs_delete_file,
    search_directory as fs_search_directory,
    search_files as fs_search_files,
)

@tool(
    description="Write content to a file in the agent workspace.",
    parse_docstring=False,
)
async def agent_write_file(
    runtime: ToolRuntime,
    filename: str,
    content: str,
    description: str = "",
    bundle_id: str = "",
    entity_key: str = "",
) -> str:
    """
    Write `content` to `filename` in the agent workspace and record a file reference.

    Args:
      filename:
        Path to the file (relative to the agent workspace root).
      content:
        The full contents to write to the file (will overwrite existing contents).
      description:
        Optional human-readable description of what the file contains.
      bundle_id:
        Optional bundle identifier to associate this file with a broader run/output group.
      entity_key:
        Optional entity identifier to associate this file with a specific researched entity.

    Returns:
      A short status message describing the file write result (success or error) that will be
      visible to the model in the tool result.
    """
  
    steps_taken = (runtime.state.get("steps_taken", 0) or 0) + 1
    runtime.state["steps_taken"] = steps_taken

    desc_text = f" - {description}" if description else ""
    logger.info(f"📝 WRITE FILE [{steps_taken}]: {filename}{desc_text}")

    # 2) Write the file
    try:
        filepath = await fs_write_file(filename, content)
        logger.info(f"✅ WRITE FILE complete: {filepath}")
        result_message = f"File written successfully: {filepath}"
        status = "success"
    except Exception as e:
        logger.error(f"❌ WRITE FILE failed: {e}")
        result_message = f"Error writing file: {e}"
        status = "error"

    # 3) Append FileReference into runtime.state["file_refs"]
    file_output = FileReference(
        file_path=filename,
        description=description,
        bundle_id=bundle_id,
        entity_key=entity_key,
    )

    file_refs = runtime.state.get("file_refs")
    if file_refs is None:
        runtime.state["file_refs"] = [file_output]
    else:
        # if you accidentally ever store a non-list, fail loudly instead of silently corrupting state
        if not isinstance(file_refs, list):
            raise TypeError(f'runtime.state["file_refs"] must be a list, got {type(file_refs)}')
        file_refs.append(file_output)

    # 4) Return a string; ToolNode/agent will wrap it in a ToolMessage with the correct tool_call_id
    if status == "success":
        if description:
            return f"{result_message} (description: {description})"
        return result_message
    else:
        # Keep it model-visible that it failed
        return result_message

@tool(
    description="Read content from a file in the agent workspace.",
    parse_docstring=False,
)
async def agent_read_file(
    runtime: ToolRuntime,
    filename: str,
) -> str:
    """
    Read content from a file.
    
    Args:
        filename: Path to the file (relative to agent_files directory)
    
    Returns:
        File content as a string
    """
    steps_taken = runtime.state.get("steps_taken", 0) + 1
    runtime.state["steps_taken"] = steps_taken
    
    logger.info(f"📖 READ FILE [{steps_taken}]: {filename}")
    
    try:
        content = await fs_read_file(filename)
        logger.info(f"✅ READ FILE complete: {filename}")
        return content
    except FileNotFoundError as e:
        logger.error(f"❌ READ FILE failed: {e}")
        return f"Error: {e}"
    except Exception as e:
        logger.error(f"❌ READ FILE failed: {e}")
        return f"Error: {e}"


@tool(
    description="Edit a file by finding and replacing text.",
    parse_docstring=False,
)
async def agent_edit_file(
    runtime: ToolRuntime,
    filename: str,
    find_text: str,
    replace_text: str,
    count: int = -1,
) -> str:
    """
    Edit a file by replacing text.
    
    Args:
        filename: Path to the file (relative to agent_files directory)
        find_text: Text to find
        replace_text: Text to replace with
        count: Number of replacements (-1 for all)
    
    Returns:
        Confirmation message
    """
    steps_taken = runtime.state.get("steps_taken", 0) + 1
    runtime.state["steps_taken"] = steps_taken
    
    logger.info(f"✏️  EDIT FILE [{steps_taken}]: {filename}")
    
    try:
        filepath = await fs_edit_file(filename, find_text, replace_text, count)
        logger.info(f"✅ EDIT FILE complete: {filepath}")
        return f"File edited successfully: {filepath}"
    except FileNotFoundError as e:
        logger.error(f"❌ EDIT FILE failed: {e}")
        return f"Error: {e}"


@tool(
    description="Delete a file from the agent workspace.",
    parse_docstring=False,
)
async def agent_delete_file(
    runtime: ToolRuntime,
    filename: str,
) -> str:
    """
    Delete a file.
    
    Args:
        filename: Path to the file (relative to agent_files directory)
    
    Returns:
        Confirmation message
    """
    steps_taken = runtime.state.get("steps_taken", 0) + 1
    runtime.state["steps_taken"] = steps_taken
    
    logger.info(f"🗑️  DELETE FILE [{steps_taken}]: {filename}")
    
    deleted = await fs_delete_file(filename)
    
    if deleted:
        logger.info(f"✅ DELETE FILE complete: {filename}")
        return f"File deleted successfully: {filename}"
    else:
        logger.warning(f"⚠️  DELETE FILE: File not found: {filename}")
        return f"File not found: {filename}"


@tool(
    description="List all files and directories in a directory within the agent workspace.",
    parse_docstring=False,
)
async def agent_list_directory(
    runtime: ToolRuntime,
    subdir: Optional[str] = None,
) -> str:
    """
    List contents of a directory.
    
    Args:
        subdir: Subdirectory to list (relative to agent_files, or None for root)
    
    Returns:
        Formatted list of files and directories
    """
    steps_taken = runtime.state.get("steps_taken", 0) + 1
    runtime.state["steps_taken"] = steps_taken
    
    logger.info(f"📂 LIST DIR [{steps_taken}]: {subdir or 'root'}")
    
    try:
        paths = await fs_search_directory(subdir)
        
        if not paths:
            return f"Directory is empty: {subdir or 'agent_files'}"
        
        files = [p for p in paths if p.is_file()]
        dirs = [p for p in paths if p.is_dir()]
        
        lines = [f"Contents of {subdir or 'agent_files'}:", ""]
        
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
        
        logger.info(f"✅ LIST DIR complete: {len(paths)} items")
        return "\n".join(lines)
    except (FileNotFoundError, NotADirectoryError) as e:
        logger.error(f"❌ LIST DIR failed: {e}")
        return f"Error: {e}"


@tool(
    description="Search for files matching a pattern in the agent workspace.",
    parse_docstring=False,
)
async def agent_search_files(
    runtime: ToolRuntime,
    pattern: str,
    subdir: Optional[str] = None,
) -> str:
    """
    Search for files using a glob pattern.
    
    Args:
        pattern: Glob pattern (e.g., "*.txt", "**/*.json")
        subdir: Subdirectory to search in (relative to agent_files, or None for root)
    
    Returns:
        List of matching file paths
    """
    steps_taken = runtime.state.get("steps_taken", 0) + 1
    runtime.state["steps_taken"] = steps_taken
    
    logger.info(f"🔍 SEARCH FILES [{steps_taken}]: pattern='{pattern}' in {subdir or 'root'}")
    
    paths = await fs_search_files(pattern, subdir)
    
    if not paths:
        return f"No files found matching pattern: {pattern}"
    
    lines = [f"Found {len(paths)} file(s) matching '{pattern}':", ""]
    for p in sorted(paths):
        size = p.stat().st_size
        lines.append(f"  📄 {p.relative_to(Path.cwd() / 'agent_files')} ({size} bytes)")
    
    logger.info(f"✅ SEARCH FILES complete: {len(paths)} matches")
    return "\n".join(lines) 


