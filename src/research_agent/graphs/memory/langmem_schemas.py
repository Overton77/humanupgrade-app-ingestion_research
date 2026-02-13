from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional

MemoryKind = Literal[
    "semantic",
    "episodic",
    "procedural",
    "error",
    "source",
    "fingerprint_entity",
    "fingerprint_source",
]


class MemoryBase(BaseModel):
    """
    Base shape LangMem can emit. We'll route these into Store namespaces.
    """
    kind: MemoryKind

    # routing keys (optional, but recommended)
    org_id: Optional[str] = None
    person_id: Optional[str] = None
    product_id: Optional[str] = None
    compound_id: Optional[str] = None
    domain: Optional[str] = None
    url: Optional[str] = None

    # traceability
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)  # short quotes/snippets or file refs
    sources: List[str] = Field(default_factory=list)   # URLs or file paths

    # generic payload
    data: Dict[str, Any] = Field(default_factory=dict)

    # versioning / time
    observed_at: Optional[str] = None  # ISO string
    ttl_days: Optional[int] = None     # for volatile facts, optional


class SemanticEntityFact(MemoryBase):
    kind: Literal["semantic"] = "semantic"
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Canonical-ish facts: aliases, domains, leadership, product specs (versioned), claims ledger links, etc.",
    )


class EpisodicRunNote(MemoryBase):
    kind: Literal["episodic"] = "episodic"
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Compact run summary: what worked, what failed, missingness checklist outcomes, source yield, plan deltas.",
    )


class ProceduralPlaybook(MemoryBase):
    kind: Literal["procedural"] = "procedural"
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Reusable playbooks: query templates, platform extraction tactics, mode heuristics, slicing/budget rules.",
    )


class ErrorSignatureMemory(MemoryBase):
    kind: Literal["error"] = "error"
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Failure signature -> mitigation. Includes tool name, error message pattern, fix recipe, fallback strategy.",
    )


class SourceFact(MemoryBase):
    kind: Literal["source"] = "source"
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Source knowledge: official domains, help center paths, sitemap URLs, high-yield pages, access constraints.",
    )


class EntityFingerprint(MemoryBase):
    kind: Literal["fingerprint_entity"] = "fingerprint_entity"
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Entity fingerprint for similarity recall (type, taxonomy distribution, platform signals, ingredient signature, etc.).",
    )


class SourceFingerprint(MemoryBase):
    kind: Literal["fingerprint_source"] = "fingerprint_source"
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Source fingerprint for similarity recall (platform signals, yield metrics, categories present, etc.).",
    )
