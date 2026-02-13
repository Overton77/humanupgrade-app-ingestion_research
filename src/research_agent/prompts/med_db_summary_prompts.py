PMC_SUMMARY_PROMPT = """
You are summarizing biomedical literature using full-text articles from PubMed Central (PMC).

You are given:
- Search context (counts and PMC IDs)
- Full-text article content (converted from XML to plain text; may be truncated)

Instructions:
1. Provide a concise summary (2–4 paragraphs) focused on what is most relevant
   to clinicians, longevity researchers, and health practitioners.
   - Highlight both clinical implications and mechanistic insights when available.
2. Extract 3–8 key findings as short bullet-point strings.
   - When possible, mention study type (e.g., RCT, cohort, case series),
     population, intervention/exposure, and major outcome.
3. Extract a list of citations with, when available:
   - pmid (if you can infer it from the text; otherwise omit)
   - doi
   - title
   - url (PMC article URL if possible, e.g. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC<PMCID>/)
4. Base your summary primarily on human data when available, but you may
   incorporate mechanistic and preclinical findings to explain *why* effects
   may occur.

Return your answer in the structured format requested by the calling code
(PubMedResultsSummary / PubMedCitation).

FULLTEXT SEARCH RESULTS AND ARTICLES:
-------------------------------------
{search_results}
"""

PUBMED_SUMMARY_PROMPT = """
You are summarizing biomedical literature results from PubMed.

You are given:
- Search context (counts and PMIDs)
- Article metadata (titles, journals, dates, authors, DOIs)
- Abstract text

Instructions:
1. Provide a concise summary (2–4 paragraphs) focused on what is most relevant
   to clinicians, longevity researchers, and health practitioners.
2. Extract 3–8 key findings as short bullet-point strings.
3. Extract a list of citations with, when available:
   - pmid
   - doi
   - title
   - url (constructed from the PMID if needed: https://pubmed.ncbi.nlm.nih.gov/PMID_HERE/)

Return your answer in the structured format requested by the calling code.

SEARCH RESULTS AND ABSTRACTS:
------------------------------
{search_results}
"""