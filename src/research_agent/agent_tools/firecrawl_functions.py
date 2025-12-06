from typing import Any, Dict, List, Optional, Literal, Union 
from firecrawl import AsyncFirecrawlApp 
from dotenv import load_dotenv  
import os 
import asyncio 


load_dotenv() 

firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")  
async_firecrawl_app = AsyncFirecrawlApp(api_key=firecrawl_api_key)   



async def firecrawl_scrape(
    app: AsyncFirecrawlApp,
    url: str,
    formats: Optional[List[Literal["markdown", "html", "raw", "screenshot"]]] = None,
    include_links: bool = False,
    max_depth: int = 1,
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





def _safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely get attribute from object or dict key."""
    if hasattr(obj, attr):
        return getattr(obj, attr, default)
    elif isinstance(obj, dict):
        return obj.get(attr, default)
    return default


def format_firecrawl_search_response(
    response: Any,
    *,
    max_content_chars: Optional[int] = None,
) -> str:
    """
    Format a Firecrawl scrape() response (Pydantic model) into a readable string.

    The response is a Pydantic model with attributes:
      - markdown: str | None
      - html: str | None  
      - raw_html: str | None
      - json: Any | None
      - summary: str | None
      - metadata: DocumentMetadata (with .title, .description, .url, etc.)
      - links: list | None
      - images: list | None
      - screenshot: str | None
      - warning: str | None

    Args:
        response: The Pydantic model returned by AsyncFirecrawlApp.scrape()
        max_content_chars: Optional limit on content length

    Returns:
        A formatted string suitable for LLM consumption.
    """
    lines: List[str] = []
    lines.append("=== Firecrawl Scrape Result ===")

    # Extract metadata
    metadata = _safe_getattr(response, "metadata")
    
    title = _safe_getattr(metadata, "title") if metadata else None
    url = _safe_getattr(metadata, "url") if metadata else None
    description = _safe_getattr(metadata, "description") if metadata else None
    language = _safe_getattr(metadata, "language") if metadata else None

    lines.append(f"Title: {title or '(no title)'}")
    lines.append(f"URL: {url or '(no url)'}")
    
    if description:
        lines.append(f"Description: {description}")
    if language:
        lines.append(f"Language: {language}")

    # Get content - prioritize markdown, then html, then raw_html, then summary
    content = (
        _safe_getattr(response, "markdown") 
        or _safe_getattr(response, "html") 
        or _safe_getattr(response, "raw_html")
        or _safe_getattr(response, "summary")
        or ""
    )

    if content:
        if max_content_chars and len(content) > max_content_chars:
            content = content[:max_content_chars] + "\n...[truncated]"
        lines.append("")
        lines.append("Content:")
        lines.append(content.strip())
    else:
        lines.append("")
        lines.append("Content: (none)")

    # Include links if present
    links = _safe_getattr(response, "links")
    if links:
        lines.append("")
        lines.append(f"Links found: {len(links)}")

    # Include warning if present
    warning = _safe_getattr(response, "warning")
    if warning:
        lines.append("")
        lines.append(f"Warning: {warning}")

    return "\n".join(lines).strip() 


def format_firecrawl_map_response(
    response: Any,
    *,
    max_urls: Optional[int] = None,
) -> str:
    """
    Format a Firecrawl map() response (Pydantic model) into a readable string.

    The response is a Pydantic model with:
      - links: List[LinkResult] where each LinkResult has .url, .title, .description

    Args:
        response: The Pydantic model returned by AsyncFirecrawlApp.map()
        max_urls: Optional cap on number of URLs to output.

    Returns:
        A formatted string of discovered URLs with metadata.
    """
    # Get links from the response - it's a Pydantic model with .links attribute
    links = _safe_getattr(response, "links")
    
    # Fallback for dict-based responses
    if links is None and isinstance(response, dict):
        links = response.get("links") or response.get("data") or []
    
    if links is None:
        links = []

    if max_urls is not None:
        links = links[:max_urls]

    lines: List[str] = []
    lines.append("=== Firecrawl URL Map Results ===")
    lines.append(f"Total URLs found: {len(links)}")
    lines.append("")

    if not links:
        lines.append("(no URLs discovered)")
        return "\n".join(lines)

    for i, link in enumerate(links, start=1):
        # LinkResult is a Pydantic model with .url, .title, .description
        url = _safe_getattr(link, "url") or "(no url)"
        title = _safe_getattr(link, "title")
        description = _safe_getattr(link, "description")

        lines.append(f"[{i}] {url}")
        if title:
            lines.append(f"    Title: {title}")
        if description:
            # Truncate long descriptions
            desc = description[:200] + "..." if len(description) > 200 else description
            lines.append(f"    Description: {desc}")
        lines.append("")  # spacing

    return "\n".join(lines).strip() 


if __name__ == "__main__": 
    async def main():
        print("=" * 60)
        print("Testing firecrawl_scrape...")
        print("=" * 60)
        scrape_result = await firecrawl_scrape(
            async_firecrawl_app, 
            "example.com", 
            formats=["markdown"]
        )
        formatted_scrape = format_firecrawl_scrape_response(scrape_result, max_content_chars=1000)
        print(formatted_scrape)
        
        print("\n" + "=" * 60)
        print("Testing firecrawl_map...")
        print("=" * 60)
        map_result = await firecrawl_map(
            async_firecrawl_app, 
            "https://daveasprey.com", 
            limit=5
        )
        formatted_map = format_firecrawl_map_response(map_result)
        print(formatted_map)
        
    asyncio.run(main())