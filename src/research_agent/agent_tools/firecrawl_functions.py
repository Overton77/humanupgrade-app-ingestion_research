from typing import Any, Dict, List, Optional, Literal
from firecrawl import AsyncFirecrawlApp


async def firecrawl_scrape(
    app: AsyncFirecrawlApp,
    url: str,
    formats: Optional[List[Literal["markdown", "html", "raw", "screenshot"]]] = None,
    include_links: bool = False,
    max_depth: int = 0,
    include_images: bool = False,
    timeout: Optional[int] = None,
    custom_headers: Optional[Dict[str, str]] = None,
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
    scrape_options: Dict[str, Any] = {
        "url": url,
    }

    if formats:
        scrape_options["formats"] = formats
    if include_links:
        scrape_options["includeLinks"] = True
    if max_depth is not None:
        scrape_options["maxDepth"] = max_depth
    if include_images:
        scrape_options["includeImages"] = True
    if custom_headers:
        scrape_options["headers"] = custom_headers

    # Firecrawl SDK name for this may be app.scrape or app.scrape_url depending on version.
    result = await app.scrape(scrape_options, timeout=timeout)
    return result


async def firecrawl_map(
    app: AsyncFirecrawlApp,
    url: str,
    max_depth: int = 1,
    limit: Optional[int] = None,
    same_domain_only: bool = True,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Async wrapper around Firecrawl's map endpoint.
    Good for discovering URLs from a base URL.

    Args:
        app: AsyncFirecrawlApp instance.
        url: Root URL to start from.
        max_depth: How many link levels deep to explore.
        limit: Max number of URLs to collect (if Firecrawl supports it).
        same_domain_only: Whether to restrict crawling to same domain.
        timeout: Optional timeout.

    Returns:
        A dict containing discovered URLs and metadata.
    """
    map_options: Dict[str, Any] = {
        "url": url,
        "maxDepth": max_depth,
        "sameDomainOnly": same_domain_only,
    }
    if limit is not None:
        map_options["limit"] = limit

    result = await app.map(map_options, timeout=timeout)
    return result 


async def firecrawl_extract(
    app: AsyncFirecrawlApp,
    url: str,
    extraction_instructions: str,
    schema: Optional[Dict[str, Any]] = None,
    max_depth: int = 0,
    formats: Optional[List[Literal["markdown", "html", "raw"]]] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Wrapper around Firecrawl's extract endpoint.

    Args:
        app: AsyncFirecrawlApp instance.
        url: URL to extract structured data from.
        extraction_instructions: Natural-language instructions for what to extract
                                 (good for LLM tools).
        schema: Optional JSON schema-like dict to shape the output.
        max_depth: How deep to follow links from this page.
        formats: Optional underlying formats to use (e.g., ["markdown"]).
        timeout: Optional timeout.

    Returns:
        A dict with structured extraction results.
    """
    extract_options: Dict[str, Any] = {
        "url": url,
        "instructions": extraction_instructions,
    }

    if schema is not None:
        extract_options["schema"] = schema
    if max_depth is not None:
        extract_options["maxDepth"] = max_depth
    if formats:
        extract_options["formats"] = formats

    result = await app.extract(extract_options, timeout=timeout)
    return result