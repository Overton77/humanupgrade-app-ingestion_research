from langgraph.graph import StateGraph, START, END  
from langgraph.prebuilt import ToolNode 
from typing_extensions import TypedDict, Annotated  
from typing import List, Dict, Any, Optional, Sequence, Literal, Union
from enum import Enum 
from langchain_core.messages import AnyMessage, BaseMessage, ToolMessage, SystemMessage, HumanMessage, filter_messages   
from langchain_openai import ChatOpenAI  
from pydantic import BaseModel, Field  
import operator   
import os   
import uuid
import json
import logging
import aiofiles
import aiofiles.os
from firecrawl import AsyncFirecrawlApp   
from langchain.agents import create_agent  
from langchain_core.prompts import PromptTemplate 
from tavily import AsyncTavilyClient 
from dotenv import load_dotenv 
from langchain.tools import tool, ToolRuntime    
from research_agent.agent_tools.tavily_functions import tavily_search, format_tavily_search_response    
from research_agent.agent_tools.firecrawl_functions import firecrawl_scrape, format_firecrawl_map_response, format_firecrawl_search_response, firecrawl_map, format_firecrawl_map_response 
from research_agent.agent_tools.filesystem_tools import write_file, read_file
from research_agent.medical_db_tools.pub_med_tools import ( 
   pubmed_literature_search_tool 
)     
from datetime import datetime 
from langchain_community.tools import WikipediaQueryRun  
from langchain_community.utilities import WikipediaAPIWrapper   
from research_agent.prompts.summary_prompts import TAVILY_SUMMARY_PROMPT, FIRECRAWL_SCRAPE_PROMPT  
from research_agent.prompts.entity_researcher_prompts import (
    ENTITY_INTEL_RESEARCH_PROMPT,
    ENTITY_INTEL_TOOL_INSTRUCTIONS,
    ENTITY_INTEL_REMINDER_PROMPT,
    ENTITY_INTEL_RESEARCH_RESULT_PROMPT,
) 
from research_agent.prompts.structured_output_prompts import ENTITY_EXTRACTION_PROMPT
from research_agent.biotech_full.output_models import (
    ResearchDirection,
    ResearchEntities,
    EntitiesIntelResearchResult, 
    GeneralCitation, 
    EntityIntelSummary,  
    EntityType, 
    TavilyResultsSummary,
    FirecrawlResultsSummary, 
    EntityIntelResearchOutput
) 

from research_agent.common.logging_utils import get_logger  

logger = get_logger(__name__)



# Base output directory for research artifacts
ENTITY_INTEL_OUTPUT_DIR = "entity_intel_outputs" 


def get_current_date_string() -> str:
    """
    Returns a clean, human-readable date string for prompts.
    Example: 'December 5, 2025'
    """
    return datetime.now().strftime("%B %d, %Y") 



# ============================================================================
# FILE SAVING UTILITIES
# ============================================================================

