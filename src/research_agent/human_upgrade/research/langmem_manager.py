from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Optional, Tuple

from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from langmem import create_memory_manager  # langmem SDK
from langmem.types import ExtractedMemory  # (memory_id, model|str) pairs in results

from .langmem_schemas import (
    MemoryBase,
    SemanticEntityFact,
    EpisodicRunNote,
    ProceduralPlaybook,
    ErrorSignatureMemory,
    SourceFact,
    EntityFingerprint,
    SourceFingerprint,
)
from .langmem_namespaces import NS, choose_entity_namespace
from research_agent.human_upgrade.persistence.checkpointer_and_store import get_persistence


# -----------------------------
# 1) Instructions prompt
# -----------------------------
MEMORY_INSTRUCTIONS = """
You are a memory extraction engine for a biotech research agent system.

Extract ONLY durable, reusable information that will improve future research:
- Semantic facts: canonical-ish entity attributes (aliases, domains, products, people, specs, claims links), version if time-sensitive.
- Procedural playbooks: reusable tactics for finding/validating info, including query templates and platform-specific extraction steps.
- Episodic notes: compact run outcomes (what worked, what failed, missingness checklist, source yield).
- Error memories: tool failure signature -> mitigation/fallback.
- Source facts: official domains, help-center structures, sitemap locations, high-yield URLs, access constraints.
- Fingerprints: entity/source fingerprints for similarity recall.

DO NOT store raw scraped text, long transcripts, or low-confidence speculation.
Always include:
- kind (semantic/episodic/procedural/error/source/fingerprint_entity/fingerprint_source)
- confidence (0-1)
- evidence (short snippets or file refs)
- sources (URLs or file paths)
Where possible, include routing keys: org_id/person_id/product_id/compound_id/domain/url.

If a memory is time-volatile (pricing, leadership, product formulation), set observed_at and optionally ttl_days.
"""


# -----------------------------
# 2) Manager factory
# -----------------------------
def build_langmem_extractor(model: str = "openai:gpt-4.1"):
    """
    Stateless extractor runnable: messages + existing -> list[ExtractedMemory].
    Signature per docs: create_memory_manager(model, schemas=..., instructions=...). :contentReference[oaicite:1]{index=1}
    """
    return create_memory_manager(
        model,
        schemas=[
            SemanticEntityFact,
            EpisodicRunNote,
            ProceduralPlaybook,
            ErrorSignatureMemory,
            SourceFact,
            EntityFingerprint,
            SourceFingerprint,
        ],
        instructions=MEMORY_INSTRUCTIONS,
        enable_inserts=True,
        enable_updates=True,
        enable_deletes=False,
    )


# -----------------------------
# 3) Routing extracted memory -> store namespace
# -----------------------------
def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def route_namespace(mem: MemoryBase, *, mission_id: Optional[str], bundle_id: Optional[str]) -> Tuple[Tuple[str, ...], str]:
    """
    Returns (namespace, key) for storing this memory in BaseStore.
    Key strategy:
      - semantic: "fact:{hash}"
      - episodic: "note:{hash}" (under mission/bundle)
      - procedural: "rule:{hash}" (under mode/agent if present else generic)
      - error: "sig:{hash}" (under tool name if provided)
      - source: "src:{hash}" (under domain/url)
      - fingerprint: "fp"
    """
    payload_key = hashlib.sha1(mem.model_dump_json().encode("utf-8")).hexdigest()[:16]

    if mem.kind == "semantic":
        ns = choose_entity_namespace(
            org_id=mem.org_id, person_id=mem.person_id, product_id=mem.product_id, compound_id=mem.compound_id
        ) or ("kg_semantic", "unscoped")
        return ns, f"fact:{payload_key}"

    if mem.kind == "episodic":
        # Prefer bundle scope, else mission scope
        if bundle_id:
            return NS.episodic_bundle(bundle_id), f"note:{payload_key}"
        if mission_id:
            return NS.episodic_mission(mission_id), f"note:{payload_key}"
        return ("episodic", "unscoped"), f"note:{payload_key}"

    if mem.kind == "procedural":
        # Optional: route by agent_type or mode if provided in data
        agent_type = (mem.data or {}).get("agent_type")
        mode = (mem.data or {}).get("mode")
        if agent_type:
            return NS.procedural_agent(str(agent_type)), f"rule:{payload_key}"
        if mode:
            return NS.procedural_mode(str(mode)), f"rule:{payload_key}"
        return ("procedural", "general"), f"rule:{payload_key}"

    if mem.kind == "error":
        tool_name = (mem.data or {}).get("tool_name") or "unknown_tool"
        return NS.errors(str(tool_name)), f"sig:{payload_key}"

    if mem.kind == "source":
        if mem.domain:
            return NS.source_domain(mem.domain), f"src:{payload_key}"
        if mem.url:
            return NS.source_url(_url_hash(mem.url)), f"src:{payload_key}"
        return ("sources", "unscoped"), f"src:{payload_key}"

    if mem.kind == "fingerprint_entity":
        entity_id = mem.org_id or mem.person_id or mem.product_id or mem.compound_id or "unknown_entity"
        return NS.fp_entity(entity_id), "fp"

    if mem.kind == "fingerprint_source":
        dom = mem.domain or "unknown_domain"
        return NS.fp_source(dom), "fp"

    return ("memories", "misc"), f"mem:{payload_key}"


