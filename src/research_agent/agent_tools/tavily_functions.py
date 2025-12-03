from typing import Literal, Union, List, Dict, Any, Optional
from tavily import AsyncTavilyClient 

async def tavily_search(
    client: AsyncTavilyClient,
    query: str,
    max_results: int = 5,
    search_depth: Literal["basic", "advanced"] = "basic",
    topic: Optional[Literal["general", "news", "finance", "shopping", "academic"]] = None,
    include_answer: bool = True,
    include_images: bool = False,
    include_raw_content: bool = False,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Async wrapper around Tavily's search method.

    Args:
        client: An initialized AsyncTavilyClient instance.
        query: Natural-language search query.
        max_results: Max number of results to return.
        search_depth: 'basic' (faster, fewer pages) or 'advanced' (more thorough).
        topic: Optional topic hint for Tavily (e.g., 'news', 'academic').
        include_answer: Whether Tavily should include its own synthesized answer.
        include_images: Whether to include image results.
        include_raw_content: Whether to include raw page text content.
        include_domains: If set, focus search on these domains (whitelist).
        exclude_domains: If set, avoid these domains (blacklist).

    Returns:
        A dict with Tavily's response (answer, results, etc.).
    """
    params: Dict[str, Any] = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": include_answer,
        "include_images": include_images,
        "include_raw_content": include_raw_content,
    }

    if topic is not None:
        params["topic"] = topic
    if include_domains:
        params["include_domains"] = include_domains
    if exclude_domains:
        params["exclude_domains"] = exclude_domains

    # Tavily async client uses `search` as well, just awaited.
    result = await client.search(**params)
    return result