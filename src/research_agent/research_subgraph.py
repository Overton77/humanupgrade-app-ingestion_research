from langgraph.graph import StateGraph, START, END  
from typing_extensions import TypedDict, Annotated  
from typing import List, Dict, Any, Optional, Sequence, Literal, Union 
from langchain_core.messages import AnyMessage, BaseMessage, ToolMessage, SystemMessage, HumanMessage, filter_messages   
from langchain_openai import ChatOpenAI  
from pydantic import BaseModel, Field  
import operator   
import os   
import uuid
from firecrawl import AsyncFirecrawlApp   
from langchain.agents import create_agent  
from langchain_core.prompts import PromptTemplate 
from tavily import AsyncTavilyClient 
from dotenv import load_dotenv 
from langchain.tools import ToolRuntime, tool    
from research_agent.agent_tools.tavily_functions import tavily_search, format_tavily_search_response    
from research_agent.agent_tools.firecrawl_functions import firecrawl_scrape, format_firecrawl_map_response, format_firecrawl_search_response, firecrawl_map, format_firecrawl_map_response 
from research_agent.agent_tools.filesystem_tools import write_file, read_file
from research_agent.medical_db_tools.pub_med_tools import ( 
   pubmed_literature_search_tool 
)    
from langchain_community.tools import WikipediaQueryRun  
from langchain_community.utilities import WikipediaAPIWrapper   
from research_agent.prompts.summary_prompts import TAVILY_SUMMARY_PROMPT, FIRECRAWL_SCRAPE_PROMPT  
from research_agent.prompts.research_prompts import (
    DEEP_RESEARCH_PROMPT, 
    TOOL_INSTRUCTIONS,
    RESEARCH_RESULT_PROMPT,
) 
from research_agent.prompts.structured_output_prompts import ENTITY_EXTRACTION_PROMPT
from research_agent.output_models import (
    DirectionResearchResult, 
    ResearchDirection,
    ResearchEntities,
    ExtractedEntityBase,
    ProductOutput,
    CompoundOutput,
    BusinessOutput,
    PersonOutput,
    CaseStudyOutput,
)




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


# ============================================================================
# INTERMEDIATE SUMMARY MODEL (for file-based context offloading)
# ============================================================================

class IntermediateSummary(BaseModel):
    """A checkpoint summary written during research for context offloading."""
    summary_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    topic_focus: str = Field(..., description="What aspect of research this summary covers")
    synthesis: str = Field(..., description="Synthesized findings so far")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in findings (0-1)")
    open_questions: List[str] = Field(default_factory=list, description="Questions still to investigate")
    key_sources: List[str] = Field(default_factory=list, description="Most important citations for this summary")


# ============================================================================
# RESEARCH STATE
# ============================================================================

class ResearchState(TypedDict, total=False):  
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
    result: DirectionResearchResult


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


# ============================================================================
# CITATION MODELS
# ============================================================================

class TavilyCitation(BaseModel): 
    url: str = Field(..., description="The URL of the source")  
    title: str = Field(..., description="The title of the source")   
    published_date: Optional[str] = Field(None, description="The published date of the source")   
    score: Optional[float] = Field(None, description="The score of the source")    

class FirecrawlCitation(BaseModel): 
    url: str = Field(..., description="The URL of the source")  
    title: str = Field(..., description="The title of the source")    
    description: Optional[str] = Field(None, description="The description of the source")   


class TavilyResultsSummary(BaseModel):  
    summary: str = Field(..., description="An extensive  summary of the search results")   
    citations: List[TavilyCitation] = Field(..., description="The citations of the search results")   

class FirecrawlResultsSummary(BaseModel):  
    summary: str = Field(..., description="A faithful summary of the markdown representation of the content")
    citations: List[FirecrawlCitation] = Field(..., description="A summary of the markdown of the content")  


# ============================================================================
# SUMMARIZATION HELPERS
# ============================================================================

