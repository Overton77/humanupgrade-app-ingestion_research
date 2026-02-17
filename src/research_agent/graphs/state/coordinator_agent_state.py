"""Coordinator Agent State Definition.

Custom state for the Coordinator Agent (LangGraph/create_agent).
Extends the base AgentState with coordinator-specific fields.
"""

from typing import Dict, Optional, Annotated
from typing_extensions import NotRequired
from langchain.agents import AgentState

from research_agent.structured_outputs.simplified_research_plan import SimplifiedResearchPlan


class CoordinatorAgentState(AgentState):
    """State for the Coordinator Agent.
    
    Extends the base AgentState (which includes messages) with coordinator-specific
    fields for tracking research plans created during planning conversations.
    """
    
    # Research plans created during conversations
    # Keyed by "{mission_title}:{thread_id}" for uniqueness
    research_plans: NotRequired[Dict[str, SimplifiedResearchPlan]]
    
    # Optional: Track the last created plan ID for easy reference
    last_plan_id: NotRequired[Optional[str]]
    
    # Optional: Track conversation metadata
    thread_id: NotRequired[Optional[str]]
