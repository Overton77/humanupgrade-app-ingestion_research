from __future__ import annotations

from typing import Any, Dict, Optional, Annotated, List, Union 
import operator 
from typing_extensions import NotRequired 
from langchain.agents import  AgentState
from research_agent.structured_outputs.research_plans_outputs import ( 
   AgentType,  
    AgentInstancePlanWithSources,  
   
) 
from research_agent.structured_outputs.file_outputs import ( 
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
    agent_type: "AgentType"

    # accumulated outputs
    file_refs: Annotated[List["FileReference"], operator.add]
    research_notes: Annotated[List[str], operator.add]
    thoughts: Annotated[List[str], operator.add]
    final_report: Optional[Union["FileReference", str]]

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

    # ------------------------------------------------------------------
    # STEP 1: research control-plane + telemetry
    # ------------------------------------------------------------------

    # incremented by tools; useful for “how deep are we in this run?”
    steps_taken: int

    # how many checkpoint files we’ve written (we’ll increment in file tools / wrapper tool)
    checkpoint_count: int

    # counts per tool name, e.g. {"tavily.search": 3, "tavily.extract": 5}
    tool_counts: NotRequired[Dict[str, int]]

    # active gap list that drives tool selection
    missing_fields: NotRequired[List[str]]

    # URLs already seen/processed (helps prevent loops)
    visited_urls: Annotated[List[str], operator.add]

    # convenience pointer for reminder prompts
    last_checkpoint_path: NotRequired[str]

    _initial_prompt_sent: bool = False