async def summarize_tavily_web_search(search_results: str) -> TavilyResultsSummary:  
    agent_instructions = TAVILY_SUMMARY_PROMPT.format(search_results=search_results) 
    web_search_summary_agent = create_agent( 
        summary_model, 
        response_format=TavilyResultsSummary, 

    )   

    web_search_summary_agent_response = await web_search_summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": agent_instructions}]}
    )

    return web_search_summary_agent_response["structured_response"]


async def summarize_firecrawl_scrape(search_results: str) -> FirecrawlResultsSummary:  
    agent_instructions = FIRECRAWL_SCRAPE_PROMPT.format(search_results=search_results) 
    web_search_summary_agent = create_agent( 
        summary_model, 
        response_format=FirecrawlResultsSummary, 

    )   

    web_search_summary_agent_response = await web_search_summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": agent_instructions}]}
    )

    return web_search_summary_agent_response["structured_response"]


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

    result = await firecrawl_map(
        app=async_firecrawl_app,
        url=url,
        search=search,
        include_subdomains=include_subdomains,
        limit=limit,
        sitemap=sitemap,
    )

    formatted_result = format_firecrawl_map_response(result) 

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
        runtime (ToolRuntime): Tool runtime containing shared agent state.
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

   
    results = await firecrawl_scrape(async_firecrawl_app, 
        url, 
        formats, 
        include_links, 
        max_depth, 
        include_images 
        ) 

    formatted_results = format_firecrawl_search_response(results)  

    summary_of_scrape = await summarize_firecrawl_scrape(formatted_results)  

    runtime.state.get("citations", []).extend([citation.url for citation in summary_of_scrape.citations])
    runtime.state.get("research_notes", []).append(summary_of_scrape.summary)

    formatted_scrape_summary = format_firecrawl_summary_results(summary_of_scrape) 

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
    
) -> str:    
    """Perform a web search using Tavily and return a summarized view of the results.

    Recommended usage:
    - Use this as a first step when you need broad coverage or multiple viewpoints
      on a topic (companies, products, people, mechanisms, protocols, etc.).
    - Use it to quickly collect top pages and their content before deciding which
      URLs to inspect more deeply with Firecrawl.

    Args:
        runtime (ToolRuntime): Tool runtime containing shared agent state.
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

    Returns:
        str: A human-readable string containing a summary of the results and
        citations/URLs of key sources.

    """

    runtime.state["steps_taken"] = runtime.state.get("steps_taken", 0) + 1 

    search_results = await tavily_search( 
        client=async_tavily_client, 
        query=query, 
        max_results=max_results, 
        search_depth=search_depth, 
        topic=topic, 
        include_images=include_images, 
        include_raw_content=include_raw_content, 
        ) 

    formatted_search_results = format_tavily_search_response(search_results)  

    web_search_summary = await summarize_tavily_web_search(formatted_search_results)   

    runtime.state.get("citations", []).extend([citation.url for citation in web_search_summary.citations])
    runtime.state.get("research_notes", []).append(web_search_summary.summary)

    web_search_summary_formatted = format_tavily_summary_results(web_search_summary)     

    return web_search_summary_formatted 


# ============================================================================
# WRITE RESEARCH SUMMARY TOOL (Incremental Synthesis + Context Offloading)
# ============================================================================

