"""
Candidate and Research Directions Graph for Entity Intel 
"""

from langgraph.graph import StateGraph, START, END    
from langgraph.types import Send 
from langgraph.graph.state import CompiledStateGraph 
from datetime import datetime 
import asyncio 

from typing_extensions import TypedDict
from typing import  Dict, Any, List, Optional, Annotated 

from langchain.agents import create_agent  
from dotenv import load_dotenv 
from langchain.agents.structured_output import ProviderStrategy 
from langchain.agents.middleware import SummarizationMiddleware
from research_agent.human_upgrade.structured_outputs.research_direction_outputs import ( 
    EntityBundlesListOutputA,
    EntityBundlesListFinal,
    compile_bundles_list, 
    EntityBundleDirectionsFinal,
) 
from research_agent.human_upgrade.structured_outputs.candidates_outputs import ( 
 
    CandidateSourcesConnected, 
    ConnectedCandidates,
    OfficialStarterSources,
    SeedExtraction,
    DomainCatalogSet,
    BusinessIdentitySlice,
    ProductsAndCompoundsSlice,
    ConnectedCandidatesAssemblerInput, 
    EntitySourceResult,
)   
from langchain_core.runnables import RunnableConfig
from langchain.tools import BaseTool 

from research_agent.human_upgrade.logger import logger
from research_agent.human_upgrade.utils.artifacts import save_json_artifact, save_text_artifact 
from research_agent.human_upgrade.prompts.seed_prompts import PROMPT_OUTPUT_A_SEED_EXTRACTION
from research_agent.human_upgrade.prompts.candidates_prompts import ( 
   PROMPT_OUTPUT_A2_CONNECTED_CANDIDATES_ASSEMBLER, PROMPT_NODE_A_OFFICIAL_STARTER_SOURCES, PROMPT_NODE_B_DOMAIN_CATALOGS 
    )
from research_agent.human_upgrade.prompts.research_directions_prompts import PROMPT_OUTPUT_A3_ENTITY_RESEARCH_DIRECTIONS
from research_agent.clients.langsmith_client import pull_prompt_from_langsmith 
from research_agent.human_upgrade.tools.web_search_tools import (
    wiki_tool, 
    tavily_map_validation, 
    tavily_search_validation,
    tavily_extract_validation, 
    
) 

from research_agent.human_upgrade.utils.formatting import format_seed_extraction_for_prompt, format_connected_candidates_for_prompt  
from research_agent.human_upgrade.prompts.candidates_prompts import ( 
    PROMPT_OUTPUT_A2_BUSINESS_IDENTITY_SLICE,
    PROMPT_OUTPUT_A2_PRODUCTS_AND_COMPOUNDS_SLICE,
    PROMPT_OUTPUT_A2_CONNECTED_CANDIDATES_ASSEMBLER,
)
from research_agent.human_upgrade.graphs.nodes.intel_mongo_nodes import ( 
    persist_candidates_node, 
    persist_research_plans_node,
    persist_domain_catalogs_node,
)

from research_agent.human_upgrade.base_models import gpt_4_1, gpt_5_mini, gpt_5_nano, gpt_5  
from research_agent.human_upgrade.persistence.checkpointer_and_store import get_persistence
from research_agent.human_upgrade.utils.dedupe import _dedupe_keep_order, _take  
from research_agent.human_upgrade.utils.candidate_graph_helpers import _guest_from_official_sources
import os  
import operator 
import json 

load_dotenv()  

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") 

openai_search_tool: Dict[str, str] = {"type": "web_search"}  





pull_prompt_names: Dict[str, str] = { 
    "seed_extraction_prompt": "seed_extraction_prompt", 
    "connected_candidate_sources_prompt": "connected_candidate_sources_prompt",
    "research_directions_prompt": "research_directions_prompt",
} 

class CandidateSourcesSliceResult(TypedDict): 
    baseDomain: str  
    connected_candidates: ConnectedCandidates  
    notes: Optional[str] = None 