async def ensure_directory_exists(path: str) -> None:
    """Ensure a directory exists, creating it if necessary."""
    dir_path = os.path.dirname(path)
    if dir_path:
        try:
            await aiofiles.os.makedirs(dir_path, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create directory {dir_path}: {e}")


async def save_json_artifact(
    data: Any,
    direction_id: str,
    artifact_type: str,
    suffix: str = "",
) -> str:
    """
    Save a JSON artifact to disk with structured naming.
    
    Args:
        data: Data to serialize (dict, Pydantic model, or JSON-serializable object)
        direction_id: The research direction ID
        artifact_type: Type of artifact (e.g., 'tavily_search', 'llm_response')
        suffix: Optional suffix for additional context
    
    Returns:
        The file path where the artifact was saved
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = str(uuid.uuid4())[:8]
    
    filename = f"{artifact_type}_{timestamp}_{short_uuid}"
    if suffix:
        filename += f"_{suffix}"
    filename += ".json"
    
    filepath = os.path.join(ENTITY_INTEL_OUTPUT_DIR, direction_id, filename)
    
    await ensure_directory_exists(filepath)
    
    # Convert to JSON-serializable format
    if hasattr(data, "model_dump"):
        json_data = data.model_dump()
    elif hasattr(data, "dict"):
        json_data = data.dict()
    elif isinstance(data, dict):
        json_data = data
    else:
        json_data = {"content": str(data)}
    
    try:
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(json.dumps(json_data, indent=2, default=str, ensure_ascii=False))
        logger.debug(f"Saved artifact: {filepath}")
    except Exception as e:
        logger.error(f"Failed to save artifact {filepath}: {e}")
        return ""
    
    return filepath


async def save_text_artifact(
    content: str,
    direction_id: str,
    artifact_type: str,
    suffix: str = "",
) -> str:
    """
    Save a text artifact to disk.
    
    Args:
        content: Text content to save
        direction_id: The research direction ID
        artifact_type: Type of artifact
        suffix: Optional suffix
    
    Returns:
        The file path where the artifact was saved
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = str(uuid.uuid4())[:8]
    
    filename = f"{artifact_type}_{timestamp}_{short_uuid}"
    if suffix:
        filename += f"_{suffix}"
    filename += ".txt"
    
    filepath = os.path.join(ENTITY_INTEL_OUTPUT_DIR, direction_id, filename)
    
    await ensure_directory_exists(filepath)
    
    try:
        async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
            await f.write(content)
        logger.debug(f"Saved text artifact: {filepath}")
    except Exception as e:
        logger.error(f"Failed to save text artifact {filepath}: {e}")
        return ""
    
    return filepath




load_dotenv() 

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") 

tavily_api_key = os.getenv("TAVILY_API_KEY") 
async_tavily_client = AsyncTavilyClient(api_key=tavily_api_key) 

firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY") 
async_firecrawl_app = AsyncFirecrawlApp(api_key=firecrawl_api_key)  

wikipedia_api_wrapper = WikipediaAPIWrapper( 
    top_k_results=4, 
    doc_content_chars_max=4000, 
) 

wiki_tool = WikipediaQueryRun(api_wrapper=wikipedia_api_wrapper)   

research_model = ChatOpenAI(
    model="gpt-5-mini", 
    reasoning={ 
        "effort": "medium", 
    },
    temperature=0.0,
    output_version="responses/v1",
    max_retries=2,
) 

summary_model = ChatOpenAI(
    model="gpt-5-mini",
    temperature=0.0,
    output_version="responses/v1",
    max_retries=2,
) 

structured_output_model = ChatOpenAI(
    model="gpt-5-mini", 
    reasoning={ 
        "effort": "medium", 
    },
    temperature=0.0,
    output_version="responses/v1",
    max_retries=2,
)






# ============================================================================
# RESEARCH STATE
# ============================================================================

class EntityIntelResearchState(TypedDict, total=False):  
    # Core tool-loop plumbing
    messages: Annotated[Sequence[BaseMessage], operator.add]
    llm_calls: int
    tool_calls: int

    # Context / config for this direction
    direction: ResearchDirection
    episode_context: str          # short summary of episode, guest, etc.

    # Accumulated research data
    research_notes: Annotated[List[str], operator.add]     # human-readable notes from each step
    citations: Annotated[List[str], operator.add]          # URLs / DOIs  

    # File-based context offloading
    file_refs: Annotated[List[str], operator.add]          # paths to intermediate summary files

    final_summary: str 
    steps_taken: int 

    structured_outputs: Annotated[List[BaseModel], operator.add]   

    # Final structured result
    result: EntitiesIntelResearchResult


async def summarize_tavily_web_search(search_results: str, direction_id: str = uuid.uuid4()) -> TavilyResultsSummary:  
    logger.info(f"📝 Summarizing Tavily search results (input length: {len(search_results)} chars)")
    
    agent_instructions = TAVILY_SUMMARY_PROMPT.format(search_results=search_results) 
    web_search_summary_agent = create_agent( 
        summary_model, 
        response_format=TavilyResultsSummary, 

    )   

    web_search_summary_agent_response = await web_search_summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": agent_instructions}]}
    )

    summary = web_search_summary_agent_response["structured_response"]
    logger.info(f"✅ Tavily summary complete: {len(summary.citations)} citations found")
    
    # Save the summary
    await save_json_artifact(
        summary,
        direction_id,
        "tavily_summary",
    )
    
    return summary


async def summarize_firecrawl_scrape(search_results: str, direction_id: str = uuid.uuid4()) -> FirecrawlResultsSummary:  
    logger.info(f"📝 Summarizing Firecrawl scrape results (input length: {len(search_results)} chars)")
    
    agent_instructions = FIRECRAWL_SCRAPE_PROMPT.format(search_results=search_results) 
    web_search_summary_agent = create_agent( 
        summary_model, 
        response_format=FirecrawlResultsSummary, 

    )   

    web_search_summary_agent_response = await web_search_summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": agent_instructions}]}
    )

    summary = web_search_summary_agent_response["structured_response"]
    logger.info(f"✅ Firecrawl summary complete: {len(summary.citations)} citations found")
    
    # Save the summary
    await save_json_artifact(
        summary,
        direction_id,
        "firecrawl_summary",
    )
    
    return summary


# ============================================================================
# RESEARCH TOOLS
# ============================================================================

@tool(
    description="Use Firecrawl to map all relevant URLs from a base URL.",
    parse_docstring=False,
) 
async def firecrawl_map_tool( 
    url: str, 
    search: Optional[str] = None,
    include_subdomains: Optional[bool] = None,
    limit: Optional[int] = None,
    sitemap: Optional[Literal["only", "include", "skip"]] = None,
   
   
) -> str:   
    """Discover and list URLs associated with a base URL (site map / crawl).

    Recommended usage:
    - Use this when you want to systematically explore a specific website
      (e.g., a company site, product site, or knowledge hub).
    - The tool returns a list of URLs with metadata (source, depth, status code).

    Args:
        url (str): The base URL to start from (e.g., "https://example.com").
        search (Optional[str], optional): Optional keyword to filter URLs; only
            URLs matching this term will be returned. Defaults to None.
        include_subdomains (Optional[bool], optional): If True, include subdomains
            in the crawl. Defaults to None (tool default behavior).
        limit (Optional[int], optional): Maximum number of URLs to return.
            Defaults to None (tool default behavior).
        sitemap (Optional[Literal["only", "include", "skip"]], optional): How to
            use the target site's sitemap:
            - "only": only use sitemap data if available.
            - "include": combine sitemap data with crawling.
            - "skip": ignore sitemap and rely on crawling.
            Defaults to None (tool default behavior).

    Returns:
        str: A human-readable summary describing the discovered URLs and any
        relevant metadata, suitable for follow-up scraping with firecrawl_scrape_tool.

    """
    logger.info(f"🗺️  FIRECRAWL MAP: Starting URL mapping for {url}")
    if search:
        logger.info(f"    Filter: '{search}'")

    result = await firecrawl_map(
        app=async_firecrawl_app,
        url=url,
        search=search,
        include_subdomains=include_subdomains,
        limit=limit,
        sitemap=sitemap,
    )

    formatted_result = format_firecrawl_map_response(result) 
    
    # Count URLs found
    url_count = formatted_result.count("http")
    logger.info(f"✅ FIRECRAWL MAP complete: ~{url_count} URLs discovered")

    # Save the raw result
    await save_json_artifact(
        {"url": url, "search": search, "result": result},
        "firecrawl_map",
        "firecrawl_map_raw",
    )

    return formatted_result  


