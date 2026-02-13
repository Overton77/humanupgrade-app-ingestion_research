from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate



GUEST_BUSINESS_PROMPT: str = """
You are extracting seed data for a database.

You MUST use ONLY:
1) the provided CONNECTED BUNDLE (this is the original, web-search-supported connection graph of candidates),
2) the provided report text.

Return JSON that matches the response schema EXACTLY.

CONNECTED BUNDLE CONTEXT
- This bundle is the upstream connected graph that led to research directions.
- Treat it as authoritative for "who is connected to who".
- Prefer entity identity and canonical names from the connected bundle when possible.
- If the report contradicts the connected bundle identity, keep the bundle identity and note the discrepancy in the description fields (do not invent new entities).

Rules:
- guest and business are required
- If multiple businesses appear, choose the PRIMARY business connected to the guest in the connected bundle
- Avoid duplicates: one canonical entity per entity_key
- Prefer entity_key values derived from canonical names and domains in the connected bundle; do not invent random keys
- Only include fields supported by the report text; if unknown, omit or set null per schema

INPUTS

CONNECTED_BUNDLE.CONNECTED (JSON):
{connected_bundle_json}

GUEST REPORT (TEXT):
{guest_report_text}

BUSINESS REPORT (TEXT):
{business_report_text}
""".strip()


PRODUCT_COMPOUND_PROMPT: str = """
You are extracting seed data for PRODUCTS and COMPOUNDS.

You MUST use ONLY:
1) the provided CONNECTED BUNDLE (this is the original, web-search-supported connection graph of candidates),
2) the provided report text.

Return JSON that matches the response schema EXACTLY.

CONNECTED BUNDLE CONTEXT
- This bundle is the upstream connected graph that led to research directions.
- Treat it as authoritative for product->compound association candidates.
- The MOST IMPORTANT requirement is that product_compound_links correctly map which compounds belong to which products.
- Prefer entity identity and canonical names from the connected bundle when possible.

Rules:
- Output ALL products mentioned in the report(s) that correspond to products in the connected bundle
- Output ALL compounds that correspond to compounds in the connected bundle
- Build product_compound_links using ONLY products+compounds that exist in the connected bundle
- Prefer entity_key values derived from canonical names and domains in the connected bundle; do not invent keys
- Avoid duplicates: one canonical entity per entity_key
- If a compound is mentioned but not connected to a product in the bundle, do NOT link it (you may still output it if it exists as a compound node)

INPUTS

CONNECTED_BUNDLE.CONNECTED (JSON):
{connected_bundle_json}

PRODUCT/COMPOUND REPORTS (TEXT):
{product_compound_report_text}
""".strip()