async def persist_extracted_memories(
    store: BaseStore,
    extracted: List[ExtractedMemory],
    *,
    mission_id: Optional[str],
    bundle_id: Optional[str],
) -> List[Tuple[Tuple[str, ...], str]]:
    """
    Writes extracted memories into the store.
    Returns list of (namespace, key) written.
    """
    written: List[Tuple[Tuple[str, ...], str]] = []

    for mem_id, mem_obj in extracted:
        # mem_obj is a Pydantic model instance (because we passed schemas)
        if isinstance(mem_obj, MemoryBase):
            ns, key = route_namespace(mem_obj, mission_id=mission_id, bundle_id=bundle_id)
            await store.put(ns, key, mem_obj.model_dump())
            written.append((ns, key))
        else:
            # fallback: store raw string memories in a generic namespace
            ns = ("memories", "untyped")
            key = f"mem:{mem_id}"
            await store.put(ns, key, {"content": str(mem_obj)})
            written.append((ns, key))

    return written


# -----------------------------
# 4) Public API: extract + persist
# -----------------------------
async def extract_and_store_memories(
    *,
    messages: List[Dict[str, str]],
    existing: Optional[List[ExtractedMemory]] = None,
    model: str = "openai:gpt-4.1",
    mission_id: Optional[str] = None,
    bundle_id: Optional[str] = None,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """
    Run LangMem extractor on a message window and persist results into your AsyncPostgresStore.
    """
    store, _checkpointer = await get_persistence()
    extractor = build_langmem_extractor(model=model)

    # create_memory_manager expects {"messages": ..., "existing": ...} in structured mode. :contentReference[oaicite:2]{index=2}
    payload = {"messages": messages, "existing": existing or []}
    extracted: List[ExtractedMemory] = await extractor.ainvoke(payload, config or {})

    written = await persist_extracted_memories(
        store,
        extracted,
        mission_id=mission_id,
        bundle_id=bundle_id,
    )

    return {"extracted": extracted, "written": written}


# -----------------------------
# 5) Recall helpers (direct)
# -----------------------------
async def recall_semantic_for_org(org_id: str) -> List[Dict[str, Any]]:
    store, _ = await get_persistence()
    # BaseStore supports search by namespace; exact API differs by store impl.
    # AsyncPostgresStore supports .search(namespace, query) in LangGraph stores.
    # We'll do a broad list via search with empty query.
    results = await store.search(NS.semantic_org(org_id), query="")
    return [r.value for r in results]


async def recall_sources_for_domain(domain: str) -> List[Dict[str, Any]]:
    store, _ = await get_persistence()
    results = await store.search(NS.source_domain(domain), query="")
    return [r.value for r in results]


async def recall_error_signatures(tool_name: str, query: str = "") -> List[Dict[str, Any]]:
    store, _ = await get_persistence()
    results = await store.search(NS.errors(tool_name), query=query)
    return [r.value for r in results]
