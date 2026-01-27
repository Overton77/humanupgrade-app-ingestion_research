from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph 
from research_agent.retrieval.async_mongo_client import _humanupgrade_db

from research_agent.agent_tools.file_system_functions import read_file_from_mongo_path
from research_agent.retrieval.intel_mongo_helpers import (
    get_plan_by_plan_id,
    get_candidate_run_by_run_id,
)

from research_agent.human_upgrade.base_models import gpt_5_mini
from research_agent.human_upgrade.logger import logger
from research_agent.common.artifacts import save_json_artifact, save_text_artifact

from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference
from research_agent.human_upgrade.structured_outputs.entity_extractions_outputs import (
    GuestBusinessExtraction,
    ProductCompoundExtraction,
)
from research_agent.human_upgrade.prompts.entity_extraction_prompts import (
    GUEST_BUSINESS_PROMPT,
    PRODUCT_COMPOUND_PROMPT,
)
from research_agent.clients.graphql_client import make_client_from_env
from research_agent.human_upgrade.utils.graphql_seeding import (
    seed_from_extraction_output,
    build_seed_provenance,
)


# ----------------------------
# State
# ----------------------------

class StructuredSeedState(TypedDict, total=False):
    plan_id: str
    run_id: str
    bundle_id: str

    # docs
    plan_doc: Dict[str, Any]
    candidate_run_doc: Dict[str, Any]

    # connected bundle (payload.connectedBundle.connected)
    connected_bundle_connected: Any  # keep flexible (list/dict)

    # execution outputs
    final_reports: List[FileReference]

    # grouped texts
    guest_report_text: str
    business_report_text: str
    product_compound_report_text: str

    # outputs (store raw dicts so state is JSONable)
    guest_business_extraction: Dict[str, Any]
    product_compound_extraction: Dict[str, Any]

    errors: List[str]


# ----------------------------
# Helpers
# ----------------------------

def _path_has_segment(path: str, seg: str) -> bool:
    p = (path or "").replace("/", "\\").lower()
    return f"\\{seg.lower()}\\" in p


def classify_report(
    fr: FileReference,
) -> Literal["GUEST", "BUSINESS", "PRODUCT_OR_COMPOUND", "UNKNOWN"]:
    ek = (getattr(fr, "entity_key", None) or "").strip().lower()
    fp = getattr(fr, "file_path", "") or ""

    # NOTE: your final_report entity_key values are "final_guest"/"final_business", so
    # we rely primarily on folder segments here.
    if ek.startswith("person:") or _path_has_segment(fp, "guest"):
        return "GUEST"
    if ek.startswith("business:") or _path_has_segment(fp, "business"):
        return "BUSINESS"
    if (
        ek.startswith("product:")
        or ek.startswith("compound:")
        or _path_has_segment(fp, "product")
        or _path_has_segment(fp, "compound")
    ):
        return "PRODUCT_OR_COMPOUND"
    return "UNKNOWN"


async def join_reports_text_from_mongo_paths(reports: List[FileReference]) -> str:
    parts: List[str] = []
    for fr in reports:
        try:
            txt = await read_file_from_mongo_path(fr.file_path)
            header = f"\n\n===== REPORT {fr.entity_key or ''} | {fr.file_path} =====\n\n"
            parts.append(header + txt)
        except Exception as e:
            parts.append(f"\n\n===== REPORT READ FAILED {fr.file_path} err={e} =====\n\n")
    return "".join(parts).strip()