class EntityIntelCandidateAndResearchDirectionsState(TypedDict, total=False):
    """State for a single entity candidate and research directions."""
    # Core tool-loop plumbing
    llm_calls: int
    tool_calls: int

    # Episode context
    episode: Dict[str, Any]

    # Existing outputs
    seed_extraction: SeedExtraction 
    # Fanout collection (one per DomainCatalog slice)
    candidate_sources_slice_outputs: Annotated[List[CandidateSourcesConnected], operator.add]
    expected_candidate_source_slices: int
    completed_candidate_source_slices: Annotated[int, operator.add]
    candidate_sources: CandidateSourcesConnected
    research_directions: EntityBundlesListFinal

    # ----------------------------
    # NEW: Intel orchestration
    # ----------------------------

    # Stable per-run identifiers (set once, reused across nodes)
    intel_run_id: str
    intel_pipeline_version: str

    # Outputs from persist_candidates_node
    candidate_entity_ids: List[str]          # candidateEntityId values inserted for this run
    dedupe_group_map: Dict[str, str]         # entityKey -> dedupeGroupId

    # Outputs from persist_research_plans_node
    research_plan_ids: List[str]    
    
    official_starter_sources: OfficialStarterSources          
    domain_catalogs: DomainCatalogSet  
    domain_catalog_set_id: str
    domain_catalog_extracted_at: datetime | str 

    error: str

    steps_taken: int
    

# Graph helpers 

def _select_business_people_urls(catalog: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Choose a logical portion of DomainCatalog buckets for Business+People agents.
    Keep it SMALL: the agent can still explore via tools, but we anchor it tightly.
    Maps to: BusinessIdentityAndLeadershipAgent, PersonBioAndAffiliationsAgent, EcosystemMapperAgent, CredibilitySignalScannerAgent
    """
    homepage = _dedupe_keep_order(catalog.get("homepageUrls") or [])
    about = _dedupe_keep_order(catalog.get("aboutUrls") or [])
    blog = _dedupe_keep_order(catalog.get("blogUrls") or [])
    leadership = _dedupe_keep_order(catalog.get("leadershipUrls") or [])
    press = _dedupe_keep_order(catalog.get("pressUrls") or [])
    policy = _dedupe_keep_order(catalog.get("policyUrls") or [])
    regulatory = _dedupe_keep_order(catalog.get("regulatoryUrls") or [])
    # platformUrls (legacy) includes technology/science sometimes; still helpful
    platform = _dedupe_keep_order(catalog.get("platformUrls") or [])
    help_center = _dedupe_keep_order(catalog.get("helpCenterUrls") or [])

    # Practical caps (tune freely)
    return {
        "homepageUrls": _take(homepage, 2),  # Usually just 1-2
        "aboutUrls": _take(about, 5),
        "blogUrls": _take(blog, 10),
        "leadershipUrls": _take(leadership, 30),
        "pressUrls": _take(press, 20),
        "policyUrls": _take(policy, 15),
        "regulatoryUrls": _take(regulatory, 10),
        "platformUrls": _take(platform, 25),
        "helpCenterUrls": _take(help_center, 10),
    }


def _select_products_compounds_urls(catalog: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Choose a logical portion for Products+Compounds agents.
    Maps to: ProductCatalogerAgent, ProductSpecAgent, TechnologyProcessAndManufacturingAgent, ClaimsExtractorAndTaxonomyMapperAgent
    """
    product_index = _dedupe_keep_order(catalog.get("productIndexUrls") or [])
    product_pages = _dedupe_keep_order(catalog.get("productPageUrls") or [])
    landing_pages = _dedupe_keep_order(catalog.get("landingPageUrls") or [])
    docs = _dedupe_keep_order(catalog.get("documentationUrls") or [])
    labels = _dedupe_keep_order(catalog.get("labelUrls") or [])
    help_center = _dedupe_keep_order(catalog.get("helpCenterUrls") or [])
    research = _dedupe_keep_order(catalog.get("researchUrls") or [])
    patents = _dedupe_keep_order(catalog.get("patentUrls") or [])
    # platformUrls may contain technology/platform pages
    platform = _dedupe_keep_order(catalog.get("platformUrls") or [])

    return {
        "productIndexUrls": _take(product_index, 25),
        "productPageUrls": _take(product_pages, 120), 
        "landingPageUrls": _take(landing_pages, 15),
        "documentationUrls": _take(docs, 40),
        "labelUrls": _take(labels, 20),
        "helpCenterUrls": _take(help_center, 15),
        "researchUrls": _take(research, 20),
        "patentUrls": _take(patents, 10),
        "platformUrls": _take(platform, 25),
    }


def _select_evidence_urls(catalog: Dict[str, Any]) -> Dict[str, List[str]]:
    """
    Choose a logical portion of DomainCatalog buckets for Evidence-related agents.
    Maps to: CaseStudyHarvestAgent, EvidenceClassifierAgent, StrengthAndGapAssessorAgent, ContraindicationsAndSafetyAgent
    """
    case_studies = _dedupe_keep_order(catalog.get("caseStudyUrls") or [])
    testimonials = _dedupe_keep_order(catalog.get("testimonialUrls") or [])
    research = _dedupe_keep_order(catalog.get("researchUrls") or [])
    patents = _dedupe_keep_order(catalog.get("patentUrls") or [])
    docs = _dedupe_keep_order(catalog.get("documentationUrls") or [])
    labels = _dedupe_keep_order(catalog.get("labelUrls") or [])
    help_center = _dedupe_keep_order(catalog.get("helpCenterUrls") or [])
    regulatory = _dedupe_keep_order(catalog.get("regulatoryUrls") or [])

    return {
        "caseStudyUrls": _take(case_studies, 50),
        "testimonialUrls": _take(testimonials, 30),
        "researchUrls": _take(research, 30),
        "patentUrls": _take(patents, 15),
        "documentationUrls": _take(docs, 40),
        "labelUrls": _take(labels, 20),
        "helpCenterUrls": _take(help_center, 15),
        "regulatoryUrls": _take(regulatory, 10),
    } 





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
        tavily_search_validation,  # fallback only 
        tavily_extract_validation,  # primary
        # tavily_map_validation,    # intentionally omitted in Node C
    ]

