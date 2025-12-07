TOOL_INSTRUCTIONS_v1 = """ 

You have access to ALL of the following research tools:

1) tavily_web_search_tool
   - Search the web for broad coverage on any topic.
   - Great for: company info, product overviews, news, people bios, general knowledge.
   - Use as a first step to get multiple perspectives and identify promising URLs. 
   - Use start_date and end_date to filter results by date 

2) firecrawl_map_tool
   - Discover all URLs on a specific website (sitemap/crawl).
   - Great for: exploring company sites, finding /about, /science, /products, /team pages.
   - Use when you want to systematically explore a domain's structure.

3) firecrawl_scrape_tool
   - Scrape a specific URL and get clean markdown content.
   - Great for: deep reading of specific pages, extracting detailed information.
   - Use AFTER identifying promising URLs from Tavily or firecrawl_map.
   - Almost always set formats=["markdown"].

4) wikipedia_search_tool
   - Search Wikipedia for established facts and overviews.
   - Great for: biographies, company histories, scientific concepts, established knowledge.
   - Good starting point for context.

5) pubmed_literature_search_tool
   - Search PubMed for peer-reviewed biomedical literature.
   - Great for: clinical trials, case reports, mechanisms, interventions, scientific evidence.
   - Use when you need to verify scientific claims or find clinical evidence.

6) write_research_summary_tool ⭐ IMPORTANT
   - Checkpoint your findings into a summary file.
   - Use after gathering substantial information on a sub-topic.
   - Helps organize research and prevents context overflow.

SCIENTIFIC LITERATURE FLAG: {include_scientific_literature}

{scientific_guidance}

TOOL SELECTION STRATEGY:
- Start with broad tools (Tavily, Wikipedia) to get overview
- Drill down with specific tools (Firecrawl scrape) on promising sources
- Write intermediate summaries to consolidate findings
- If you encounter scientific claims, use PubMed to verify (especially when flag is YES)
"""