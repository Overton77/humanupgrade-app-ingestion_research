from langgraph.graph import StateGraph, START, END  
from langgraph.prebuilt import ToolNode, InjectedState  
from typing_extensions import TypedDict, Annotated  
from typing import List, Dict, Any, Optional, Sequence, Literal, Union 
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
from research_agent.prompts.evidence_researcher_prompts import (
    EVIDENCE_TOOL_INSTRUCTIONS,
    EVIDENCE_RESEARCH_PROMPT,
    EVIDENCE_RESEARCH_REMINDER_PROMPT,
    CLAIM_VALIDATION_STRATEGY,
    MECHANISM_EXPLANATION_STRATEGY,
    RISK_BENEFIT_STRATEGY,
    COMPARATIVE_EFFECTIVENESS_STRATEGY,
    CLAIM_VALIDATION_REMINDER,
    MECHANISM_EXPLANATION_REMINDER,
    RISK_BENEFIT_REMINDER,
    COMPARATIVE_EFFECTIVENESS_REMINDER,
    EVIDENCE_RESULT_PROMPT,
    ADVICE_SNIPPET_PROMPT,
    EXTRACT_CLAIM_VALIDATION_PROMPT,
    EXTRACT_MECHANISM_EXPLANATION_PROMPT,
    EXTRACT_RISK_BENEFIT_PROMPT,
    EXTRACT_COMPARATIVE_ANALYSIS_PROMPT,
    EvidenceIntermediateSummary,
)
from research_agent.output_models import (
    ResearchDirection, 
    ResearchDirectionType, 
    TavilyResultsSummary,
    FirecrawlResultsSummary, 
    
) 

from research_agent.graph_states.evidence_research_subgraph import (
    EvidenceResearchResult,
    ClaimValidation,
    MechanismPathway,
    MechanismExplanation,
    Benefit,
    Risk,
    RiskBenefitProfile,
    ComparativeAnalysis,
    EvidenceItem,
    AdviceSnippet,
    AdviceSnippets, 
    EvidenceResearchOutput, 
)

from research_agent.common.logging_utils import get_logger  

logger = get_logger(__name__)

# Base output directory for research artifacts
EVIDENCE_RESEARCH_OUTPUT_DIR = "evidence_research_outputs" 

openai_web_search = {"type": "web_search"} 


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
    
    filepath = os.path.join(EVIDENCE_RESEARCH_OUTPUT_DIR, direction_id, filename)
    
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
    
    filepath = os.path.join(EVIDENCE_RESEARCH_OUTPUT_DIR, direction_id, filename)
    
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


def get_current_date_string() -> str:
    """
    Returns a clean, human-readable date string for prompts.
    Example: 'December 5, 2025'
    """
    return datetime.now().strftime("%B %d, %Y") 


# ============================================================================
# INTERMEDIATE SUMMARY MODEL (for file-based context offloading)
# ============================================================================

class EvidenceIntermediateSummary(BaseModel):
    """Enhanced intermediate summary for evidence research."""
    summary_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    direction_id: str
    direction_type: ResearchDirectionType
    
    topic_focus: str = Field(..., description="What aspect of research this summary covers")
    synthesis: str = Field(..., description="Synthesized findings so far")
    confidence: float = Field(..., ge=0.0, le=1.0)
    
    # Evidence-specific fields
    evidence_items_collected: List[EvidenceItem] = Field(default_factory=list)
    
    # Type-specific progress tracking
    claim_validation_progress: Optional[Dict[str, Any]] = Field(
        None,
        description="For CLAIM_VALIDATION: current verdict, supporting/contradicting evidence counts"
    )
    
    mechanism_explanation_progress: Optional[Dict[str, Any]] = Field(
        None,
        description="For MECHANISM_EXPLANATION: pathway steps identified so far"
    )
    
    risk_benefit_progress: Optional[Dict[str, Any]] = Field(
        None,
        description="For RISK_BENEFIT_PROFILE: benefits and risks tallied"
    )
    
    comparative_progress: Optional[Dict[str, Any]] = Field(
        None,
        description="For COMPARATIVE_EFFECTIVENESS: comparators identified"
    )
    
    open_questions: List[str] = Field(default_factory=list)
    key_sources: List[str] = Field(default_factory=list)
    
    next_steps_recommended: List[str] = Field(
        default_factory=list,
        description="What the agent should investigate next"
    )

# ============================================================================
# RESEARCH STATE
# ============================================================================

class EvidenceResearchState(TypedDict, total=False):  
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
    evidence_items: Annotated[List[EvidenceItem], operator.add]  # structured evidence items

    # File-based context offloading
    file_refs: Annotated[List[str], operator.add]          # paths to intermediate summary files

    # Progress tracking counters
    steps_taken: int 
    summaries_written: int  # count of intermediate summaries

    # Type-specific progress tracking (appended as research progresses)
    # Each entry in the list is a progress snapshot from write_evidence_summary_tool
    claim_validation_progress: Annotated[List[Dict[str, Any]], operator.add]  # verdict evolution, evidence counts
    mechanism_explanation_progress: Annotated[List[Dict[str, Any]], operator.add]  # pathway steps, molecules
    risk_benefit_progress: Annotated[List[Dict[str, Any]], operator.add]  # benefits/risks tallied
    comparative_progress: Annotated[List[Dict[str, Any]], operator.add]  # comparators, rankings

    structured_outputs: Annotated[List[BaseModel], operator.add]   

    # Final structured result
    result: EvidenceResearchResult