def format_firecrawl_summary_results(summary: FirecrawlResultsSummary) -> str:
    """
    Format a FirecrawlResultsSummary into a readable string,
    emphasizing content fidelity and descriptive metadata.
    """
    lines: List[str] = []
    lines.append("=== Firecrawl Scrape Summary ===")
    lines.append(summary.summary)
    lines.append("")

    lines.append("=== Citations ===")
    if not summary.citations:
        lines.append("(no citations provided)")
    else:
        for c in summary.citations:
            desc_str = f"\n  Description: {c.description}" if c.description else ""
            lines.append(f"- {c.title}\n  URL: {c.url}{desc_str}")

    return "\n".join(lines)


@tool(
    description="Use Firecrawl to turn a URL into readable markdown or text content.",
    parse_docstring=False,
)
async def firecrawl_scrape_tool(  
    runtime: ToolRuntime,  
    url: str,  
    formats: Optional[List[Literal["markdown", "html", "raw", "screenshot"]]] = None,
    include_links: bool = False,
    max_depth: int = 0,
    include_images: bool = False,
) -> str:   

    """Scrape a specific URL and convert the page into digestible content.

    Recommended usage:
    - Use this AFTER you have identified promising URLs (for example via
      Tavily web search or firecrawl_map_tool).
    - In almost all cases, set `formats=["markdown"]` so you get a clean,
      readable markdown representation.
    - Set `include_links=True` if you also want the outgoing links from the page.
    - `max_depth` should usually remain 0 (just this page) unless you explicitly
      want to follow internal links from the starting URL.
    - `include_images=True` can be used when image metadata is important, but
      it is usually not required for text-based summarization.

    Args:
        url (str): The URL to scrape.
        formats (Optional[List[Literal["markdown", "html", "raw", "screenshot"]]],
            optional): Output formats requested from Firecrawl. Typically
            `["markdown"]` for LLM consumption. Defaults to None (tool may use
            a sensible default).
        include_links (bool, optional): If True, include outgoing links from the
            page in the result. Defaults to False.
        max_depth (int, optional): Depth of crawling from the starting URL.
            0 means only this page. Defaults to 0.
        include_images (bool, optional): If True, include image metadata from the
            page. Defaults to False.

    Returns:
        str: A summarized string based on the scraped content, suitable for the
        agent to read, and consistent with any research state updates.

    """
    # Get direction_id for file naming
    direction = runtime.state.get("direction")
    direction_id = direction.id if direction else "unknown"
    
    logger.info(f"🔍 FIRECRAWL SCRAPE: Scraping URL: {url}")

    results = await firecrawl_scrape(async_firecrawl_app, 
        url, 
        formats, 
        include_links, 
        max_depth, 
        include_images 
        ) 

    formatted_results = format_firecrawl_search_response(results)  
    
    # Save raw scrape results
    await save_text_artifact(
        formatted_results,
        direction_id,
        "firecrawl_scrape_raw",
        suffix=url.replace("https://", "").replace("http://", "").replace("/", "_")[:50],
    )

    summary_of_scrape = await summarize_firecrawl_scrape(formatted_results, direction_id)  

    runtime.state.get("citations", []).extend([citation.url for citation in summary_of_scrape.citations])
    runtime.state.get("research_notes", []).append(summary_of_scrape.summary)

    formatted_scrape_summary = format_firecrawl_summary_results(summary_of_scrape) 
    
    logger.info(f"✅ FIRECRAWL SCRAPE complete: {len(summary_of_scrape.citations)} citations extracted")

    return formatted_scrape_summary 


def format_tavily_summary_results(summary: TavilyResultsSummary) -> str:
    """
    Format a TavilyResultsSummary into a clean, readable string
    for logging, notes, or feeding into downstream summarizers.
    """
    lines: List[str] = []
    lines.append("=== Tavily Web Search Summary ===")
    lines.append(summary.summary)
    lines.append("")

    lines.append("=== Citations ===")
    if not summary.citations:
        lines.append("(no citations provided)")
    else:
        for c in summary.citations:
            published_str = f" | Published: {c.published_date}" if c.published_date else ""
            score_str = f" | Score: {c.score:.4f}" if c.score is not None else ""

            lines.append(f"- {c.title}\n  URL: {c.url}{published_str}{score_str}")

    return "\n".join(lines) 


