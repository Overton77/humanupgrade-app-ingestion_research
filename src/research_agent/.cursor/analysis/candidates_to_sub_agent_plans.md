A cleaner “deeply thought” order
Stage A — Identity anchors (cheap, high precision)

official_sources
Output: canonical guest + business + primary official domains (and known subdomains like help/learn/research/blog).

Stage B — Official-site catalog (enumeration, not research)

domain_catalogs (but broaden it into an “OfficialSiteCatalogSet”)
Output: lists of URLs + light metadata. This is where you ensure “coverage.”

Stage C — Candidate graph construction (uses the catalog)

candidates_connected
Use the catalog’s product URLs (and now also exec/case-study URLs) to improve:

product enumeration

executive/person candidates (leadership pages)

evidence/case-study candidates (company-used “proof” assets)

Stage D — Research directions (planning only)

research_directions
Should reference: connected bundle + catalog facets + “source set hints”.

Stage E — Expansion + curation (now it’s okay to go wider)

Catalog Expansion (non-official optional)
Now you expand beyond official site (partners, reviews, regulators, publications).

Full Source Curation
Produce per-subagent SourceSets + budgets.

Stage F — Sub-agent planning + execution

Sub-agent plan generation (LLM structured output)

Run sub-agents (parallel, with gating on dependencies)

Your key question: should the Domain Catalog step include ALL Executives + ALL Case Studies?

Yes—but only as enumeration, not deep extraction.
This is the crucial trade-off:

Why it’s worth it

Makes downstream precise: Your SourceSetCurator and sub-agent planner can allocate work intelligently (e.g., “there are 38 products, 7 exec bios, 12 case-study pages”).

Reduces missed coverage: Execs and “evidence” pages are often not linked cleanly from the shop/product index, so you’ll miss them if DomainCatalog is “products only.”

Keeps official-first discipline: You harvest the company’s own framing before you ever go “open web.”

Why it can become painful if done wrong

If DomainCatalog becomes “full content extraction,” it turns into a research agent and gets slow + noisy.

Exec pages and case-study pages can be ambiguous (blog posts, testimonials, “research” marketing pages, etc.). The catalog step should not try to judge, just collect & label.

So the move is: expand DomainCatalog into a structured “OfficialSiteCatalogSet” with multiple facets.

What I’d add to DomainCatalog (minimal, high leverage)
1) Products facet (you already have)

productPageUrls (+ optional SKU handles if Shopify)

productIndexUrls (shop, collections, sitemap products)

2) Leadership / People facet (new)

leadershipIndexUrls (e.g., /about, /pages/about-us, /team, /leadership)

executiveProfileUrls (just URLs + inferred names/titles if obvious from URL/page title)

No full bio extraction here

3) Evidence facet (new)

This is your “CaseStudyHarvestAgent seed list,” official-only:

evidenceIndexUrls (e.g., /pages/research, /blogs, /pages/testimonials, /clinical, /science)

caseStudyUrls / testimonialUrls / whitepaperUrls / “results” urls

optionally tag each URL with a coarse evidenceKind: case_study | testimonial | whitepaper | research_page | blog_post

4) Help / Policies facet (often critical)

helpCenterCategoryUrls + articleUrls (or just category roots)

warranty/returns/shipping/privacy/terms URLs

manuals PDF URLs (these are gold for specs + warnings)

This becomes a single official-site “inventory snapshot”.

Practical rule: keep DomainCatalog deterministic and bounded

To avoid scope creep, give it strict constraints:

Official domains only (including known subdomains).

Output is URL lists + tiny metadata (title, lastmod if sitemap provides it).

Hard caps with pagination strategy (e.g., max 500 URLs per facet; if exceeded, store “next seeds” for expansion agents).

Prefer sitemap/known patterns first, then fall back to crawl/map.

This keeps the step fast and stable, and you can always have later agents do deeper extraction.