def _safe_get(d: Dict[str, Any], path: List[str]) -> Any:
    """
    Safely navigate nested dictionaries by a list of keys.
    
    Example:
        _safe_get(doc, ["a", "b", "c"]) is equivalent to doc["a"]["b"]["c"]
        but returns None if any intermediate key is missing or not a dict.
    
    Args:
        d: The dictionary to navigate
        path: List of keys to follow (e.g., ["payload", "connectedBundle", "connected"])
    
    Returns:
        The value at the nested path, or None if any key is missing or intermediate value is not a dict
    """
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _parse_final_reports_from_plan_doc(plan_doc: Dict[str, Any]) -> List[FileReference]:
    """
    Extract finalReports from plan_doc.execution.finalReports.
    
    The MongoDB document structure is:
        plan_doc["execution"]["finalReports"] -> List[FileReference dicts]
    
    Returns empty list if execution or finalReports is missing.
    """
    # Navigate: plan_doc -> execution -> finalReports
    raw = _safe_get(plan_doc, ["execution", "finalReports"]) or []
    out: List[FileReference] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        try:
            out.append(FileReference(**item))
        except Exception:
            # Be permissive: if schema drift, keep minimal fields
            fp = (item or {}).get("file_path") if isinstance(item, dict) else None
            if fp:
                out.append(FileReference(file_path=fp))
    return out


def _extract_connected_bundle_connected(candidate_run_doc: Dict[str, Any]) -> Any:
    """
    Extract the connected bundle array from candidate_run_doc.
    
    The MongoDB document structure is:
        candidate_run_doc["payload"]["connectedBundle"]["connected"] -> List[ConnectedNode dicts]
    
    This is the array of connected nodes (guest + businesses + products + compounds + platforms)
    that was created by the entity candidates research directions graph.
    
    Returns None if any part of the path is missing.
    """
    # Navigate: candidate_run_doc -> payload -> connectedBundle -> connected
    connected = _safe_get(candidate_run_doc, ["payload", "connectedBundle", "connected"])
    return connected


# ----------------------------
# Nodes
# ----------------------------

async def init_structured_seed(state: StructuredSeedState) -> StructuredSeedState:
    return {"errors": []}


async def load_docs_node(state: StructuredSeedState) -> StructuredSeedState:
    plan_id = state.get("plan_id")
    run_id = state.get("run_id")
    errors = state.get("errors") or []

    if not plan_id:
        errors.append("Missing state.plan_id")
        return {"errors": errors}
    if not run_id:
        errors.append("Missing state.run_id")
        return {"errors": errors}

    # ✅ keyword-only calls
    plan_doc = await get_plan_by_plan_id(db=_humanupgrade_db, plan_id=plan_id)
    if not plan_doc:
        errors.append(f"Plan not found for planId={plan_id}")
        return {"errors": errors}

    cand_doc = await get_candidate_run_by_run_id(db=_humanupgrade_db, run_id=run_id)
    if not cand_doc:
        errors.append(f"Candidate run not found for runId={run_id}")
        return {"errors": errors}

    # Extract bundleId (can be at top level or in directions.bundleId)
    bundle_id = plan_doc.get("bundleId") or (plan_doc.get("directions") or {}).get("bundleId") or ""
    if not bundle_id:
        errors.append(f"bundleId missing on planId={plan_id}")

    # Extract finalReports from plan_doc.execution.finalReports
    # These are the synthesized research reports for each direction (GUEST, BUSINESS, PRODUCT, COMPOUND, PLATFORM)
    final_reports = _parse_final_reports_from_plan_doc(plan_doc)
    if not final_reports:
        errors.append(f"No execution.finalReports found on planId={plan_id}")

    # Extract connected bundle from candidate_run_doc.payload.connectedBundle.connected
    # This is the original connected bundle structure with guest, businesses, products, compounds, platforms
    # It's needed to provide context to the extraction agents
    connected_bundle_connected = _extract_connected_bundle_connected(cand_doc)
    if connected_bundle_connected is None:
        errors.append(f"payload.connectedBundle.connected missing on candidate runId={run_id}")
    elif not isinstance(connected_bundle_connected, list):
        errors.append(f"payload.connectedBundle.connected is not a list on candidate runId={run_id}")

    return {
        "plan_doc": plan_doc,
        "candidate_run_doc": cand_doc,
        "bundle_id": bundle_id,
        "final_reports": final_reports,
        "connected_bundle_connected": connected_bundle_connected,
        "errors": errors,
    }