@tool(
    description="Search the web for information about a specific topic or query.",
    parse_docstring=False,
)
async def tavily_web_search_tool(   
    runtime: ToolRuntime,  
    query: str,  
    max_results: int = 5, 
    search_depth: Literal["basic", "advanced"] = "basic",  
    topic: Optional[Literal["general", "news", "finance"]] = "general", 
    include_images: bool = False,  
    include_raw_content: bool | Literal["markdown", "text"] = False,   
    start_date: Optional[str] = None,  
    end_date: Optional[str] = None,  
    
) -> str:    
    """Perform a web search using Tavily and return a summarized view of the results.

    Recommended usage:
    - Use this as a first step when you need broad coverage or multiple viewpoints
      on a topic (companies, products, people, mechanisms, protocols, etc.).
    - Use it to quickly collect top pages and their content before deciding which
      URLs to inspect more deeply with Firecrawl.

    Args:
        query (str): Natural-language search query describing what you want to know.
        max_results (int, optional): Maximum number of results to retrieve.
            Defaults to 5.
        search_depth (Literal["basic", "advanced"], optional): Depth of search.
            "basic" is faster and hits fewer pages; "advanced" is slower but more
            thorough. Defaults to "basic".
        topic (Optional[Literal["general", "news", "finance"]], optional): Topic
            specialization for the search. "general" for broad web search,
            "news" to emphasize recent coverage, "finance" to emphasize financial/
            market-related information. Defaults to "general".
        include_images (bool, optional): If True, include image results metadata.
            Defaults to False.
        include_raw_content (bool | Literal["markdown", "text"], optional): Whether
            and how to include raw page content in the results.
            - False: do not include full page content.
            - "markdown": include raw markdown/text content of pages.
            - "text": include plain text content.
            Defaults to False.
        start_date (Optional[str], optional): Optional start date for search.
            Defaults to None.
        end_date (Optional[str], optional): Optional end date for search.
            Defaults to None.

    Returns:
        str: A human-readable string containing a summary of the results and
        citations/URLs of key sources.

    """
    # Get direction_id for file naming
    direction = runtime.state.get("direction")
    direction_id = direction.id if direction else "unknown"
    
    steps_taken = runtime.state.get("steps_taken", 0) + 1
    runtime.state["steps_taken"] = steps_taken
    
    logger.info(f"🌐 TAVILY SEARCH [{steps_taken}]: '{query[:80]}{'...' if len(query) > 80 else ''}'")
    logger.info(f"    Params: max_results={max_results}, depth={search_depth}, topic={topic}")

    search_results = await tavily_search( 
        client=async_tavily_client, 
        query=query, 
        max_results=max_results, 
        search_depth=search_depth, 
        topic=topic, 
        include_images=include_images, 
        include_raw_content=include_raw_content, 
        start_date=start_date,
        end_date=end_date,
        ) 

    # Save raw search results
    await save_json_artifact(
        {"query": query, "params": {"max_results": max_results, "search_depth": search_depth, "topic": topic}, "results": search_results},
        direction_id,
        "tavily_search_raw",
        suffix=query[:30].replace(" ", "_"),
    )

    formatted_search_results = format_tavily_search_response(search_results)  

    web_search_summary = await summarize_tavily_web_search(formatted_search_results, direction_id)   

    runtime.state.get("citations", []).extend([citation.url for citation in web_search_summary.citations])
    runtime.state.get("research_notes", []).append(web_search_summary.summary)

    web_search_summary_formatted = format_tavily_summary_results(web_search_summary)     
    
    logger.info(f"✅ TAVILY SEARCH complete: {len(web_search_summary.citations)} citations, summary length: {len(web_search_summary.summary)} chars")

    return web_search_summary_formatted 


# ============================================================================
# WRITE ENTITY INTEL SUMMARY TOOL (Entity Profiling + Context Offloading)
# ============================================================================

@tool(
    description="Write a lightweight entity intelligence summary. "
                "Use this after gathering key information about a Person, Business, Product, or Compound.",
    parse_docstring=False,
)
async def write_entity_intel_summary_tool(
    runtime: ToolRuntime,
    entity_type: Literal["person", "business", "product", "compound", "other"],
    entity_name: str,
    synthesis_summary: str,
    key_source_citations: Optional[List[GeneralCitation]] = None,
    open_questions: Optional[List[str]] = None,
    onsite_efficacy_claims: Optional[List[str]] = None,
    related_entities: Optional[List[str]] = None,
) -> str:
    """
    Create a lightweight checkpoint summary for an entity profile.

    Arguments:
        entity_type: The type of entity being profiled 
                     ("person", "business", "product", "compound", or "other").
        entity_name: Primary name of the entity.
        synthesis_summary: A short (3–5 sentence) synthesized summary describing 
                           what has been learned about the entity so far.
        key_sources: A short list of authoritative URLs used in building the profile.
        open_questions: Remaining questions or gaps still requiring investigation.
        onsite_efficacy_claims: Claims found on official sites about mechanisms, 
                                benefits, or efficacy that may need scientific verification.
        related_entities: Names or identifiers of related entities discovered 
                          during the profiling process.

    Returns:
        A confirmation string including the file path where the summary was stored.
    """

    direction = runtime.state.get("direction")
    direction_id = direction.id if direction else "unknown"

    summary = EntityIntelSummary(
        entity_type=EntityType(entity_type),
        entity_name=entity_name,
        synthesis_summary=synthesis_summary.strip(),
        key_source_citations=key_source_citations or [],
        open_questions=open_questions or [],
        onsite_efficacy_claims=onsite_efficacy_claims or [],
        related_entities=related_entities or [],
    )

    filename = f"research/{direction_id}/entity_{entity_type}_{summary.summary_id}.json"
    await write_file(filename, summary.model_dump_json(indent=2))

    # Also record in state
    file_refs = runtime.state.get("file_refs", []) or []
    file_refs.append(filename)
    runtime.state["file_refs"] = file_refs

    # Write a compact note for in-context reflection
    compact_note = (
        f"[ENTITY SUMMARY: {entity_name} ({entity_type})]\n"
        f"Summary: {synthesis_summary}...\n"
        f"Sources: {', '.join([c.url for c in summary.key_source_citations[:8]]) if summary.key_source_citations else 'None'}\n"
        f"Claims: {', '.join(onsite_efficacy_claims) or 'None'}\n"
        f"Open Questions: {', '.join(summary.open_questions) or 'None'}\n"
        f"Related: {', '.join(summary.related_entities) or 'None'}\n"
    )  

    research_notes = runtime.state.get("research_notes", []) or []
    research_notes.append(compact_note)
    runtime.state["research_notes"] = research_notes


    return (
        f"✓ Entity summary saved for '{entity_name}'\n"
        f"  File: {filename}\n"
        f"  Key Sources: {len(summary.key_source_citations)}\n"
        f"  Efficacy Claims: {len(summary.onsite_efficacy_claims)}\n"
        f"  Open Questions: {len(summary.open_questions)}"
    )

