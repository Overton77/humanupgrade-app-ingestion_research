from langchain.tools import tool, ToolRuntime  
from langchain_community.tools import WikipediaQueryRun  
from langchain_community.utilities import WikipediaAPIWrapper    
from pathlib import Path 
from typing import Optional, Literal, Union, List, Tuple 
from research_agent.agent_tools.tavily_functions import (
    tavily_search,
    format_tavily_search_response,
    tavily_extract,
    tavily_map,
    format_tavily_extract_response,
    format_tavily_map_response,
)   
from research_agent.human_upgrade.structured_outputs.sources_and_search_summary_outputs import TavilyCitation
from research_agent.human_upgrade.tools.utils.runtime_helpers import increment_steps, write_citations
from research_agent.human_upgrade.tools.utils.web_search_helpers import summarize_tavily_web_search, summarize_tavily_extract, format_tavily_summary_results
from research_agent.human_upgrade.logger import logger 
from research_agent.human_upgrade.utils.artifacts import save_json_artifact, save_text_artifact
from research_agent.human_upgrade.async_tavily_client import async_tavily_client 
from research_agent.human_upgrade.base_models import gpt_5_mini
import asyncio 


wikipedia_api_wrapper = WikipediaAPIWrapper( 
    top_k_results=4, 
    doc_content_chars_max=4000, 
)  





_wikipedia_tool_instance = WikipediaQueryRun(api_wrapper=wikipedia_api_wrapper) 



# Wrap Wikipedia tool in @tool decorator for ToolNode compatibility
@tool(
    description="Search Wikipedia for information about a topic. Useful for finding general knowledge, biographical information, company histories, and scientific concepts.",
    parse_docstring=False,
)
async def wiki_search_tool(query: str) -> str:
    """Search Wikipedia for information about a topic."""
    
    return await _wikipedia_tool_instance.ainvoke(query)

wiki_tool = wiki_search_tool





async def _tavily_search_impl(
    query: str,
    max_results: int = 5,
    search_depth: Literal["basic", "advanced"] = "basic",
    topic: Optional[Literal["general", "news", "finance"]] = "general",
    include_images: bool = False,
    include_raw_content: bool | Literal["markdown", "text"] = False,
) -> Tuple[str, List[TavilyCitation]]:
    """Implementation of Tavily web search."""
    logger.info(f"🌐 TAVILY SEARCH: '{query[:80]}{'...' if len(query) > 80 else ''}'")
    
    search_results = await tavily_search(
        client=async_tavily_client,
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
        include_images=include_images,
        include_raw_content=include_raw_content,
    )
    
    await save_json_artifact(
        {"query": query, "results": search_results},
        "test_run",
        "tavily_search_raw",
        suffix=query[:30].replace(" ", "_"),
    )
    
    formatted_search_results = format_tavily_search_response(search_results)
    web_search_summary = await summarize_tavily_web_search(formatted_search_results, gpt_5_mini)
    web_search_summary_formatted = format_tavily_summary_results(web_search_summary)
    
    logger.info(f"✅ TAVILY SEARCH complete: {len(web_search_summary.citations)} citations")
    return web_search_summary_formatted, web_search_summary.citations


async def _tavily_extract_impl(
    urls: Union[str, List[str]],
    query: Optional[str] = None,
    chunks_per_source: int = 3,
    extract_depth: Literal["basic", "advanced"] = "basic",
    include_images: bool = False,
    include_favicon: bool = False,
    format: Literal["markdown", "text"] = "markdown",
) -> Tuple[str, List[TavilyCitation]]:
    """Implementation of Tavily extract."""
    url_list = urls if isinstance(urls, list) else [urls]
    logger.info(f"🔗 TAVILY EXTRACT: {len(url_list)} URL(s)")
    
    extract_results = await tavily_extract(
        client=async_tavily_client,
        urls=urls,
        query=query,
        chunks_per_source=chunks_per_source,
        extract_depth=extract_depth,
        include_images=include_images,
        include_favicon=include_favicon,
        format=format,
    )
    
    await save_json_artifact(
        {"urls": url_list, "query": query, "results": extract_results},
        "test_run",
        "tavily_extract_raw",
        suffix=f"{len(url_list)}_urls",
    )
    
    formatted_extract_results = format_tavily_extract_response(extract_results)
    extract_summary = await summarize_tavily_extract(formatted_extract_results, gpt_5_mini)
    extract_summary_formatted = format_tavily_summary_results(extract_summary)
    
    logger.info(f"✅ TAVILY EXTRACT complete: {len(extract_summary.citations)} citations")
    return extract_summary_formatted, extract_summary.citations