async def seed_extraction_node(state: EntityIntelCandidateAndResearchDirectionsState) -> EntityIntelCandidateAndResearchDirectionsState:  
    episode: Dict[str, Any] = state.get("episode", {})
    webpage_summary: str = episode.get("webPageSummary") 
    episode_url: str = episode.get("episodePageUrl")
    
    if not webpage_summary:
        raise ValueError("episode.webPageSummary is required")
    if not episode_url:
        raise ValueError("episode.episodePageUrl is required")
    
    logger.info(f"🌱 Starting seed extraction for episode: {episode_url[:80]}...")   
    # The seed Extraction prompt will be generalized to any entity research need. Start with query. Start with sources 
    seed_extraction_prompt: str = PROMPT_OUTPUT_A_SEED_EXTRACTION.format(
        episode_url=episode_url, # This will turn into general starter sources for any research need ENTITY BASED 
        webpage_summary=webpage_summary, # This will turn into general context for any research need  ENTITY BASED 
    )  

    seed_extraction_agent: CompiledStateGraph = create_agent(   
     
        gpt_5_mini,   
        tools=[openai_search_tool], 
        response_format=ProviderStrategy(SeedExtraction),  
           name="seed_extraction_agent",
    ) 

    response = await seed_extraction_agent.ainvoke( 
        {"messages": [{"role": "user", "content": seed_extraction_prompt}]} 
    ) 

    seed_extraction_output: SeedExtraction = response["structured_response"]
    
    logger.info(
        "✅ Seed extraction complete: guests=%s businesses=%s products=%s compounds=%s",
        len(seed_extraction_output.guest_candidates) if seed_extraction_output.guest_candidates else 0,
        len(seed_extraction_output.business_candidates) if seed_extraction_output.business_candidates else 0,
        len(seed_extraction_output.product_candidates) if seed_extraction_output.product_candidates else 0,
        len(seed_extraction_output.compound_candidates) if seed_extraction_output.compound_candidates else 0,
    )

    return { 
        "seed_extraction": seed_extraction_output,
    }  