# ============================================================================
# ALL TOOLS - Agent has access to everything
# ============================================================================

# All research tools available to the entity intel agent
ENTITY_INTEL_TOOLS = [
    tavily_web_search_tool,
    firecrawl_scrape_tool,
    firecrawl_map_tool,
    wiki_tool,
    pubmed_literature_search_tool,
    write_entity_intel_summary_tool,
]

tools_by_name = {t.name: t for t in ENTITY_INTEL_TOOLS}


def get_tool_instructions(direction: ResearchDirection) -> str:
    """
    Get tool instructions based on the research direction.
    Uses include_scientific_literature flag to guide tool prioritization.
    """
    return ENTITY_INTEL_TOOL_INSTRUCTIONS


def format_list_for_prompt(items: List[str], bullet: str = "-", empty_msg: str = "(none)") -> str:
    """
    Format a list of strings into a nicely formatted string for prompts.
    
    Args:
        items: List of strings to format
        bullet: Bullet character to use (default: "-")
        empty_msg: Message to return if list is empty
    
    Returns:
        Formatted string with one item per line
    """
    if not items:
        return empty_msg
    return "\n".join(f"{bullet} {item}" for item in items)  


# ============================================================================
# GRAPH NODES
# ============================================================================ 

# ============================================================================
# ENTITY INTEL CALL MODEL NODE
# ============================================================================
# Uses ENTITY_INTEL_RESEARCH_PROMPT on first call (llm_calls == 0)
# Switches to ENTITY_INTEL_REMINDER_PROMPT after first call (llm_calls > 0)

async def call_entity_intel_model(state: EntityIntelResearchState) -> EntityIntelResearchState:
    """
    LLM decides what to do next for this entity intel research direction.
    
    Uses the full ENTITY_INTEL_RESEARCH_PROMPT on the first call,
    then switches to the more compact ENTITY_INTEL_REMINDER_PROMPT 
    for subsequent calls to save context window space.
    """
    direction = state["direction"] 
    direction_id = direction.id
    episode_context = state.get("episode_context", "") or "(no episode context provided)"
    notes = state.get("research_notes", [])
    llm_calls = state.get("llm_calls", 0)
    steps_taken = state.get("steps_taken", 0)
    
    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"🤖 CALL MODEL [{direction_id}] - LLM Call #{llm_calls + 1}")
    logger.info(f"    Title: {direction.title[:60]}{'...' if len(direction.title) > 60 else ''}")
    logger.info(f"    Steps: {steps_taken}/{direction.max_steps}, Notes: {len(notes)}")
    logger.info(f"{'='*60}")

    # Agent gets entity intel tools
    model_with_tools = research_model.bind_tools(ENTITY_INTEL_TOOLS) 

    tool_instructions = get_tool_instructions(direction)

    # Format lists for prompt insertion
    research_questions_str = format_list_for_prompt(
        direction.research_questions, 
        bullet="•", 
        empty_msg="(no specific questions provided)"
    )
    primary_entities_str = format_list_for_prompt(
        direction.primary_entities, 
        bullet="•", 
        empty_msg="(no primary entities specified)"
    )
    claimed_by_str = format_list_for_prompt(
        direction.claimed_by, 
        bullet="•", 
        empty_msg="(none)"
    )
    key_outcomes_str = format_list_for_prompt(
        direction.key_outcomes_of_interest, 
        bullet="•", 
        empty_msg="(none)"
    )
    key_mechanisms_str = format_list_for_prompt(
        direction.key_mechanisms_to_examine, 
        bullet="•", 
        empty_msg="(none)"
    )

    # Choose prompt based on whether this is the first call or a follow-up
    if llm_calls == 0:
        # First call: Use full ENTITY_INTEL_RESEARCH_PROMPT with complete context
        logger.info(f"    Using: ENTITY_INTEL_RESEARCH_PROMPT (first call)")
        system = ENTITY_INTEL_RESEARCH_PROMPT.format(
            current_date=get_current_date_string(),
            direction_id=direction.id,
            episode_id=direction.episode_id,
            direction_title=direction.title,
            direction_type=direction.direction_type.value,
            research_questions=research_questions_str,
            primary_entities=primary_entities_str,
            claim_text=direction.claim_text or "(no specific claim)",
            claimed_by=claimed_by_str,
            key_outcomes_of_interest=key_outcomes_str,
            key_mechanisms_to_examine=key_mechanisms_str,
            priority=direction.priority,
            max_steps=direction.max_steps,
            episode_context=episode_context,
            tool_instructions=tool_instructions,
        )
    else:
        # Follow-up calls: Use compact ENTITY_INTEL_REMINDER_PROMPT
        logger.info(f"    Using: ENTITY_INTEL_REMINDER_PROMPT (follow-up call #{llm_calls + 1})")
        system = ENTITY_INTEL_REMINDER_PROMPT.format(
            current_date=get_current_date_string(),
            direction_id=direction.id,
            direction_type=direction.direction_type.value,
            research_questions=research_questions_str,
            primary_entities=primary_entities_str,
            claim_text=direction.claim_text or "(no specific claim)",
            max_steps=direction.max_steps,
        )
   
    # Existing conversation messages in this subgraph
    messages = list(state.get("messages", []))
    
    logger.debug(f"    Messages in context: {len(messages)}")

    ai_msg = await model_with_tools.ainvoke([system] + messages)
    
    # Log what the model decided to do
    tool_calls = getattr(ai_msg, "tool_calls", []) or []
    if tool_calls:
        logger.info(f"🔧 Model requested {len(tool_calls)} tool call(s):")
        for tc in tool_calls:
            tool_name = tc.get("name", "unknown")
            args = tc.get("args", {})
            # Truncate long args for display
            args_str = str(args)[:100] + "..." if len(str(args)) > 100 else str(args)
            logger.info(f"    → {tool_name}: {args_str}")
    else:
        content_preview = str(ai_msg.content)[:200] if ai_msg.content else "(no content)"
        logger.info(f"💬 Model response (no tools): {content_preview}...")
    
    # Save the LLM response
    await save_json_artifact(
        {
            "role": "assistant",
            "content": ai_msg.content,
            "tool_calls": [{"name": tc.get("name"), "args": tc.get("args")} for tc in tool_calls] if tool_calls else [],
            "prompt_type": "research" if llm_calls == 0 else "reminder",
        },
        direction_id,
        "llm_response",
        suffix=f"call_{llm_calls + 1}",
    )

    return {
        "messages": [ai_msg],
        "llm_calls": llm_calls + 1,
    }



