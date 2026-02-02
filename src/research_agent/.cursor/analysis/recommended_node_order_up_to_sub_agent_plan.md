Recommended node order (v1 that won’t bite you later)

seed_extraction

Extract guest/business/product/platform mentions from episode context.

Goal: cheap signal to drive official discovery.

official_sources

Find the canonical guest + business anchors (and primary domain(s)).

Output: OfficialStarterSources (or whatever you call it) + candidate canonical names.

official_site_catalog_sets (your “Domain Catalog” upgraded)

For each official domain: breadth crawl/map to enumerate:

product index pages

product pages

help center / FAQ / manuals / policies

leadership/team pages

“evidence” pages (case studies, testimonials-as-studies, whitepapers, “science” pages)

press pages

Output: OfficialSiteCatalogSet (your renamed DomainCatalogSet), stored as an artifact and referenced in intel_candidate_run.domainCatalog.

candidate_sources

Build CandidateSourcesConnected using:

seed_extraction entities

official_sources anchors

official_site_catalog_sets (breadth enumerations)

This is where you create the connected bundle (guest → business → products/platforms/compounds).

Important: keep this step mostly deterministic + rule-based, not “research-y”.

persist_candidates

Persist run + entities + dedupe groups (as you already do).

generate_research_directions (lightweight plan from connected bundle)

This is still your “direction plan” for: GUEST/BUSINESS/PRODUCT/COMPOUND/PLATFORM.

Keep it “what to research / required fields / starter sources”.

catalog_expansion

Only now do you broaden beyond the official site:

verify missing aliases (“LEO System” problem)

discover manuals hosted off-domain

distributor pages, marketplaces, regulatory databases

high-recall for press/reputation signals

Output: expansion artifacts + additional discovered URLs, tagged by category.

source_set_curator

Takes inputs from:

official_site_catalog_sets

candidate_sources connected bundle

catalog_expansion results

research_directions

Produces per-category/per-subagent SourceSets (curated + deduped + prioritized).

This must run before subagent planning (see below).

subagent_builder (planner)

Consumes:

research_directions

source sets

thresholds (products count, domains count, evidence volume)

Produces:

SubAgentPlan + SubAgentRuns skeletons (slices, budgets, dependencies)

run_subagents

Executes SubAgentRuns in parallel (respecting dependencies).

persist_research_plans / persist_runs

Save final outputs, file refs, artifacts, and run status.