from langchain.agents import create_agent 
from typing import List, Dict, Any, Optional

from langchain_openai import ChatOpenAI
from research_agent.prompts.web_search_summary_prompts import TAVILY_SUMMARY_PROMPT 
from research_agent.utils.logger import logger  
from research_agent.structured_outputs.sources_and_search_summary_outputs import TavilyResultsSummary
from research_agent.utils.artifacts import save_json_artifact 
from langchain.agents.structured_output import ProviderStrategy  



async def summarize_tavily_web_search(
    search_results: str,  
    model: ChatOpenAI, 
) -> TavilyResultsSummary:  
    """Summarize Tavily search results."""
    logger.info(f"📝 Summarizing Tavily search results (input length: {len(search_results)} chars)")
    
    agent_instructions = TAVILY_SUMMARY_PROMPT.format(search_results=search_results) 
    web_search_summary_agent = create_agent( 
        model, 
        response_format=ProviderStrategy(TavilyResultsSummary),  
        name="tavily_summary_agent",
    )   

    web_search_summary_agent_response = await web_search_summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": agent_instructions}]}
    )

    summary = web_search_summary_agent_response["structured_response"]
    logger.info(f"✅ Tavily summary complete: {len(summary.citations)} citations found")
    
    await save_json_artifact(summary, "test_run", "tavily_summary")
    
    return summary


async def summarize_tavily_extract(
    extract_results: str,
    model: ChatOpenAI,
) -> TavilyResultsSummary:
    """Summarize Tavily extract results."""
    logger.info(f"📝 Summarizing Tavily extract results (input length: {len(extract_results)} chars)")
    
    agent_instructions = TAVILY_SUMMARY_PROMPT.format(search_results=extract_results)
    extract_summary_agent = create_agent(
        model,
        response_format=ProviderStrategy(TavilyResultsSummary),
        name="tavily_extract_summary_agent",
    )

    extract_summary_agent_response = await extract_summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": agent_instructions}]}
    )

    summary = extract_summary_agent_response["structured_response"]
    logger.info(f"✅ Tavily extract summary complete: {len(summary.citations)} citations found")
    
    await save_json_artifact(summary, "test_run", "tavily_extract_summary")
    
    return summary




# ============================================================================
# RESEARCH TOOLS
# ============================================================================

def format_tavily_summary_results(summary: TavilyResultsSummary) -> str:
    """Format a TavilyResultsSummary into a readable string."""
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

def format_tavily_map_response(response: Dict[str, Any], *, urls_override: Optional[List[str]] = None) -> str:
    base_url = response.get("base_url", "unknown")
    results = urls_override if urls_override is not None else (response.get("results", []) or [])

    lines: List[str] = []
    lines.append(f"=== Site Map: {base_url} ===")
    lines.append(f"Discovered {len(results)} URL(s):")
    lines.append("")

    if not results:
        lines.append("(no URLs discovered)")
    else:
        for idx, url in enumerate(results, start=1):
            lines.append(f"{idx}. {url}")

    return "\n".join(lines).strip()