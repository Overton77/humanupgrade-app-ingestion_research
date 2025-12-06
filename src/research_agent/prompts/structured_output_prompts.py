"""
Prompts for structured output extraction from research results.
"""

ENTITY_EXTRACTION_PROMPT = """
You are extracting structured entities from research findings for the Human Upgrade Podcast knowledge base.

RESEARCH DIRECTION
------------------
Direction ID: {direction_id}
Topic: {topic}
Description: {description}
Overview: {overview}

RESEARCH SUMMARY
----------------
{extensive_summary}

KEY FINDINGS
------------
{key_findings}

CITATIONS (use these for source attribution)
--------------------------------------------
{citations}

EXTRACTION GUIDELINES
---------------------
1. Only extract entities with CLEAR evidence in the research above.
2. For each entity, include source URLs from the citations that support it.
3. Set confidence scores appropriately:
   - 0.9-1.0: Explicitly named with substantial details in the research
   - 0.7-0.89: Clearly mentioned with some context
   - 0.5-0.69: Inferred from context but not explicitly detailed
   - Below 0.5: Do NOT extract (too speculative)
4. Use name fields (business_name, product_names, affiliations, etc.) to indicate 
   relationships between entities - downstream processing will link them.
5. Include extraction_notes for any important context or caveats.
6. For compounds, try to capture mechanism_of_action if discussed.
7. For case studies, prioritize PubMed/clinical trial sources.

ENTITY TYPES TO EXTRACT
-----------------------
- businesses: Companies, organizations, brands mentioned
- products: Specific products, supplements, devices, programs (include price if mentioned)
- people: Guests, founders, researchers, executives
- compounds: Bioactive compounds, supplement ingredients, molecules (e.g., NAD+, creatine, resveratrol)
- case_studies: Clinical evidence, research papers, studies, trials mentioned

IMPORTANT
---------
- Set direction_id to "{direction_id}" for ALL extracted entities.
- Empty lists are fine if no entities of that type are found.
- Quality over quantity: prefer fewer well-supported entities over many guesses.
- Always include at least one source in the sources list for each entity.

Return a ResearchEntities object with lists for each entity type.
"""


# Kept for backwards compatibility - use ENTITY_EXTRACTION_PROMPT instead
STRUCTURED_OUTPUT_PROMPT = ENTITY_EXTRACTION_PROMPT