_prebuilt_tool_node = ToolNode(ENTITY_INTEL_TOOLS)


async def tool_node(state: EntityIntelResearchState) -> EntityIntelResearchState:
    """
    Execute tool calls requested by the last AI message.
    
    Uses the prebuilt ToolNode which properly injects ToolRuntime into tools,
    with additional logic for step counting and max_steps enforcement.
    """
    direction = state["direction"]
    direction_id = direction.id
    last_msg = state["messages"][-1]
    tool_calls = getattr(last_msg, "tool_calls", []) or []

    max_steps = direction.max_steps
    steps_taken = state.get("steps_taken", 0)
    
    logger.info(f"")
    logger.info(f"⚙️  TOOL NODE [{direction_id}] - Step {steps_taken + 1}/{max_steps}")

    # Safety: if we've hit max_steps, tell the model to finalize
    if steps_taken >= max_steps:
        logger.warning(f"⚠️  MAX STEPS REACHED ({max_steps}). Requesting model to finalize.")
        summary_msg = SystemMessage(
            content=(
                "You have reached the maximum number of tool steps "
                "for this entity intel research direction. Please stop calling tools, "
                "write a final entity profile using write_entity_intel_summary_tool if you haven't, "
                "and prepare to finalize your entity profiles."
            )
        )
        return {
            "messages": [summary_msg],
        }

    if not tool_calls:
        logger.debug("    No tool calls to execute")
        # Nothing to do; just return state unchanged
        return {"messages": []}
    
    logger.info(f"    Executing {len(tool_calls)} tool(s)...")

    # Use the prebuilt ToolNode which handles ToolRuntime injection
    # The ToolNode.ainvoke() receives the full state and properly injects
    # the runtime into tools that have ToolRuntime parameters
    try:
        tool_result = await _prebuilt_tool_node.ainvoke(state)
        
        # Log tool results
        result_messages = tool_result.get("messages", [])
        for msg in result_messages:
            if hasattr(msg, "name") and hasattr(msg, "content"):
                content_preview = str(msg.content)[:150] + "..." if len(str(msg.content)) > 150 else str(msg.content)
                logger.info(f"    ✓ {msg.name}: {content_preview}")
                
                # Save tool result
                await save_text_artifact(
                    str(msg.content),
                    direction_id,
                    f"tool_result_{msg.name}",
                )
        
        logger.info(f"✅ TOOL NODE complete: {len(result_messages)} result(s)")
        
    except Exception as e:
        logger.error(f"❌ TOOL NODE ERROR: {e}")
        # Save error info
        await save_json_artifact(
            {"error": str(e), "tool_calls": [tc.get("name") for tc in tool_calls]},
            direction_id,
            "tool_error",
        )
        raise

    # Merge the tool results with our step counting
    return {
        "messages": tool_result.get("messages", []),
        "tool_calls": state.get("tool_calls", 0) + 1,
        "steps_taken": steps_taken + 1,
    }

    

# ============================================================================
# RESEARCH OUTPUT NODE (Updated to read from files)
# ============================================================================

research_result_model = ChatOpenAI( 
    model="gpt-5.1",  
    temperature=0.0, 
    output_version="responses/v1",
    max_retries=2,
)


