from langchain.tools import tool, ToolRuntime  
from langchain_community.tools import WikipediaQueryRun  
from langchain_community.utilities import WikipediaAPIWrapper    
from pathlib import Path 
from typing import Optional, Literal, Union, List, Tuple, Annotated, Dict, Any
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
from research_agent.human_upgrade.tools.utils.dedupe import dedupe_urls


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
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    output_mode: Literal["summary", "raw"] = "summary",
) -> Tuple[str, List[TavilyCitation]]:
    logger.info(f"🌐 TAVILY SEARCH: '{query[:80]}{'...' if len(query) > 80 else ''}'")

    search_results = await tavily_search(
        client=async_tavily_client,
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
        include_images=include_images,
        include_raw_content=include_raw_content,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        start_date=start_date,
        end_date=end_date,
    )

    await save_json_artifact(
        {"query": query, "results": search_results},
        "test_run",
        "tavily_search_raw",
        suffix=query[:30].replace(" ", "_"),
    )

    formatted = format_tavily_search_response(
        search_results,
        max_results=max_results,
        max_content_chars=1200,  
    )

    if output_mode == "raw":
        # IMPORTANT: no summarization so URLs/lists aren’t lost
        return formatted, []

    # summary mode (current behavior)
    web_search_summary = await summarize_tavily_web_search(formatted, gpt_5_mini)
    return format_tavily_summary_results(web_search_summary), web_search_summary.citations


async def _tavily_extract_impl(
    urls: Union[str, List[str]],
    query: Optional[str] = None,
    chunks_per_source: int = 3,
    extract_depth: Literal["basic", "advanced"] = "basic",
    include_images: bool = False,
    include_favicon: bool = False,
    format: Literal["markdown", "text"] = "markdown",
    output_mode: Literal["summary", "raw"] = "summary",
) -> Tuple[str, List[TavilyCitation]]:
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

    formatted = format_tavily_extract_response(
        extract_results,
        max_results=10,
        max_content_chars=5000,
    )

    if output_mode == "raw":
        return formatted, []

    extract_summary = await summarize_tavily_extract(formatted, gpt_5_mini)
    return format_tavily_summary_results(extract_summary), extract_summary.citations


async def _tavily_map_impl(
    url: str,
    instructions: Optional[str] = None,
    max_depth: int = 2,
    max_breadth: int = 60,   # lowered default (agent can increase)
    limit: int = 120,        # lowered default (agent can increase)
    output_mode: Literal["formatted", "raw"] = "formatted",
    dedupe: bool = True,
    max_return_urls: Optional[int] = 300,  # cap what LLM sees; None = no cap
    drop_fragment: bool = True,
    drop_query: bool = False,
) -> str:
    logger.info(f"🗺️  TAVILY MAP: '{url[:80]}{'...' if len(url) > 80 else ''}'")

    map_results = await tavily_map(
        client=async_tavily_client,
        url=url,
        instructions=instructions,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
    )

    # Save full raw output (no dedupe/cap) for debugging
    await save_json_artifact(
        {"url": url, "instructions": instructions, "results": map_results},
        "test_run",
        "tavily_map_raw",
        suffix=url.replace("/", "_")[:30],
    )

    urls: list[str] = (map_results.get("results", []) or [])
    raw_count = len(urls)

    if dedupe and urls:
        urls = dedupe_urls(urls, drop_fragment=drop_fragment, drop_query=drop_query)

    deduped_count = len(urls)

    if max_return_urls is not None and deduped_count > max_return_urls:
        urls = urls[:max_return_urls]

    returned_count = len(urls)
    base = map_results.get("base_url", url)

    if output_mode == "raw":
        # URL-per-line for easy parsing + keep counts for transparency
        header = (
            "=== RAW MAP RESULTS ===\n"
            f"Base: {base}\n"
            f"Raw URLs: {raw_count} | Deduped: {deduped_count} | Returned: {returned_count}\n"
        )
        return header + "\n".join(urls)

    # formatted mode (numbered list)
    # Use urls_override so the printed count matches returned URLs, not raw.
    return format_tavily_map_response(map_results, urls_override=urls)

# ============================================================================
# VALIDATION TOOLS (NO STEP COUNTING)
# ============================================================================

