# DomainCatalog Enhancements for Agent Source Curation

## Overview

Enhanced the `DomainCatalog` structure to better support source curation for sub-agent instances in the `full_entities_standard` research workflow. The changes add granular URL categories that map directly to agent `source_focus` requirements.

## Changes Made

### 1. New URL Categories Added

#### Identity & Core Pages
- **`homepageUrls`**: Official homepage/root URLs (1-2 URLs typically)
  - Maps to: `"official_home/about/blog/press"` (BusinessIdentityAndLeadershipAgent)

- **`aboutUrls`**: About/company/mission/who-we-are pages (distinct from leadership/team)
  - Maps to: `"official_home/about/blog/press"` (BusinessIdentityAndLeadershipAgent)

- **`blogUrls`**: Blog/news/article pages hosted on official domain
  - Maps to: `"official_home/about/blog/press"` (BusinessIdentityAndLeadershipAgent)

#### Products & Marketing
- **`landingPageUrls`**: Marketing/promotional/campaign pages
  - Maps to: `"product pages + landing pages"` (ClaimsExtractorAndTaxonomyMapperAgent)

#### Evidence & Research
- **`researchUrls`**: Official research/platform/science/technology pages (explanatory/mechanism pages)
  - Maps to: `"official_research/platform pages"` (TechnologyProcessAndManufacturingAgent)
  - **Note**: Separated from `caseStudyUrls` for clarity

- **`testimonialUrls`**: First-party testimonials/customer stories (anecdotal)
  - Maps to: `"first-party testimonials"` (ProductReviewsAgent)
  - **Note**: Separated from `caseStudyUrls` to distinguish anecdotal from evidence

- **`patentUrls`**: Patent references, proprietary process disclosures
  - Maps to: `"patents/whitepapers"` (TechnologyProcessAndManufacturingAgent)

#### Support & Documentation
- **`labelUrls`**: Product labels, ingredient lists, supplement facts, nutrition labels
  - Maps to: `"labels"` (ProductSpecAgent, ContraindicationsAndSafetyAgent)

#### Policies & Legal
- **`regulatoryUrls`**: Regulatory compliance/safety warnings (if hosted on official domain)
  - Maps to: `"regulatory signals"` (CredibilitySignalScannerAgent, ContraindicationsAndSafetyAgent)

### 2. Updated Existing Categories

- **`caseStudyUrls`**: Clarified to focus on company-controlled evidence (case studies, outcomes, whitepapers)
  - No longer includes testimonials or research/mechanism pages

- **`platformUrls`**: Marked as legacy bucket, prefer specific buckets when possible

## Agent Source Mapping

### Stage 1: Entity Biography, Identity & Ecosystem

| Agent Type | Source Focus | DomainCatalog Categories |
|------------|--------------|--------------------------|
| BusinessIdentityAndLeadershipAgent | `official_home/about/blog/press` | `homepageUrls`, `aboutUrls`, `blogUrls`, `pressUrls` |
| PersonBioAndAffiliationsAgent | `official_leadership + scholarly/pub profiles` | `leadershipUrls` |
| EcosystemMapperAgent | `press_news + official_platform/about` | `pressUrls`, `aboutUrls`, `platformUrls` |
| CredibilitySignalScannerAgent | `press_news + regulatory signals` | `pressUrls`, `regulatoryUrls` |

### Stage 2: Products, Specifications, Technology & Claims

| Agent Type | Source Focus | DomainCatalog Categories |
|------------|--------------|--------------------------|
| ProductCatalogerAgent | `official_products + navigation hubs + product index pages` | `productIndexUrls`, `productPageUrls` |
| ProductSpecAgent | `official_product_detail + official_docs_manuals + help snippets` | `productPageUrls`, `documentationUrls`, `labelUrls`, `helpCenterUrls` |
| TechnologyProcessAndManufacturingAgent | `official_research/platform pages + patents/whitepapers` | `researchUrls`, `patentUrls`, `platformUrls` |
| ClaimsExtractorAndTaxonomyMapperAgent | `product pages + landing pages + help_center + labels` | `productPageUrls`, `landingPageUrls`, `helpCenterUrls`, `labelUrls` |
| ProductReviewsAgent | `marketplace_reviews + first-party testimonials` | `testimonialUrls` (external reviews via tools) |

### Stage 3: Evidence & Validation Snapshot

| Agent Type | Source Focus | DomainCatalog Categories |
|------------|--------------|--------------------------|
| CaseStudyHarvestAgent | `company-controlled evidence + independent studies` | `caseStudyUrls`, `testimonialUrls` (company-controlled) |
| EvidenceClassifierAgent | `evidence artifacts from discovery` | Uses outputs from CaseStudyHarvestAgent |
| StrengthAndGapAssessorAgent | `classified evidence + claims ledger` | Uses outputs from EvidenceClassifierAgent |
| ContraindicationsAndSafetyAgent | `help/labels/manuals + regulatory signals` | `helpCenterUrls`, `labelUrls`, `documentationUrls`, `regulatoryUrls` |

## Helper Functions Updated

### `_select_business_people_urls()`
Now includes: `homepageUrls`, `aboutUrls`, `blogUrls`, `regulatoryUrls` in addition to existing categories.

### `_select_products_compounds_urls()`
Now includes: `landingPageUrls`, `labelUrls`, `researchUrls`, `patentUrls` in addition to existing categories.

### `_select_evidence_urls()` (NEW)
New helper function for Stage 3 evidence-related agents:
- `caseStudyUrls`
- `testimonialUrls`
- `researchUrls`
- `patentUrls`
- `documentationUrls`
- `labelUrls`
- `helpCenterUrls`
- `regulatoryUrls`

## Prompt Updates

Updated `PROMPT_NODE_B_DOMAIN_CATALOGS` to include:
- Detailed instructions for each new category
- Clear distinctions between similar categories (e.g., `researchUrls` vs `caseStudyUrls`)
- Guidance on when to use each bucket

## Benefits

1. **Precise Source Mapping**: Each agent type can now receive exactly the URLs it needs based on its `source_focus` requirements
2. **Better Separation of Concerns**: Clear distinction between evidence (case studies) vs explanatory (research pages) vs anecdotal (testimonials)
3. **Improved Source Curation**: Sub-optimal source curation step can now reliably match DomainCatalog categories to agent requirements
4. **Backward Compatible**: Existing code continues to work; new categories are additive

## Next Steps

1. Update source curation logic to use these new categories when matching agent `source_requirements`
2. Test with real domain catalogs to ensure proper categorization
3. Consider adding metadata to URLs (e.g., `evidenceKind` tag for case studies vs testimonials) if needed
