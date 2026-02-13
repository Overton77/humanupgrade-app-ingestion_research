"""MongoDB repositories for candidate pipeline artifacts."""
from __future__ import annotations

from research_agent.services.mongo.candidates.seeds_repo import (
    upsert_candidate_seed_doc,
    get_candidate_seed_doc_by_run_id,
    delete_candidate_seed_doc_by_run_id,
)

from research_agent.services.mongo.candidates.official_sources_repo import (
    upsert_official_starter_sources_doc,
    get_official_starter_sources_doc_by_run_id,
    delete_official_starter_sources_doc_by_run_id,
)

from research_agent.services.mongo.candidates.domain_catalogs_repo import (
    upsert_domain_catalog_set_doc,
    get_domain_catalog_set_doc_by_run_id,
    delete_domain_catalog_set_doc_by_run_id,
)

from research_agent.services.mongo.candidates.connected_candidates_repo import (
    upsert_connected_candidates_doc,
    get_connected_candidates_docs_by_run_id,
    get_connected_candidates_doc_by_run_and_domain,
    delete_connected_candidates_docs_by_run_id,
)

from research_agent.services.mongo.candidates.candidate_sources_repo import (
    upsert_candidate_sources_connected_doc,
    get_candidate_sources_connected_doc_by_run_id,
    delete_candidate_sources_connected_doc_by_run_id,
)

from research_agent.services.mongo.candidates.runs_repo import (
    create_or_get_candidate_run,
    update_run_status,
    update_run_outputs,
    update_run_stats,
    get_candidate_run_by_id,
    get_candidate_runs_by_query,
)

from research_agent.services.mongo.candidates.entities_repo import (
    bulk_insert_candidate_entities,
    delete_candidate_entities_for_run,
    get_candidate_entities_by_run_id,
    upsert_dedupe_group_and_add_member,
    get_dedupe_group_by_entity_key,
    get_all_dedupe_groups_for_type,
    flatten_connected_candidates_to_entity_docs,
    build_entity_key,
)

__all__ = [
    # Seeds
    "upsert_candidate_seed_doc",
    "get_candidate_seed_doc_by_run_id",
    "delete_candidate_seed_doc_by_run_id",
    
    # Official Sources
    "upsert_official_starter_sources_doc",
    "get_official_starter_sources_doc_by_run_id",
    "delete_official_starter_sources_doc_by_run_id",
    
    # Domain Catalogs
    "upsert_domain_catalog_set_doc",
    "get_domain_catalog_set_doc_by_run_id",
    "delete_domain_catalog_set_doc_by_run_id",
    
    # Connected Candidates
    "upsert_connected_candidates_doc",
    "get_connected_candidates_docs_by_run_id",
    "get_connected_candidates_doc_by_run_and_domain",
    "delete_connected_candidates_docs_by_run_id",
    
    # Candidate Sources
    "upsert_candidate_sources_connected_doc",
    "get_candidate_sources_connected_doc_by_run_id",
    "delete_candidate_sources_connected_doc_by_run_id",
    
    # Runs
    "create_or_get_candidate_run",
    "update_run_status",
    "update_run_outputs",
    "update_run_stats",
    "get_candidate_run_by_id",
    "get_candidate_runs_by_query",
    
    # Entities
    "bulk_insert_candidate_entities",
    "delete_candidate_entities_for_run",
    "get_candidate_entities_by_run_id",
    "upsert_dedupe_group_and_add_member",
    "get_dedupe_group_by_entity_key",
    "get_all_dedupe_groups_for_type",
    "flatten_connected_candidates_to_entity_docs",
    "build_entity_key",
]
