"""
Entity Intel Graph: Connected Candidates + Sources

Renamed + generalized:
- Graph name: EntityIntelConnectedCandidatesAndSources
- Replaced episode/webPageSummary/episodePageUrl with:
  - query
  - starter_sources
  - starter_content

This graph is intended to have a SMALL InputState and SMALL OutputState for easy API/task usage.
"""

from __future__ import annotations

import asyncio
import json
import operator
import os
from datetime import datetime
from typing import Any, Dict, List,  Annotated

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain.tools import BaseTool
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from research_agent.clients.langsmith_client import pull_prompt_from_langsmith
from research_agent.infrastructure.llm.base_models import gpt_5_mini
from research_agent.graphs.nodes.intel_mongo_nodes_beanie import (
    initialize_run_node,
    persist_seeds_node,
    persist_official_sources_node,
    persist_domain_catalogs_node_beanie,
    persist_connected_candidates_slices_node,
    persist_candidates_node_beanie,
)
from research_agent.utils.logger import logger
from research_agent.infrastructure.storage.postgres.langgraph_persistence import get_persistence
from research_agent.prompts.candidates_prompts import (
    PROMPT_NODE_OFFICIAL_STARTER_SOURCES,
    PROMPT_NODE_DOMAIN_CATALOGS_FOCUSED,
    PROMPT_NODE_C1_ORG_IDENTITY_PEOPLE_TECH_SLICE,
    PROMPT_NODE_C2_PRODUCTS_COMPOUNDS_SLICE,
    PROMPT_NODE_C3_CONNECTED_CANDIDATES_ASSEMBLER,
)
from research_agent.prompts.seed_prompts import PROMPT_NODE_SEED_ENTITY_EXTRACTION
from research_agent.tools.web_search_tools import (
    tavily_extract_validation,
    tavily_map_validation,
    tavily_search_validation,
    wiki_tool,
)
from research_agent.utils.artifacts import save_json_artifact
from research_agent.utils.dedupe import _dedupe_keep_order, _take
from research_agent.utils.formatting import (
    format_seed_extraction_for_prompt,
)

from research_agent.structured_outputs.candidates_outputs import (
    OrgIdentityPeopleTechnologySlice,
    ProductsAndCompoundsSlice,
    CandidateSourcesConnected,
    ConnectedCandidates,
    ConnectedCandidatesAssemblerInput,
    DomainCatalogSet,
    OfficialStarterSources,
   
    SeedExtraction,
)
from research_agent.infrastructure.storage.redis.client import get_streams_manager
from research_agent.infrastructure.storage.redis.streams_manager import StreamAddress
from research_agent.infrastructure.storage.redis.event_registry import (
    GROUP_GRAPH,
    CHANNEL_ENTITY_DISCOVERY,
    EVENT_TYPE_SLICE_STARTED,
    EVENT_TYPE_SLICE_COMPLETE,
    EVENT_TYPE_MERGE_COMPLETE,
)

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")  # noqa: SIM112

openai_search_tool: Dict[str, str] = {"type": "web_search"}


# -----------------------------------------------------------------------------
# LangGraph API boundary schemas
# -----------------------------------------------------------------------------
class EntityIntelConnectedCandidatesAndSourcesInputState(TypedDict, total=False):
    """
    Small input state intended for FastAPI + Taskiq request bodies.

    query: the user's intent / question / target entity to investigate
    starter_sources: optional starting URLs/domains to anchor discovery
    starter_content: optional "starter context" (notes, pasted text, previous summary, etc.)
    intel_run_id: optional run ID for persistence and event tracking (if not provided, will be generated)
    """
    query: str
    starter_sources: List[str]
    starter_content: str
    intel_run_id: str


class EntityIntelConnectedCandidatesAndSourcesOutputState(TypedDict, total=False):
    """
    Small output state intended for FastAPI + Taskiq response bodies.
    
    Returns the final merged candidate sources plus metadata about what was persisted.
    """
    candidate_sources: CandidateSourcesConnected
    intel_run_id: str
    intel_pipeline_version: str
    candidate_entity_ids: List[str]
    dedupe_group_map: Dict[str, str]