@tool(
    description="Search the web for information about a topic using Tavily. Returns results (summary or raw) and citations when summary mode is used.",
    parse_docstring=False,
)
async def tavily_search_validation(
    runtime: ToolRuntime,
    query: Annotated[
        str,
        "Search query. Keep short but specific (entity + required fields). Use site: filters and official-domain terms when helpful."
    ],
    max_results: Annotated[
        int,
        "Max results to return (1–20). Higher increases recall but adds noise + tokens."
    ] = 10,
    search_depth: Annotated[
        Literal["basic", "advanced"],
        "basic=faster/cheaper; advanced=better relevance + more evidence snippets per source."
    ] = "advanced",
    topic: Annotated[
        Optional[Literal["general", "news", "finance"]],
        "Retrieval category hint. Use 'news' for recent coverage, 'finance' for market/earnings context."
    ] = "general",
    include_images: Annotated[
        bool,
        "Include image URLs (usually unnecessary for validation)."
    ] = False,
    include_raw_content: Annotated[
        bool | Literal["markdown", "text"],
        "Include cleaned page content per result. Prefer False to avoid bloat; use 'markdown' or 'text' when you need page text."
    ] = False,
    include_domains: Annotated[
        Optional[List[str]],
        "Optional domain allowlist to lock onto official sources (e.g., ['example.com','shop.example.com'])."
    ] = None,
    exclude_domains: Annotated[
        Optional[List[str]],
        "Optional domain blocklist to avoid retailers/affiliates/low-quality sources."
    ] = None,
    start_date: Annotated[
        Optional[str],
        "Optional start date filter (YYYY-MM-DD). Most useful with topic='news'."
    ] = None,
    end_date: Annotated[
        Optional[str],
        "Optional end date filter (YYYY-MM-DD). Most useful with topic='news'."
    ] = None,
    output_mode: Annotated[
        Literal["summary", "raw"],
        "summary=LLM-compressed output with citations; raw=formatted raw results with URLs preserved (no summarization)."
    ] = "summary",
) -> str:
    out, _ = await _tavily_search_impl(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
        include_images=include_images,
        include_raw_content=include_raw_content,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        start_date=start_date,
        end_date=end_date,
        output_mode=output_mode,
    )
    return out


@tool(
    description="Extract content from one or more URLs using Tavily Extract. Returns results (summary or raw) and citations when summary mode is used.",
    parse_docstring=False,
)
async def tavily_extract_validation(
    runtime: ToolRuntime,
    urls: Annotated[
        Union[str, List[str]],
        "1 URL or a list of URLs to extract from (prefer official pages: /products, /shop, /collections, /ingredients, /about)."
    ],
    query: Annotated[
        Optional[str],
        "Optional extraction filter. Provide required fields/keywords to return only relevant chunks (recommended for long pages)."
    ] = None,
    chunks_per_source: Annotated[
        int,
        "How many relevant chunks to pull per URL (1–5). Higher = more coverage + more tokens."
    ] = 3,
    extract_depth: Annotated[
        Literal["basic", "advanced"],
        "basic=faster/cheaper; advanced=better for dense pages, tables, and storefront/JS-heavy pages."
    ] = "basic",
    include_images: Annotated[
        bool,
        "Include images found on the page (usually unnecessary)."
    ] = False,
    include_favicon: Annotated[
        bool,
        "Include site favicon URL in results (cosmetic/attribution)."
    ] = False,
    format: Annotated[
        Literal["markdown", "text"],
        "Output format for extracted content. markdown is usually best for structure; text can be simpler but may be slower."
    ] = "markdown",
    output_mode: Annotated[
        Literal["summary", "raw"],
        "summary=LLM-compressed output with citations; raw=formatted extracted content with URLs preserved (no summarization)."
    ] = "summary",
) -> str:
    out, _ = await _tavily_extract_impl(
        urls=urls,
        query=query,
        chunks_per_source=chunks_per_source,
        extract_depth=extract_depth,
        include_images=include_images,
        include_favicon=include_favicon,
        format=format,
        output_mode=output_mode,
    )
    return out


@tool(
    description="Map a website to discover internal links using Tavily Map. Returns a formatted list or raw URL list (optionally deduped).",
    parse_docstring=False,
)
async def tavily_map_validation(
    runtime: ToolRuntime,
    url: Annotated[
        str,
        "Root URL or domain to map (prefer official home/docs root)."
    ],
    instructions: Annotated[
        Optional[str],
        "Optional guidance to steer discovery (e.g., 'Find product pages, shop/collections, ingredients/supplement facts; ignore blog/careers')."
    ] = None,
    max_depth: Annotated[
        int,
        "How many link-hops from the root to explore (1–5). Depth increases cost quickly; 2 is typical for product discovery."
    ] = 2,
    max_breadth: Annotated[
        int,
        "Max links to follow per level/page (1–500). Higher increases recall on storefront navs but can explode."
    ] = 120,
    limit: Annotated[
        int,
        "Hard cap on total URLs processed/returned by the mapper. Raise when enumerating large catalogs."
    ] = 250,
    output_mode: Annotated[
        Literal["formatted", "raw"],
        "formatted=numbered list; raw=URL-per-line output (best for downstream parsing)."
    ] = "formatted",
    dedupe: Annotated[
        bool,
        "Deduplicate discovered URLs before returning them to the model (recommended True)."
    ] = True,
    max_return_urls: Annotated[
        Optional[int],
        "Cap URLs returned to the model after dedupe (artifact still stores full raw output). None = no cap."
    ] = 300,
    drop_fragment: Annotated[
        bool,
        "Drop #fragment anchors during dedupe (recommended True)."
    ] = True,
    drop_query: Annotated[
        bool,
        "Drop ?query strings during dedupe. NOT recommended for ecommerce (variants/SKUs may be encoded in query params)."
    ] = False,
) -> str:
    return await _tavily_map_impl(
        url=url,
        instructions=instructions,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
        output_mode=output_mode,
        dedupe=dedupe,
        max_return_urls=max_return_urls,
        drop_fragment=drop_fragment,
        drop_query=drop_query,
    )

