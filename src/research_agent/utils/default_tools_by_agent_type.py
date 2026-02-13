
DEFAULT_TOOLS_BY_AGENT_TYPE: dict[str, list[str]] = {
  "BusinessIdentityAndLeadershipAgent": [
    "tavily.search", "tavily.extract", "tavily.map", "browser.playwright", "fs.write", "fs.read", "think"
  ],
  "PersonBioAndAffiliationsAgent": [
    "search.exa", "search.tavily", "browser.playwright", "scholar.semantic_scholar", "scholar.pubmed",
    "fs.write", "fs.read", 
  ],
  "ProductCatalogerAgent": [
    "search.tavily", "extract.tavily", "browser.playwright", "fs.write", "fs.read", 
  ],
  "ProductSpecAgent": [
    "browser.playwright", "extract.tavily", "doc.pdf_text", "doc.pdf_screenshot_ocr",
    "fs.write", "fs.read", 
  ],
  "TechnologyProcessAndManufacturingAgent": [
    "search.tavily", "browser.playwright", "extract.tavily", "doc.pdf_text",
    "scholar.semantic_scholar", "fs.write", "fs.read", 
  ],
  "ClaimsExtractorAndTaxonomyMapperAgent": [
    "extract.tavily", "browser.playwright", "fs.write", "fs.read", 
  ],
  "CaseStudyHarvestAgent": [
    "search.exa", "search.tavily", "extract.tavily", "browser.playwright", "doc.pdf_text",
    "fs.write", "fs.read", 
  ],
  "ClinicalEvidenceTriageAgent": [
    "scholar.pubmed", "scholar.semantic_scholar", "registry.clinicaltrials",
    "search.tavily", "fs.write", "fs.read", 
  ],
  "ContraindicationsAndSafetyAgent": [
    "extract.tavily", "browser.playwright", "doc.pdf_text", "search.tavily",
    "fs.write", "fs.read", 
  ],
  "ProductReviewsAgent": [
    "search.exa", "search.tavily", "browser.playwright", "extract.tavily",
    "fs.write", "fs.read", 
  ],
  "KnowledgeSynthesizerAgent": [
    "fs.read", "fs.write", 
  ],
  "ClaimConfidenceScorerAgent": [
    "fs.read", "fs.write", 
  ],
  "NarrativeAnalystAgent": [
    "fs.read", "fs.write", 
  ],
  "ResearchRouterAgent": [
    "fs.read", "fs.write"
  ],
}



FULL_ENTITIES_BASIC_DEFAULT_TOOL_MAP: dict[str, list[str]] = {
    "BusinessIdentityAndLeadershipAgent": [
        "tavily.search",
        "tavily.extract", 
        "tavily.map",
        "wiki.search",
        # "fs.read",
        # "fs.write",
        "checkpoint.write",
        "think",
    ],
    "PersonBioAndAffiliationsAgent": [
        "tavily.search",
        "tavily.extract", 
        "wiki.search",
        "fs.read",
        "fs.write",
        "think",
    ],
    "EcosystemMapperAgent": [
        "exa.search",
        "exa.find_similar",
        "tavily.extract",
        "fs.read",
        "fs.write",
        "think",
    ],
    "ProductSpecAgent": [
        "browser.playwright",
        "tavily.search",
        "tavily.crawl",
        "tavily.extract",
        "fs.read",
        "fs.write",
        "think",
    ],
    "CaseStudyHarvestAgent": [
        "tavily.search",
        "tavily.extract", 
        "tavily.map",
        "fs.read",
        "fs.write",
        "think",
    ],
}