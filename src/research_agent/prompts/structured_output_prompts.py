"""
Prompts for structured output extraction from research results.
"""

ENTITY_EXTRACTION_PROMPT = """
You are extracting structured entities from the *final synthesized entity-intelligence output* 
for a single research direction of the Human Upgrade Podcast knowledge system.

Your input contains:
- The direction_id that all extracted entities must inherit.
- A master extensive summary of the research.
- Key findings that highlight the most salient insights.
- A curated list of key source citations (URLs, DOIs, PMIDs, etc.).
- A list of entity_intel_ids discovered earlier in the research loop that may signal
  which entities are important, though you MUST NOT invent entities.

RESEARCH CONTEXT
----------------
Direction ID: {direction_id}

ENTITY INTEL IDS (contextual hints)
-----------------------------------
These IDs indicate which entities were previously recognized as important.
Do NOT fabricate new entities solely from these IDs, but use them to increase
confidence when the same entities appear in the summary.

{entity_intel_ids}

RESEARCH SUMMARY (Primary extraction source)
--------------------------------------------
{extensive_summary}

KEY FINDINGS
------------
{key_findings}

KEY SOURCE CITATIONS  
(use these for SourceAttribution entries)
-----------------------------------------
{citations}

CITATION → SOURCE MAPPING RULES
-------------------------------
When assigning sources to an extracted entity:
1. Every entity MUST have **at least one** SourceAttribution.
2. For each citation:
   - If it is a URL → url=<the URL>, source_type inferred from domain:
       * PubMed → "pubmed"
       * DOI link → "other"
       * Company website → "company_website"
       * News domain → "news"
       * Wikipedia → "wikipedia"
       * ClinicalTrials.gov → "clinical_trial"
   - If it is a PMID/DOI without URL → treat as pubmed/other accordingly.
3. If no citation matches perfectly, choose the most relevant citation supporting
   that entity’s description.

EXTRACTION GUIDELINES
---------------------
1. Extract ONLY entities with clear, explicit evidence in the summary or findings.
2. Do NOT infer entities unless:
   - They are named directly, or
   - They are strongly implied by multiple statements with clear attributes.
3. Confidence scoring:
   - 0.90–1.00 → explicitly named with detailed attributes.
   - 0.70–0.89 → clearly mentioned with some context.
   - 0.50–0.69 → weakly supported; extract ONLY IF clearly relevant.
   - <0.50 → DO NOT EXTRACT.
4. Use relationship fields intentionally:
   - BusinessOutput.product_names
   - BusinessOutput.executive_names
   - PersonOutput.affiliations
   - ProductOutput.business_name
   - CompoundOutput.related_product_names
   - CaseStudyOutput.related_compound_names / product_names
5. Use extraction_notes to explain WHY the entity was extracted.
6. Case studies should reference PubMed/clinical evidence when available.
7. Quality > quantity. It is better to return fewer entities with strong support.

ENTITY TYPES TO EXTRACT
-----------------------
- businesses: companies, brands, organizations
- products: supplements, devices, programs (include price only if explicitly mentioned)
- people: founders, researchers, executives, experts
- compounds: bioactive molecules, supplement ingredients, mechanistic agents
- case_studies: clinical trials, research papers, studies supporting claims

REQUIRED OUTPUT FORMAT
----------------------
Return a **ResearchEntities** object with fields:
- businesses: List[BusinessOutput]
- products: List[ProductOutput]
- people: List[PersonOutput]
- compounds: List[CompoundOutput]
- case_studies: List[CaseStudyOutput]

CRITICAL
-------- 
- Every entity MUST include at least one SourceAttribution  
- Do NOT include entities not explicitly supported by the summary or findings  
- Empty lists are acceptable if no entities exist in that category  

Produce ONLY the structured ResearchEntities JSON — no explanations.
"""


# Kept for backwards compatibility - use ENTITY_EXTRACTION_PROMPT instead
STRUCTURED_OUTPUT_PROMPT = ENTITY_EXTRACTION_PROMPT
