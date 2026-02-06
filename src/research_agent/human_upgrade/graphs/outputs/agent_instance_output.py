# outputs/instance_output.py
from pydantic import BaseModel
from typing import List, Optional
from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference
from research_agent.human_upgrade.structured_outputs.research_plans_outputs import AgentType

class AgentInstanceOutput(BaseModel):
    instance_id: str
    agent_type: AgentType
    final_report: Optional[FileReference] = None
    file_refs: List[FileReference] = []
    workspace_root: str