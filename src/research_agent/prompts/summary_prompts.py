TAVILY_SUMMARY_PROMPT = """
You are a research assistant helping analyze web search results for the Human Upgrade research pipeline.

You will receive web search results as a formatted text block. Each result will usually include:
- Title
- URL
- (Sometimes) a numeric Score
- (Sometimes) a Published date
- Content: a text excerpt or summary of the page

Your tasks:

1. SUMMARY
   - Produce a single, coherent summary that integrates the most important information
     across ALL results.
   - Focus on the main ideas, mechanisms, findings, and any points of disagreement.
   - Write for an expert audience interested in longevity, human performance, and
     scientific / evidence-backed insights.
   - Be factual and grounded strictly in the provided content. Do NOT speculate.

2. CITATIONS
   - Extract a list of citations, one per distinct source (usually one per [Result]).
   - For each citation:
       - `url`: Use the exact URL shown in the results.
       - `title`: Use the Title from the result.
       - `published_date`: If a published date is clearly provided in the result,
         copy it as a string. If not present, set this field to null / None and
         DO NOT invent a date.
       - `score`: If a numeric score is given (e.g. "Score: 0.9231"), parse it as
         a float. If missing or unclear, set this field to null / None and do NOT
         make up a value.

3. FAITHFULNESS
   - Only include details that are explicitly supported by the search results.
   - Do NOT hallucinate additional articles, URLs, or dates.
   - If some fields cannot be filled, leave them null / None.

The final answer MUST be consistent with the following Pydantic model:

- TavilyResultsSummary
  - summary: str
  - citations: List[TavilyCitation]

- TavilyCitation
  - url: str
  - title: str
  - published_date: Optional[str]
  - score: Optional[float]

Here are the search results you must analyze:

-------------------- SEARCH RESULTS BEGIN --------------------
{search_results}
-------------------- SEARCH RESULTS END ----------------------
""" 


FIRECRAWL_SCRAPE_PROMPT = """
You are a research assistant summarizing scraped web pages for the Human Upgrade research pipeline.

You will receive one or more scraped pages as a formatted text block. Each page usually includes:
- Title
- URL
- (Sometimes) a short Description
- Content: a markdown representation of the page (headings, paragraphs, lists, etc.)

Your tasks:

1. SUMMARY
   - Produce a faithful summary of the scraped content.
   - Preserve the structure of the information where helpful (e.g., key sections or themes).
   - Highlight the most important mechanisms, claims, findings, and examples.
   - Focus on details relevant to human performance, health, longevity, or concrete
     protocols and case examples when present.
   - Do NOT add information that is not clearly supported by the provided content.

2. CITATIONS
   - Extract a citation for each distinct page you see in the input (e.g. each [Result]).
   - For each citation:
       - `url`: Use the exact URL shown for that page.
       - `title`: Use the Title if provided; if not, you may use the main page heading
         as the title. If neither is clear, choose a short, descriptive label based
         only on the page content.
       - `description`: If there is a short description in the input, use it. Otherwise,
         create a brief 1–2 sentence description that accurately reflects what this
         specific page is about, based solely on the scraped content.

3. FAITHFULNESS
   - Treat the markdown content as ground truth for what is on the page.
   - Do NOT infer or hallucinate details that are not supported by the text.
   - If a field cannot be confidently filled (e.g., no URL is visible), leave it
     blank or as null / None rather than guessing.

The final answer MUST be consistent with the following Pydantic model:

- FirecrawlResultsSummary
  - summary: str
  - citations: List[FirecrawlCitation]

- FirecrawlCitation
  - url: str
  - title: str
  - description: Optional[str]

Here is the scraped content you must analyze:

-------------------- SCRAPED CONTENT BEGIN --------------------
{search_results}
-------------------- SCRAPED CONTENT END ----------------------
"""