# ============================================================================
# LLM MODELS
# ============================================================================

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
    model="gpt-5-nano",
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



async def summarize_tavily_web_search(search_results: str, direction_id: str = "unknown") -> TavilyResultsSummary:  
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


async def summarize_firecrawl_scrape(search_results: str, direction_id: str = "unknown") -> FirecrawlResultsSummary:  
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
# WRITE EVIDENCE SUMMARY TOOL (Incremental Synthesis + Progress Tracking)
# ============================================================================

@tool(
    description=(
        "Write an intermediate evidence summary to consolidate findings and track progress. "
        "Use this after gathering substantial evidence (5-7 studies or sources) on a sub-topic."
    ),
    parse_docstring=False,
)
async def write_evidence_summary_tool(
    runtime: ToolRuntime,
    topic_focus: str,
    synthesis: str,
    confidence: float,
    open_questions: List[str],
    key_sources: List[str],
    progress_update: Optional[Dict[str, Any]] = None,
    next_steps_recommended: Optional[List[str]] = None,
) -> str:
    """
    Consolidate evidence research findings into an intermediate summary with progress tracking.
    
    Call this tool when you have gathered enough evidence on a specific aspect and want to:
    1. Free up context by offloading findings to a file
    2. Create a checkpoint with type-specific progress tracking
    3. Guide next research steps
    
    Args:
        topic_focus (str): What specific aspect this summary covers 
            (e.g., "supporting evidence for claim", "mechanism pathway mapping", 
            "benefit-risk balance for elderly").
        synthesis (str): Your synthesized understanding (2-4 paragraphs).
            Integrate evidence strength, limitations, and key insights.
        confidence (float): 0.0-1.0 confidence score for these findings.
            - 0.0-0.3: Low (limited/contradictory sources)
            - 0.4-0.6: Medium (some evidence, gaps remain)
            - 0.7-1.0: High (strong evidence, multiple sources agree)
        open_questions (List[str]): Questions that remain unanswered.
        key_sources (List[str]): Most important PMIDs/DOIs/URLs (2-5 sources).
        progress_update (Optional[Dict[str, Any]]): Type-specific progress data.
            For CLAIM_VALIDATION: {"verdict_leaning": "partially_supported", 
                                   "supporting_count": 5, "contradicting_count": 2}
            For MECHANISM_EXPLANATION: {"pathway_steps_mapped": 4, 
                                       "molecules_identified": ["Nrf2", "SOD"]}
            For RISK_BENEFIT: {"benefits_count": 4, "risks_count": 3, 
                              "assessment_leaning": "favorable"}
            For COMPARATIVE: {"comparators_found": ["intervention_a", "intervention_b"], 
                            "ranking_emerging": ["primary", "a", "b"]}
        next_steps_recommended (Optional[List[str]]): What to investigate next.
    
    Returns:
        str: Confirmation with the file path where summary was stored.
    """
    direction = runtime.state.get("direction")
    direction_id = direction.id if direction else "unknown"
    direction_type = direction.direction_type if direction else None
    
    logger.info(f"📄 WRITE EVIDENCE SUMMARY: '{topic_focus}' (confidence: {confidence:.2f})")
    logger.info(f"    Type: {direction_type.value if direction_type else 'unknown'}")
    logger.info(f"    Open questions: {len(open_questions)}, Key sources: {len(key_sources)}")
    
    # Create the EvidenceIntermediateSummary model
    summary = EvidenceIntermediateSummary(
        direction_id=direction_id,
        direction_type=direction_type if direction_type else ResearchDirectionType.CLAIM_VALIDATION,
        topic_focus=topic_focus,
        synthesis=synthesis,
        confidence=confidence,
        open_questions=open_questions,
        key_sources=key_sources,
        next_steps_recommended=next_steps_recommended or [],
    )
    
    # Set type-specific progress based on direction_type
    if direction_type and progress_update:
        if direction_type == ResearchDirectionType.CLAIM_VALIDATION:
            summary.claim_validation_progress = progress_update
        elif direction_type == ResearchDirectionType.MECHANISM_EXPLANATION:
            summary.mechanism_explanation_progress = progress_update
        elif direction_type == ResearchDirectionType.RISK_BENEFIT_PROFILE:
            summary.risk_benefit_progress = progress_update
        elif direction_type == ResearchDirectionType.COMPARATIVE_EFFECTIVENESS:
            summary.comparative_progress = progress_update
    
    # Write to file system (under research/<direction_id>/)
    filename = f"research/{direction_id}/evidence_summary_{summary.summary_id}.json"
    await write_file(filename, summary.model_dump_json(indent=2))
    
    # Also save to research_outputs directory
    await save_json_artifact(
        summary,
        direction_id,
        "evidence_intermediate_summary",
        suffix=topic_focus[:30].replace(" ", "_"),
    )
    
    # Track file reference in state
    file_refs = runtime.state.get("file_refs", [])
    if file_refs is None:
        file_refs = []
    file_refs.append(filename)
    runtime.state["file_refs"] = file_refs
    
    # Update summaries_written counter
    summaries_written = runtime.state.get("summaries_written", 0)
    runtime.state["summaries_written"] = summaries_written + 1
    
    # UPDATE TYPE-SPECIFIC PROGRESS IN STATE (APPEND, NOT OVERWRITE)
    if direction_type and progress_update:
        if direction_type == ResearchDirectionType.CLAIM_VALIDATION:
            # Get current progress list and append new update
            claim_progress = runtime.state.get("claim_validation_progress", [])
            if claim_progress is None:
                claim_progress = []
            claim_progress.append(progress_update)
            runtime.state["claim_validation_progress"] = claim_progress
            logger.info(f"    Appended to claim_validation_progress (total entries: {len(claim_progress)})")
            
        elif direction_type == ResearchDirectionType.MECHANISM_EXPLANATION:
            # Get current progress list and append new update
            mechanism_progress = runtime.state.get("mechanism_explanation_progress", [])
            if mechanism_progress is None:
                mechanism_progress = []
            mechanism_progress.append(progress_update)
            runtime.state["mechanism_explanation_progress"] = mechanism_progress
            logger.info(f"    Appended to mechanism_explanation_progress (total entries: {len(mechanism_progress)})")
            
        elif direction_type == ResearchDirectionType.RISK_BENEFIT_PROFILE:
            # Get current progress list and append new update
            risk_benefit_prog = runtime.state.get("risk_benefit_progress", [])
            if risk_benefit_prog is None:
                risk_benefit_prog = []
            risk_benefit_prog.append(progress_update)
            runtime.state["risk_benefit_progress"] = risk_benefit_prog
            logger.info(f"    Appended to risk_benefit_progress (total entries: {len(risk_benefit_prog)})")
            
        elif direction_type == ResearchDirectionType.COMPARATIVE_EFFECTIVENESS:
            # Get current progress list and append new update
            comparative_prog = runtime.state.get("comparative_progress", [])
            if comparative_prog is None:
                comparative_prog = []
            comparative_prog.append(progress_update)
            runtime.state["comparative_progress"] = comparative_prog
            logger.info(f"    Appended to comparative_progress (total entries: {len(comparative_prog)})")
    
    # Also add compact version to research_notes
    progress_str = f"\nProgress Update: {progress_update}" if progress_update else ""
    next_steps_str = f"\nNext Steps: {'; '.join(next_steps_recommended)}" if next_steps_recommended else ""
    
    compact_note = (
        f"[EVIDENCE SUMMARY: {topic_focus}]\n"
        f"Confidence: {confidence}\n\n"
        f"{synthesis}\n\n"
        f"Open Questions: {'; '.join(open_questions) if open_questions else 'None'}\n"
        f"Key Sources: {', '.join(key_sources) if key_sources else 'None cited'}"
        f"{progress_str}"
        f"{next_steps_str}"
    )
    research_notes = runtime.state.get("research_notes", [])
    if research_notes is None:
        research_notes = []
    research_notes.append(compact_note)
    runtime.state["research_notes"] = research_notes
    
    logger.info(f"✅ WRITE EVIDENCE SUMMARY complete: saved to {filename}")
    
    return (
        f"✓ Evidence summary written to {filename}\n"
        f"  Topic: {topic_focus}\n"
        f"  Confidence: {confidence}\n"
        f"  Open questions: {', '.join(open_questions) if open_questions else 'None'}\n"
        f"  Progress tracked: {bool(progress_update)}\n\n"
        f"Continue researching other aspects or stop if you have sufficient evidence."
    )