class EntityIntelConnectedCandidatesAndSourcesState(
    EntityIntelConnectedCandidatesAndSourcesInputState,
    EntityIntelConnectedCandidatesAndSourcesOutputState,
    TypedDict,
    total=False,
):
    """
    Overall internal state for orchestration + persistence.

    NOTE: This can evolve without breaking API contracts, because the graph
    uses input_schema/output_schema.
    """

    # Core tool-loop plumbing
    llm_calls: int
    tool_calls: int

    # ----------------------------
    # Generalized run context
    # ----------------------------
    query: str
    starter_sources: List[str]
    starter_content: str

    # Existing outputs
    seed_extraction: SeedExtraction

    # Fanout collection (one per DomainCatalog slice)
    candidate_sources_slice_outputs: Annotated[List[CandidateSourcesConnected], operator.add]

    # Final merged output (also OutputState)
    candidate_sources: CandidateSourcesConnected

    # ----------------------------
    # Intel orchestration (persisted bookkeeping)
    # ----------------------------
    intel_run_id: str
    intel_pipeline_version: str

    # Outputs from persist_candidates_node
    candidate_entity_ids: List[str]          # candidateEntityId inserted for this run
    dedupe_group_map: Dict[str, str]         # entityKey -> dedupeGroupId

    # Domain catalogs
    official_starter_sources: OfficialStarterSources
    domain_catalogs: DomainCatalogSet
    domain_catalog_set_id: str
    domain_catalog_extracted_at: datetime | str

    error: str
    steps_taken: int


# -----------------------------------------------------------------------------
# Graph helpers
# -----------------------------------------------------------------------------
def _select_org_identity_people_tech_urls(catalog: Dict[str, Any]) -> Dict[str, List[str]]:
    homepage = _dedupe_keep_order(catalog.get("homepageUrls") or [])
    about = _dedupe_keep_order(catalog.get("aboutUrls") or [])
    leadership = _dedupe_keep_order(catalog.get("leadershipUrls") or [])
    press = _dedupe_keep_order(catalog.get("pressUrls") or [])
    help_center = _dedupe_keep_order(catalog.get("helpCenterUrls") or [])
    platform = _dedupe_keep_order(catalog.get("platformUrls") or [])
    research = _dedupe_keep_order(catalog.get("researchUrls") or [])
    policy = _dedupe_keep_order(catalog.get("policyUrls") or [])
    regulatory = _dedupe_keep_order(catalog.get("regulatoryUrls") or [])

    # Identity slice is precision-first
    return {
        "homepageUrls": _take(homepage, 2),
        "aboutUrls": _take(about, 6),
        "leadershipUrls": _take(leadership, 25),
        "researchUrls": _take(research, 20),
        "platformUrls": _take(platform, 15),
        "pressUrls": _take(press, 10),
        "helpCenterUrls": _take(help_center, 6),
        "policyUrls": _take(policy, 6),
        "regulatoryUrls": _take(regulatory, 6),
    }


def _select_offerings_products_compounds_urls(catalog: Dict[str, Any]) -> Dict[str, List[str]]:
    product_index = _dedupe_keep_order(catalog.get("productIndexUrls") or [])
    product_pages = _dedupe_keep_order(catalog.get("productPageUrls") or [])
    docs = _dedupe_keep_order(catalog.get("documentationUrls") or [])
    labels = _dedupe_keep_order(catalog.get("labelUrls") or [])
    help_center = _dedupe_keep_order(catalog.get("helpCenterUrls") or [])
    research = _dedupe_keep_order(catalog.get("researchUrls") or [])
    patents = _dedupe_keep_order(catalog.get("patentUrls") or [])
    landing_pages = _dedupe_keep_order(catalog.get("landingPageUrls") or [])

    return {
        "productIndexUrls": _take(product_index, 12),
        "productPageUrls": _take(product_pages, 60),
        "documentationUrls": _take(docs, 30),
        "labelUrls": _take(labels, 15),
        "helpCenterUrls": _take(help_center, 10),
        "researchUrls": _take(research, 12),
        "patentUrls": _take(patents, 8),
        "landingPageUrls": _take(landing_pages, 10),
    }