async def group_and_read_reports_node(state: StructuredSeedState) -> StructuredSeedState:
    final_reports = state.get("final_reports") or []
    guest: List[FileReference] = []
    business: List[FileReference] = []
    prodcomp: List[FileReference] = []
    unknown: List[FileReference] = []

    for fr in final_reports:
        t = classify_report(fr)
        if t == "GUEST":
            guest.append(fr)
        elif t == "BUSINESS":
            business.append(fr)
        elif t == "PRODUCT_OR_COMPOUND":
            prodcomp.append(fr)
        else:
            unknown.append(fr)

    # Pick “best” guest/business report = first (you can sort later if you want)
    guest_text = await join_reports_text_from_mongo_paths(guest[:1]) if guest else ""
    business_text = await join_reports_text_from_mongo_paths(business[:1]) if business else ""
    prodcomp_text = await join_reports_text_from_mongo_paths(prodcomp) if prodcomp else ""

    errors = state.get("errors") or []
    if not guest and not guest_text:
        errors.append("No guest final report found (GUEST folder). Proceeding with bundle only.")
    if not business and not business_text:
        errors.append("No business final report found (BUSINESS folder). Proceeding with bundle only.")
    if not prodcomp and not prodcomp_text:
        errors.append("No product/compound final reports found. Proceeding with bundle only.")

    if unknown:
        errors.append(f"Unknown finalReports not used: {len(unknown)}")

    return {
        "guest_report_text": guest_text,
        "business_report_text": business_text,
        "product_compound_report_text": prodcomp_text,
        "errors": errors,
    }


# ----------------------------
# Agents (create_agent + response_format)
# ----------------------------

def build_guest_business_agent() -> CompiledStateGraph:
    return create_agent(
        model=gpt_5_mini,
        tools=[],
        response_format=GuestBusinessExtraction,
        name="guest_business_extraction_agent",
    )


def build_product_compound_agent() -> CompiledStateGraph:
    return create_agent(
        model=gpt_5_mini,
        tools=[],
        response_format=ProductCompoundExtraction,
        name="product_compound_extraction_agent",
    )


async def extract_guest_business_node(
    state: StructuredSeedState,
    config: RunnableConfig,
) -> StructuredSeedState:
    """
    Extract guest and business entities from the connected bundle and final reports.
    
    Inputs:
        - connected_bundle_connected: The original connected bundle structure (List[ConnectedNode])
        - guest_report_text: Text from final GUEST report
        - business_report_text: Text from final BUSINESS report
    
    Output:
        - guest_business_extraction: Structured extraction with guest and business data
    """
    connected = state.get("connected_bundle_connected")
    # connected is a List[ConnectedNode] where each node has:
    #   - guest: EntityRef
    #   - businesses: List[BusinessBundle] (each with business, products, platforms)
    #   - notes: Optional[str]
    connected_bundle_json = json.dumps(connected or [], ensure_ascii=False, indent=2)

    prompt = GUEST_BUSINESS_PROMPT.format(
        connected_bundle_json=connected_bundle_json,
        guest_report_text=state.get("guest_report_text", ""),
        business_report_text=state.get("business_report_text", ""),
    )

    agent = build_guest_business_agent()
    resp = await agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config,
    )

    structured: GuestBusinessExtraction = resp["structured_response"]

    # Artifacts for debugging
    try:
        bundle_id = state.get("bundle_id") or "unknown_bundle"
        await save_text_artifact(
            prompt,
            "newest_research_outputs",
            "seed_extraction",
            "guest_business_prompt",
        )
        await save_json_artifact(
            structured.model_dump(),
            "newest_research_outputs",
            "seed_extraction",
            "guest_business_structured",
        )
    except Exception:
        logger.exception("Failed to save guest+business extraction artifacts")

    return {"guest_business_extraction": structured.model_dump()}


