# outputs/substage_output.py
from pydantic import BaseModel
from typing import Dict, List
from research_agent.human_upgrade.graphs.outputs.agent_instance_output import AgentInstanceOutput

class SubStageOutput(BaseModel):
    substage_id: str
    substage_name: str
    instance_ids: List[str]
    instance_outputs: Dict[str, AgentInstanceOutput]