async def official_sources_node(
    state: EntityIntelCandidateAndResearchDirectionsState,
) -> EntityIntelCandidateAndResearchDirectionsState:
    seed_extraction: SeedExtraction | None = state.get("seed_extraction")
    if seed_extraction is None:
        raise ValueError("seed_extraction is required")

    episode: Dict[str, Any] = state.get("episode", {})
    episode_url: str = episode.get("episodePageUrl", "unknown")

    formatted_fields: Dict[str, str] = format_seed_extraction_for_prompt(seed_extraction)

    prompt = PROMPT_NODE_A_OFFICIAL_STARTER_SOURCES.format(
        episode_url=episode_url,
        guest_candidates=formatted_fields["guest_candidates"],
        business_candidates=formatted_fields["business_candidates"],
        product_candidates=formatted_fields["product_candidates"],
    )

    agent = create_agent(
        gpt_5_mini,
        tools=OFFICIAL_STARTER_TOOLS,
        response_format=ProviderStrategy(OfficialStarterSources),
        name="official_sources_agent",
    )

    response = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    official_sources: OfficialStarterSources = response["structured_response"]

    await save_json_artifact(
        official_sources.model_dump(),
        "test_run",
        "official_starter_sources",
        suffix=episode_url.replace("/", "_")[:30],
    )

    return {"official_starter_sources": official_sources}


async def domain_catalogs_node(
    state: EntityIntelCandidateAndResearchDirectionsState,
) -> EntityIntelCandidateAndResearchDirectionsState:
    official_sources: OfficialStarterSources | None = state.get("official_starter_sources")
    if official_sources is None:
        raise ValueError("official_starter_sources is required for domain_catalogs_node")

    episode: Dict[str, Any] = state.get("episode", {})
    episode_url: str = episode.get("episodePageUrl", "unknown")

    prompt = PROMPT_NODE_B_DOMAIN_CATALOGS.format(
        episode_url=episode_url,
        official_starter_sources_json=official_sources.model_dump_json(indent=2),
    )

    agent = create_agent(
        gpt_5_mini,
        tools=DOMAIN_CATALOG_TOOLS,
        response_format=ProviderStrategy(DomainCatalogSet),
        name="domain_catalogs_agent",
    )

    response = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]})
    domain_catalogs: DomainCatalogSet = response["structured_response"]

    await save_json_artifact(
        domain_catalogs.model_dump(),
        "test_run",
        "domain_catalogs",
        suffix=episode_url.replace("/", "_")[:30],
    )

    return {"domain_catalogs": domain_catalogs}



async def _ainvoke_bounded(agent: CompiledStateGraph, payload: Dict[str, Any], sem: asyncio.Semaphore) -> Dict[str, Any]:
    async with sem:
        return await agent.ainvoke(payload)

def fanout_candidate_source_slices(
    state: EntityIntelCandidateAndResearchDirectionsState,
) -> List[Send]:
    domain_catalogs = state["domain_catalogs"]
    catalogs = domain_catalogs.catalogs if hasattr(domain_catalogs, "catalogs") else (domain_catalogs.get("catalogs") or [])

    sends: List[Send] = []
    for cat in catalogs:
        sends.append(
            Send(
                "candidate_sources_slice",
                {
                    "catalog": cat.model_dump() if hasattr(cat, "model_dump") else cat,
                    "episode": state.get("episode") or {},
                    "seed_extraction": state["seed_extraction"].model_dump() if hasattr(state["seed_extraction"], "model_dump") else state["seed_extraction"],
                    "official_starter_sources": state["official_starter_sources"].model_dump() if hasattr(state["official_starter_sources"], "model_dump") else state["official_starter_sources"],
                    
                  
                },
            )
        )

    return sends
    