def _filter_catalogs_for_fanout(
    catalogs: List[Dict[str, Any]] | List[Any],
    max_catalogs: int = 3,
) -> List[Dict[str, Any]]:
    """
    Keep the smallest set of highest-value DomainCatalogs for downstream slice fanout.
    Org-first; allow shop/docs/help if distinct and within budget.
    """
    # normalize to dicts
    normalized: List[Dict[str, Any]] = [
        c.model_dump() if hasattr(c, "model_dump") else dict(c)
        for c in (catalogs or [])
    ]

    def score(cat: Dict[str, Any]) -> tuple:
        # lower tuple is better
        priority = int(cat.get("priority") or 99)
        role = (cat.get("sourceDomainRole") or "").lower()
        key = (cat.get("targetEntityKey") or "")
        is_org = 0 if key.startswith("ORG:") else 1
        role_rank = {"primary": 0, "shop": 1, "help": 2, "docs": 2, "blog": 5, "other": 9}.get(role, 6)
        return (is_org, priority, role_rank)

    normalized.sort(key=score)

    # de-dupe by baseDomain
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for cat in normalized:
        bd = (cat.get("baseDomain") or "").lower().strip()
        if not bd or bd in seen:
            continue
        out.append(cat)
        seen.add(bd)
        if len(out) >= max_catalogs:
            break

    return out


VALIDATION_TOOLS: List[BaseTool] = [
    wiki_tool,
    tavily_search_validation,
    tavily_extract_validation,
    tavily_map_validation,
]

OFFICIAL_STARTER_TOOLS = [
    tavily_search_validation,
    tavily_extract_validation,
    wiki_tool,
]

DOMAIN_CATALOG_TOOLS = [
    tavily_map_validation,
    tavily_extract_validation,
]

CONNECTED_TOOLS = [
    wiki_tool,
    tavily_search_validation,   # fallback only
    tavily_extract_validation,  # primary
    # tavily_map_validation intentionally omitted in Node C
]


# -----------------------------------------------------------------------------
# Helper: Progress Event Publishing
# -----------------------------------------------------------------------------
async def _publish_progress(
    run_id: str,
    event_type: str,
    data: Dict[str, Any],
) -> None:
    """
    Helper to publish progress events to Redis Streams.
    
    This allows real-time WebSocket updates as the graph executes.
    """
    try:
        manager = await get_streams_manager()
        addr = StreamAddress(
            group=GROUP_GRAPH,
            channel=CHANNEL_ENTITY_DISCOVERY,
            key=run_id,
        )
        await manager.publish(addr, event_type=event_type, data=data)
    except Exception as e:
        # Don't fail the node if event publishing fails
        logger.warning(f"Failed to publish progress event {event_type}: {e}")


# -----------------------------------------------------------------------------
# Nodes
# -----------------------------------------------------------------------------
async def seed_extraction_node(
    state: EntityIntelConnectedCandidatesAndSourcesState,
) -> EntityIntelConnectedCandidatesAndSourcesState:
    query: str = state.get("query", "")
    starter_sources: List[str] = state.get("starter_sources", []) or []
    starter_content: str = state.get("starter_content", "")

    if not query:
        raise ValueError("query is required")

    logger.info("🌱 Starting seed extraction for query: %s", query[:120])

    # NOTE: Prompts will be updated to accept these generalized fields.
    seed_extraction_prompt: str = PROMPT_NODE_SEED_ENTITY_EXTRACTION.format(
        query=query,
        starter_sources_json=json.dumps(starter_sources, indent=2),
        starter_content=starter_content,
    )

    seed_extraction_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        tools=[openai_search_tool],
        response_format=ProviderStrategy(SeedExtraction),
        name="seed_entity_extraction_agent",
    )

    response = await seed_extraction_agent.ainvoke(
        {"messages": [{"role": "user", "content": seed_extraction_prompt}]}
    )

    seed_extraction_output: SeedExtraction = response["structured_response"]

    logger.info(
        "✅ Seed extraction complete: people=%s orgs=%s products=%s compounds=%s tech=%s",
        len(seed_extraction_output.people_candidates or []),
        len(seed_extraction_output.organization_candidates or []),
        len(seed_extraction_output.product_candidates or []),
        len(seed_extraction_output.compound_candidates or []),
        len(seed_extraction_output.technology_candidates or []),
    )


    return {"seed_extraction": seed_extraction_output}


