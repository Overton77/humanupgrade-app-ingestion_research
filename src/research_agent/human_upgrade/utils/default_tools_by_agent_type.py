DEFAULT_TOOLS_BY_AGENT_TYPE = {
  "BusinessIdentityAndLeadershipAgent": [
    "search.tavily", "extract.tavily", "browser.playwright", "fs.write", "fs.read", "context.summarize"
  ],
  "PersonBioAndAffiliationsAgent": [
    "search.exa", "search.tavily", "browser.playwright", "scholar.semantic_scholar", "scholar.pubmed",
    "fs.write", "fs.read", "context.summarize"
  ],
  "ProductCatalogerAgent": [
    "search.tavily", "extract.tavily", "browser.playwright", "fs.write", "fs.read", "context.summarize"
  ],
  "ProductSpecAgent": [
    "browser.playwright", "extract.tavily", "doc.pdf_text", "doc.pdf_screenshot_ocr",
    "fs.write", "fs.read", "context.summarize"
  ],
  "TechnologyProcessAndManufacturingAgent": [
    "search.tavily", "browser.playwright", "extract.tavily", "doc.pdf_text",
    "scholar.semantic_scholar", "fs.write", "fs.read", "context.summarize"
  ],
  "ClaimsExtractorAndTaxonomyMapperAgent": [
    "extract.tavily", "browser.playwright", "fs.write", "fs.read", "context.summarize"
  ],
  "CaseStudyHarvestAgent": [
    "search.exa", "search.tavily", "extract.tavily", "browser.playwright", "doc.pdf_text",
    "fs.write", "fs.read", "context.summarize"
  ],
  "ClinicalEvidenceTriageAgent": [
    "scholar.pubmed", "scholar.semantic_scholar", "registry.clinicaltrials",
    "search.tavily", "fs.write", "fs.read", "context.summarize"
  ],
  "ContraindicationsAndSafetyAgent": [
    "extract.tavily", "browser.playwright", "doc.pdf_text", "search.tavily",
    "fs.write", "fs.read", "context.summarize"
  ],
  "ProductReviewsAgent": [
    "search.exa", "search.tavily", "browser.playwright", "extract.tavily",
    "fs.write", "fs.read", "context.summarize"
  ],
  "KnowledgeSynthesizerAgent": [
    "fs.read", "fs.write", "context.summarize"
  ],
  "ClaimConfidenceScorerAgent": [
    "fs.read", "fs.write", "context.summarize"
  ],
  "NarrativeAnalystAgent": [
    "fs.read", "fs.write", "context.summarize"
  ],
  "ResearchRouterAgent": [
    "fs.read", "fs.write"
  ],
}
