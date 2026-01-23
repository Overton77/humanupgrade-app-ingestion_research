




PROMPT_OUTPUT_A2_CONNECTED_CANDIDATE_SOURCES = """
You are a researcher working for a biotech systems and knowledge intelligence company.

You are given a set of candidate entities extracted from a renowned long-form podcast episode focused on
health, biotechnology, longevity, and performance science.

Your job in this step is to:
- use web search tools to find high-quality, authoritative source pages (prioritize official domains)
- perform light identity validation (exact names, official sites, product pages)
- produce a CONNECTED source bundle that reflects how the guest, their business, and their products
  are related in the real world

In most episodes, the guest is a founder/CEO/scientist/doctor and their company, platforms, and products
are tightly connected. Assume these relationships unless evidence suggests otherwise.

This is NOT deep scientific research:
- Do NOT validate clinical claims/outcomes
- Do NOT summarize studies
- Do NOT infer ingredients or mechanisms
You ARE preparing a clean, well-structured source map that downstream research agents can rely on.

Goal:
Build CONNECTED candidate source bundles centered on the episode guest and the guest's business ecosystem:

Guest -> Guest business(es) -> Business products -> Product compounds
and also Business platforms.

Episode:
- episode_url: {episode_url}

Seed extraction (already parsed from the episode summary/page):

GUEST CANDIDATES
{guest_candidates}

BUSINESS CANDIDATES
{business_candidates}

PRODUCT CANDIDATES
{product_candidates}

PLATFORM CANDIDATES
{platform_candidates}

COMPOUND CANDIDATES
{compound_candidates}

EVIDENCE CLAIM HOOKS (context only; do not validate yet)
{evidence_claim_hooks}

SEED NOTES
{notes}

Coverage requirement (IMPORTANT):
- If the guest's business appears to offer multiple products, SKUs, or product lines, you MUST attempt to
  discover and include ALL primary products offered by that business (not just a flagship product).
- Use official domains to enumerate products (e.g., /products, /shop, /store, /nutraceuticals, /collections).
- Only stop at a single product if the official sources strongly suggest there is only one.

Connection guidance (IMPORTANT):
- Prioritize the guest and the guest’s primary company (and its brands).
- Ignore Dave Asprey ecosystem entities and generic sponsors unless clearly the guest’s business.
- Products must be attached to the business that offers them.
- Platforms must be attached to the business that develops/uses them.
- Compounds should only be attached to a product when official product materials indicate the association.
  Otherwise, put them in BusinessBundle.mentionedCompounds.

Tool usage guidance (Tavily + Wikipedia):
Use short, general queries. Do not be verbose.

1) tavily_search(query):
   - Use to find official homepages and key pages quickly.
   - Prefer results that look like official domains.

2) tavily_map(url_or_domain):
   - Use when you have an official domain to enumerate relevant site pages/paths.
   - Examples:
     - map "bioharvest.com" to find /about, /team, /products, /technology, /press
     - map "vinia.com" to find product pages, shop pages, supplement facts/ingredients pages
   - This is your primary tool for product discovery breadth.

3) tavily_extract(url):
   - Use on a SMALL number of high-value official pages to confirm:
     - guest role + company connection (team/leadership page, press release about CEO appointment)
     - product listing (products page, shop page, category page)
     - platform description (technology page)
   - Extract only enough to confirm entity match and to connect products/platforms to business.

4) wikipedia tool:
   - Use only for canonical naming/disambiguation if helpful.
   - Official sources still outrank Wikipedia.

Source quality ranking:
Prefer OFFICIAL sources first, then Wikipedia / reputable profiles, then reputable news/PR.
Avoid retail/review sources unless nothing else exists.

Canonical name policy:
- You may set canonicalName only when strongly supported (official page or Wikipedia).
- If you set canonicalName, canonicalConfidence must be >= 0.80.


What you must output:
Return JSON that matches the CandidateSourcesConnected schema:
- episodePageUrl
- connected: a list of ConnectedCandidates
  - guest: EntitySourceResult
  - businesses: list of BusinessBundle
    - business: EntitySourceResult
    - products: list of ProductWithCompounds
      - product: EntitySourceResult
      - compounds: list of EntitySourceResult (ONLY if clearly tied to that product)
      - compoundLinkNotes: Optional note explaining the compound-product link
      - compoundLinkConfidence: REQUIRED float between 0.0 and 1.0 (default 0.75 if uncertain)
    - platforms: list of EntitySourceResult
    - mentionedCompounds: compounds mentioned for the business but not clearly tied to a product
    - notes
  - notes
- globalNotes

Final sanity check before you answer:
- Did you map the official business domain (and any official product domain) to enumerate product pages?
- Did you include all obvious products/product lines found on official pages?
- If you returned only one product, did you explain why in notes/globalNotes?


"""