@tool(
    description="Write an intermediate research summary to consolidate findings before continuing. "
                "Use this after gathering substantial information on a sub-topic.",
    parse_docstring=False,
)
async def write_research_summary_tool(
    runtime: ToolRuntime,
    topic_focus: str,
    synthesis: str,
    confidence: float,
    open_questions: List[str],
    key_sources: List[str],
) -> str:
    """
    Consolidate research findings into an intermediate summary file.
    
    Call this tool when you have gathered enough information on a specific
    aspect and want to:
    1. Free up context by offloading findings to a file
    2. Create a checkpoint before investigating other aspects
    3. Organize your research into coherent themes
    
    Args:
        runtime (ToolRuntime): Tool runtime containing shared agent state.
        topic_focus (str): What specific aspect this summary covers 
            (e.g., "product mechanism", "clinical evidence", "company background").
        synthesis (str): Your synthesized understanding of the findings.
            Should be 2-4 paragraphs that capture the key insights.
        confidence (float): 0.0-1.0 confidence score for these findings.
            - 0.0-0.3: Low confidence (limited/contradictory sources)
            - 0.4-0.6: Medium confidence (some evidence, gaps remain)
            - 0.7-1.0: High confidence (strong evidence, multiple sources agree)
        open_questions (List[str]): Questions that remain unanswered.
            These help guide further research if needed.
        key_sources (List[str]): Most important URLs/DOIs supporting this summary.
            Include 2-5 of the most authoritative sources.
    
    Returns:
        str: Confirmation with the file path where summary was stored.
    """
    direction = runtime.state.get("direction")
    direction_id = direction.id if direction else "unknown"
    
    # Create the IntermediateSummary model
    summary = IntermediateSummary(
        topic_focus=topic_focus,
        synthesis=synthesis,
        confidence=confidence,
        open_questions=open_questions,
        key_sources=key_sources,
    )
    
    # Write to file system (under research/<direction_id>/)
    filename = f"research/{direction_id}/summary_{summary.summary_id}.json"
    await write_file(filename, summary.model_dump_json(indent=2))
    
    # Track file reference in state for later aggregation
    file_refs = runtime.state.get("file_refs", [])
    if file_refs is None:
        file_refs = []
    file_refs.append(filename)
    runtime.state["file_refs"] = file_refs
    
    # Also add a compact version to research_notes for backward compatibility
    # and in case files aren't accessible
    compact_note = (
        f"[SUMMARY: {topic_focus}]\n"
        f"Confidence: {confidence}\n\n"
        f"{synthesis}\n\n"
        f"Open Questions: {'; '.join(open_questions) if open_questions else 'None'}\n"
        f"Key Sources: {', '.join(key_sources[:3]) if key_sources else 'None cited'}"
    )
    research_notes = runtime.state.get("research_notes", [])
    if research_notes is None:
        research_notes = []
    research_notes.append(compact_note)
    runtime.state["research_notes"] = research_notes
    
    return (
        f"✓ Summary written to {filename}\n"
        f"  Topic: {topic_focus}\n"
        f"  Confidence: {confidence}\n"
        f"  Open questions: {len(open_questions)}\n\n"
        f"You can now continue researching other aspects or stop if you have enough information."
    )


# ============================================================================
# ALL TOOLS - Agent has access to everything
# ============================================================================

# All research tools available to the agent
ALL_RESEARCH_TOOLS = [
    tavily_web_search_tool,
    firecrawl_scrape_tool,
    firecrawl_map_tool,
    wiki_tool,
    pubmed_literature_search_tool,
    write_research_summary_tool,
]

tools_by_name = {t.name: t for t in ALL_RESEARCH_TOOLS}


def get_tool_instructions(direction: ResearchDirection) -> str:
    """
    Get tool instructions based on the research direction.
    Uses include_scientific_literature flag to guide tool prioritization.
    """
    return TOOL_INSTRUCTIONS.format(
        include_scientific_literature="YES" if direction.include_scientific_literature else "NO",
        scientific_guidance=(
            "PRIORITIZE PubMed for peer-reviewed evidence on mechanisms, interventions, and clinical outcomes. "
            "Use it to verify scientific claims found on company/product websites."
            if direction.include_scientific_literature
            else "PubMed is available if you discover scientific claims that need verification, "
            "but focus primarily on web research for this direction."
        ),
    )


# ============================================================================
# GRAPH NODES
# ============================================================================

