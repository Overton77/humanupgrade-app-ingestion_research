from typing import Any, Dict, List, Optional, Literal, Union 
from firecrawl import AsyncFirecrawlApp


async def firecrawl_scrape(
    app: AsyncFirecrawlApp,
    url: str,
    formats: Optional[List[Literal["markdown", "html", "raw", "screenshot"]]] = None,
    include_links: bool = False,
    max_depth: int = 0,
    include_images: bool = False,
) -> Dict[str, Any]:
    """
    High-level async wrapper around Firecrawl's scrape endpoint.

    Args:
        app: An initialized AsyncFirecrawlApp instance.
        url: Single URL to scrape.
        formats: Which formats to return. Most useful for LLMs: ["markdown"].
        include_links: Whether to also extract outgoing links.
        max_depth: How deep to follow internal links (0 = just this page).
        include_images: Whether to include image metadata.
        timeout: Optional timeout in seconds for this scrape.
        custom_headers: Optional HTTP headers to send.

    Returns:
        A dict with scraped content in requested formats (implementation-specific).
    """
    # Pass keyword arguments directly to the SDK method
    result = await app.scrape(
        url,
        formats=formats,
        include_links=include_links,
        max_depth=max_depth,
        include_images=include_images,
    
    )
    return result


async def firecrawl_map(
    app: AsyncFirecrawlApp,
    url: str,
    search: Optional[str] = None,
    include_subdomains: Optional[bool] = None,
    limit: Optional[int] = None,
    sitemap: Optional[Literal["only", "include", "skip"]] = None,
) -> Dict[str, Any]:
    """
    Async wrapper around Firecrawl's map endpoint.
    Good for discovering URLs from a base URL.

    Args:
        app: AsyncFirecrawlApp instance.
        url: Root URL to start from.
        search: Optional search term to filter URLs.
        include_subdomains: Whether to include subdomains in the mapping.
        limit: Max number of URLs to collect.
        sitemap: How to handle sitemaps: "only" (only use sitemap), "include" (use sitemap + crawl), "skip" (ignore sitemap).
        timeout: Optional timeout.
        integration: Optional integration identifier.

    Returns:
        A dict containing discovered URLs and metadata.
    """
    # Pass keyword arguments directly to the SDK method
    result = await app.map(
        url,
        search=search,
        include_subdomains=include_subdomains,
        limit=limit,
        sitemap=sitemap,
       
        
    )
    return result 





def format_firecrawl_search_response(
    response: Dict[str, Any] | List[Dict[str, Any]],
    *,
    max_results: Optional[int] = None,
    max_content_chars: Optional[int] = None,
) -> str:
    """
    Format Firecrawl search (or scrape) response into a string suitable for LLM summarization.

    Handles:
      - SERP-only results: title, url, description
      - Scraped results: markdown/html/rawHtml as content
      - Optionally truncates long content
    """

    # Normalize
    if isinstance(response, dict) and "data" in response:
        results = response["data"]
    elif isinstance(response, list):
        results = response
    else:
        raise ValueError("Unexpected Firecrawl response format")

    if max_results is not None:
        results = results[:max_results]

    lines: List[str] = []
    lines.append("=== Firecrawl Search Results ===")

    if not results:
        lines.append("(no results)")
    else:
        for i, r in enumerate(results, start=1):
            title = r.get("title") or "(no title)"
            url = r.get("url") or r.get("metadata", {}).get("sourceURL") or "(no url)"
            description = r.get("description")
            # Try content: prioritize markdown, fallback to html or rawHtml
            content = r.get("markdown") or r.get("html") or r.get("rawHtml") or ""
            if max_content_chars and content and len(content) > max_content_chars:
                content = content[:max_content_chars] + "\n...[truncated]"

            lines.append(f"[Result {i}]")
            lines.append(f"Title: {title}")
            lines.append(f"URL: {url}")
            if description:
                lines.append(f"Description: {description}")
            if content:
                lines.append("Content:")
                lines.append(content.strip())
            else:
                lines.append("Content: (none)")

            lines.append("")  # empty line between results

    return "\n".join(lines).strip() 


def format_firecrawl_map_response(
    response: Dict[str, Any] | List[Dict[str, Any]],
    *,
    max_urls: Optional[int] = None,
) -> str:
    """
    Format a Firecrawl `map()` response into a clean, readable string.

    Handles both:
      - Full dict response: { success, data: [...] }
      - Bare list of URL metadata objects

    Each entry includes:
        - url
        - source (if present)
        - depth (if present)
        - statusCode (if present)
        - error (if present)

    Args:
        response: The result of AsyncFirecrawlApp.map() or equivalent.
        max_urls: Optional cap on number of URLs to output.

    Returns:
        A formatted string of discovered URLs with metadata.
    """
    # Normalize to list of items
    if isinstance(response, dict) and "data" in response:
        items = response["data"]
    elif isinstance(response, list):
        items = response
    else:
        raise ValueError(f"Unexpected Firecrawl map() response type: {type(response)!r}")

    if max_urls is not None:
        items = items[:max_urls]

    lines: List[str] = []
    lines.append("=== Firecrawl URL Map Results ===")

    if not items:
        lines.append("(no URLs discovered)")
        return "\n".join(lines)

    for i, entry in enumerate(items, start=1):
        url = entry.get("url", "(no url)")
        source = entry.get("source")  # 'sitemap' | 'crawl' | ...
        depth = entry.get("depth")
        status = entry.get("statusCode")
        error = entry.get("error")

        lines.append(f"[URL {i}]")
        lines.append(f"URL: {url}")
        if source:
            lines.append(f"Source: {source}")
        if depth is not None:
            lines.append(f"Depth: {depth}")
        if status is not None:
            lines.append(f"Status Code: {status}")
        if error:
            lines.append(f"Error: {error}")

        lines.append("")  # spacing

    return "\n".join(lines).strip()