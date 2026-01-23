from langchain.tools import tool, ToolRuntime  
from langchain_community.tools import WikipediaQueryRun  
from langchain_community.utilities import WikipediaAPIWrapper    
from pathlib import Path 
from typing import Optional, Literal, Union, List, Tuple, Annotated
from langgraph.types import Command
from langchain.messages import ToolMessage
from research_agent.agent_tools.tavily_functions import (
    tavily_search,
    format_tavily_search_response,
    tavily_extract,
    tavily_map,
    format_tavily_extract_response,
    format_tavily_map_response,
)   
from research_agent.human_upgrade.structured_outputs.sources_and_search_summary_outputs import TavilyCitation
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
async def wiki_search_tool(runtime: ToolRuntime, query: str) -> Command:
    """Search Wikipedia for information about a topic."""
    result = await _wikipedia_tool_instance.ainvoke(query)
    
    # Increment steps
    steps = int(runtime.state.get("steps_taken", 0) or 0) + 1
    logger.info(f"📊 Step {steps}")
    
    # Return Command with state updates
    return Command(
        update={
            "steps_taken": steps,
            "messages": [ToolMessage(content=result, tool_call_id=runtime.tool_call_id)],
        }
    )

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
    # --- tavily_search_research args ---
    query: Annotated[
        str,
        "Search query (be specific: entity + requiredField + evidence terms + site: filters when useful)."
    ],
    max_results: Annotated[
        int,
        "Max results to return (keeps noise + context down)."
    ] = 5,
    search_depth: Annotated[
        Literal["basic", "advanced"],
        "basic=cheaper/faster; advanced=deeper evidence (use for key claims)."
    ] = "basic",
    topic: Annotated[
        Optional[Literal["general", "news", "finance"]],
        "Domain filter for retrieval; use 'news' for recent coverage."
    ] = "general",
    include_images: Annotated[
        bool,
        "Include image URLs (rarely needed for research checkpoints)."
    ] = False,
    include_raw_content: Annotated[
        bool | Literal["markdown", "text"],
        "Include page content for each result; prefer False to avoid bloat (True→markdown)."
    ] = False,
) -> Command:
    """Search the web using Tavily."""
    search_results, citations = await _tavily_search_impl(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
        include_images=include_images,
        include_raw_content=include_raw_content,
    ) 

    # Increment steps and track citations
    steps = int(runtime.state.get("steps_taken", 0) or 0) + 1
    logger.info(f"📊 Step {steps}")
    logger.info(f"📊 Citations written: {len(citations)}")
    
    # Return Command with state updates
    return Command(
        update={
            "steps_taken": steps,
            "messages": [ToolMessage(content=search_results, tool_call_id=runtime.tool_call_id)],
            # Note: citations would need a reducer in state schema if you want to track them
        }
    )


@tool(
    description="Extract content from one or more URLs using Tavily Extract. Returns formatted content with citations.",
    parse_docstring=False,
)
async def tavily_extract_research(
    runtime: ToolRuntime,
    # --- tavily_extract_research args ---
    urls: Annotated[
        Union[str, List[str]],
        "1 URL or a list of URLs to extract from (usually top 3–5 from search)."
    ],
    query: Annotated[
        Optional[str],
        "CRITICAL: extraction filter—list missing requiredFields/keywords so only relevant chunks return."
    ] = None,
    chunks_per_source: Annotated[
        int,
        "How many relevant chunks to pull per URL (higher = more coverage + more tokens)."
    ] = 3,
    extract_depth: Annotated[
        Literal["basic", "advanced"],
        "basic=cheaper; advanced=better for dense/long pages (use when needed)."
    ] = "basic",
    include_images: Annotated[
        bool,
        "Include images found on the page (usually unnecessary)."
    ] = False,
    include_favicon: Annotated[
        bool,
        "Include site favicon URL in results (cosmetic)."
    ] = False,
    format: Annotated[
        Literal["markdown", "text"],
        "Output format for extracted content; markdown is usually best for readability/citations."
    ] = "markdown",
) -> Command:
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

    # Increment steps and track citations
    steps = int(runtime.state.get("steps_taken", 0) or 0) + 1
    logger.info(f"📊 Step {steps}")
    logger.info(f"📊 Citations written: {len(citations)}")
    
    # Return Command with state updates
    return Command(
        update={
            "steps_taken": steps,
            "messages": [ToolMessage(content=extract_results, tool_call_id=runtime.tool_call_id)],
        }
    )


@tool(
    description="Map a website to discover internal links using Tavily Map. Returns a formatted list of discovered URLs.",
    parse_docstring=False,
)
async def tavily_map_research(
    runtime: ToolRuntime,
    # --- tavily_map_research args ---
    url: Annotated[str, "Root URL to map (authoritative site/home/docs root)."],
    instructions: Annotated[Optional[str], "CRITICAL: natural-language guidance that steers which internal URLs are discovered/returned."] = None,
    max_depth: Annotated[int, "How many link-hops from the root to explore (depth grows cost fast)."] = 1,
    max_breadth: Annotated[int, "Max links to follow per level/page (controls horizontal explosion)."] = 15,
    limit: Annotated[int, "Hard cap on total URLs returned/processed (prevents runaway maps)."] = 25,
) -> Command:
    """Map a website using Tavily."""
    # Increment steps
    steps = int(runtime.state.get("steps_taken", 0) or 0) + 1
    logger.info(f"📊 Step {steps}")
    
    map_results = await _tavily_map_impl(
        url=url,
        instructions=instructions,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
    )
    
    # Return Command with state updates
    return Command(
        update={
            "steps_taken": steps,
            "messages": [ToolMessage(content=map_results, tool_call_id=runtime.tool_call_id)],
        }
    )


    