# ============================================================================
# ALL TOOLS - Agent has access to everything
# ============================================================================

# All evidence research tools available to the agent
ALL_EVIDENCE_RESEARCH_TOOLS = [
    tavily_web_search_tool,
    firecrawl_scrape_tool,
    firecrawl_map_tool,  
    wiki_tool,
    pubmed_literature_search_tool,
    write_evidence_summary_tool,
]

tools_by_name = {t.name: t for t in ALL_EVIDENCE_RESEARCH_TOOLS}


def get_evidence_tool_instructions() -> str:
    """
    Get evidence-specific tool instructions based on the research direction.
    """
    
    
    return EVIDENCE_TOOL_INSTRUCTIONS


def get_direction_type_strategy(direction_type: ResearchDirectionType) -> str:
    """Get the strategy text based on direction type."""
    strategy_map = {
        ResearchDirectionType.CLAIM_VALIDATION: CLAIM_VALIDATION_STRATEGY,
        ResearchDirectionType.MECHANISM_EXPLANATION: MECHANISM_EXPLANATION_STRATEGY,
        ResearchDirectionType.RISK_BENEFIT_PROFILE: RISK_BENEFIT_STRATEGY,
        ResearchDirectionType.COMPARATIVE_EFFECTIVENESS: COMPARATIVE_EFFECTIVENESS_STRATEGY,
    }
    return strategy_map.get(direction_type, "")