async def research_output_node(state: EntityIntelResearchState) -> EntityIntelResearchState:
    """
    Produce a DirectionResearchResult by aggregating file-based summaries
    and research notes via structured LLM call.
    """
    direction = state["direction"]
    direction_id = direction.id
    episode_context = state.get("episode_context", "") or "(none)"
    file_refs = state.get("file_refs", []) or []
    citations = state.get("citations", []) or []
    notes = state.get("research_notes", []) or []  

    original_research_questions = direction.research_questions or [] 

    original_research_primary_entities = direction.primary_entities or []   

    original_key_outcomes_of_interest = direction.key_outcomes_of_interest or []   

    original_key_mechanisms_to_examine = direction.key_mechanisms_to_examine or []   


    
    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"📊 RESEARCH OUTPUT NODE [{direction_id}]")
    logger.info(f"{'='*60}")

    # Aggregate intermediate summaries from files
    aggregated_content = ""
    
    if file_refs:
        intermediate_summaries = []
        for file_path in file_refs:
            try:
                content = await read_file(file_path)
                intermediate_summaries.append(f"--- File: {file_path} ---\n{content}")
                logger.debug(f"    Loaded file: {file_path}")
            except FileNotFoundError:
                logger.warning(f"    File not found: {file_path}")
                # File not found, skip (notes should have backup)
                continue
            except Exception as e:
                logger.warning(f"    Error reading {file_path}: {e}")
                # Log but continue
                continue
        
        if intermediate_summaries:
            aggregated_content = "=== INTERMEDIATE RESEARCH SUMMARIES (from files) ===\n\n"
            aggregated_content += "\n\n".join(intermediate_summaries)
            aggregated_content += "\n\n"
    
    # Add research_notes (which may include compact summaries as backup)
    if notes:
        aggregated_content += "=== RESEARCH NOTES ===\n\n"
        aggregated_content += "\n\n---\n\n".join(notes)
    
    # If nothing was collected, note that
    if not aggregated_content.strip():
        aggregated_content = "(no research notes or summaries collected)"
        logger.warning("    No research content collected!")
    else:
        logger.info(f"    Aggregated content length: {len(aggregated_content)} chars")

    # Save the aggregated content before sending to LLM
    await save_text_artifact(
        aggregated_content,
        direction_id,
        "aggregated_research_content",
    )

    prompt = ENTITY_INTEL_RESEARCH_RESULT_PROMPT.format(
        original_research_questions="\n".join(
            f"- {q}" for q in original_research_questions
        ) or "None specified.",
        original_research_primary_entities="\n".join(
            f"- {e}" for e in original_research_primary_entities
        ) or "None specified.",
        original_key_outcomes_of_interest="\n".join(
            f"- {o}" for o in original_key_outcomes_of_interest
        ) or "None specified.",
        original_key_mechanisms_to_examine="\n".join(
            f"- {m}" for m in original_key_mechanisms_to_examine
        ) or "None specified.",
        research_notes=aggregated_content, 
    )

    logger.info(f"    Generating structured research result...")

    # Use strong model with structured output
    result_agent = create_agent(
        research_result_model,
        response_format=EntityIntelResearchOutput,
    )

    agent_response = await result_agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]}
    )

    entities_intel_result: EntityIntelResearchOutput = agent_response["structured_response"] 

    final_entity_intel_result: EntitiesIntelResearchResult = EntitiesIntelResearchResult(
        direction_id=direction_id,
        extensive_summary=entities_intel_result.extensive_summary,
        entity_intel_ids=entities_intel_result.entity_intel_ids,
        key_findings=entities_intel_result.key_findings,
        key_source_citations=entities_intel_result.key_source_citations,
    )


    
    # Log result summary
    logger.info(f"✅ RESEARCH OUTPUT complete:")
    logger.info(f"    Summary length: {len(final_entity_intel_result.extensive_summary) if final_entity_intel_result.extensive_summary else 0} chars")
    logger.info(f"    Key findings: {len(final_entity_intel_result.key_findings) if final_entity_intel_result.key_findings else 0}")
    logger.info(f"    Confidence: {final_entity_intel_result.confidence_score if hasattr(final_entity_intel_result, 'confidence_score') else 'N/A'}")
    
    # Save the final research result
    await save_json_artifact(
        final_entity_intel_result,
        direction_id,
        "final_entity_intel_result_final",
    )

    # Only update the parts we intend to change; LangGraph will merge this into state.
    return {
        "result": final_entity_intel_result,
    }


# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================

def should_continue_entity_intel(
    state: EntityIntelResearchState,
) -> Literal["tool_node", "entity_intel_output_node"]:
    """Route based on tool calls and step budget for entity intel research."""
    direction_id = state["direction"].id
    messages = state.get("messages", [])
    if not messages:
        logger.info(f"🔀 ROUTING [{direction_id}]: No messages → entity_intel_output_node")
        return "entity_intel_output_node"

    last_message = messages[-1]
    steps_taken = state.get("steps_taken", 0)
    max_steps = state["direction"].max_steps
    
    has_tool_calls = bool(getattr(last_message, "tool_calls", None))
    within_budget = steps_taken < max_steps

    if has_tool_calls and within_budget:
        logger.info(f"🔀 ROUTING [{direction_id}]: Tool calls present, step {steps_taken}/{max_steps} → tool_node")
        return "tool_node"
    
    if has_tool_calls and not within_budget:
        logger.info(f"🔀 ROUTING [{direction_id}]: Tool calls present but budget exhausted ({steps_taken}/{max_steps}) → entity_intel_output_node")
    else:
        logger.info(f"🔀 ROUTING [{direction_id}]: No tool calls → entity_intel_output_node")

    return "entity_intel_output_node"  
    

# ============================================================================
# ENTITY EXTRACTION MODEL
# ============================================================================

