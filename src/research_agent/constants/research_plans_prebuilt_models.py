"""
Pre-built Research Plan Definitions

This module contains comprehensive definitions for research plan modes, including:
- Stage and sub-stage structures
- Agent type definitions with tools and outputs
- Dependencies and parallelization rules
- Detailed descriptions and purposes

These definitions can be used in prompts, validation, and plan generation.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field 

# TODO: Will probably need to add Structured Outputs where needed 




class AgentTypeDefinition(BaseModel):
    """Definition of an agent type with its tools, outputs, and description."""
    name: str
    description: str
    default_tools: List[str] = Field(default_factory=list)
    typical_outputs: List[str] = Field(default_factory=list)
    source_focus: Optional[str] = None


class SubStageDefinition(BaseModel):
    """Definition of a sub-stage within a research plan."""
    sub_stage_id: str  # e.g., "S1.1"
    name: str
    description: str
    purpose: str  # What questions this stage answers
    responsibilities: List[str] = Field(default_factory=list)
    agent_type: str
    outputs: List[str] = Field(default_factory=list)
    source_focus: str
    parallelization_notes: Optional[str] = None
    is_required: bool = True
    is_optional: bool = False
    depends_on_substages: List[str] = Field(default_factory=list)


class StageDefinition(BaseModel):
    """Definition of a stage within a research plan."""
    stage_id: str  # e.g., "S1"
    name: str
    description: str
    purpose: str
    assumptions: Optional[str] = None
    sub_stages: List[SubStageDefinition] = Field(default_factory=list)
    dependencies: str = ""  # Description of stage dependencies
    parallelization: str = ""  # Description of parallelization rules
    what_it_intentionally_does_not_do: Optional[List[str]] = None


class PrebuiltResearchPlan(BaseModel):
    """Complete definition of a pre-built research plan mode."""
    stage_mode: str
    goal: str
    description: str
    planning_rule: str
    execution_model: str
    stages: List[StageDefinition] = Field(default_factory=list)
    agent_type_definitions: Dict[str, AgentTypeDefinition] = Field(default_factory=dict)
    global_tool_expectations: str = ""
    what_this_mode_intentionally_does_not_do: List[str] = Field(default_factory=list)
    why_ready_to_implement: List[str] = Field(default_factory=list)