async def extract_product_compound_node(
    state: StructuredSeedState,
    config: RunnableConfig,
) -> StructuredSeedState:
    """
    Extract product and compound entities from the connected bundle and final reports.
    
    Inputs:
        - connected_bundle_connected: The original connected bundle structure (List[ConnectedNode])
        - product_compound_report_text: Text from final PRODUCT and COMPOUND reports
    
    Output:
        - product_compound_extraction: Structured extraction with products, compounds, and links
    """
    connected = state.get("connected_bundle_connected")
    # connected is a List[ConnectedNode] where each node has:
    #   - businesses: List[BusinessBundle] (each with products containing compounds)
    #   The products are nested under businesses, and compounds are nested under products
    connected_bundle_json = json.dumps(connected or [], ensure_ascii=False, indent=2)

    prompt = PRODUCT_COMPOUND_PROMPT.format(
        connected_bundle_json=connected_bundle_json,
        product_compound_report_text=state.get("product_compound_report_text", ""),
    )

    agent = build_product_compound_agent()
    resp = await agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config,
    )

    structured: ProductCompoundExtraction = resp["structured_response"]

    # Artifacts for debugging
    try:
        bundle_id = state.get("bundle_id") or "unknown_bundle"
        await save_text_artifact(
            prompt,
            "newest_research_outputs",
            "seed_extraction",
            "product_compound_prompt",
        )
        await save_json_artifact(
            structured.model_dump(),
            "newest_research_outputs",
            "seed_extraction",
            "product_compound_structured",
        )
    except Exception:
        logger.exception("Failed to save product+compound extraction artifacts")

    return {"product_compound_extraction": structured.model_dump()}


async def finalize_structured_seed(state: StructuredSeedState) -> StructuredSeedState:
    """
    Finalize the structured seed extraction by seeding the database via GraphQL.
    """
    errors = state.get("errors") or []
    plan_doc = state.get("plan_doc", {})
    guest_business_extraction = state.get("guest_business_extraction")
    product_compound_extraction = state.get("product_compound_extraction")
    
    # Check if we have the required extraction outputs
    if not guest_business_extraction:
        errors.append("Missing guest_business_extraction in state")
        return {"errors": errors}
    
    if not product_compound_extraction:
        errors.append("Missing product_compound_extraction in state")
        return {"errors": errors}
    
    # Get episode URL from plan_doc (top-level field: episodeUrl)
    episode_url = plan_doc.get("episodeUrl")
    if not episode_url:
        errors.append("Missing episodeUrl in plan_doc")
        return {"errors": errors}
    
    # Get business name for lookup (optional)
    business_data = guest_business_extraction.get("business", {})
    business_name = business_data.get("canonical_name")
    
    # Extract seed provenance metadata from state
    plan_id = state.get("plan_id")
    if not plan_id:
        errors.append("Missing plan_id in state (required for seed provenance)")
        return {"errors": errors}
    
    bundle_id = state.get("bundle_id")
    run_id = state.get("run_id")
    final_reports = state.get("final_reports", [])
    
    # Get execution metadata from plan_doc
    execution = plan_doc.get("execution", {})
    execution_run_id = execution.get("executionRunId")
    pipeline_version = plan_doc.get("pipelineVersion")
    episode_id = plan_doc.get("episodeId")
    
    # Build seed provenance (base version, direction_type will be set per entity type)
    # Note: plan_id is required, other fields are optional
    try:
        seed_provenance = build_seed_provenance(
            plan_id=plan_id,
            bundle_id=bundle_id,
            run_id=run_id,
            execution_run_id=execution_run_id,
            pipeline_version=pipeline_version,
            episode_id=episode_id,
            episode_url=episode_url,
            final_reports=final_reports,
        )
        logger.info(f"✅ Built seed provenance: planId={plan_id}, bundleId={bundle_id}, runId={run_id}")
    except Exception as e:
        error_msg = f"Failed to build seed provenance: {e}"
        logger.exception(error_msg)
        errors.append(error_msg)
        return {"errors": errors}
    
    # Create GraphQL client
    client = make_client_from_env()
    
    try:
        # Seed the database
        seeding_result = await seed_from_extraction_output(
            client=client,
            guest_business_extraction=guest_business_extraction,
            product_compound_extraction=product_compound_extraction,
            episode_url=episode_url,
            business_name=business_name,
            seed_provenance=seed_provenance,
        )
        
        logger.info(f"✅ Seeding complete: business_id={seeding_result.get('business', {}).get('business_id')}")
        
        # Log warnings if guest/episode update failed
        if not seeding_result.get("episode"):
            guest_data = guest_business_extraction.get("guest", {})
            guest_name = guest_data.get("canonical_name", "unknown")
            logger.warning(f"⚠️  Could not update episode with guest '{guest_name}' - guest may not exist in database yet")
        
        return {
            "seeding_result": seeding_result,
            "errors": errors,
        }
    
    except Exception as e:
        error_msg = f"Failed to seed database: {e}"
        logger.exception(error_msg)
        errors.append(error_msg)
        return {"errors": errors}
    
    finally:
        await client.http_client.aclose()