# ============================================================================
# RESEARCH TOOLS (WITH STEP COUNTING)
# ============================================================================

@tool(
    description="Search the web for information about a topic using Tavily. Returns results (summary or raw) with citations when summary mode is used.",
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

    include_domains: Annotated[
        Optional[List[str]],
        "Optional domain allowlist (official-domain lock). Example: ['example.com', 'shop.example.com']."
    ] = None,
    exclude_domains: Annotated[
        Optional[List[str]],
        "Optional domain blocklist to avoid aggregators/retail/affiliate sites."
    ] = None,
    start_date: Annotated[
        Optional[str],
        "Optional start date filter (YYYY-MM-DD). Mostly useful for news."
    ] = None,
    end_date: Annotated[
        Optional[str],
        "Optional end date filter (YYYY-MM-DD). Mostly useful for news."
    ] = None,
    output_mode: Annotated[
        Literal["summary", "raw"],
        "summary=LLM-compressed with citations; raw=formatted raw results with URLs preserved (no summarization)."
    ] = "summary",
) -> Command:
    """Search the web using Tavily."""
    search_results, citations = await _tavily_search_impl(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
        include_images=include_images,
        include_raw_content=include_raw_content,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        start_date=start_date,
        end_date=end_date,
        output_mode=output_mode,
    )

    steps = int(runtime.state.get("steps_taken", 0) or 0) + 1
    logger.info(f"📊 Step {steps}")
    logger.info(f"📊 Citations written: {len(citations)} (mode={output_mode})")

    return Command(
        update={
            "steps_taken": steps,
            "messages": [ToolMessage(content=search_results, tool_call_id=runtime.tool_call_id)],
        }
    )


@tool(
    description="Extract content from one or more URLs using Tavily Extract. Returns content (summary or raw) with citations when summary mode is used.",
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
        "How many relevant chunks to pull per URL (higher = more coverage + more tokens). Range typically 1–5."
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
    output_mode: Annotated[
        Literal["summary", "raw"],
        "summary=LLM-compressed with citations; raw=formatted extracted content with URLs preserved (no summarization)."
    ] = "summary",
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
        output_mode=output_mode,
    )

    steps = int(runtime.state.get("steps_taken", 0) or 0) + 1
    logger.info(f"📊 Step {steps}")
    logger.info(f"📊 Citations written: {len(citations)} (mode={output_mode})")

    return Command(
        update={
            "steps_taken": steps,
            "messages": [ToolMessage(content=extract_results, tool_call_id=runtime.tool_call_id)],
        }
    )

@tool(
    description="Map a website to discover internal links using Tavily Map. Returns a formatted list or raw URL list (deduped).",
    parse_docstring=False,
)
async def tavily_map_research(
    runtime: ToolRuntime,
    url: Annotated[str, "Root URL to map (authoritative site/home/docs root)."],
    instructions: Annotated[Optional[str], "Natural-language guidance to steer discovery."] = None,
    max_depth: Annotated[int, "How many link-hops from the root to explore."] = 2,
    max_breadth: Annotated[int, "Max links to follow per level/page."] = 60,
    limit: Annotated[int, "Hard cap on total URLs processed/returned."] = 120,
    output_mode: Annotated[Literal["formatted", "raw"], "formatted=numbered list; raw=URL-per-line."] = "formatted",
    dedupe: Annotated[bool, "Deduplicate discovered URLs (recommended True)."] = True,
    max_return_urls: Annotated[Optional[int], "Cap URLs returned to the LLM (raw artifact still saves full list)."] = 300,
    drop_fragment: Annotated[bool, "Drop #fragment anchors during dedupe (recommended True)."] = True,
    drop_query: Annotated[bool, "Drop ?query during dedupe (NOT recommended for ecommerce)."] = False,
) -> Command:
    steps = int(runtime.state.get("steps_taken", 0) or 0) + 1
    logger.info(f"📊 Step {steps}")

    map_results_str = await _tavily_map_impl(
        url=url,
        instructions=instructions,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
        output_mode=output_mode,
        dedupe=dedupe,
        max_return_urls=max_return_urls,
        drop_fragment=drop_fragment,
        drop_query=drop_query,
    )

    return Command(
        update={
            "steps_taken": steps,
            "messages": [ToolMessage(content=map_results_str, tool_call_id=runtime.tool_call_id)],
        }
    )


