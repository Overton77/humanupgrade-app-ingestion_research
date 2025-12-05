from typing import Any, Dict, List, Optional, Literal
from firecrawl import AsyncFirecrawlApp



async def firecrawl_extract(
    app: AsyncFirecrawlApp,
    urls: List[str],
    prompt: str,
    schema: Optional[Dict[str, Any]] = None,
    system_prompt: Optional[str] = None,
    allow_external_links: Optional[bool] = None,
    enable_web_search: Optional[bool] = None,
    show_sources: Optional[bool] = None,
    scrape_options: Optional[Dict[str, Any]] = None,
    ignore_invalid_urls: Optional[bool] = None,
    poll_interval: int = 2,
    timeout: Optional[int] = None,
    integration: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Wrapper around Firecrawl's extract endpoint.

    Args:
        app: AsyncFirecrawlApp instance.
        urls: List of URLs to extract structured data from (supports wildcards like "https://example.com/*").
        prompt: Natural-language prompt/instructions for what to extract (good for LLM tools).
        schema: Optional JSON schema-like dict to shape the output.
        system_prompt: Optional system prompt for the extraction.
        allow_external_links: Whether to allow following external links.
        enable_web_search: Whether to enable web search during extraction.
        show_sources: Whether to include source information in results.
        scrape_options: Optional dict with scrape options (e.g., {"formats": ["markdown"]}).
        ignore_invalid_urls: Whether to ignore invalid URLs.
        poll_interval: Interval in seconds for polling extraction status (default: 2).
        timeout: Optional timeout.
        integration: Optional integration identifier.

    Returns:
        A dict with structured extraction results.
    """
    # Pass keyword arguments directly to the SDK method
    result = await app.extract(
        urls=urls,
        prompt=prompt,
        schema=schema,
        system_prompt=system_prompt,
        allow_external_links=allow_external_links,
        enable_web_search=enable_web_search,
        show_sources=show_sources,
        scrape_options=scrape_options,
        ignore_invalid_urls=ignore_invalid_urls,
        poll_interval=poll_interval,
        timeout=timeout,
        integration=integration,
    )
    return result