async def official_sources_node(
    state: EntityIntelConnectedCandidatesAndSourcesState,
) -> EntityIntelConnectedCandidatesAndSourcesState:
    seed_extraction: SeedExtraction | None = state.get("seed_extraction")
    if seed_extraction is None:
        raise ValueError("seed_extraction is required")

    query: str = state.get("query", "")
    starter_sources: List[str] = state.get("starter_sources", []) or []
    starter_content: str = state.get("starter_content", "")

    formatted_fields: Dict[str, str] = format_seed_extraction_for_prompt(seed_extraction)

    prompt: str = PROMPT_NODE_OFFICIAL_STARTER_SOURCES.format(
        query=query,
        starter_sources_json=json.dumps(starter_sources, indent=2),
        starter_content=starter_content,
        people_candidates=formatted_fields.get("people_candidates", ""),
        organization_candidates=formatted_fields.get("organization_candidates", ""),
        product_candidates=formatted_fields.get("product_candidates", ""),
        technology_candidates=formatted_fields.get("technology_candidates", ""),
    )

    agent = create_agent(
        gpt_5_mini,
        tools=OFFICIAL_STARTER_TOOLS,
        response_format=ProviderStrategy(OfficialStarterSources),
        name="official_starter_sources_agent",
    )

    response = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    official_sources: OfficialStarterSources = response["structured_response"]

    await save_json_artifact(
        official_sources.model_dump(),
        "test_run",
        "official_starter_sources",
        suffix=query.replace("/", "_")[:30] or "query",
    )

    return {"official_starter_sources": official_sources}

async def domain_catalogs_node(
    state: EntityIntelConnectedCandidatesAndSourcesState,
) -> EntityIntelConnectedCandidatesAndSourcesState:
    official_sources: OfficialStarterSources | None = state.get("official_starter_sources")
    if official_sources is None:
        raise ValueError("official_starter_sources is required for domain_catalogs_node")

    query: str = state.get("query", "")
    starter_sources: List[str] = state.get("starter_sources", []) or []
    starter_content: str = state.get("starter_content", "")

    # Hard guardrail (you can later make this configurable per endpoint/task)
    selected_domain_budget: int = 3

    prompt = PROMPT_NODE_DOMAIN_CATALOGS_FOCUSED.format(
        query=query,
        starter_sources_json=json.dumps(starter_sources, indent=2),
        starter_content=starter_content,
        official_starter_sources_json=official_sources.model_dump_json(indent=2),
        selected_domain_budget=selected_domain_budget,
    )

    agent = create_agent(
        gpt_5_mini,
        tools=DOMAIN_CATALOG_TOOLS,
        response_format=ProviderStrategy(DomainCatalogSet),
        name="domain_catalogs_focused_agent",
    )

    response = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    domain_catalogs: DomainCatalogSet = response["structured_response"]

    await save_json_artifact(
        domain_catalogs.model_dump(),
        "test_run",
        "domain_catalogs",
        suffix=query.replace("/", "_")[:30] or "query",
    )

    return {"domain_catalogs": domain_catalogs}


async def _ainvoke_bounded(
    agent: CompiledStateGraph,
    payload: Dict[str, Any],
    sem: asyncio.Semaphore,
) -> Dict[str, Any]:
    async with sem:
        return await agent.ainvoke(payload)