async def candidate_sources_slice_node(
    state:EntityIntelCandidateAndResearchDirectionsState,
) -> EntityIntelCandidateAndResearchDirectionsState:
    """
    For ONE DomainCatalog:
      - run Business+People agent and Products+Compounds agent concurrently (bounded)
      - run Assembler agent to produce ConnectedCandidates
      - return CandidateSourcesConnected with a single ConnectedCandidates in .connected
    """
    catalog: Dict[str, Any] = state["catalog"]
    episode: Dict[str, Any] = state.get("episode") or {}
    seed_extraction = state["seed_extraction"]
    official_sources = state["official_starter_sources"]

    episode_url = episode.get("episodePageUrl", "unknown")
    base_domain = catalog.get("baseDomain") or "unknown"

    # --- prepare small URL slices ---
    business_urls = _select_business_people_urls(catalog)
    products_urls = _select_products_compounds_urls(catalog)

    # --- build prompts ---
    business_prompt = PROMPT_OUTPUT_A2_BUSINESS_IDENTITY_SLICE.format(
        episode_url=episode_url,
        base_domain=base_domain,
        # keep small: only the buckets that matter + minimal context
        url_buckets_json=json.dumps(business_urls, indent=2),
        catalog_min_json=json.dumps(
            {
                "baseDomain": catalog.get("baseDomain"),
                "mappedFromUrl": catalog.get("mappedFromUrl"),
                "sourceDomainRole": catalog.get("sourceDomainRole"),
            },
            indent=2,
        ),
        seed_json=json.dumps(seed_extraction, indent=2) if isinstance(seed_extraction, dict) else json.dumps(seed_extraction, default=str, indent=2),
        official_sources_json=json.dumps(official_sources, indent=2) if isinstance(official_sources, dict) else json.dumps(official_sources, default=str, indent=2),
    )

    products_prompt = PROMPT_OUTPUT_A2_PRODUCTS_AND_COMPOUNDS_SLICE.format(
        episode_url=episode_url,
        base_domain=base_domain,
        url_buckets_json=json.dumps(products_urls, indent=2),
        catalog_min_json=json.dumps(
            {
                "baseDomain": catalog.get("baseDomain"),
                "mappedFromUrl": catalog.get("mappedFromUrl"),
                "sourceDomainRole": catalog.get("sourceDomainRole"),
            },
            indent=2,
        ),
        seed_json=json.dumps(seed_extraction, indent=2) if isinstance(seed_extraction, dict) else json.dumps(seed_extraction, default=str, indent=2),
        official_sources_json=json.dumps(official_sources, indent=2) if isinstance(official_sources, dict) else json.dumps(official_sources, default=str, indent=2),
    )

    
    business_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        tools=CONNECTED_TOOLS,
        response_format=ProviderStrategy(BusinessIdentitySlice),
        name=f"business_identity_slice_agent_{base_domain}",
    )

    products_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        tools=CONNECTED_TOOLS,
        response_format=ProviderStrategy(ProductsAndCompoundsSlice),
        name=f"products_compounds_slice_agent_{base_domain}",
    )

    # Bound concurrency inside the slice node (2 calls)
    sem = asyncio.Semaphore(2)

    business_task = _ainvoke_bounded(
        business_agent,
        {"messages": [{"role": "user", "content": business_prompt}]},
        sem,
    )
    products_task = _ainvoke_bounded(
        products_agent,
        {"messages": [{"role": "user", "content": products_prompt}]},
        sem,
    )

    business_resp, products_resp = await asyncio.gather(business_task, products_task)

    business_slice: BusinessIdentitySlice = business_resp["structured_response"]
    products_slice: ProductsAndCompoundsSlice = products_resp["structured_response"]

    # --- assembler input ---
    guest = _guest_from_official_sources(official_sources, seed_extraction)

    assembler_input = ConnectedCandidatesAssemblerInput(
        guest=EntitySourceResult(**guest) if not isinstance(guest, EntitySourceResult) else guest,
        businessSlice=business_slice,
        productsSlice=products_slice,
        episodeUrl=episode_url,
    )

    assembler_prompt = PROMPT_OUTPUT_A2_CONNECTED_CANDIDATES_ASSEMBLER.format(
        episode_url=episode_url,
        base_domain=base_domain,
        assembler_input_json=assembler_input.model_dump_json(indent=2),
        # You can optionally also include tiny hints:
        # "merge_rules": "...",
    )

    assembler_agent: CompiledStateGraph = create_agent(
        gpt_5_mini,
        tools=CONNECTED_TOOLS,
        response_format=ProviderStrategy(ConnectedCandidates),
        name=f"connected_candidates_assembler_{base_domain}",
    )

    assembled = await assembler_agent.ainvoke({"messages": [{"role": "user", "content": assembler_prompt}]})
    connected_candidates: ConnectedCandidates = assembled["structured_response"]

    # Wrap per-slice output as CandidateSourcesConnected
    out = CandidateSourcesConnected(
        connected=[connected_candidates],
        globalNotes=f"Per-domain slice for {base_domain}; assembled from Business+People and Products+Compounds agents.",
    ) 

    await save_json_artifact(
        out.model_dump(),
        "test_run",
        "candidate_sources_connected_slice",
        suffix=base_domain.replace("/", "_")[:30] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
    )

    return {
        # ✅ This key should be a reducer list in your parent state, e.g. Annotated[List[CandidateSourcesConnected], operator.add]
        "candidate_sources_slice_outputs": [out],
        # # Join counters (reduced into parent state)
        # "expected_candidate_source_slices": int(state.get("expected_candidate_source_slices") or 0),
        # "completed_candidate_source_slices": 1,
    }

