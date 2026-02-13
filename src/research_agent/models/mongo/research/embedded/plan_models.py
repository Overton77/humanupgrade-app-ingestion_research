# research_agent/mission/plan_models.py
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field

from research_agent.models.mongo.research.enums import (
    StageMode, ObjectiveSpec, SourceRef, SliceSpec,
    InstanceOutputRequirement, OutputRequirement, OutputType
)

class SubStagePlan(BaseModel):
    sub_stage_id: str
    name: str
    description: Optional[str] = None
    agent_instances: List[str] = []
    can_run_in_parallel: bool = True
    depends_on_substages: List[str] = []

class StagePlan(BaseModel):
    stage_id: str
    name: str
    description: Optional[str] = None
    sub_stages: List[SubStagePlan] = []
    depends_on_stages: List[str] = []

class AgentInstancePlan(BaseModel):
    instance_id: str
    agent_type: str
    stage_id: str
    sub_stage_id: str
    slice: Optional[SliceSpec] = None
    objectives: List[ObjectiveSpec] = []
    starter_sources: List[SourceRef] = []

    # Preferred deps:
    requires_instance_output: List[InstanceOutputRequirement] = []

    # Replace artifacts with outputs:
    requires_outputs: List[OutputRequirement] = []
    produces_outputs: List[OutputType] = []

    notes: Optional[str] = None

class ResearchMissionPlan(BaseModel):
    mission_id: str
    stage_mode: StageMode
    target_businesses: List[str] = []
    target_people: List[str] = []
    target_products: List[str] = []
    mission_objectives: List[ObjectiveSpec] = []

    stages: List[StagePlan] = []
    agent_instances: List[AgentInstancePlan] = []

    notes: Optional[str] = None