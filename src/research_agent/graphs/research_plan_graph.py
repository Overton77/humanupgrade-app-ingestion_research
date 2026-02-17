"""
Research Plan Creation Graph (LangGraph)
- Runs source expansion to discover supplementary URLs
- Then creates the complete ResearchMissionPlanFinal in one pass with all agent instances and sources

Flow: source_expansion → build_research_plan_mission
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, TypedDict, cast

from langchain.chat_models import BaseChatModel 
from dotenv import load_dotenv  
from langchain_community.utilities import oracleai
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy 
from research_agent.infrastructure.llm.base_models import gpt_4_1, gpt_5_nano, gpt_5_mini 
from research_agent.structured_outputs.research_plans_outputs import (
    StageMode,
    ResearchMissionPlanFinal,
    InitialResearchPlan,
    SourceExpansion,
    AgentInstancePlanWithSources,
)  
from research_agent.utils.default_tools_by_agent_type import DEFAULT_TOOLS_BY_AGENT_TYPE 
from research_agent.structured_outputs.candidates_outputs import DomainCatalog 
from research_agent.prompts.domain_expansion_source_curations_prompts import ( 
    PROMPT_SOURCE_EXPANSION
)  

from research_agent.utils.entity_slice_inputs import build_slicing_inputs_from_connected_candidates
from research_agent.utils.artifacts import save_json_artifact
import os  

load_dotenv()  

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") 

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


openai_search_tool: Dict[str, str] = {"type": "web_search"}  



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
    source_expansion: Dict[str, Any]               # SourceExpansion model_dump
    domain_catalogs: List[Dict[str, Any]]          # DomainCatalog model_dump list
    final_research_mission_plan: Dict[str, Any]    # ResearchMissionPlanFinal model_dump 
    agent_instance_plans_with_sources: List[Dict[str, Any]] # AgentInstancePlanWithSources model_dump list

    # Logging/debug
    run_id: str
    notes: List[str]





class SourceExpansionOutput(BaseModel):
    source_expansion: SourceExpansion
    notes: Optional[str] = None




class AgentInstancePlansWithSourcesOutput(BaseModel):
    agent_instances: List[AgentInstancePlanWithSources] = Field(default_factory=list)
    notes: Optional[str] = None


async def build_initial_research_plan_node(
    state: ResearchPlanCreationState,
) -> ResearchPlanCreationState:
    research_mode = cast(StageMode, state.get("research_mode", "full_entities_standard"))
    connected = state.get("connected_candidates", {})
    mode_and_agent_recs = state.get("mode_and_agent_recs", {})
    tool_recs = state.get("tool_recs", {})

    # Build SLICING_INPUTS from ConnectedCandidates (deterministic)
    slicing_inputs = build_slicing_inputs_from_connected_candidates(
        connected,
        max_products_per_slice=5,
        max_people_per_slice=5,
    )

    from research_agent.prompts.research_plan_prompts import format_initial_research_plan_prompt

    prompt = format_initial_research_plan_prompt(
        stage_mode=research_mode,
        connected_candidates_json=_safe_json(connected),
        mode_and_agent_recommendations_json=_safe_json(mode_and_agent_recs),
        tool_recommendations_json=_safe_json(tool_recs),
        slicing_inputs_json=_safe_json(slicing_inputs),
    )

    agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        response_format=ProviderStrategy(InitialResearchPlan),
        name="build_initial_research_plan_agent",
    )

    resp = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    out: InitialResearchPlan = resp["structured_response"]

    run_id = state.get("run_id", "unknown")
    plan_dict = out.model_dump()
    saved_path = await save_json_artifact(
        data=plan_dict,
        direction_id="test_run",
        artifact_type="initial_research_plan",
        suffix=f"{run_id}",
    )
    print(f"✅ InitialResearchPlan saved to: {saved_path}")

    return {
        **state,
        "initial_research_plan": plan_dict,
        "notes": (state.get("notes", []) + [f"Initial research plan built and saved to {saved_path}"]).copy(),
    }

async def source_expansion_node(
    state: ResearchPlanCreationState,
) -> ResearchPlanCreationState:
    connected = state.get("connected_candidates", {})
    # Use domain_catalogs if available, otherwise fall back to starter_domain_catalogs
    domain_catalogs = state.get("starter_domain_catalogs", []) or state.get("domain_catalogs", [])

    prompt = PROMPT_SOURCE_EXPANSION.format(
        CONNECTED_CANDIDATES_JSON=_safe_json(connected),
        DOMAIN_CATALOGS_JSON=_safe_json(domain_catalogs),
    )

    agent: CompiledStateGraph = create_agent(
        gpt_5_nano,
        tools=[openai_search_tool],
        response_format=ProviderStrategy(SourceExpansionOutput),
        name="source_expansion_agent",
    )

    resp = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    out: SourceExpansionOutput = resp["structured_response"]

    # Save the source expansion artifact
    run_id = state.get("run_id", "unknown")
    expansion_dict = out.source_expansion.model_dump()
    saved_path = await save_json_artifact(
        data=expansion_dict,
        direction_id="test_run",
        artifact_type="source_expansion",
        suffix=f"{run_id}",
    )
    print(f"✅ SourceExpansion saved to: {saved_path}")

    return {
        **state,
        "source_expansion": expansion_dict,
        "notes": (state.get("notes", []) + [f"Source expansion complete and saved to {saved_path}", out.notes or ""]).copy(),
    }


async def attach_sources_to_agent_instances_node(
    state: ResearchPlanCreationState,
) -> ResearchPlanCreationState:
    initial_plan = state.get("initial_research_plan", {})
    source_expansion = state.get("source_expansion", {})
    domain_catalogs = state.get("domain_catalogs", []) or state.get("starter_domain_catalogs", [])

    if not initial_plan:
        raise ValueError("initial_research_plan is required before attach_sources_to_agent_instances_node")
    if not source_expansion:
        raise ValueError("source_expansion is required before attach_sources_to_agent_instances_node")

    # You’ll create this new prompt template
    from research_agent.prompts.research_plan_prompts import ATTACH_SOURCES_TO_AGENT_INSTANCES_PROMPTS
    research_mode = cast(StageMode, state.get("research_mode", "full_entities_standard"))
    prompt_tmpl = ATTACH_SOURCES_TO_AGENT_INSTANCES_PROMPTS.get(research_mode, "TODO: mode not implemented")

    prompt = prompt_tmpl.format(
        INITIAL_PLAN_JSON=_safe_json(initial_plan),
        SOURCE_EXPANSION_JSON=_safe_json(source_expansion),
        DOMAIN_CATALOGS_JSON=_safe_json(domain_catalogs),
    )

    agent: CompiledStateGraph = create_agent(
        gpt_5_mini,  
        response_format=ProviderStrategy(AgentInstancePlansWithSourcesOutput),
        name="attach_sources_to_agent_instances_agent",
    )

    resp = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    out: AgentInstancePlansWithSourcesOutput = resp["structured_response"]

    run_id = state.get("run_id", "unknown")
    instances_dict_list = [x.model_dump() for x in out.agent_instances]

    saved_path = await save_json_artifact(
        data={"agent_instances": instances_dict_list, "notes": out.notes},
        direction_id="test_run",
        artifact_type="agent_instance_plans_with_sources",
        suffix=f"{run_id}",
    )
    print(f"✅ AgentInstancePlanWithSources list saved to: {saved_path}")
    print(f"📌 Returned {len(instances_dict_list)} agent instance plans w/ sources")

    return {
        **state,
        "agent_instance_plans_with_sources": instances_dict_list,
        "notes": (state.get("notes", []) + [f"Agent instance sources attached and saved to {saved_path}", out.notes or ""]).copy(),
    }


def _ordered_instance_ids(initial_plan: Dict[str, Any]) -> List[str]:
    base_instances = initial_plan.get("agent_instances", [])
    ids: List[str] = []
    for inst in base_instances:
        iid = inst.get("instance_id")
        if not iid:
            raise ValueError("Missing instance_id in initial_plan.agent_instances")
        ids.append(iid)
    return ids


def _collect_stage_references(initial_plan: Dict[str, Any]) -> List[str]:
    stages = initial_plan.get("stages", [])
    referenced: List[str] = []
    for st in stages:
        for ss in (st.get("sub_stages") or []):
            referenced.extend(ss.get("agent_instances") or [])
    return referenced


def _assert_stage_refs_consistent(*, stage_refs: List[str], instance_ids: List[str]) -> None:
    instance_id_set = set(instance_ids)
    missing = [iid for iid in stage_refs if iid not in instance_id_set]
    if missing:
        raise ValueError(f"Stage/substage references unknown instance_ids: {missing[:10]} (and {max(0, len(missing)-10)} more)")


def _assert_invariant_fields_match(base: Dict[str, Any], src: Dict[str, Any]) -> None:
    # Strict invariants
    for f in ["instance_id", "agent_type", "stage_id", "sub_stage_id"]:
        if base.get(f) != src.get(f):
            raise ValueError(f"Invariant field changed for {base.get('instance_id')}: field={f}")

    # Slice: compare only the identity + core contents (avoid None/missing noise)
    base_slice = base.get("slice") or None
    src_slice = src.get("slice") or None

    if (base_slice is None) != (src_slice is None):
        raise ValueError(f"Slice presence changed for {base.get('instance_id')}")

    if base_slice and src_slice:
        # Require slice_id match
        if base_slice.get("slice_id") != src_slice.get("slice_id"):
            raise ValueError(f"slice_id changed for {base.get('instance_id')}")
        # Require core lists match exactly (this matters for slicing correctness)
        if base_slice.get("product_names", []) != src_slice.get("product_names", []):
            raise ValueError(f"slice.product_names changed for {base.get('instance_id')}")
        if base_slice.get("person_names", []) != src_slice.get("person_names", []):
            raise ValueError(f"slice.person_names changed for {base.get('instance_id')}")

    # Objectives + artifact dependencies should not change
    for f in ["objectives", "requires_artifacts", "produces_artifacts"]:
        if base.get(f) != src.get(f):
            raise ValueError(f"Invariant field changed for {base.get('instance_id')}: field={f}")

def _index_by_instance_id(instances: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for inst in instances:
        iid = inst.get("instance_id")
        if not iid:
            raise ValueError("Missing instance_id in agent instance")
        if iid in out:
            raise ValueError(f"Duplicate instance_id: {iid}")
        out[iid] = inst
    return out



async def assemble_research_mission_plan_final_node(
    state: ResearchPlanCreationState,
) -> ResearchPlanCreationState:
    initial_plan = state.get("initial_research_plan", {})
    with_sources_list = state.get("agent_instance_plans_with_sources", [])

    if not initial_plan:
        raise ValueError("initial_research_plan is required before assemble_research_mission_plan_final_node")
    if with_sources_list is None:
        raise ValueError("agent_instance_plans_with_sources is required before assemble_research_mission_plan_final_node")

    base_instances = initial_plan.get("agent_instances", [])
    base_ids_in_order = _ordered_instance_ids(initial_plan)

    base_by_id = _index_by_instance_id(base_instances)
    with_sources_by_id = _index_by_instance_id(with_sources_list)

    # 1:1 match (strict)
    missing = [iid for iid in base_by_id.keys() if iid not in with_sources_by_id]
    extra = [iid for iid in with_sources_by_id.keys() if iid not in base_by_id]

    if missing:
        raise ValueError(f"Missing AgentInstancePlanWithSources for instance_ids: {missing[:10]} (and {max(0, len(missing)-10)} more)")
    if extra:
        raise ValueError(f"Unexpected extra instance_ids in AgentInstancePlanWithSources: {extra[:10]} (and {max(0, len(extra)-10)} more)")

    # Invariant checks
    for iid, base in base_by_id.items():
        _assert_invariant_fields_match(base, with_sources_by_id[iid])

    # Validate stage references still make sense
    stage_refs = _collect_stage_references(initial_plan)
    _assert_stage_refs_consistent(stage_refs=stage_refs, instance_ids=base_ids_in_order)

    # Assemble final plan (preserve exact agent_instances order)
    final_dict = {
        "mission_id": initial_plan.get("mission_id"),
        "stage_mode": initial_plan.get("stage_mode", state.get("research_mode", "full_entities_standard")),
        "target_businesses": initial_plan.get("target_businesses", []),
        "target_people": initial_plan.get("target_people", []),
        "target_products": initial_plan.get("target_products", []),
        "mission_objectives": initial_plan.get("mission_objectives", []),
        "stages": initial_plan.get("stages", []),
        "agent_instances": [with_sources_by_id[iid] for iid in base_ids_in_order],
        "notes": initial_plan.get("notes"),
    }

    validated = ResearchMissionPlanFinal(**final_dict)
    plan_dict = validated.model_dump()

    run_id = state.get("run_id", "unknown")
    saved_path = await save_json_artifact(
        data=plan_dict,
        direction_id="test_run",
        artifact_type="research_mission_plan",
        suffix=f"{run_id}",
    )

    print(f"✅ ResearchMissionPlanFinal assembled and saved to: {saved_path}")
    print(f"📊 Contains {len(plan_dict.get('agent_instances', []))} agent instances")

    return {
        **state,
        "final_research_mission_plan": plan_dict,
        "notes": (state.get("notes", []) + [f"Research mission plan assembled and saved to {saved_path}"]).copy(),
    }

# =============================================================================
# Graph factory
# =============================================================================

def build_research_plan_creation_graph(*, llm: BaseChatModel) -> CompiledStateGraph:
    graph: StateGraph = StateGraph(ResearchPlanCreationState)

    async def _n1(state: ResearchPlanCreationState) -> ResearchPlanCreationState:
        return await build_initial_research_plan_node(state)

    async def _n2(state: ResearchPlanCreationState) -> ResearchPlanCreationState:
        return await source_expansion_node(state)

    async def _n3(state: ResearchPlanCreationState) -> ResearchPlanCreationState:
        return await attach_sources_to_agent_instances_node(state)

    async def _n4(state: ResearchPlanCreationState) -> ResearchPlanCreationState:
        return await assemble_research_mission_plan_final_node(state)

    graph.add_node("build_initial_plan", _n1)
    graph.add_node("source_expansion", _n2)
    graph.add_node("attach_sources_to_agent_instances", _n3)
    graph.add_node("assemble_final_plan", _n4)

    graph.add_edge(START, "build_initial_plan")
    graph.add_edge("build_initial_plan", "source_expansion")
    graph.add_edge("source_expansion", "attach_sources_to_agent_instances")
    graph.add_edge("attach_sources_to_agent_instances", "assemble_final_plan")
    graph.add_edge("assemble_final_plan", END)

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


async def run_research_plan_test() -> Dict[str, Any]:
    """
    Test script to run the full research plan creation graph with starter data.
    """
    from research_agent.scripts.test_data.one_thousand_roads import (
        STARTER_CONNECTED_CANDIDATES__BRAD_PITZELE__ONETHOUSANDROADS,
        STARTER_DOMAIN_CATALOG_SET__ONETHOUSANDROADS__EWOT_EP_1301,
    )

    # Extract the catalogs from the DomainCatalogSet
    starter_catalogs = STARTER_DOMAIN_CATALOG_SET__ONETHOUSANDROADS__EWOT_EP_1301["catalogs"]
    
    # Set up initial state with starter data
    initial_state: ResearchPlanCreationState = {
        "run_id": f"test_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "research_mode": "full_entities_basic",  
        "connected_candidates": STARTER_CONNECTED_CANDIDATES__BRAD_PITZELE__ONETHOUSANDROADS,
        "sub_agent_types": [],
        "starter_domain_catalogs": starter_catalogs,
        "mode_and_agent_recs": {
            "stage_mode": "full_entities_basic",  # Matches research_mode
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

    # Run the full graph
    graph = build_research_plan_creation_graph(llm=gpt_5_mini)
    result_state = await graph.ainvoke(initial_state)
    
    # Extract the ResearchMissionPlanFinal from the result
    research_plan_dict = result_state.get("final_research_mission_plan", {})
    
    # Save the ResearchMissionPlanFinal output
    run_id = result_state.get("run_id", "unknown")
    saved_path = await save_json_artifact(
        data=research_plan_dict,
        direction_id="test_run",
        artifact_type="research_mission_plan",
        suffix=f"one_thousand_roads_{run_id}",
    )
    
    print(f"✅ ResearchMissionPlanFinal saved to: {saved_path}")
    print(f"📊 ResearchMissionPlanFinal contains {len(research_plan_dict.get('agent_instances', []))} agent instances")
    
    # Verify it's using AgentInstancePlanWithSources with starter_sources
    agent_instances = research_plan_dict.get("agent_instances", [])
    if agent_instances:
        first_instance = agent_instances[0]
        if "starter_sources" in first_instance:
            print("✅ Verified: Using AgentInstancePlanWithSources structure (has starter_sources)")
        else:
            print("⚠️  Warning: Missing starter_sources in agent instance")
    
    return result_state


if __name__ == "__main__":
    import asyncio
    from research_agent.infrastructure.llm.base_models import gpt_5_nano
    
    async def main():
        result = await run_research_plan_test()
        print("\n✅ Test complete!")
        return result
    
    asyncio.run(main())