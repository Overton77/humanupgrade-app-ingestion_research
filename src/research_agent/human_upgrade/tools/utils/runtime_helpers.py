from langchain.tools import ToolRuntime  
from research_agent.human_upgrade.logger import logger  
from typing import List  
from research_agent.human_upgrade.structured_outputs.sources_and_search_summary_outputs import TavilyCitation

def increment_steps(runtime: ToolRuntime) -> None:
    """Runtime transformer to increment steps_taken counter."""
    steps_taken = runtime.state.get("steps_taken", 0) + 1
    runtime.state["steps_taken"] = steps_taken
    logger.info(f"📊 Step {steps_taken}") 

def write_citations(runtime: ToolRuntime, citations: List[TavilyCitation]) -> None:
    """Runtime transformer to write citations to the state.""" 

    current_citations = runtime.state.get("citations", []) or []
    current_citations.extend(citations)
    runtime.state["citations"] = current_citations
    logger.info(f"📊 Citations written: {len(current_citations)}")