async def call_model(state: ResearchState) -> ResearchState:
    """LLM decides what to do next for this research direction."""
    direction = state["direction"] 
    episode_context = state.get("episode_context", "")
    notes = state.get("research_notes", [])

    # Agent gets ALL tools - no silos
    model_with_tools = research_model.bind_tools(ALL_RESEARCH_TOOLS) 

    tool_instructions = get_tool_instructions(direction)

    system = SystemMessage(
        content=DEEP_RESEARCH_PROMPT.format(
            direction_id=direction.id,
            topic=direction.topic,
            description=direction.description,
            overview=direction.overview,
            include_scientific_literature="YES" if direction.include_scientific_literature else "NO",
            depth=direction.depth,
            priority=direction.priority,
            max_steps=direction.max_steps,
            query_seed=direction.topic,
            tool_instructions=tool_instructions,
        )
    )

    # existing conversation messages in this subgraph
    messages = list(state.get("messages", []))

    ai_msg = await model_with_tools.ainvoke([system] + messages)

    return {
        "messages": [ai_msg],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


async def tool_node(state: ResearchState) -> ResearchState:
    """Execute tool calls requested by the last AI message."""
    last_msg = state["messages"][-1]
    tool_calls = getattr(last_msg, "tool_calls", []) or []

    max_steps = state["direction"].max_steps
    steps_taken = state.get("steps_taken", 0)

    # safety: if we've hit max_steps, tell the model to summarize instead
    if steps_taken >= max_steps:
        summary_msg = SystemMessage(
            content=(
                "You have reached the maximum number of tool steps "
                "for this research direction. Please stop calling tools, "
                "write a final summary using write_research_summary_tool if you haven't, "
                "and prepare to finalize."
            )
        )
        return {
            "messages": [summary_msg],
        }

    if not tool_calls:
        # nothing to do; just return state unchanged
        return {"messages": []}

    results: List[str] = []

    for tc in tool_calls:
        tool = tools_by_name.get(tc.get("name"))
        if tool is None:
            # tool not registered; return an error-ish message
            results.append(f"Tool {tc.get('name')} not found.")
            continue

        # tool.ainvoke expects args dict (and will receive ToolRuntime automatically)
        result = await tool.ainvoke(tc.get("args") or {})
        results.append(result)

    tool_outputs: List[ToolMessage] = [
        ToolMessage(
            content=result,
            name=tc.get("name"),
            tool_call_id=tc.get("id"),
        )
        for result, tc in zip(results, tool_calls)
    ]

    return {
        "messages": tool_outputs,
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


async def research_output_node(state: ResearchState) -> ResearchState:
    """
    Produce a DirectionResearchResult by aggregating file-based summaries
    and research notes via structured LLM call.
    """
    direction = state["direction"]
    episode_context = state.get("episode_context", "") or "(none)"
    file_refs = state.get("file_refs", []) or []
    citations = state.get("citations", []) or []
    notes = state.get("research_notes", []) or []

    # Aggregate intermediate summaries from files
    aggregated_content = ""
    
    if file_refs:
        intermediate_summaries = []
        for file_path in file_refs:
            try:
                content = await read_file(file_path)
                intermediate_summaries.append(f"--- File: {file_path} ---\n{content}")
            except FileNotFoundError:
                # File not found, skip (notes should have backup)
                continue
            except Exception as e:
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

    prompt = RESEARCH_RESULT_PROMPT.format(
        topic=direction.topic,
        description=direction.description,
        overview=direction.overview,
        include_scientific_literature="YES" if direction.include_scientific_literature else "NO",
        depth=direction.depth,
        priority=direction.priority,
        episode_context=episode_context,
        research_notes=aggregated_content,
        citations="\n".join(citations) if citations else "(no citations collected)",
    )

    # Use strong model with structured output
    result_agent = create_agent(
        research_result_model,
        response_format=DirectionResearchResult,
    )

    agent_response = await result_agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]}
    )

    direction_result: DirectionResearchResult = agent_response["structured_response"]

    # Ensure we don't lose citations from state if the model omits them
    if not direction_result.citations:
        direction_result.citations = citations

    # We still know the direction_id here; set it if the model left it blank
    if not direction_result.direction_id:
        direction_result.direction_id = direction.id

    # Only update the parts we intend to change; LangGraph will merge this into state.
    return {
        "result": direction_result,
    }


# ============================================================================
# ROUTING FUNCTIONS
# ============================================================================