def get_direction_type_reminder(direction_type: ResearchDirectionType) -> str:
    """Get the reminder text based on direction type."""
    reminder_map = {
        ResearchDirectionType.CLAIM_VALIDATION: CLAIM_VALIDATION_REMINDER,
        ResearchDirectionType.MECHANISM_EXPLANATION: MECHANISM_EXPLANATION_REMINDER,
        ResearchDirectionType.RISK_BENEFIT_PROFILE: RISK_BENEFIT_REMINDER,
        ResearchDirectionType.COMPARATIVE_EFFECTIVENESS: COMPARATIVE_EFFECTIVENESS_REMINDER,
    }
    return reminder_map.get(direction_type, "")


# ============================================================================
# GRAPH NODES
# ============================================================================ 

# Figure out how to use memory injection and a compressed research prompt after the first and after (some n ) 
# number of message iterations 

async def call_evidence_model(state: EvidenceResearchState) -> EvidenceResearchState:
    """
    LLM decides what to do next for this evidence research direction.
    Uses evidence-specific prompts with type-specific strategies.
    """
    direction = state["direction"] 
    direction_id = direction.id
    direction_type = direction.direction_type
    episode_context = state.get("episode_context", "")
    notes = state.get("research_notes", [])
    llm_calls = state.get("llm_calls", 0)
    steps_taken = state.get("steps_taken", 0)
    summaries_written = state.get("summaries_written", 0)
    citations_count = len(state.get("citations", []))
    
    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"🤖 CALL EVIDENCE MODEL [{direction_id}] - LLM Call #{llm_calls + 1}")
    logger.info(f"    Type: {direction_type.value}")
    logger.info(f"    Title: {direction.title[:60]}{'...' if len(direction.title) > 60 else ''}")
    logger.info(f"    Steps: {steps_taken}/{direction.max_steps}, Summaries: {summaries_written}, Citations: {citations_count}")
    logger.info(f"{'='*60}")

    # Agent gets ALL evidence research tools
    model_with_tools = research_model.bind_tools(ALL_EVIDENCE_RESEARCH_TOOLS) 

    tool_instructions = get_evidence_tool_instructions()
    direction_type_strategy = get_direction_type_strategy(direction_type)

    # Use comprehensive prompt on first call, reminder on subsequent calls
    if llm_calls == 0:
        # First call - use comprehensive EVIDENCE_RESEARCH_PROMPT
        system = EVIDENCE_RESEARCH_PROMPT.format(
            direction_id=direction.id,
            direction_title=direction.title,
            direction_type=direction_type.value,
            research_questions="\n".join(f"- {q}" for q in direction.research_questions),
            primary_entities=", ".join(direction.primary_entities) if direction.primary_entities else "None",
            claim_text=direction.claim_text or "N/A",
            claimed_by=", ".join(direction.claimed_by) if direction.claimed_by else "N/A",
            key_outcomes_of_interest=", ".join(direction.key_outcomes_of_interest) if direction.key_outcomes_of_interest else "N/A",
            key_mechanisms_to_examine=", ".join(direction.key_mechanisms_to_examine) if direction.key_mechanisms_to_examine else "N/A",
            priority=direction.priority,
            max_steps=direction.max_steps,
            episode_context=episode_context or "(no context provided)",
            tool_instructions=tool_instructions,
            direction_type_strategy=direction_type_strategy,
            current_date=get_current_date_string(),
        )
        logger.debug(f"    Using COMPREHENSIVE evidence research prompt")
    else:
        # Subsequent calls - use compressed EVIDENCE_RESEARCH_REMINDER_PROMPT
        direction_type_reminder = get_direction_type_reminder(direction_type)
        
        system = EVIDENCE_RESEARCH_REMINDER_PROMPT.format(
            direction_type=direction_type.value,
            current_date=get_current_date_string(),
            direction_id=direction.id,
            research_questions="\n".join(f"- {q}" for q in direction.research_questions),
            primary_entities=", ".join(direction.primary_entities) if direction.primary_entities else "None",
            claim_text=direction.claim_text or "N/A",
            steps_taken=steps_taken,
            max_steps=direction.max_steps,
            summaries_count=summaries_written,
            citations_count=citations_count,
            direction_type_reminder=direction_type_reminder,
        )
        logger.debug(f"    Using REMINDER evidence research prompt")
   
    # existing conversation messages in this subgraph
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
        },
        direction_id,
        "llm_response",
        suffix=f"call_{llm_calls + 1}",
    )

    return {
        "messages": [ai_msg],
        "llm_calls": llm_calls + 1,
    }



_prebuilt_evidence_tool_node = ToolNode(ALL_EVIDENCE_RESEARCH_TOOLS)


