"""
Research Plan Creation Graph (LangGraph)
- Produces an InitialResearchPlan first (mostly complete, but WITHOUT curated starter_sources bound)
- Then runs DomainExpansionAgent + SourceCuratorAgent
- Then crafts the final ResearchMissionPlan (with starter_sources + tool policies bound per instance)

You asked for:
1) A dict of keys -> formattable prompts keyed by stage_modes (only full_entities_standard filled)
2) A LangGraph StateGraph using langchain.create_agent inside nodes, similar style to your example
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, TypedDict, cast

from langchain.chat_models import BaseChatModel
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy 
from research_agent.human_upgrade.base_models import gpt_4_1, gpt_5_nano 
from research_agent.human_upgrade.prompts.research_plan_prompts import RESEARCH_PLAN_PROMPTS, FULL_ENTITIES_STANDARD_V2_MODE_SPEC_TEXT
from research_agent.human_upgrade.structured_outputs.research_plans_outputs import (StageMode,
 ResearchMissionPlanFinal, ResearchPlan,  CuratedSourcesBundle 
)  
from research_agent.human_upgrade.utils.default_tools_by_agent_type import DEFAULT_TOOLS_BY_AGENT_TYPE 
from research_agent.human_upgrade.structured_outputs.candidates_outputs import DomainCatalog  
from research_agent.human_upgrade.prompts.domain_expansion_source_curations_prompts import ( 
    PROMPT_DOMAIN_EXPANSION, PROMPT_SOURCE_CURATION, PROMPT_FINALIZE_PLAN 
) 
from research_agent.human_upgrade.utils.artifacts import save_json_artifact


def _safe_json(obj: Any) -> str:
    """
    Deterministic-ish JSON for prompt injection.
    You can swap for orjson if you prefer.
    """
    import json
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)

# =============================================================================
# Graph State
# =============================================================================

class ResearchPlanCreationState(TypedDict, total=False):
    # Inputs
    research_mode: StageMode
    connected_candidates: Dict[str, Any]  # ConnectedCandidates model_dump
    sub_agent_types: List[str]           # optional constraints/hints
    starter_domain_catalogs: List[Dict[str, Any]]  # DomainCatalog model_dump (can be empty)
    mode_and_agent_recs: Dict[str, Any]            # ModeAndAgentRecommendationsBundle model_dump
    tool_recs: Dict[str, Any]                      # ToolRecommendationsBundle model_dump

    # Artifacts as we go
    initial_research_plan: Dict[str, Any]          # InitialResearchPlan model_dump
    domain_catalogs: List[Dict[str, Any]]          # expanded domain catalogs
    curated_sources_bundle: Dict[str, Any]         # CuratedSourcesBundle model_dump
    final_research_mission_plan: Dict[str, Any]    # ResearchMissionPlan model_dump

    # Logging/debug
    run_id: str
    notes: List[str]





class InitialResearchPlanOutput(BaseModel):
    plan: ResearchPlan


class DomainExpansionOutput(BaseModel):
    domain_catalogs: List[DomainCatalog] = Field(default_factory=list)
    notes: Optional[str] = None


class SourceCurationOutput(BaseModel):
    curated_sources: CuratedSourcesBundle
    notes: Optional[str] = None


class FinalPlanOutput(BaseModel):
    plan: ResearchMissionPlanFinal




async def build_initial_research_plan_node(
    state: ResearchPlanCreationState,
   
) -> ResearchPlanCreationState:
    mode: StageMode = cast(StageMode, state.get("research_mode", "full_entities_standard"))
    prompt_tmpl = RESEARCH_PLAN_PROMPTS.get(mode, "TODO: mode not implemented")

    connected = state.get("connected_candidates", {})
    starter_catalogs = state.get("starter_domain_catalogs", [])
    mode_recs = state.get("mode_and_agent_recs", {})
    tool_recs = state.get("tool_recs", {})

    # Fill prompt placeholders
    prompt = prompt_tmpl.format(
        MODE_SPEC=FULL_ENTITIES_STANDARD_V2_MODE_SPEC_TEXT,
        CONNECTED_CANDIDATES_JSON=_safe_json(connected),
        MODE_AND_AGENT_RECOMMENDATIONS_JSON=_safe_json(mode_recs),
        TOOL_RECOMMENDATIONS_JSON=_safe_json(tool_recs),
    )

    agent: CompiledStateGraph = create_agent(
        gpt_5_nano, 
        response_format=ProviderStrategy(ResearchPlan),
        name="research_plan_builder_agent",
    )

    resp = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    out: ResearchPlan = resp["structured_response"] 

    return {
        **state,
        "initial_research_plan": out.model_dump(),
        "notes": (state.get("notes", []) + ["Initial research plan built"]),
    }


async def domain_expansion_node(
    state: ResearchPlanCreationState,
) -> ResearchPlanCreationState:
    initial_plan = state.get("initial_research_plan")
    if not initial_plan:
        raise ValueError("initial_research_plan is required before domain_expansion_node")

    connected = state.get("connected_candidates", {})
    starter_catalogs = state.get("starter_domain_catalogs", [])

    prompt = PROMPT_DOMAIN_EXPANSION.format(
        CONNECTED_CANDIDATES_JSON=_safe_json(connected),
        INITIAL_PLAN_JSON=_safe_json(initial_plan),
        STARTER_DOMAIN_CATALOGS_JSON=_safe_json(starter_catalogs),
    )

    agent: CompiledStateGraph = create_agent(
        gpt_5_nano,
        response_format=ProviderStrategy(DomainExpansionOutput),
        name="domain_expansion_agent",
    )

    resp = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    out: DomainExpansionOutput = resp["structured_response"]

    return {
        **state,
        "domain_catalogs": [dc.model_dump() for dc in out.domain_catalogs],
        "notes": (state.get("notes", []) + ["Domain expansion complete", out.notes or ""]).copy(),
    }


async def source_curation_node(
    state: ResearchPlanCreationState,
) -> ResearchPlanCreationState:
    initial_plan = state.get("initial_research_plan")
    domain_catalogs = state.get("domain_catalogs", [])
    tool_recs = state.get("tool_recs", {})

    if not initial_plan:
        raise ValueError("initial_research_plan is required before source_curation_node")

    prompt = PROMPT_SOURCE_CURATION.format(
        INITIAL_PLAN_JSON=_safe_json(initial_plan),
        DOMAIN_CATALOGS_JSON=_safe_json(domain_catalogs),
        TOOL_RECS_JSON=_safe_json(tool_recs),
    )

    agent: CompiledStateGraph = create_agent(
        gpt_5_nano,
        response_format=ProviderStrategy(SourceCurationOutput),
        name="source_curator_agent",
    )

    resp = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    out: SourceCurationOutput = resp["structured_response"]

    return {
        **state,
        "curated_sources_bundle": out.curated_sources.model_dump(),
        "notes": (state.get("notes", []) + ["Source curation complete", out.notes or ""]).copy(),
    }


async def finalize_research_mission_plan_node(
    state: ResearchPlanCreationState,
) -> ResearchPlanCreationState:
    initial_plan = state.get("initial_research_plan")
    curated_sources = state.get("curated_sources_bundle") 
    # This is all that is needed it is deterministic  

    return { 

    }


# =============================================================================
# Graph factory
# =============================================================================

def build_research_plan_creation_graph(*, llm: BaseChatModel) -> CompiledStateGraph:
    """
    Returns a compiled graph you can run like:
      graph = build_research_plan_creation_graph(llm=gpt_5_mini)
      result = await graph.ainvoke(initial_state)
    """

    graph: StateGraph = StateGraph(ResearchPlanCreationState)

    # Wrap nodes with closures to inject llm cleanly
    async def _n1(state: ResearchPlanCreationState) -> ResearchPlanCreationState:
        return await build_initial_research_plan_node(state)

    async def _n2(state: ResearchPlanCreationState) -> ResearchPlanCreationState:
        return await domain_expansion_node(state)

    async def _n3(state: ResearchPlanCreationState) -> ResearchPlanCreationState:
        return await source_curation_node(state)

    async def _n4(state: ResearchPlanCreationState) -> ResearchPlanCreationState:
        return await finalize_research_mission_plan_node(state)

    graph.add_node("build_initial_plan", _n1)
    # graph.add_node("domain_expansion", _n2)
    # graph.add_node("source_curation", _n3)
    # graph.add_node("finalize_plan", _n4)

    graph.add_edge(START, "build_initial_plan")
    # graph.add_edge("build_initial_plan", "domain_expansion")
    # graph.add_edge("domain_expansion", "source_curation")
    # graph.add_edge("source_curation", "finalize_plan")
    # graph.add_edge("finalize_plan", END) 
    graph.add_edge("build_initial_plan", END)

    return graph.compile()



async def run_plan_creation_example(*, llm: BaseChatModel) -> Dict[str, Any]:
    graph = build_research_plan_creation_graph(llm=llm)

    initial_state: ResearchPlanCreationState = {
        "run_id": f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "research_mode": "full_entities_standard",
        "connected_candidates": {
            # ConnectedCandidates.model_dump() here
        },
        "sub_agent_types": [
            # optional hints/constraints
        ],
        "starter_domain_catalogs": [],
        "mode_and_agent_recs": {
            # ModeAndAgentRecommendationsBundle.model_dump()
            "stage_mode": "full_entities_standard",
            "max_total_agent_instances": 30,
            "allow_product_reviews": False,
            "priorities": ["claims", "safety"],
        },
        "tool_recs": {
            # ToolRecommendationsBundle.model_dump()
            "allowed_tools": [
                "search.tavily", "search.exa",
                "browser.playwright", "extract.tavily",
                "doc.pdf_text", "doc.pdf_screenshot_ocr",
                "scholar.pubmed", "scholar.semantic_scholar",
                "registry.clinicaltrials",
                "fs.read", "fs.write", "context.summarize",
            ],
            "default_tools_by_agent_type": {
                **DEFAULT_TOOLS_BY_AGENT_TYPE,
            },
        },
        "notes": [],
    }

    result = await graph.ainvoke(initial_state)
    return result


async def run_initial_plan_node_test() -> Dict[str, Any]:
    """
    Test script to run only build_initial_research_plan_node with starter data.
    """
    from research_agent.human_upgrade.scripts.test_data.one_thousand_roads import (
        STARTER_CONNECTED_CANDIDATES__BRAD_PITZELE__ONETHOUSANDROADS,
        STARTER_DOMAIN_CATALOG_SET__ONETHOUSANDROADS__EWOT_EP_1301,
    )

    # Extract the catalogs from the DomainCatalogSet
    starter_catalogs = STARTER_DOMAIN_CATALOG_SET__ONETHOUSANDROADS__EWOT_EP_1301["catalogs"]
    
    # Set up initial state with starter data
    initial_state: ResearchPlanCreationState = {
        "run_id": f"test_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "research_mode": "full_entities_standard",  # Matches RESEARCH_PLAN_PROMPTS key
        "connected_candidates": STARTER_CONNECTED_CANDIDATES__BRAD_PITZELE__ONETHOUSANDROADS,
        "sub_agent_types": [],
        "starter_domain_catalogs": starter_catalogs,
        "mode_and_agent_recs": {
            "stage_mode": "full_entities_standard",  # Matches StageMode type
            "max_total_agent_instances": 30,
            "allow_product_reviews": False,
            "priorities": ["claims", "safety", "evidence"]
        },
        "tool_recs": {
            "allowed_tools": [
                "search.tavily", "search.exa",
                "browser.playwright", "extract.tavily",
                "doc.pdf_text", "doc.pdf_screenshot_ocr",
                "scholar.pubmed", "scholar.semantic_scholar",
                "registry.clinicaltrials",
                "fs.read", "fs.write", "context.summarize",
            ],
            "default_tools_by_agent_type": {
                **DEFAULT_TOOLS_BY_AGENT_TYPE,
            },
        },
        "notes": [],
    }

    # Run only the build_initial_research_plan_node
    result_state = await build_initial_research_plan_node(initial_state)
    
    # Extract the ResearchPlan from the result (now directly in initial_research_plan, not wrapped)
    research_plan_dict = result_state.get("initial_research_plan", {})
    
    # Save the ResearchPlan output
    run_id = result_state.get("run_id", "unknown")
    saved_path = await save_json_artifact(
        data=research_plan_dict,
        direction_id="test_run",
        artifact_type="research_plan",
        suffix=f"one_thousand_roads_{run_id}",
    )
    
    print(f"✅ ResearchPlan saved to: {saved_path}")
    print(f"📊 ResearchPlan contains {len(research_plan_dict.get('agent_instances', []))} agent instances")
    
    # Verify it's using PlanAgentInstance, not AgentInstancePlanWithSources
    agent_instances = research_plan_dict.get("agent_instances", [])
    if agent_instances:
        first_instance = agent_instances[0]
        # Check if it has the PlanAgentInstance structure (should have recommended_source_categories, not starter_sources)
        if "recommended_source_categories" in first_instance and "starter_sources" not in first_instance:
            print("✅ Verified: Using PlanAgentInstance structure (has recommended_source_categories, no starter_sources)")
        elif "starter_sources" in first_instance:
            print("⚠️  Warning: Found starter_sources - this suggests AgentInstancePlanWithSources instead of PlanAgentInstance")
        else:
            print("⚠️  Warning: Could not verify instance structure")
    
    return result_state


if __name__ == "__main__":
    import asyncio
    from research_agent.human_upgrade.base_models import gpt_5_nano
    
    async def main():
        result = await run_initial_plan_node_test()
        print("\n✅ Test complete!")
        return result
    
    asyncio.run(main())