# outputs/stage_output.py
from pydantic import BaseModel
from typing import Dict
from research_agent.human_upgrade.graphs.outputs.substage_output import SubStageOutput

class StageOutput(BaseModel):
    stage_id: str
    stage_name: str
    substages: Dict[str, SubStageOutput]  # substage_id -> SubStageOutput
