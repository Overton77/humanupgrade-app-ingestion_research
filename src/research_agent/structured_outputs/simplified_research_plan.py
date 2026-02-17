"""Simplified Research Plan Models for Coordinator Agent.

These models are designed to be easier for the LLM to work with during 
the initial planning phase with the research administrator.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


class ResearchObjective(BaseModel):
    """A single research objective with success criteria."""
    objective: str = Field(..., description="Clear, specific objective")
    rationale: str = Field(..., description="Why this objective is important")
    success_criteria: List[str] = Field(
        default_factory=list,
        description="How we'll know this objective is achieved"
    )


class AgentInstance(BaseModel):
    """A specific agent instance within a substage."""
    agent_name: str = Field(..., description="Name/type of agent (e.g., 'Business Profile Agent', 'Product Claims Agent')")
    purpose: str = Field(..., description="What this agent will research/accomplish")
    target_entities: List[str] = Field(
        default_factory=list,
        description="Specific entities this agent will research (companies, products, people)"
    )
    key_questions: List[str] = Field(
        default_factory=list,
        description="Key questions this agent will answer"
    )
    estimated_cost: Optional[str] = Field(
        None,
        description="Rough estimate: low, medium, high, or specific dollar amount"
    )


class SubStage(BaseModel):
    """A substage within a research stage."""
    name: str = Field(..., description="Substage name (e.g., 'Company Background Research')")
    description: str = Field(..., description="What happens in this substage")
    agent_instances: List[AgentInstance] = Field(
        default_factory=list,
        description="Agent instances that execute in this substage"
    )
    can_run_parallel: bool = Field(
        True,
        description="Whether agent instances can run in parallel"
    )
    estimated_duration: Optional[str] = Field(
        None,
        description="Rough time estimate (e.g., '30 minutes', '2 hours')"
    )


class Stage(BaseModel):
    """A major stage in the research plan."""
    name: str = Field(..., description="Stage name (e.g., 'Discovery & Mapping', 'Deep Dive Analysis')")
    description: str = Field(..., description="Overview of this stage's purpose")
    substages: List[SubStage] = Field(
        default_factory=list,
        description="Substages within this stage"
    )
    stage_objectives: List[str] = Field(
        default_factory=list,
        description="What should be accomplished by end of this stage"
    )


class BudgetConstraints(BaseModel):
    """Budget and resource constraints for the research plan."""
    max_budget_usd: Optional[float] = Field(
        None,
        description="Maximum budget in USD (None = no hard limit)"
    )
    max_duration_hours: Optional[float] = Field(
        None,
        description="Maximum duration in hours (None = no hard limit)"
    )
    priority: Literal["speed", "cost", "depth", "balanced"] = Field(
        "balanced",
        description="What to optimize for"
    )
    notes: Optional[str] = Field(
        None,
        description="Additional budget notes or considerations"
    )


class SimplifiedResearchPlan(BaseModel):
    """Simplified research plan for coordinator-administrator collaboration."""
    
    # Core mission info
    mission_title: str = Field(..., description="Brief title for this research mission")
    mission_description: str = Field(..., description="Overview of what we're researching and why")
    
    # Scope
    target_entities: List[str] = Field(
        default_factory=list,
        description="Companies, products, people, or topics to research"
    )
    
    # Objectives
    research_objectives: List[ResearchObjective] = Field(
        default_factory=list,
        description="Key objectives this research aims to achieve"
    )
    
    # Budget & constraints
    budget_constraints: BudgetConstraints = Field(
        default_factory=BudgetConstraints,
        description="Budget and resource constraints"
    )
    
    # The plan
    stages: List[Stage] = Field(
        default_factory=list,
        description="Research stages (in execution order)"
    )
    
    # Total estimates
    estimated_total_cost: Optional[str] = Field(
        None,
        description="Total estimated cost for entire plan"
    )
    estimated_total_duration: Optional[str] = Field(
        None,
        description="Total estimated duration for entire plan"
    )
    
    # Approval workflow
    requires_approval: bool = Field(
        True,
        description="Whether this plan needs human approval before execution"
    )
    
    run_immediately_if_approved: bool = Field(
        False,
        description="If approved, whether to run immediately or wait for explicit trigger"
    )
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = Field(
        None,
        description="Additional notes, caveats, or considerations"
    )
