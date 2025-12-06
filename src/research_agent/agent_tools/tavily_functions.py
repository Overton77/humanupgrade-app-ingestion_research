from typing import Literal, Union, List, Dict, Any, Optional
from tavily import AsyncTavilyClient  
from datetime import datetime  
import asyncio 

async def tavily_search(
    client: AsyncTavilyClient,
    query: str,
    max_results: int = 5,  

    search_depth: Literal["basic", "advanced"] = "basic",
    topic: Optional[Literal["general", "news", "finance"]] = None,
    include_images: bool = False,
    include_raw_content: bool | Literal["markdown", "text"] = False, 
    start_date: Optional[str] = None,  
    end_date: Optional[str] = None, 
) -> Dict[str, Any]:
    """
    Async wrapper around Tavily's search method.

    Args:
        query: Natural-language search query.
        max_results: Max number of results to return.
        search_depth: 'basic' (faster, fewer pages) or 'advanced' (more thorough).
        topic: Optional topic hint for Tavily (e.g., 'news', 'academic').
        include_answer: Whether Tavily should include its own synthesized answer.
        include_images: Whether to include image results.
        include_raw_content: Whether to include raw page text content.
        include_domains: If set, focus search on these domains (whitelist).
        exclude_domains: If set, avoid these domains (blacklist).
        start_date: Optional start date for search.
        end_date: Optional end date for search.
    Returns:
        A dict with Tavily's response (answer, results, etc.).
    """
   

    # Tavily async client uses `search` as well, just awaited.
    result = await client.search( 

        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
        include_images=include_images,
        include_raw_content=include_raw_content,
      
        start_date=start_date,
        end_date=end_date,
    )
    return result  

async def tavily_search_multiple(
    client: AsyncTavilyClient,
    queries: List[str],
    max_results: int = 5,  

    search_depth: Literal["basic", "advanced"] = "basic",
    topic: Optional[Literal["general", "news", "finance"]] = None,
    include_images: bool = False,
    include_raw_content: bool | Literal["markdown", "text"] = False,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None, 
    start_date: Optional[str] = None,  
    end_date: Optional[str] = None, 
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
   

    # Tavily async client uses `search` as well, just awaited.   
     

    results = await asyncio.gather(*[client.search(query=query, max_results=max_results, search_depth=search_depth, topic=topic, include_images=include_images, include_raw_content=include_raw_content, 
     include_domains=include_domains, exclude_domains=exclude_domains, start_date=start_date, end_date=end_date) for query in queries])
 


   
    return results 


def format_tavily_search_response(
    response: Dict[str, Any] | List[Dict[str, Any]],
    *,
    max_results: Optional[int] = None,
    max_content_chars: Optional[int] = None,
) -> str:
    """
    Format Tavily search results into a compact, LLM-friendly string.

    Works with:
      - The raw TavilyClient.search() response (dict with 'results' and 'images').
      - The langchain TavilySearch tool output (same shape).
      - Or directly with a bare list of result dicts.

    Fields included per result:
      - title
      - url
      - score (float)
      - optional published_date
      - content (falls back to raw_content if content is missing)

    Also includes image results (if present) with:
      - url
      - optional description

    Args:
        response: Tavily search response or list of result objects.
        max_results: Optional cap on number of results to format.
        max_content_chars: Optional cap on content length per result.

    Returns:
        A well-structured string ready to feed to a summarization model.
    """
    # Normalize to dict with "results" and "images"
    if isinstance(response, list):
        results = response
        images: List[Any] = []
        query_str = None
    elif isinstance(response, dict):
        results = response.get("results") or []
        images = response.get("images") or []
        query_str = response.get("query") 



    if max_results is not None:
        results = results[:max_results]

    lines: List[str] = []

    # Optional header with original query
    if query_str:
        lines.append(f"Search query: {query_str}")
        lines.append("")

    # --- Main results ---
    lines.append("=== Web Results ===")
    if not results:
        lines.append("(no results)")
    else:
        for idx, r in enumerate(results, start=1):
            title = r.get("title") or "(no title)"
            url = r.get("url") or "(no url)"
            score = r.get("score")
            published_date = r.get("published_date")

            # content fallback to raw_content
            content = r.get("content") or r.get("raw_content") or ""
            if max_content_chars is not None and content and len(content) > max_content_chars:
                content = content[:max_content_chars] + " …[truncated]"

            lines.append(f"[Result {idx}]")
            lines.append(f"Title: {title}")
            lines.append(f"URL: {url}")

            if score is not None:
                try:
                    lines.append(f"Score: {float(score):.4f}")
                except (TypeError, ValueError):
                    lines.append(f"Score: {score}")

            if published_date:
                lines.append(f"Published date: {published_date}")

            if content:
                lines.append("Content:")
                lines.append(content.strip())
            else:
                lines.append("Content: (empty)")

            lines.append("")  # blank line between results

    # --- Image results ---
    lines.append("=== Image Results ===")
    if not images:
        lines.append("(no images)")
    else:
        for idx, img in enumerate(images, start=1):
            # Tavily can return either a simple string URL or a dict with more fields
            if isinstance(img, str):
                img_url = img
                description = None
            elif isinstance(img, dict):
                img_url = img.get("url") or img.get("image_url") or "(no url)"
                description = img.get("description") or img.get("alt") or None
            else:
                img_url = f"(unexpected image type: {img!r})"
                description = None

            lines.append(f"[Image {idx}]")
            lines.append(f"URL: {img_url}")
            if description:
                lines.append(f"Description: {description}")
            lines.append("")

    return "\n".join(lines).strip() 



