Recommended default order (stage gates)
Stage 0 — Scope + inputs (cheap, sets everyone up)

DomainCatalogExpansionAgent

SourceSetCuratorAgent (creates per-subagent source sets + budgets)

Stage 1 — High-signal “ground truth” (run in parallel)

BusinessIdentityAndLeadershipAgent

PersonBioAndAffiliationsAgent

ProductSpecAgent (often the heaviest; starts early)

HelpCenterAgent (if a help subdomain exists)

PressAndReputationAgent

Stage 2 — Dependent enrichment (kicks off when specs/help exist)

ProductCompoundsAgent (depends on ProductSpec output)

ContraindicationsAndSafetyAgent (benefits from HelpCenter + product pages)

CaseStudyHarvestAgent (benefits from curated source sets and “research/clinical” sections)

Stage 3 — Triage / synthesis layer (small, quality-focused)

ClinicalEvidenceTriageAgent (uses PubMed / scholar-ish tools; operates on harvested claims/case-studies)

TechnologyProcessAgent (optional; best after product/help discovery so it knows what to look for)

This ordering minimizes wasted browsing: you expand + curate sources first, then parallelize heavy extraction, then run the agents that need those outputs.

Consolidated Sub-Agent Types + tool bundles
1) DomainCatalogExpansionAgent

Goal: Expand official site map beyond what you already have (products, help center, manuals PDFs, “research” pages).
Tools:

Search: Tavily Search (fast), plus fallback (DuckDuckGo / Brave / Serper / Exa).

Web browsing / crawling: Playwright Browser Toolkit (handles JS-heavy pages).

Targeted extraction: Tavily Extract for pulling page content cleanly once URLs are known.

Optional scraping-at-scale: Apify (if you want structured crawling pipelines).

2) SourceSetCuratorAgent (structured output)

Goal: Produce SourceSets per subagent (official URLs, help categories, product page URLs, “research” URLs, press URLs), plus budgets + notes.
Tools:

Same as above, but emphasize Search + Tavily Extract for verification.

3) ProductSpecAgent

Goal: For N products: price, variants, components, specs, manuals, warnings, warranty, “what’s included.”
Tools:

Web browsing: Playwright Browser Toolkit (click variants, expand accordions, handle Shopify/React, etc.).

Extraction: Tavily Extract (fast text capture for stable pages).

Search fallback: Tavily Search / Exa / Serper.

4) HelpCenterAgent

Goal: Mine help subdomain categories/articles: setup, contraindications, maintenance, warranty/returns, claims language.
Tools:

Search + extract: Tavily Search + Tavily Extract.

Web browsing: Playwright when help center uses heavy JS navigation.

5) ProductCompoundsAgent

Goal: Map products → compounds/actives/material exposures (or in device cases: “delivered substance” like oxygen), plus basic normalization.
Tools:

Wikipedia (fast normalization) + Wikidata (IDs/aliases).

PubMed + Semantic Scholar API for quick “what is it / what’s it used for” context.

Search fallback: Tavily Search.

6) ContraindicationsAndSafetyAgent

Goal: Collect safety guidance (contraindications, warnings, adverse events language) from official + reputable sources.
Tools:

Official-first: Tavily Search + Tavily Extract.

Browse when needed: Playwright.

7) CaseStudyHarvestAgent

Goal: Gather company-used evidence artifacts (case studies, whitepapers, “clinical results,” testimonial pages framed as studies). No deep validation yet—just harvest + index.
Tools:

Search: Tavily Search (plus Exa for “published date / author” signals when available).

Extraction: Tavily Extract for clean capture and quoting.

Browse: Playwright if content is gated behind UI interactions.

8) ClinicalEvidenceTriageAgent (lightweight)

Goal: Triage the harvested claims: find likely clinical anchors, related terms, “is this even a real study,” and build a shortlist for later deep verification.
Tools:

PubMed, Semantic Scholar API, arXiv (where relevant), Wikipedia for quick grounding.

Search fallback: Tavily Search / Google Scholar tool (if you add it).

9) TechnologyProcessAgent

Goal: “How it works” pages, protocols, manufacturing/QA statements, materials, process claims.
Tools:

Search + extract: Tavily Search + Tavily Extract.

Browse: Playwright for interactive diagrams / tabbed specs.

10) BusinessIdentityAndLeadershipAgent

Goal: Canonical business identity, leadership, positioning, contact, “wellness vs medical” posture (light).
Tools:

Search: Tavily Search + (Brave / DuckDuckGo / Serper fallback).

Browse: Playwright if leadership info is buried or dynamically loaded.

11) PressAndReputationAgent

Goal: Press coverage, controversies, BBB-style signals (if you choose), recall/regulatory news mentions, review landscape.
Tools:

Search: Exa (nice metadata), Tavily Search, Serper.

Optional finance/news hooks: Yahoo Finance News / Polygon IO / Alpha Vantage if you’re tracking public companies or press cycles tied to tickers.

12) PersonBioAndAffiliationsAgent

Goal: Bio, roles, affiliations, profiles, prior companies, credibility anchors.
Tools:

Search: Tavily Search + fallback providers.

Browse: Playwright for LinkedIn-like dynamic pages when allowed/needed.

Tool consolidation (the “core toolbox” you’ll reuse everywhere)

Core search (pick 2–3 + fallbacks):

Tavily Search, Exa Search, DuckDuckGoSearch, Brave Search, Google Serper, Jina Search.

Core browsing / interaction:

Playwright Browser Toolkit (your workhorse), Requests Toolkit (cheap fetches).

Core extraction:

Tavily Extract (and optionally Tavily Map if you’re using it for discovery flows).

Core research / medical-ish:

PubMed, Semantic Scholar API, Wikipedia, Wikidata, arXiv (optional).

Optional finance/news:

Yahoo Finance News, Alpha Vantage, Polygon IO (only if it’s relevant to entity types you’re researching).

If you want the “trade-off” cut (fewer agent types), the cleanest minimal set that still covers your new capabilities is:

DomainCatalogExpansionAgent → SourceSetCuratorAgent → ProductSpecAgent + HelpCenterAgent + (BusinessIdentity / PersonBio) → CaseStudyHarvestAgent → ClinicalEvidenceTriageAgent.