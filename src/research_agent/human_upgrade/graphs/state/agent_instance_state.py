from __future__ import annotations

from typing import Any, Dict, Optional, Annotated, List, Union, Callable 
import operator 
from typing_extensions import NotRequired 
from langchain.agents import create_agent, AgentState
from research_agent.human_upgrade.structured_outputs.research_plans_outputs import ( 
   AgentType,  
    AgentInstancePlanWithSources,  
   
) 
from research_agent.human_upgrade.structured_outputs.file_outputs import ( 
    FileReference 
) 


""" 
AgentInstancePlanWithSources: 
{
    "instance_id": "string",
    "agent_type": "AgentType",
    "stage_id": "string",
    "sub_stage_id": "string",
    "slice": SliceSpec,
    "objectives": [Objective], 
    "starter_sources": [CuratedSource],
    "requires_artifacts": ["string", "..."],
    "produces_artifacts": ["string", "..."],
    "notes": "string" OR null
}


"""


class WorkerAgentState(AgentState):
    agent_instance_plan: AgentInstancePlanWithSources
    agent_type: AgentType

    # accumulated outputs
    file_refs: Annotated[List[FileReference], operator.add]
    research_notes: Annotated[List[str], operator.add]
    thoughts: Annotated[List[str], operator.add]
    final_report: Optional[Union[FileReference, str]]

    # prompting anchors
    last_plan: NotRequired[str]
    open_questions: NotRequired[List[str]]
    current_focus: NotRequired[Dict[str, str]]  # {"entity": "...", "focus": "..."}

    # new generic ledger (artifact / objective keys)
    progress_ledger: NotRequired[Dict[str, Dict[str, Any]]]

    # orchestration context (for indexing and later fan-in)
    mission_id: str 
    stage_id: str 
    sub_stage_id: str
    sub_stage_name: NotRequired[str]

    # IMPORTANT: deterministic per-instance workspace root (string path)
    workspace_root: str 

    objective: str 
    seed_context: NotRequired[Dict[str, Any]]
    tool_budget: NotRequired[Dict[str, Any]] 
