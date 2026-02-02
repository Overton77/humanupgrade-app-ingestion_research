from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

Namespace = Tuple[str, ...]


@dataclass(frozen=True)
class NS:
    # --- semantic entity memory ---
    @staticmethod
    def semantic_org(org_id: str) -> Namespace:
        return ("kg_semantic", "org", org_id)

    @staticmethod
    def semantic_person(person_id: str) -> Namespace:
        return ("kg_semantic", "person", person_id)

    @staticmethod
    def semantic_product(product_id: str) -> Namespace:
        return ("kg_semantic", "product", product_id)

    @staticmethod
    def semantic_compound(compound_id: str) -> Namespace:
        return ("kg_semantic", "compound", compound_id)

    # --- episodic run memory ---
    @staticmethod
    def episodic_mission(mission_id: str) -> Namespace:
        return ("episodic", "mission", mission_id)

    @staticmethod
    def episodic_bundle(bundle_id: str) -> Namespace:
        return ("episodic", "bundle", bundle_id)

    # --- procedural memory ---
    @staticmethod
    def procedural_mode(mode: str) -> Namespace:
        return ("procedural", "research_mode", mode)

    @staticmethod
    def procedural_agent(agent_type: str) -> Namespace:
        return ("procedural", "agent_type", agent_type)

    # --- error memory ---
    @staticmethod
    def errors(tool_name: str) -> Namespace:
        return ("errors", "tool", tool_name)

    # --- sources ---
    @staticmethod
    def source_domain(domain: str) -> Namespace:
        return ("sources", "domain", domain)

    @staticmethod
    def source_url(url_hash: str) -> Namespace:
        return ("sources", "url", url_hash)

    # --- fingerprints ---
    @staticmethod
    def fp_entity(org_or_entity_id: str) -> Namespace:
        return ("fingerprints", "entity", org_or_entity_id)

    @staticmethod
    def fp_source(domain: str) -> Namespace:
        return ("fingerprints", "source", domain)


def choose_entity_namespace(
    *,
    org_id: Optional[str],
    person_id: Optional[str],
    product_id: Optional[str],
    compound_id: Optional[str],
) -> Optional[Namespace]:
    if product_id:
        return NS.semantic_product(product_id)
    if person_id:
        return NS.semantic_person(person_id)
    if compound_id:
        return NS.semantic_compound(compound_id)
    if org_id:
        return NS.semantic_org(org_id)
    return None