def fanout_candidate_source_slices(
    state: EntityIntelConnectedCandidatesAndSourcesState,
) -> List[Send]:
    # Prefer the filtered list if persist step provided it
    catalogs_any = state.get("domain_catalogs_for_fanout")

    if catalogs_any is None:
        domain_catalogs = state.get("domain_catalogs")
        if domain_catalogs is None:
            logger.warning("No domain_catalogs found in state; returning empty Send list")
            return []
        catalogs_any = domain_catalogs.catalogs if hasattr(domain_catalogs, "catalogs") else (domain_catalogs.get("catalogs") or [])

    filtered_catalogs = _filter_catalogs_for_fanout(catalogs_any, max_catalogs=3)

    sends: List[Send] = []
    total_slices = len(filtered_catalogs)
    
    for idx, cat in enumerate(filtered_catalogs):
        sends.append(
            Send(
                "candidate_sources_slice",
                {
                    "catalog": cat,
                    "query": state.get("query", ""),
                    "starter_sources": state.get("starter_sources", []) or [],
                    "starter_content": state.get("starter_content", ""),
                    "seed_extraction": (
                        state["seed_extraction"].model_dump()
                        if hasattr(state["seed_extraction"], "model_dump")
                        else state["seed_extraction"]
                    ),
                    "official_starter_sources": (
                        state["official_starter_sources"].model_dump()
                        if hasattr(state["official_starter_sources"], "model_dump")
                        else state["official_starter_sources"]
                    ),
                    # Add slice tracking metadata
                    "slice_index": idx,
                    "total_slices": total_slices,
                    "intel_run_id": state.get("intel_run_id"),  # Pass run_id for progress events
                },
            )
        )

    return sends