async def _tavily_map_impl(
    url: str,
    instructions: Optional[str] = None,
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 25,
) -> str:
    """Implementation of Tavily map."""
    logger.info(f"🗺️  TAVILY MAP: '{url[:80]}{'...' if len(url) > 80 else ''}'")
    
    map_results = await tavily_map(
        client=async_tavily_client,
        url=url,
        instructions=instructions,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
    )
    
    discovered_urls = map_results.get("results", [])
    
    await save_json_artifact(
        {"url": url, "instructions": instructions, "results": map_results},
        "test_run",
        "tavily_map_raw",
        suffix=url.replace("/", "_")[:30],
    )
    
    formatted_map_results = format_tavily_map_response(map_results)
    logger.info(f"✅ TAVILY MAP complete: {len(discovered_urls)} URLs discovered")
    
    return formatted_map_results


# ============================================================================
# VALIDATION TOOLS (NO STEP COUNTING)
# ============================================================================

@tool(
    description="Search the web for information about a topic using Tavily. Returns summarized results with citations.",
    parse_docstring=False,
)
async def tavily_search_validation(
    runtime: ToolRuntime,
    query: str,
    max_results: int = 5,
    search_depth: Literal["basic", "advanced"] = "basic",
    topic: Optional[Literal["general", "news", "finance"]] = "general",
    include_images: bool = False,
    include_raw_content: bool | Literal["markdown", "text"] = False,
) -> str:
    """Search the web using Tavily."""
    search_results, _ = await _tavily_search_impl(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
        include_images=include_images,
        include_raw_content=include_raw_content,
    )
    return search_results


@tool(
    description="Extract content from one or more URLs using Tavily Extract. Returns formatted content with citations.",
    parse_docstring=False,
)
async def tavily_extract_validation(
    runtime: ToolRuntime,
    urls: Union[str, List[str]],
    query: Optional[str] = None,
    chunks_per_source: int = 3,
    extract_depth: Literal["basic", "advanced"] = "basic",
    include_images: bool = False,
    include_favicon: bool = False,
    format: Literal["markdown", "text"] = "markdown",
) -> str:
    """Extract content from URLs using Tavily."""
    extract_results, _ = await _tavily_extract_impl(
        urls=urls,
        query=query,
        chunks_per_source=chunks_per_source,
        extract_depth=extract_depth,
        include_images=include_images,
        include_favicon=include_favicon,
        format=format,
    )
    return extract_results


@tool(
    description="Map a website to discover internal links using Tavily Map. Returns a formatted list of discovered URLs.",
    parse_docstring=False,
)
async def tavily_map_validation(
    runtime: ToolRuntime,
    url: str,
    instructions: Optional[str] = None,
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 25,
) -> str:
    """Map a website using Tavily."""
    return await _tavily_map_impl(
        url=url,
        instructions=instructions,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
    )



# ============================================================================
# RESEARCH TOOLS (WITH STEP COUNTING)
# ============================================================================

@tool(
    description="Search the web for information about a topic using Tavily. Returns summarized results with citations.",
    parse_docstring=False,
)
async def tavily_search_research(
    runtime: ToolRuntime,
    query: str,
    max_results: int = 5,
    search_depth: Literal["basic", "advanced"] = "basic",
    topic: Optional[Literal["general", "news", "finance"]] = "general",
    include_images: bool = False,
    include_raw_content: bool | Literal["markdown", "text"] = False,
) -> str:
    """Search the web using Tavily."""
    search_results, citations = await _tavily_search_impl(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
        include_images=include_images,
        include_raw_content=include_raw_content,
    ) 

    # These are cheap synchronous operations - call them directly
    increment_steps(runtime)
    write_citations(runtime, citations)

    return search_results


@tool(
    description="Extract content from one or more URLs using Tavily Extract. Returns formatted content with citations.",
    parse_docstring=False,
)
async def tavily_extract_research(
    runtime: ToolRuntime,
    urls: Union[str, List[str]],
    query: Optional[str] = None,
    chunks_per_source: int = 3,
    extract_depth: Literal["basic", "advanced"] = "basic",
    include_images: bool = False,
    include_favicon: bool = False,
    format: Literal["markdown", "text"] = "markdown",
) -> str:
    """Extract content from URLs using Tavily."""
    extract_results, citations = await _tavily_extract_impl(
        urls=urls,
        query=query,
        chunks_per_source=chunks_per_source,
        extract_depth=extract_depth,
        include_images=include_images,
        include_favicon=include_favicon,
        format=format,
    )

    # These are cheap synchronous operations - call them directly
    increment_steps(runtime)
    write_citations(runtime, citations)

    return extract_results


@tool(
    description="Map a website to discover internal links using Tavily Map. Returns a formatted list of discovered URLs.",
    parse_docstring=False,
)
async def tavily_map_research(
    runtime: ToolRuntime,
    url: str,
    instructions: Optional[str] = None,
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 25,
) -> str:
    """Map a website using Tavily."""
    increment_steps(runtime)  

    return await _tavily_map_impl(
        url=url,
        instructions=instructions,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
    )


    


