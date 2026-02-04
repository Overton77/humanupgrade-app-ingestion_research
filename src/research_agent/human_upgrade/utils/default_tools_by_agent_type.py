DEFAULT_TOOLS_BY_AGENT_TYPE = {
  "BusinessIdentityAndLeadershipAgent": [
    "tavily.search", "tavily.extract", "playwright.specs", "fs.write", "fs.read", "context.summarize"
  ],
  "PersonBioAndAffiliationsAgent": [
    "exa.search", "tavily.search", "playwright.specs", "semantic_scholar.search", "pubmed.literature_search",
    "fs.write", "fs.read", "context.summarize"
  ],
  "ProductCatalogerAgent": [
    "tavily.search", "tavily.extract", "playwright.specs", "fs.write", "fs.read", "context.summarize"
  ],
  "ProductSpecAgent": [
    "playwright.specs", "tavily.extract", "doc.pdf_text", "doc.pdf_screenshot_ocr",
    "fs.write", "fs.read", "context.summarize"
  ],
  "TechnologyProcessAndManufacturingAgent": [
    "tavily.search", "playwright.specs", "tavily.extract", "doc.pdf_text",
    "semantic_scholar.search", "fs.write", "fs.read", "context.summarize"
  ],
  "ClaimsExtractorAndTaxonomyMapperAgent": [
    "tavily.extract", "playwright.specs", "fs.write", "fs.read", "context.summarize"
  ],
  "CaseStudyHarvestAgent": [
    "exa.search", "tavily.search", "tavily.extract", "playwright.specs", "doc.pdf_text",
    "fs.write", "fs.read", "context.summarize"
  ],
  "ClinicalEvidenceTriageAgent": [
    "pubmed.literature_search", "semantic_scholar.search", "registry.clinicaltrials",
    "tavily.search", "fs.write", "fs.read", "context.summarize"
  ],
  "ContraindicationsAndSafetyAgent": [
    "tavily.extract", "playwright.specs", "doc.pdf_text", "tavily.search",
    "fs.write", "fs.read", "context.summarize"
  ],
  "ProductReviewsAgent": [
    "exa.search", "tavily.search", "playwright.specs", "tavily.extract",
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