# ----------------------------
# Subgraph builder
# ----------------------------

def make_structured_seed_subgraph() -> CompiledStateGraph:
    g: StateGraph = StateGraph(StructuredSeedState)

    g.add_node("init", init_structured_seed)
    g.add_node("load_docs", load_docs_node)
    g.add_node("group_and_read", group_and_read_reports_node)
    g.add_node("extract_guest_business", extract_guest_business_node)
    g.add_node("extract_product_compound", extract_product_compound_node)
    g.add_node("finalize", finalize_structured_seed)

    g.set_entry_point("init")
    g.add_edge("init", "load_docs")
    g.add_edge("load_docs", "group_and_read")

    # business first (so you can later upsert business & capture id)
    g.add_edge("group_and_read", "extract_guest_business")
    g.add_edge("extract_guest_business", "extract_product_compound")
    g.add_edge("extract_product_compound", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


# ----------------------------
# Runner
# ----------------------------

async def run_structured_seed_extraction(
    *,
    plan_id: str,
    run_id: str,
    user_id: str = "dev",
) -> Dict[str, Any]:
    graph = make_structured_seed_subgraph()

    # Keep config minimal; you can add checkpoint/store later if desired.
    cfg = RunnableConfig(
        configurable={
            "thread_id": f"seed_extract__plan__{plan_id}__run__{run_id}",
            "user_id": user_id,
        }
    )

    init_state: StructuredSeedState = {
        "plan_id": plan_id,
        "run_id": run_id,
        "errors": [],
    }

    out: Dict[str, Any] = await graph.ainvoke(init_state, cfg)

    # Persist the final output as one bundle artifact for easy inspection
    try:
        bundle_id = out.get("bundle_id") or "unknown_bundle"
        await save_json_artifact(
            out,
            "newest_research_outputs",
            "seed_extraction",
            "structured_seed_graph_output",
        )
    except Exception:
        logger.exception("Failed to save structured seed graph output artifact")

    return out


if __name__ == "__main__":
    # Hardcoded IDs you provided
    RUN_ID = "837653f3-622d-4b37-a583-c3cec3ff4ee2"
    PLAN_ID = "4b50d45c-ab5b-4dc3-a2bb-aab03e907297"

    result = asyncio.run(
        run_structured_seed_extraction(
            plan_id=PLAN_ID,
            run_id=RUN_ID,
            user_id="dev",
        )
    )

    # Print minimal summary
    print("\n✅ Structured seed extraction complete")
    print("bundle_id:", result.get("bundle_id"))
    print("errors:", result.get("errors") or [])
    print("guest_business_extraction keys:", list((result.get("guest_business_extraction") or {}).keys()))
    print("product_compound_extraction keys:", list((result.get("product_compound_extraction") or {}).keys()))