def should_continue_research(
    state: ResearchState,
) -> Literal["tool_node", "research_output_node"]:
    """Route based on tool calls and step budget."""
    messages = state.get("messages", [])
    if not messages:
        return "research_output_node"

    last_message = messages[-1]
    steps_taken = state.get("steps_taken", 0)
    max_steps = state["direction"].max_steps

    if getattr(last_message, "tool_calls", None) and steps_taken < max_steps:
        return "tool_node"

    return "research_output_node"  
    

# ============================================================================
# ENTITY EXTRACTION MODEL
# ============================================================================

entity_extraction_model = ChatOpenAI(
    model="gpt-4o",
    temperature=0.0,
    max_retries=2,
)


# ============================================================================
# SINGLE-PASS ENTITY EXTRACTION NODE
# ============================================================================

async def extract_structured_entities(state: ResearchState) -> ResearchState:
    """
    Single-pass entity extraction using structured output.
    
    Extracts businesses, products, people, compounds, and case studies
    from the research results in one deterministic call.
    """
    direction = state["direction"]
    result = state.get("result")
    citations = state.get("citations", []) or []
    
    # Build the extraction prompt
    extensive_summary = (
        result.extensive_summary if result and result.extensive_summary else "(no summary available)"
    )
    key_findings = (
        "\n".join(f"- {f}" for f in result.key_findings) 
        if result and result.key_findings 
        else "(no key findings)"
    )
    citations_text = "\n".join(citations) if citations else "(no citations collected)"
    
    prompt = ENTITY_EXTRACTION_PROMPT.format(
        direction_id=direction.id,
        topic=direction.topic,
        description=direction.description,
        overview=direction.overview,
        extensive_summary=extensive_summary,
        key_findings=key_findings,
        citations=citations_text,
    )
    
    # Use .with_structured_output() for deterministic extraction
    extraction_model = entity_extraction_model.with_structured_output(
        ResearchEntities,
        method="json_schema",
        strict=True,
    )
    
    try:
        entities: ResearchEntities = await extraction_model.ainvoke(prompt)
    except Exception as e:
        # If extraction fails, return empty entities
        print(f"Entity extraction failed: {e}")
        entities = ResearchEntities()
    
    # Collect all extracted entities and ensure direction_id is set
    all_outputs: List[ExtractedEntityBase] = []
    
    for business in entities.businesses:
        if not business.direction_id or business.direction_id == "":
            business.direction_id = direction.id
        all_outputs.append(business)
    
    for product in entities.products:
        if not product.direction_id or product.direction_id == "":
            product.direction_id = direction.id
        all_outputs.append(product)
    
    for person in entities.people:
        if not person.direction_id or person.direction_id == "":
            person.direction_id = direction.id
        all_outputs.append(person)
    
    for compound in entities.compounds:
        if not compound.direction_id or compound.direction_id == "":
            compound.direction_id = direction.id
        all_outputs.append(compound)
    
    for case_study in entities.case_studies:
        if not case_study.direction_id or case_study.direction_id == "":
            case_study.direction_id = direction.id
        all_outputs.append(case_study)
    
    return {
        "structured_outputs": all_outputs,
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ============================================================================
# BUILD THE GRAPH
# ============================================================================

research_subgraph_builder = StateGraph(ResearchState)

# Research loop nodes
research_subgraph_builder.add_node("call_model", call_model)
research_subgraph_builder.add_node("tool_node", tool_node)
research_subgraph_builder.add_node("research_output_node", research_output_node)

# Entity extraction node (single-pass, no tool loop)
research_subgraph_builder.add_node("extract_entities", extract_structured_entities)

# Entry point
research_subgraph_builder.set_entry_point("call_model")

# LLM node conditionally goes to tool loop or to final output
research_subgraph_builder.add_conditional_edges(
    "call_model",
    should_continue_research,
    {
        "tool_node": "tool_node",
        "research_output_node": "research_output_node",
    },
)

# After tools, go back to the LLM
research_subgraph_builder.add_edge("tool_node", "call_model") 

# After research output, extract entities then end
research_subgraph_builder.add_edge("research_output_node", "extract_entities")
research_subgraph_builder.add_edge("extract_entities", END)

# Compile subgraph
# research_subgraph = research_subgraph_builder.compile()