# def route_after_candidate_sources_slice(
#     state: "EntityIntelCandidateAndResearchDirectionsState",
# ) -> str:
#     """
#     Fanout join gate:
#     - For each slice completion, only trigger the merge ONCE (when last slice completes).
#     - Other slice branches terminate via `slice_done`.
#     """
#     expected = int(state.get("expected_candidate_source_slices") or 0)
#     completed = int(state.get("completed_candidate_source_slices") or 0)
#     if expected > 0 and completed >= expected:
#         return "merge"
#     return "done"

# async def slice_done_node(state: Dict[str, Any]) -> Dict[str, Any]:
#     """No-op node to end non-final fanout branches cleanly."""
#     return {}

async def merge_candidate_sources_node(
    state: "EntityIntelCandidateAndResearchDirectionsState",
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
            # If it came back as dict
            merged_connected.extend((out.get("connected") or []))
            gn = out.get("globalNotes")
            if gn:
                notes.append(gn)

    merged = CandidateSourcesConnected(
        connected=merged_connected,
        globalNotes=" | ".join(notes) if notes else "Merged candidate sources slices.",
    )

    return {"candidate_sources": merged}




# ============================================================================
# BUILD SUBGRAPH
# ============================================================================
def build_entity_candidates_connected_graph() -> StateGraph:
    builder: StateGraph = StateGraph(EntityIntelCandidateAndResearchDirectionsState)

    # Core nodes
    builder.add_node("seed_extraction", seed_extraction_node)
    builder.add_node("official_sources", official_sources_node)
    builder.add_node("domain_catalogs", domain_catalogs_node)

    # Persistence
    builder.add_node("persist_domain_catalogs", persist_domain_catalogs_node)
    builder.add_node("persist_candidates", persist_candidates_node)
    builder.add_node("persist_research_plans", persist_research_plans_node)

    # Fan-out nodes
    builder.add_node("candidate_sources_slice", candidate_sources_slice_node)
    builder.add_node("merge_candidate_sources", merge_candidate_sources_node)
    # builder.add_node("slice_done", slice_done_node)

    # Directions
    

    builder.set_entry_point("seed_extraction")

    # A -> B
    builder.add_edge("seed_extraction", "official_sources")
    builder.add_edge("official_sources", "domain_catalogs")

    # Persist catalogs first (so state has artifact ref)
    builder.add_edge("domain_catalogs", "persist_domain_catalogs")

    # Fanout from persisted point
    builder.add_conditional_edges("persist_domain_catalogs", fanout_candidate_source_slices, 
    then="merge_candidate_sources"
    )

    builder.add_edge("merge_candidate_sources", "persist_candidates")  
  

    # Get out  

    # TODO: Add State field for research_mode and generate_plan and add conditional edge  
    # TODO: ... add conditional edge going to the research_plan_graph that will be imported. 


    return builder



async def make_entity_candidates_connected_graph(config: RunnableConfig) -> CompiledStateGraph:
    """
    Graph factory for LangSmith Studio / LangGraph CLI.
    Called per run; we reuse process-wide store/checkpointer.
    """
    store, checkpointer = await get_persistence()

    # IMPORTANT: checkpoint namespace is provided at runtime via config["configurable"]["checkpoint_ns"]
    # so compile once with the saver; per-run separation happens via config.
    graph: CompiledStateGraph = build_entity_candidates_connected_graph().compile(
        checkpointer=checkpointer,
        store=store,
    )
    return graph