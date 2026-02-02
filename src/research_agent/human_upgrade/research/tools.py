from __future__ import annotations
from typing import Any, Dict
from langchain_core.tools import tool

@tool
def placeholder_web_search(query: str) -> str:
    """Placeholder web search tool."""
    return f"[placeholder_web_search] query={query}"

@tool
def placeholder_file_write(path: str, content: str) -> str:
    """Placeholder file write tool. Replace with your scoped FS tools."""
    # You will replace this with your agent-scoped file system functions/tools.
    return f"[placeholder_file_write] wrote {len(content)} chars to {path}"

TOOL_REGISTRY = {
    "web_search": placeholder_web_search,
    "file_write": placeholder_file_write,
}
