# -----------------------------------------------------------------------------
# ✅ Quick-test variable: ResearchMissionPlanFinal-compatible payload
# Paste this into a test module and do:
#   plan = ResearchMissionPlanFinal.model_validate(MISSION_PLAN_JSON)
# -----------------------------------------------------------------------------
from research_agent.human_upgrade.structured_outputs.research_plans_outputs import ResearchMissionPlanFinal 
MISSION_PLAN_JSON: dict = {
  "mission_id": "mission_onethousandroads_001",
  "stage_mode": "full_entities_basic",
  "target_businesses": [
    "One Thousand Roads"
  ],
  "target_people": [
    "Brad Pitzele"
  ],
  "target_products": [
    "10 LPM EWOT System (NextGen Mask)",
    "2000-series EWOT System",
    "Add-on 10 LPM Concentrator",
    "EWOT Reservoir with Mask (High Flow)",
    "CatalystMax Red Light Therapy Panel"
  ],
  "mission_objectives": [
    {
      "objective": "Establish authoritative entity identity and leadership",
      "sub_objectives": [
        "Compile canonical business biography and public-facing pages",
        "Identify leadership and primary personnel with roles and affiliations",
        "Map organizational structure and operating posture"
      ],
      "success_criteria": [
        "EntityBiography produced with canonical name, domains, and key pages",
        "At least one corroborated profile for founder/leader (Brad Pitzele)",
        "OperatingPostureSummary describing product focus and positioning"
      ]
    },
    {
      "objective": "Extract complete product specifications for cataloged products",
      "sub_objectives": [
        "Collect ingredient/material, dosage/flow, usage, warnings, and pricing",
        "Run conditional Playwright workflows only for product pages missing required fields",
        "Produce normalized product spec records for downstream evidence triage"
      ],
      "success_criteria": [
        "ProductSpecs produced for each product slice with required-fields completeness check",
        "Playwright requests documented and bounded to products that failed static extraction",
        "All product records include source pointers (to be filled during evidence discovery)"
      ]
    },
    {
      "objective": "Harvest and label basic evidence artifacts relevant to claims and safety",
      "sub_objectives": [
        "Search for company-provided case studies, whitepapers, and manuals",
        "Collect independent studies or trials that reference products or mechanisms",
        "Organize evidence with affiliation labeling for provenance"
      ],
      "success_criteria": [
        "EvidenceArtifacts produced including company-controlled and independent sources",
        "At least one labeled evidence item per product if available",
        "Evidence prioritized by relevance to claims and safety"
      ]
    }
  ],
  "stages": [
    {
      "stage_id": "S1",
      "name": "Entity Biography, Identity & Ecosystem",
      "description": "Establish who this entity is, who leads it, and how it positions itself.",
      "sub_stages": [
        {
          "sub_stage_id": "S1.1",
          "name": "Organization Identity & Structure",
          "description": "Entity Biography & Organizational Overview",
          "agent_instances": [
            "BusinessIdentityAndLeadershipAgent:S1:S1.1:single"
          ],
          "can_run_in_parallel": True,
          "depends_on_substages": []
        },
        {
          "sub_stage_id": "S1.2",
          "name": "People & Roles",
          "description": "People, Leadership & Expert Roles",
          "agent_instances": [
            "PersonBioAndAffiliationsAgent:S1:S1.2:people_01_of_01"
          ],
          "can_run_in_parallel": True,
          "depends_on_substages": []
        },
        {
          "sub_stage_id": "S1.3",
          "name": "Ecosystem Positioning",
          "description": "Ecosystem Positioning",
          "agent_instances": [
            "EcosystemMapperAgent:S1:S1.3:single"
          ],
          "can_run_in_parallel": True,
          "depends_on_substages": []
        }
      ],
      "depends_on_stages": []
    },
    {
      "stage_id": "S2",
      "name": "Product Specifications",
      "description": "Extract core product specifications and details.",
      "sub_stages": [
        {
          "sub_stage_id": "S2.1",
          "name": "Product Specs + Conditional Playwright Request (Batch)",
          "description": (
            "Given a provided product catalog (up to ~5 products), extract core product specs via static sources first; "
            "when required fields are missing, request a bounded Playwright workflow from an external tool and merge results."
          ),
          "agent_instances": [
            "ProductSpecAgent:S2:S2.1:products_01_of_01"
          ],
          "can_run_in_parallel": True,
          "depends_on_substages": []
        }
      ],
      "depends_on_stages": []
    },
    {
      "stage_id": "S3",
      "name": "Evidence Discovery",
      "description": "Harvest basic evidence artifacts.",
      "sub_stages": [
        {
          "sub_stage_id": "S3.1",
          "name": "Evidence Discovery",
          "description": "Evidence Discovery",
          "agent_instances": [
            "CaseStudyHarvestAgent:S3:S3.1:single"
          ],
          "can_run_in_parallel": True,
          "depends_on_substages": []
        }
      ],
      "depends_on_stages": []
    }
  ],
  "agent_instances": [
    {
      "instance_id": "BusinessIdentityAndLeadershipAgent:S1:S1.1:single",
      "agent_type": "BusinessIdentityAndLeadershipAgent",
      "stage_id": "S1",
      "sub_stage_id": "S1.1",
      "slice": None,
      "objectives": [
        {
          "objective": "Compile authoritative entity biography and corporate identity",
          "sub_objectives": [
            "Identify canonical domain(s) and official product/catalog pages",
            "Extract About/Founders content and corporate timeline",
            "Produce a high-level operating posture summary"
          ],
          "success_criteria": [
            "EntityBiography artifact with canonicalName, domains, and top official pages",
            "HighLevelTimeline covering founding and product launches (when available)",
            "OperatingPostureSummary describing product focus and market claims"
          ]
        }
      ],
      "starter_sources": [
        {
          "url": "https://www.onethousandroads.com/",
          "category": "official_home",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/pages/about-us",
          "category": "official_leadership",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/pages/shop",
          "category": "official_products",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/pages/ewot-research",
          "category": "official_research",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://help.onethousandroads.com/",
          "category": "official_help_center",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/pages/product-warranty",
          "category": "official_docs_manuals",
          "title": None,
          "notes": None,
          "language": "en"
        }
      ],
      "requires_artifacts": [
        "seed_business_name"
      ],
      "produces_artifacts": [
        "EntityBiography",
        "OperatingPostureSummary",
        "HighLevelTimeline",
        "ProductList"
      ],
      "notes": "Single instance to establish canonical company-level identity from official pages."
    },
    {
      "instance_id": "PersonBioAndAffiliationsAgent:S1:S1.2:people_01_of_01",
      "agent_type": "PersonBioAndAffiliationsAgent",
      "stage_id": "S1",
      "sub_stage_id": "S1.2",
      "slice": {
        "dimension": "people",
        "slice_id": "people_01_of_01",
        "rationale": (
          "Single identified leader (Brad Pitzele) fits within max_people_per_slice; "
          "per-person enrichment to capture roles and affiliations."
        ),
        "product_names": [],
        "person_names": [
          "Brad Pitzele"
        ],
        "source_urls": [],
        "notes": None
      },
      "objectives": [
        {
          "objective": "Enrich profiles for identified people and map affiliations",
          "sub_objectives": [
            "Collect role, title, LinkedIn/official profiles, and affiliation history",
            "Anchor credentials and prior relevant work",
            "Link people to company role responsibilities"
          ],
          "success_criteria": [
            "PeopleProfiles produced for Brad Pitzele with corroborated affiliation(s)",
            "RoleResponsibilityMap linking person to organizational functions",
            "CredentialAnchors with at least one corroborating source per major claim (to be filled during evidence discovery)"
          ]
        }
      ],
      "starter_sources": [
        {
          "url": "https://www.onethousandroads.com/pages/about-us",
          "category": "official_leadership",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/",
          "category": "official_home",
          "title": None,
          "notes": None,
          "language": "en"
        }
      ],
      "requires_artifacts": [
        "seed_person_names",
        "EntityBiography"
      ],
      "produces_artifacts": [
        "PeopleProfiles",
        "RoleResponsibilityMap",
        "CredentialAnchors"
      ],
      "notes": "Per-people slice to ensure targeted enrichment and avoid mixing multiple persons in one instance."
    },
    {
      "instance_id": "EcosystemMapperAgent:S1:S1.3:single",
      "agent_type": "EcosystemMapperAgent",
      "stage_id": "S1",
      "sub_stage_id": "S1.3",
      "slice": None,
      "objectives": [
        {
          "objective": "Map market and ecosystem positioning of the entity",
          "sub_objectives": [
            "Identify competitors, partners, and adjacent market categories",
            "Produce a partner/platform graph and competitor set",
            "Highlight unique positioning or claims relative to competitors"
          ],
          "success_criteria": [
            "CompetitorSet with 3-8 direct or near competitors identified",
            "PartnerAndPlatformGraph outlining any integrations or distribution channels",
            "MarketCategoryPlacement describing the company's market framing"
          ]
        }
      ],
      "starter_sources": [
        {
          "url": "https://www.onethousandroads.com/",
          "category": "official_home",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://ewot.com",
          "category": "other",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://liveo2.com",
          "category": "other",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://davincimedicalusa.com",
          "category": "other",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://optimalbreathing.com/pages/turbo-oxygen",
          "category": "other",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://laserclinical.com/product/maxxo2/",
          "category": "other",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.prnewswire.com/news-releases/aoti-secures-major-expansion-funding-from-leading-healthcare-financier-301510572.html",
          "category": "press_news",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://davincimedicalusa.com/pages/press",
          "category": "press_news",
          "title": None,
          "notes": None,
          "language": "en"
        }
      ],
      "requires_artifacts": [
        "EntityBiography",
        "ProductList"
      ],
      "produces_artifacts": [
        "CompetitorSet",
        "PartnerAndPlatformGraph",
        "MarketCategoryPlacement"
      ],
      "notes": "Single instance for ecosystem mapping using company pages and market signals."
    },
    {
      "instance_id": "ProductSpecAgent:S2:S2.1:products_01_of_01",
      "agent_type": "ProductSpecAgent",
      "stage_id": "S2",
      "sub_stage_id": "S2.1",
      "slice": {
        "dimension": "products",
        "slice_id": "products_01_of_01",
        "rationale": (
          "All five cataloged products fit within max_products_per_slice (<=5); "
          "batch extraction preferred with conditional Playwright for missing required fields."
        ),
        "product_names": [
          "10 LPM EWOT System (NextGen Mask)",
          "2000-series EWOT System",
          "Add-on 10 LPM Concentrator",
          "EWOT Reservoir with Mask (High Flow)",
          "CatalystMax Red Light Therapy Panel"
        ],
        "person_names": [],
        "source_urls": [],
        "notes": None
      },
      "objectives": [
        {
          "objective": "Extract detailed product specifications and required fields",
          "sub_objectives": [
            "Static extraction from official product pages for ingredients, dosages/flow rates, usage, warnings, and pricing",
            "Run bounded Playwright workflows only for product pages missing required-fields",
            "Normalize product spec records for downstream evidence triage"
          ],
          "success_criteria": [
            "ProductSpecs produced for each product in the slice with completeness flags",
            "Documented Playwright requests only for products that failed static extraction",
            "IngredientOrMaterialLists and UsageAndWarningSnippets populated where available"
          ]
        }
      ],
      "starter_sources": [
        {
          "url": "https://www.onethousandroads.com/products/10-lpm-ewot-system-nextgen-mask",
          "category": "official_product_detail",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/products/2000-series-ewot-system",
          "category": "official_product_detail",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/products/add-on-10lpm-concentrator",
          "category": "official_product_detail",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/products/ewot-reservoir-with-ewot-mask-high-flow",
          "category": "official_product_detail",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/products/catalystmax-red-light-therapy-panel",
          "category": "official_product_detail",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/pages/shop",
          "category": "official_products",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://help.onethousandroads.com/article/62-recommended-session-lengths-for-ewot-training",
          "category": "official_help_center",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/pages/ewot-product-warranty",
          "category": "official_docs_manuals",
          "title": None,
          "notes": None,
          "language": "en"
        }
      ],
      "requires_artifacts": [
        "product_names_list",
        "seed_product_pages"
      ],
      "produces_artifacts": [
        "ProductSpecs",
        "IngredientOrMaterialLists",
        "UsageAndWarningSnippets"
      ],
      "notes": "Batch instance covers the full provided product catalog; Playwright usage is conditional per product."
    },
    {
      "instance_id": "CaseStudyHarvestAgent:S3:S3.1:single",
      "agent_type": "CaseStudyHarvestAgent",
      "stage_id": "S3",
      "sub_stage_id": "S3.1",
      "slice": None,
      "objectives": [
        {
          "objective": "Harvest evidence artifacts relevant to product claims and safety",
          "sub_objectives": [
            "Collect company-controlled case studies, whitepapers, manuals, and product support docs",
            "Search for independent studies, trials, or third-party evaluations referencing products or mechanisms",
            "Label evidence artifacts with affiliation and relevance metadata"
          ],
          "success_criteria": [
            "EvidenceArtifacts produced and associated with corresponding products or claims",
            "Affiliation labeling differentiating company-provided vs independent evidence",
            "At least one evidence artifact linked to each product where available"
          ]
        }
      ],
      "starter_sources": [
        {
          "url": "https://www.onethousandroads.com/pages/ewot-research",
          "category": "official_research",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.onethousandroads.com/pages/ewot-product-warranty",
          "category": "official_docs_manuals",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://help.onethousandroads.com/article/62-recommended-session-lengths-for-ewot-training",
          "category": "official_help_center",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://pubmed.ncbi.nlm.nih.gov/32329780/",
          "category": "scholarly",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://pubmed.ncbi.nlm.nih.gov/31616520/",
          "category": "scholarly",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://pubmed.ncbi.nlm.nih.gov/16015135/",
          "category": "scholarly",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://liveo2.com/science/",
          "category": "official_research",
          "title": None,
          "notes": None,
          "language": "en"
        },
        {
          "url": "https://www.prnewswire.com/news-releases/topical-oxygen-therapy-awarded-positive-treatment-recommendation-by-the-international-working-group-on-the-diabetic-foot-in-their-2023-diabetic-foot-ulcer-guidelines-301824538.html",
          "category": "press_news",
          "title": None,
          "notes": None,
          "language": "en"
        }
      ],
      "requires_artifacts": [
        "EntityBiography",
        "ProductSpecs"
      ],
      "produces_artifacts": [
        "EvidenceArtifacts"
      ],
      "notes": "Single instance to gather initial evidence; further triage may spawn specialized clinical or claims agents in later stages."
    }
  ],
  "notes": (
    "Initial research plan follows full_entities_basic blueprint. People and product slices strictly applied per inputs; "
    "no starter sources included."
  )
}


if __name__ == "__main__":
    plan = ResearchMissionPlanFinal.model_validate(MISSION_PLAN_JSON)
    print(plan) 