entity_extraction_model = ChatOpenAI(
    model="gpt-5-mini",
    temperature=0.0,
    max_retries=2,
)


# ============================================================================
# SINGLE-PASS ENTITY EXTRACTION NODE
# ============================================================================

async def extract_structured_entities(state: EntityIntelResearchState) -> EntityIntelResearchState:
    """
    Single-pass entity extraction using structured output.
    
    Extracts businesses, products, people, compounds, and case studies
    from the research results in one deterministic call.
    """
    direction = state["direction"]
    direction_id = direction.id
    result = state.get("result")
    key_source_citations = result.key_source_citations or [] 

    entity_intel_ids = result.entity_intel_ids or []   

    
    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"🏷️  ENTITY EXTRACTION [{direction_id}]")
    logger.info(f"    Title: {direction.title[:60]}{'...' if len(direction.title) > 60 else ''}")
    logger.info(f"{'='*60}")
    
    # Build the extraction prompt
    extensive_summary = (
        result.extensive_summary if result and result.extensive_summary else "(no summary available)"
    )
    key_findings = (
        "\n".join(f"- {f}" for f in result.key_findings) 
        if result and result.key_findings 
        else "(no key findings)"
    )
    citations_text = "\n".join(
        f"- {c.title}: {c.url}" if c.title else f"- {c.url}"
        for c in key_source_citations
    ) if key_source_citations else "(no citations collected)"
    
    logger.info(f"    Input summary length: {len(extensive_summary)} chars")
    logger.info(f"    Key findings count: {len(result.key_findings) if result and result.key_findings else 0}")
    
    prompt = ENTITY_EXTRACTION_PROMPT.format(
        extensive_summary=extensive_summary,
        key_findings=key_findings,
        citations=citations_text,
        entity_intel_ids="\n".join(f"- {e}" for e in entity_intel_ids) or "(none identified)",
)

    entity_extraction_agent = create_agent( 
        entity_extraction_model, 
        response_format=ResearchEntities,  
    )
    

    
    try:
        logger.info(f"    Extracting entities...")
        response_data = await entity_extraction_agent.ainvoke([ 
            {"role": "system", "content": prompt}
        ]) 

        entities: ResearchEntities = response_data["structured_response"]  
    except Exception as e:
        # If extraction fails, return empty entities
        logger.error(f"❌ Entity extraction failed: {e}")
        await save_json_artifact(
            {"error": str(e)},
            direction_id,
            "entity_extraction_error",
        )
        entities = ResearchEntities()
    
    # Collect all extracted entities
    all_outputs: List[BaseModel] = []
    
    for business in entities.businesses:
        all_outputs.append(business)
    
    for product in entities.products:
        all_outputs.append(product)
    
    for person in entities.people:
        all_outputs.append(person)
    
    for compound in entities.compounds:
        all_outputs.append(compound)
    
    for case_study in entities.case_studies:
        all_outputs.append(case_study)
    
    # Log extraction results
    logger.info(f"✅ ENTITY EXTRACTION complete:")
    logger.info(f"    Businesses: {len(entities.businesses)}")
    logger.info(f"    Products: {len(entities.products)}")
    logger.info(f"    People: {len(entities.people)}")
    logger.info(f"    Compounds: {len(entities.compounds)}")
    logger.info(f"    Case Studies: {len(entities.case_studies)}")
    logger.info(f"    TOTAL ENTITIES: {len(all_outputs)}")
    
    # Save extracted entities
    await save_json_artifact(
        {
            "businesses": [b.model_dump() if hasattr(b, 'model_dump') else str(b) for b in entities.businesses],
            "products": [p.model_dump() if hasattr(p, 'model_dump') else str(p) for p in entities.products],
            "people": [p.model_dump() if hasattr(p, 'model_dump') else str(p) for p in entities.people],
            "compounds": [c.model_dump() if hasattr(c, 'model_dump') else str(c) for c in entities.compounds],
            "case_studies": [cs.model_dump() if hasattr(cs, 'model_dump') else str(cs) for cs in entities.case_studies],
        },
        direction_id,
        "extracted_entities",
    )
    
    return {
        "structured_outputs": all_outputs,
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ============================================================================
# BUILD THE ENTITY INTEL SUBGRAPH
# ============================================================================

entity_intel_subgraph_builder = StateGraph(EntityIntelResearchState)

# Entity intel research loop nodes
entity_intel_subgraph_builder.add_node("call_entity_intel_model", call_entity_intel_model)
entity_intel_subgraph_builder.add_node("tool_node", tool_node)
entity_intel_subgraph_builder.add_node("entity_intel_output_node", research_output_node)

# Entity extraction node (single-pass, no tool loop)
entity_intel_subgraph_builder.add_node("extract_entities", extract_structured_entities)

# Entry point
entity_intel_subgraph_builder.set_entry_point("call_entity_intel_model")

# LLM node conditionally goes to tool loop or to final output
entity_intel_subgraph_builder.add_conditional_edges(
    "call_entity_intel_model",
    should_continue_entity_intel,
    {
        "tool_node": "tool_node",
        "entity_intel_output_node": "entity_intel_output_node",
    },
)

# After tools, go back to the LLM
entity_intel_subgraph_builder.add_edge("tool_node", "call_entity_intel_model") 

# After entity intel output, extract entities then end
entity_intel_subgraph_builder.add_edge("entity_intel_output_node", "extract_entities")
entity_intel_subgraph_builder.add_edge("extract_entities", END)

# Compile subgraph
# entity_intel_subgraph = entity_intel_subgraph_builder.compile()
