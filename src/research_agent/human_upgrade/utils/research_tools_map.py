"""
Research Tools Map

This module provides a comprehensive mapping of tool names to their actual tool instances/functions.
Tool names follow the format: provider.tool_name (e.g., "search.tavily", "fs.write")

All tools are imported from their respective modules and mapped here for easy lookup.
"""

from typing import Dict, Any, Optional

# Import Tavily tools (research variants)
from research_agent.human_upgrade.tools.web_search_tools import (
    tavily_search_research,
    tavily_extract_research,
    tavily_map_research,
    tavily_crawl_general,
    wiki_search_tool,
)

# Import file system tools
from research_agent.human_upgrade.tools.file_system_tools import (
    agent_write_file,
    agent_read_file,
    agent_edit_file,
    agent_delete_file,
    agent_list_directory,
    agent_search_files,
    agent_list_outputs,
)

# Import think tool
from research_agent.human_upgrade.tools.think_tool import think_tool

# Import playwright tool
from research_agent.human_upgrade.tools.playwright_agent_tool import playwright_mcp_specs

# Import research integration tools
from research_agent.human_upgrade.tools.research_integration_tools import (
    exa_search,
    exa_find_similar,
    serper_search,
    duckduckgo_search,
    duckduckgo_search_results,
    pubmed,
    semantic_scholar,
    yahoo_finance,
    google_finance,
    google_trends,
)

# Import PubMed tools (if available)
# These are advanced tools that provide search + summarization + citations
try:
    from research_agent.medical_db_tools.pub_med_tools import (
        pubmed_literature_search_tool,  # PubMed search with abstracts + LLM summarization
        pmc_fulltext_literature_tool,   # PMC full-text search + LLM summarization
    )
    PUBMED_TOOLS_AVAILABLE = True
except ImportError:
    PUBMED_TOOLS_AVAILABLE = False
    pubmed_literature_search_tool = None
    pmc_fulltext_literature_tool = None

# Note: context.summarize is a middleware feature, not a tool function
# doc.pdf_text, doc.pdf_screenshot_ocr, and registry.clinicaltrials are not yet implemented
# These are left as None for now and can be added when implemented

RESEARCH_TOOLS_MAP: Dict[str, Optional[Any]] = {
    # ============================================================================
    # Tavily Tools (Research Variants)
    # ============================================================================
    "tavily.search": tavily_search_research,
    "search.tavily": tavily_search_research,  # Alias for compatibility
    "tavily.extract": tavily_extract_research,
    "extract.tavily": tavily_extract_research,  # Alias for compatibility
    "tavily.map": tavily_map_research,
    "tavily.crawl": tavily_crawl_general,
    
    # ============================================================================
    # Wikipedia
    # ============================================================================
    "wiki.search": wiki_search_tool,
    "search.wiki": wiki_search_tool,  # Alias for compatibility
    
    # ============================================================================
    # Exa Search Tools
    # ============================================================================
    "exa.search": exa_search,
    "search.exa": exa_search,  # Alias for compatibility
    "exa.find_similar": exa_find_similar,
    
    # ============================================================================
    # Google Serper
    # ============================================================================
    "serper.search": serper_search,
    "search.serper": serper_search,  # Alias for compatibility
    
    # ============================================================================
    # DuckDuckGo Tools
    # ============================================================================
    "duckduckgo.search": duckduckgo_search,
    "duckduckgo.search_results": duckduckgo_search_results,
    
    # ============================================================================
    # Academic/Scholarly Tools
    # ============================================================================
    # Basic PubMed search (from langchain_community)
    "pubmed.search": pubmed,
    "pubmed.basic": pubmed,  # Alias for basic PubMed search
    
    # Advanced PubMed literature search with summarization (recommended)
    # Searches PubMed, fetches abstracts, and returns summarized citation-rich report
    "pubmed.literature_search": pubmed_literature_search_tool if PUBMED_TOOLS_AVAILABLE else None,
    "scholar.pubmed": pubmed_literature_search_tool if PUBMED_TOOLS_AVAILABLE else pubmed,  # Default PubMed tool for agents
    
    # PubMed Central (PMC) full-text search with summarization
    # Searches PMC for full-text articles and returns summarized report
    "pmc.fulltext": pmc_fulltext_literature_tool if PUBMED_TOOLS_AVAILABLE else None,
    "pubmed.fulltext": pmc_fulltext_literature_tool if PUBMED_TOOLS_AVAILABLE else None,  # Alias
    "scholar.pmc": pmc_fulltext_literature_tool if PUBMED_TOOLS_AVAILABLE else None,  # Alias
    
    # Semantic Scholar
    "semantic_scholar.search": semantic_scholar,
    "scholar.semantic_scholar": semantic_scholar,  # Alias for compatibility
    
    # ============================================================================
    # Finance Tools
    # ============================================================================
    "yahoo.finance": yahoo_finance,
    "google.finance": google_finance,
    "google.trends": google_trends,
    
    # ============================================================================
    # Browser/Automation Tools
    # ============================================================================
    "playwright.specs": playwright_mcp_specs,
    "browser.playwright": playwright_mcp_specs,  # Alias for compatibility
    
    # ============================================================================
    # File System Tools
    # ============================================================================
    "fs.write": agent_write_file,
    "fs.read": agent_read_file,
    "fs.edit": agent_edit_file,
    "fs.delete": agent_delete_file,
    "fs.list": agent_list_directory,
    "fs.search": agent_search_files,
    "fs.list_outputs": agent_list_outputs,
    
    # ============================================================================
    # Planning/Thinking Tools
    # ============================================================================
    "think": think_tool,
    "plan": think_tool,  # Alias for compatibility
    
    # ============================================================================
    # Context/Memory Tools
    # ============================================================================
    # Note: context.summarize is a middleware, not a tool function
    "context.summarize": None,  # Placeholder - handled by middleware
    
    # ============================================================================
    # Document/PDF Tools (Not Yet Implemented)
    # ============================================================================
    "doc.pdf_text": None,  # TODO: Implement PDF text extraction
    "doc.pdf_screenshot_ocr": None,  # TODO: Implement PDF screenshot OCR
    
    # ============================================================================
    # Registry Tools (Not Yet Implemented)
    # ============================================================================
    "registry.clinicaltrials": None,  # TODO: Implement ClinicalTrials.gov tool
    
    # ============================================================================
    # Other Tools (Not Yet Implemented)
    # ============================================================================
    "fetch.http": None,  # TODO: Implement HTTP fetch tool
    "extract.readability": None,  # TODO: Implement Readability extraction
    "media.youtube_transcript": None,  # TODO: Implement YouTube transcript tool
    "reviews.web": None,  # TODO: Implement web reviews tool
}


def get_tool(tool_name: str) -> Optional[Any]:
    """
    Get a tool by its name.
    
    Args:
        tool_name: The tool name (e.g., "search.tavily", "fs.write")
        
    Returns:
        The tool function/instance, or None if not found/not implemented
    """
    return RESEARCH_TOOLS_MAP.get(tool_name)


def get_available_tools() -> Dict[str, bool]:
    """
    Returns a dictionary indicating which tools are available (not None).
    
    Returns:
        Dictionary with tool names as keys and availability (bool) as values
    """
    return {
        tool_name: tool is not None
        for tool_name, tool in RESEARCH_TOOLS_MAP.items()
    }


def list_implemented_tools() -> list[str]:
    """
    Returns a list of tool names that are actually implemented (not None).
    
    Returns:
        List of implemented tool names
    """
    return [
        tool_name
        for tool_name, tool in RESEARCH_TOOLS_MAP.items()
        if tool is not None
    ]