async def evidence_tool_node(state: EvidenceResearchState) -> EvidenceResearchState:
    """
    Execute evidence research tool calls requested by the last AI message.
    
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
    logger.info(f"⚙️  EVIDENCE TOOL NODE [{direction_id}] - Step {steps_taken + 1}/{max_steps}")

    # Safety: if we've hit max_steps, tell the model to finalize
    if steps_taken >= max_steps:
        logger.warning(f"⚠️  MAX STEPS REACHED ({max_steps}). Requesting model to finalize.")
        summary_msg = SystemMessage(
            content=(
                "You have reached the maximum number of tool steps "
                "for this evidence research direction. Please stop calling tools, "
                "write a final evidence summary using write_evidence_summary_tool if you haven't, "
                "and prepare to finalize your research."
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
        tool_result = await _prebuilt_evidence_tool_node.ainvoke(state)
        
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
        
        logger.info(f"✅ EVIDENCE TOOL NODE complete: {len(result_messages)} result(s)")
        
    except Exception as e:
        logger.error(f"❌ EVIDENCE TOOL NODE ERROR: {e}")
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
# EVIDENCE OUTPUT NODE (Evidence-specific result generation)
# ============================================================================

evidence_result_model = ChatOpenAI( 
    model="gpt-5.1",  
    temperature=0.0, 
    output_version="responses/v1",
    max_retries=2,
)

advice_snippet_model = ChatOpenAI(
    model="gpt-5-mini",
    temperature=0.0,
    output_version="responses/v1",
    max_retries=2,
)


async def generate_advice_snippets(
    evidence_result: EvidenceResearchResult,
    direction: ResearchDirection,
) -> AdviceSnippets:
    """
    Generate actionable advice snippets from the evidence research result.
    """
    logger.info(f"    Generating advice snippets...")
    
    evidence_result_summary = {
        "short_answer": evidence_result.short_answer,
        "long_answer": evidence_result.long_answer,
        "evidence_strength": evidence_result.evidence_strength,
        "key_points": evidence_result.key_points,
    }
    
    direction_context = {
        "title": direction.title,
        "direction_type": direction.direction_type.value,
        "primary_entities": direction.primary_entities,
        "claim_text": direction.claim_text,
    }
    
    prompt = ADVICE_SNIPPET_PROMPT.format(
        evidence_result=json.dumps(evidence_result_summary, indent=2),
        direction_context=json.dumps(direction_context, indent=2),
    )
    
    try:
        advice_agent = create_agent(
            advice_snippet_model,
            response_format=AdviceSnippets,
        )
        
        response = await advice_agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
        
        snippets = response["structured_response"]
        logger.info(f"    ✓ Generated {len(snippets.advice_snippets)} advice snippets")
        return snippets
    except Exception as e:
        logger.error(f"    ✗ Failed to generate advice snippets: {e}")
        return AdviceSnippets(advice_snippets=[])


async def evidence_output_node(state: EvidenceResearchState) -> EvidenceResearchState:
    """
    Produce an EvidenceResearchResult by aggregating file-based summaries
    and research notes, then generate advice snippets.
    """
    direction = state["direction"]
    direction_id = direction.id
    direction_type = direction.direction_type
    file_refs = state.get("file_refs", []) or []
    citations = state.get("citations", []) or []
    notes = state.get("research_notes", []) or []
    
    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"📊 EVIDENCE OUTPUT NODE [{direction_id}]")
    logger.info(f"    Type: {direction_type.value}")
    logger.info(f"    Title: {direction.title[:60]}{'...' if len(direction.title) > 60 else ''}")
    logger.info(f"    Aggregating: {len(file_refs)} file refs, {len(notes)} notes, {len(citations)} citations")
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
                continue
            except Exception as e:
                logger.warning(f"    Error reading {file_path}: {e}")
                continue
        
        if intermediate_summaries:
            aggregated_content = "=== INTERMEDIATE EVIDENCE SUMMARIES (from files) ===\n\n"
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
        "aggregated_evidence_content",
    )

    # Build the evidence result prompt
    prompt = EVIDENCE_RESULT_PROMPT.format(
        direction_id=direction.id,
        direction_type=direction_type.value,
        direction_title=direction.title,
        research_questions="\n".join(f"- {q}" for q in direction.research_questions),
        claim_text=direction.claim_text or "N/A",
        aggregated_research_content=aggregated_content,
        citations="\n".join(citations) if citations else "(no citations collected)",
    )

    logger.info(f"    Generating structured evidence result...")

    # Use strong model with structured output
    evidence_agent = create_agent(
        evidence_result_model,
        response_format=EvidenceResearchOutput,
    )

    agent_response = await evidence_agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]}
    )

    evidence_result: EvidenceResearchOutput = agent_response["structured_response"] 

    

    # Ensure direction_id is set
    
    
    # Generate advice snippets
    advice_snippet = await generate_advice_snippets(evidence_result, direction)
    
    final_evidence_result: EvidenceResearchResult = EvidenceResearchResult(
        direction_id=direction.id,
        short_answer=evidence_result.short_answer,
        long_answer=evidence_result.long_answer,
        evidence_strength=evidence_result.evidence_strength,
        key_points=evidence_result.key_points,
        advice_snippets=advice_snippet.advice_snippets,
        evidence_items=evidence_result.evidence_items,
    )
    
    # Log result summary
    logger.info(f"✅ EVIDENCE OUTPUT complete:")
    logger.info(f"    Short answer length: {len(final_evidence_result.short_answer) if final_evidence_result.short_answer else 0} chars")
    logger.info(f"    Long answer length: {len(final_evidence_result.long_answer) if final_evidence_result.long_answer else 0} chars")
    logger.info(f"    Key points: {len(final_evidence_result.key_points) if final_evidence_result.key_points else 0}")
    logger.info(f"    Evidence items: {len(final_evidence_result.evidence_items) if final_evidence_result.evidence_items else 0}")
    logger.info(f"    Advice snippets: {len(final_evidence_result.advice_snippets) if final_evidence_result.advice_snippets else 0}")
    logger.info(f"    Evidence strength: {final_evidence_result.evidence_strength}")
    
    # Save the final evidence result
    await save_json_artifact(
        final_evidence_result,
        direction_id,
        "final_evidence_result_final",
    )

    # Only update the parts we intend to change; LangGraph will merge this into state.
    return {
        "result": final_evidence_result,
    }


# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================

def should_continue_evidence_research(
    state: EvidenceResearchState,
) -> Literal["evidence_tool_node", "evidence_output_node"]:
    """Route based on tool calls and step budget for evidence research."""
    direction_id = state["direction"].id
    messages = state.get("messages", [])
    if not messages:
        logger.info(f"🔀 ROUTING [{direction_id}]: No messages → evidence_output_node")
        return "evidence_output_node"

    last_message = messages[-1]
    steps_taken = state.get("steps_taken", 0)
    max_steps = state["direction"].max_steps
    
    has_tool_calls = bool(getattr(last_message, "tool_calls", None))
    within_budget = steps_taken < max_steps

    if has_tool_calls and within_budget:
        logger.info(f"🔀 ROUTING [{direction_id}]: Tool calls present, step {steps_taken}/{max_steps} → evidence_tool_node")
        return "evidence_tool_node"
    
    if has_tool_calls and not within_budget:
        logger.info(f"🔀 ROUTING [{direction_id}]: Tool calls but budget exhausted ({steps_taken}/{max_steps}) → evidence_output_node")
    else:
        logger.info(f"🔀 ROUTING [{direction_id}]: No tool calls → evidence_output_node")

    return "evidence_output_node"  
    

# ============================================================================
# TYPE-SPECIFIC EXTRACTION MODEL
# ============================================================================

type_specific_extraction_model = ChatOpenAI(
    model="gpt-5-mini",
    reasoning={
        "effort": "medium",
    },
    temperature=0.0,
    max_retries=2,
)


# ============================================================================
# TYPE-SPECIFIC EXTRACTION HELPER FUNCTIONS
# ============================================================================

async def extract_claim_validation(
    direction: ResearchDirection,
    evidence_result: EvidenceResearchResult,
    state: EvidenceResearchState,
) -> ClaimValidation:
    """Extract ClaimValidation structured output."""
    direction_id = direction.id
    logger.info(f"    Extracting ClaimValidation...")
    
    # Gather context
    research_notes = "\n\n".join(state.get("research_notes", []))
    evidence_result_summary = {
        "short_answer": evidence_result.short_answer,
        "long_answer": evidence_result.long_answer,
        "evidence_strength": evidence_result.evidence_strength,
        "key_points": evidence_result.key_points,
        "evidence_items": [
            {
                "title": ei.study_title,
                "finding": ei.key_finding,
                "design": ei.design,
            }
            for ei in evidence_result.evidence_items[:10]  
        ] if evidence_result.evidence_items else [],
    }
    
    prompt = EXTRACT_CLAIM_VALIDATION_PROMPT.format(
        direction_id=direction.id,
        claim_text=direction.claim_text or "N/A",
        claimed_by=", ".join(direction.claimed_by) if direction.claimed_by else "N/A",
        evidence_result_summary=json.dumps(evidence_result_summary, indent=2),
        research_notes=research_notes[:5000],  # Limit to avoid token overflow
    )
    

    extraction_model = create_agent( 
        type_specific_extraction_model,
        response_format=ClaimValidation, 
    )
    
    try:
        claim_validation = await extraction_model.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )  

        claim_validation_final: ClaimValidation = claim_validation["structured_response"] 
        logger.info(f"    ✓ ClaimValidation extracted: verdict={claim_validation_final.verdict}")
        return claim_validation_final 
    except Exception as e:
        logger.error(f"    ✗ ClaimValidation extraction failed: {e}")
        # Return minimal valid object
        return ClaimValidation(
            direction_id=direction_id,
            claim_text=direction.claim_text or "Unknown claim",
            verdict="insufficient_evidence",
            evidence_strength="unknown",
            nuance_explanation="Extraction failed, unable to validate claim.",
            confidence_score=0.0,
        )


async def extract_mechanism_explanation(
    direction: ResearchDirection,
    evidence_result: EvidenceResearchResult,
    state: EvidenceResearchState,
) -> MechanismExplanation:
    """Extract MechanismExplanation structured output."""
    direction_id = direction.id
    logger.info(f"    Extracting MechanismExplanation...")
    
    research_notes = "\n\n".join(state.get("research_notes", []))
    evidence_result_summary = {
        "short_answer": evidence_result.short_answer,
        "long_answer": evidence_result.long_answer,
        "key_points": evidence_result.key_points,
    }
    
    prompt = EXTRACT_MECHANISM_EXPLANATION_PROMPT.format(
        direction_id=direction.id,
        key_mechanisms=", ".join(direction.key_mechanisms_to_examine) if direction.key_mechanisms_to_examine else "N/A",
        key_outcomes=", ".join(direction.key_outcomes_of_interest) if direction.key_outcomes_of_interest else "N/A",
        evidence_result_summary=json.dumps(evidence_result_summary, indent=2),
        research_notes=research_notes[:5000],
    )
    

    extraction_model = create_agent( 
        type_specific_extraction_model,
        response_format=MechanismExplanation, 
    )
    
    try:
        mechanism = await extraction_model.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )  

        mechanism_final: MechanismExplanation = mechanism["structured_response"] 
        logger.info(f"    ✓ MechanismExplanation extracted: {len(mechanism_final.pathway_steps)} pathway steps")
        return mechanism_final
    except Exception as e:
        logger.error(f"    ✗ MechanismExplanation extraction failed: {e}")
        return MechanismExplanation(
            direction_id=direction_id,
            mechanism_name="Unknown mechanism",
            intervention="Unknown intervention",
            target_outcome="Unknown outcome",
            overall_plausibility="unknown",
            evidence_strength="unknown",
            animal_vs_human="Extraction failed, unable to determine.",
        )


async def extract_risk_benefit_profile(
    direction: ResearchDirection,
    evidence_result: EvidenceResearchResult,
    state: EvidenceResearchState,
) -> RiskBenefitProfile:
    """Extract RiskBenefitProfile structured output."""
    direction_id = direction.id
    logger.info(f"    Extracting RiskBenefitProfile...")
    
    research_notes = "\n\n".join(state.get("research_notes", []))
    evidence_result_summary = {
        "short_answer": evidence_result.short_answer,
        "long_answer": evidence_result.long_answer,
        "key_points": evidence_result.key_points,
    }
    
    # Infer intervention name from primary entities or title
    intervention_name = direction.primary_entities[0] if direction.primary_entities else direction.title
    
    prompt = EXTRACT_RISK_BENEFIT_PROMPT.format(
        direction_id=direction.id,
        intervention_name=intervention_name,
        key_outcomes=", ".join(direction.key_outcomes_of_interest) if direction.key_outcomes_of_interest else "N/A",
        evidence_result_summary=json.dumps(evidence_result_summary, indent=2),
        research_notes=research_notes[:5000],
    )
    

    extraction_model = create_agent( 
        type_specific_extraction_model,
        response_format=RiskBenefitProfile, 
    )
    
    try:
        risk_benefit = await extraction_model.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )  

        risk_benefit_final: RiskBenefitProfile = risk_benefit["structured_response"] 
        logger.info(f"    ✓ RiskBenefitProfile extracted: {len(risk_benefit_final.benefits)} benefits, {len(risk_benefit_final.risks)} risks")
        return risk_benefit_final
    except Exception as e:
        logger.error(f"    ✗ RiskBenefitProfile extraction failed: {e}")
        return RiskBenefitProfile(
            direction_id=direction_id,
            intervention_name=intervention_name,
            intended_use="Unknown",
            overall_assessment="insufficient_data",
            assessment_rationale="Extraction failed, unable to assess risk-benefit profile.",
            evidence_quality_overall="unknown",
        )


async def extract_comparative_analysis(
    direction: ResearchDirection,
    evidence_result: EvidenceResearchResult,
    state: EvidenceResearchState,
) -> ComparativeAnalysis:
    """Extract ComparativeAnalysis structured output."""
    direction_id = direction.id
    logger.info(f"    Extracting ComparativeAnalysis...")
    
    research_notes = "\n\n".join(state.get("research_notes", []))
    evidence_result_summary = {
        "short_answer": evidence_result.short_answer,
        "long_answer": evidence_result.long_answer,
        "key_points": evidence_result.key_points,
    }
    
    # Infer primary intervention from primary entities or title
    primary_intervention = direction.primary_entities[0] if direction.primary_entities else direction.title
    
    prompt = EXTRACT_COMPARATIVE_ANALYSIS_PROMPT.format(
        direction_id=direction.id,
        primary_intervention=primary_intervention,
        key_outcomes=", ".join(direction.key_outcomes_of_interest) if direction.key_outcomes_of_interest else "N/A",
        evidence_result_summary=json.dumps(evidence_result_summary, indent=2),
        research_notes=research_notes[:5000],
    )
  

    extraction_model = create_agent( 
        type_specific_extraction_model,
        response_format=ComparativeAnalysis, 
    )
    
    try:
        comparative = await extraction_model.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )  

        comparative_final: ComparativeAnalysis = comparative["structured_response"] 
        logger.info(f"    ✓ ComparativeAnalysis extracted: {len(comparative_final.comparators)} comparators")
        return comparative_final
    except Exception as e:
        logger.error(f"    ✗ ComparativeAnalysis extraction failed: {e}")
        return ComparativeAnalysis(
            direction_id=direction_id,
            primary_intervention=primary_intervention,
            ranking_rationale="Extraction failed, unable to perform comparative analysis.",
            evidence_quality="unknown",
        )


# ============================================================================
# TYPE-SPECIFIC STRUCTURED EXTRACTION NODE
# ============================================================================

async def extract_type_specific_structures(state: EvidenceResearchState) -> EvidenceResearchState:
    """
    Extract type-specific structured outputs based on direction_type.
    
    Extracts ClaimValidation, MechanismExplanation, RiskBenefitProfile,
    or ComparativeAnalysis depending on the research direction type.
    """
    direction = state["direction"]
    direction_id = direction.id
    direction_type = direction.direction_type
    evidence_result = state.get("result")
    
    logger.info(f"")
    logger.info(f"{'='*60}")
    logger.info(f"🏷️  TYPE-SPECIFIC EXTRACTION [{direction_id}]")
    logger.info(f"    Type: {direction_type.value}")
    logger.info(f"    Title: {direction.title[:60]}{'...' if len(direction.title) > 60 else ''}")
    logger.info(f"{'='*60}")
    
    if not evidence_result:
        logger.warning(f"    No evidence result available for extraction!")
        return {
            "llm_calls": state.get("llm_calls", 0) + 1,
        }
    
    structured_outputs: List[BaseModel] = []
    
    # Route to appropriate extraction function based on direction_type
    if direction_type == ResearchDirectionType.CLAIM_VALIDATION:
        claim_validation = await extract_claim_validation(direction, evidence_result, state)
        structured_outputs.append(claim_validation)
        
        # Save individual output
        await save_json_artifact(
            claim_validation,
            direction_id,
            "claim_validation_final",
        )
        
    elif direction_type == ResearchDirectionType.MECHANISM_EXPLANATION:
        mechanism = await extract_mechanism_explanation(direction, evidence_result, state)
        structured_outputs.append(mechanism)
        
        # Save individual output
        await save_json_artifact(
            mechanism,
            direction_id,
            "mechanism_explanation_final",
        )
        
    elif direction_type == ResearchDirectionType.RISK_BENEFIT_PROFILE:
        risk_benefit = await extract_risk_benefit_profile(direction, evidence_result, state)
        structured_outputs.append(risk_benefit)
        
        # Save individual output
        await save_json_artifact(
            risk_benefit,
            direction_id,
            "risk_benefit_profile_final",
        )
        
    elif direction_type == ResearchDirectionType.COMPARATIVE_EFFECTIVENESS:
        comparative = await extract_comparative_analysis(direction, evidence_result, state)
        structured_outputs.append(comparative)
        
        # Save individual output
        await save_json_artifact(
            comparative,
            direction_id,
            "comparative_analysis_final",
        )
    
    else:
        logger.warning(f"    Unknown direction_type: {direction_type}")
    
    # Log extraction summary
    logger.info(f"✅ TYPE-SPECIFIC EXTRACTION complete:")
    logger.info(f"    Extracted {len(structured_outputs)} structured output(s)")
    for output in structured_outputs:
        logger.info(f"    - {type(output).__name__}")
    
    return {
        "structured_outputs": structured_outputs,
        "llm_calls": state.get("llm_calls", 0) + 1,
    }

# ============================================================================
# BUILD THE EVIDENCE RESEARCH SUBGRAPH
# ============================================================================

evidence_research_subgraph_builder = StateGraph(EvidenceResearchState)

# Evidence research loop nodes
evidence_research_subgraph_builder.add_node("call_evidence_model", call_evidence_model)
evidence_research_subgraph_builder.add_node("evidence_tool_node", evidence_tool_node)
evidence_research_subgraph_builder.add_node("evidence_output_node", evidence_output_node)
evidence_research_subgraph_builder.add_node("extract_type_specific_structures", extract_type_specific_structures)

# Entry point - start with the evidence model
evidence_research_subgraph_builder.set_entry_point("call_evidence_model")

# LLM node conditionally goes to tool loop or to final output
evidence_research_subgraph_builder.add_conditional_edges(
    "call_evidence_model",
    should_continue_evidence_research,
    {
        "evidence_tool_node": "evidence_tool_node",
        "evidence_output_node": "evidence_output_node",
    },
)

# After tools, go back to the LLM
evidence_research_subgraph_builder.add_edge("evidence_tool_node", "call_evidence_model")

# After evidence output, extract type-specific structures then end
evidence_research_subgraph_builder.add_edge("evidence_output_node", "extract_type_specific_structures")
evidence_research_subgraph_builder.add_edge("extract_type_specific_structures", END)

# Compile evidence research subgraph
# evidence_research_subgraph = evidence_research_subgraph_builder.compile()

# logger.info("✅ Evidence Research Subgraph compiled successfully!")
# logger.info(f"    Nodes: {list(evidence_research_subgraph.nodes.keys())}")
# logger.info(f"    Entry point: call_evidence_model")
# logger.info(f"    Exit point: extract_type_specific_structures → END")
