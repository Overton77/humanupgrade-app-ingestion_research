# outputs/mission_output.py
from pydantic import BaseModel
from typing import Dict
from research_agent.human_upgrade.graphs.outputs.stage_output import StageOutput

class MissionOutput(BaseModel):
    mission_id: str
    stages: Dict[str, StageOutput]  # stage_id -> StageOutput