async def candidate_sources_slice_node(
    state: EntityIntelConnectedCandidatesAndSourcesState,
) -> EntityIntelConnectedCandidatesAndSourcesState:
    """
    For ONE DomainCatalog:
      - run OrgIdentity+People+Technology agent (C1) and Products+Compounds agent (C2) concurrently (bounded)
      - run Assembler agent (C3) to produce ConnectedCandidates
      - return CandidateSourcesConnected with a single ConnectedCandidates in .connected
    """
    catalog: Dict[str, Any] | None = state.get("catalog")
    if catalog is None:
        raise ValueError("catalog is required in candidate_sources_slice_node (should be provided via Send)")
    
    query: str = state.get("query", "")
    starter_sources: List[str] = state.get("starter_sources", []) or []
    starter_content: str = state.get("starter_content", "")

    seed_extraction = state.get("seed_extraction")
    if seed_extraction is None:
        raise ValueError("seed_extraction is required in candidate_sources_slice_node")
    
    official_sources = state.get("official_starter_sources")
    if official_sources is None:
        raise ValueError("official_starter_sources is required in candidate_sources_slice_node")

    base_domain = catalog.get("baseDomain") or "unknown"
    
    # Get slice tracking metadata
    slice_index = state.get("slice_index", 0)
    total_slices = state.get("total_slices", 1)
    run_id = state.get("intel_run_id")
    
    # Publish slice started event
    if run_id:
        await _publish_progress(
            run_id=run_id,
            event_type=EVENT_TYPE_SLICE_STARTED,
            data={
                "base_domain": base_domain,
                "slice_index": slice_index,
                "total_slices": total_slices,
            },
        )

    # --- prepare small URL slices ---
    org_urls = _select_org_identity_people_tech_urls(catalog)
    offerings_urls = _select_offerings_products_compounds_urls(catalog)

    # --- prompts ---
    org_prompt = PROMPT_NODE_C1_ORG_IDENTITY_PEOPLE_TECH_SLICE.format(
        query=query,
        starter_content=starter_content,
        base_domain=base_domain,
        url_buckets_json=json.dumps(org_urls, indent=2),
        catalog_min_json=json.dumps(
            {
                "baseDomain": catalog.get("baseDomain"),
                "mappedFromUrl": catalog.get("mappedFromUrl"),
                "sourceDomainRole": catalog.get("sourceDomainRole"),
            },
            indent=2,
        ),
        seed_json=json.dumps(seed_extraction, default=str, indent=2),
        official_sources_json=json.dumps(official_sources, default=str, indent=2),
    )

    offerings_prompt = PROMPT_NODE_C2_PRODUCTS_COMPOUNDS_SLICE.format(
        query=query,
        starter_content=starter_content,
        base_domain=base_domain,
        url_buckets_json=json.dumps(offerings_urls, indent=2),
        catalog_min_json=json.dumps(
            {
                "baseDomain": catalog.get("baseDomain"),
                "mappedFromUrl": catalog.get("mappedFromUrl"),
                "sourceDomainRole": catalog.get("sourceDomainRole"),
            },
            indent=2,
        ),
        seed_json=json.dumps(seed_extraction, default=str, indent=2),
        official_sources_json=json.dumps(official_sources, default=str, indent=2),
    )

    # --- agents ---
    org_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        tools=CONNECTED_TOOLS,
        response_format=ProviderStrategy(OrgIdentityPeopleTechnologySlice),
        name=f"org_identity_people_tech_slice_agent_{base_domain}",
    )

    offerings_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        tools=CONNECTED_TOOLS,
        response_format=ProviderStrategy(ProductsAndCompoundsSlice),
        name=f"products_compounds_slice_agent_{base_domain}",
    )

    # Bound concurrency inside the slice node (2 calls)
    sem = asyncio.Semaphore(2)

    org_task = _ainvoke_bounded(
        org_agent,
        {"messages": [{"role": "user", "content": org_prompt}]},
        sem,
    )
    offerings_task = _ainvoke_bounded(
        offerings_agent,
        {"messages": [{"role": "user", "content": offerings_prompt}]},
        sem,
    )

    org_resp, offerings_resp = await asyncio.gather(org_task, offerings_task)

    org_slice: OrgIdentityPeopleTechnologySlice = org_resp["structured_response"]
    products_slice: ProductsAndCompoundsSlice = offerings_resp["structured_response"]

    # --- primary anchors pass-through from seed if present ---
    primary_person = getattr(seed_extraction, "primary_person", None)
    primary_org = getattr(seed_extraction, "primary_organization", None)
    primary_tech = getattr(seed_extraction, "primary_technology", None) if hasattr(seed_extraction, "primary_technology") else None

    assembler_input = ConnectedCandidatesAssemblerInput(
        query=query,
        starter_content=starter_content,
        baseDomain=base_domain,
        mappedFromUrl=catalog.get("mappedFromUrl"),
        sourceDomainRole=catalog.get("sourceDomainRole"),
        primary_person=primary_person,
        primary_organization=primary_org,
        primary_technology=primary_tech,
        orgSlice=org_slice,
        productsSlice=products_slice,
    )

    assembler_prompt = PROMPT_NODE_C3_CONNECTED_CANDIDATES_ASSEMBLER.format(
        query=query,
        base_domain=base_domain,
        starter_content=starter_content or "",  # Provide empty string if None
        assembler_input_json=assembler_input.model_dump_json(indent=2),
    )

    assembler_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        tools=CONNECTED_TOOLS,
        response_format=ProviderStrategy(ConnectedCandidates),
        name=f"connected_candidates_assembler_{base_domain}",
    )

    assembled = await assembler_agent.ainvoke({"messages": [{"role": "user", "content": assembler_prompt}]})
    connected_candidates: ConnectedCandidates = assembled["structured_response"]

    out = CandidateSourcesConnected(
        connected=[connected_candidates],
        globalNotes=f"Per-domain slice for {base_domain}; assembled from Org+People+Tech and Products+Compounds slices.",
    )

    await save_json_artifact(
        out.model_dump(),
        "test_run",
        "candidate_sources_connected_slice",
        suffix=base_domain.replace("/", "_")[:30] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    
    # Publish slice complete event
    if run_id:
        candidate_count = len(out.connected) if hasattr(out, "connected") else len(out.get("connected", []))
        await _publish_progress(
            run_id=run_id,
            event_type=EVENT_TYPE_SLICE_COMPLETE,
            data={
                "base_domain": base_domain,
                "slice_index": slice_index,
                "total_slices": total_slices,
                "candidate_count": candidate_count,
            },
        )

    return {
        "candidate_sources_slice_outputs": [out],
    }

async def merge_candidate_sources_node(
    state: EntityIntelConnectedCandidatesAndSourcesState,
) -> Dict[str, Any]:
    slice_outputs: List[CandidateSourcesConnected] = state.get("candidate_sources_slice_outputs", []) or []

    merged_connected: List[ConnectedCandidates] = []
    notes: List[str] = []

    for out in slice_outputs:
        if hasattr(out, "connected"):
            merged_connected.extend(out.connected or [])
            if out.globalNotes:
                notes.append(out.globalNotes)
        else:
            merged_connected.extend((out.get("connected") or []))
            gn = out.get("globalNotes")
            if gn:
                notes.append(gn)

    merged = CandidateSourcesConnected(
        connected=merged_connected,
        globalNotes=" | ".join(notes) if notes else "Merged candidate sources slices.",
    )
    
    # Publish merge complete event
    run_id = state.get("intel_run_id")
    if run_id:
        await _publish_progress(
            run_id=run_id,
            event_type=EVENT_TYPE_MERGE_COMPLETE,
            data={
                "total_candidates": len(merged_connected),
                "total_slices": len(slice_outputs),
            },
        )

    return {"candidate_sources": merged}


# -----------------------------------------------------------------------------
# BUILD GRAPH
# -----------------------------------------------------------------------------
def build_entity_intel_connected_candidates_and_sources_graph() -> StateGraph:
    """
    Graph name: EntityIntelConnectedCandidatesAndSources

    Uses:
      - input_schema: EntityIntelConnectedCandidatesAndSourcesInputState
      - output_schema: EntityIntelConnectedCandidatesAndSourcesOutputState
      - internal state: EntityIntelConnectedCandidatesAndSourcesState
    """
    builder: StateGraph = StateGraph(
        EntityIntelConnectedCandidatesAndSourcesState,
        input_schema=EntityIntelConnectedCandidatesAndSourcesInputState,
        output_schema=EntityIntelConnectedCandidatesAndSourcesOutputState,
    )

    # Persistence nodes (Beanie)
    builder.add_node("initialize_run", initialize_run_node)
    builder.add_node("persist_seeds", persist_seeds_node)
    builder.add_node("persist_official_sources", persist_official_sources_node)
    builder.add_node("persist_domain_catalogs", persist_domain_catalogs_node_beanie)
    builder.add_node("persist_connected_slices", persist_connected_candidates_slices_node)
    builder.add_node("persist_candidates", persist_candidates_node_beanie)

    # Core nodes
    builder.add_node("seed_extraction", seed_extraction_node)
    builder.add_node("official_sources", official_sources_node)
    builder.add_node("domain_catalogs", domain_catalogs_node)

    # Fan-out nodes
    builder.add_node("candidate_sources_slice", candidate_sources_slice_node)
    builder.add_node("merge_candidate_sources", merge_candidate_sources_node)

    # Start with run initialization
    builder.set_entry_point("initialize_run")

    # Initialize -> seed extraction
    builder.add_edge("initialize_run", "seed_extraction")

    # Core pipeline: A -> B -> C with persistence after each step
    builder.add_edge("seed_extraction", "persist_seeds")
    builder.add_edge("persist_seeds", "official_sources")
    builder.add_edge("official_sources", "persist_official_sources")
    builder.add_edge("persist_official_sources", "domain_catalogs")
    builder.add_edge("domain_catalogs", "persist_domain_catalogs")

    # Fan-out from persisted point using Send API
    # The routing function returns List[Send] which creates dynamic edges to candidate_sources_slice nodes
    builder.add_conditional_edges(
        "persist_domain_catalogs",
        fanout_candidate_source_slices,
    )

    # Fan-in: all candidate_sources_slice nodes converge to merge_candidate_sources
    builder.add_edge("candidate_sources_slice", "merge_candidate_sources")

    # After merge, persist per-domain slice documents, then persist final merged graph + entities
    builder.add_edge("merge_candidate_sources", "persist_connected_slices")
    builder.add_edge("persist_connected_slices", "persist_candidates")
    
    # Final node -> END
    builder.add_edge("persist_candidates", END)

    return builder


async def make_entity_intel_connected_candidates_and_sources_graph(
    config: RunnableConfig,
) -> CompiledStateGraph:
    """
    Graph factory for LangSmith Studio / LangGraph CLI.
    Called per run; we reuse process-wide store/checkpointer.

    IMPORTANT: checkpoint namespace is provided at runtime via config["configurable"]["checkpoint_ns"]
    so compile once with the saver; per-run separation happens via config.
    """
    store, checkpointer = await get_persistence()

    graph: CompiledStateGraph = build_entity_intel_connected_candidates_and_sources_graph().compile(
        checkpointer=checkpointer,
        store=store,
    )
    return graph


