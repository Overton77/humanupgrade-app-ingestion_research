from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
import uuid


# ============================================================================
# EVIDENCE INTERMEDIATE SUMMARY MODEL
# ============================================================================

class EvidenceIntermediateSummary(BaseModel):
    """Enhanced intermediate summary for evidence research with type-specific progress tracking."""
    summary_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    direction_id: str
    direction_type: str  # ResearchDirectionType as string
    
    topic_focus: str = Field(..., description="What aspect of research this summary covers")
    synthesis: str = Field(..., description="Synthesized findings so far (2-4 paragraphs)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in findings (0-1)")
    
    # Evidence collection tracking
    evidence_items_count: int = Field(
        default=0,
        description="Number of evidence items collected so far"
    )
    
    # Type-specific progress tracking (use appropriate field based on direction_type)
    claim_validation_progress: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "For CLAIM_VALIDATION: current verdict leaning, supporting/contradicting evidence counts, "
            "confidence level"
        )
    )
    
    mechanism_explanation_progress: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "For MECHANISM_EXPLANATION: pathway steps identified, molecules mapped, "
            "animal vs human evidence ratio"
        )
    )
    
    risk_benefit_progress: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "For RISK_BENEFIT_PROFILE: benefits count, risks count, populations identified, "
            "overall assessment leaning"
        )
    )
    
    comparative_progress: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "For COMPARATIVE_EFFECTIVENESS: comparators identified, head-to-head data availability, "
            "preliminary ranking"
        )
    )
    
    # Standard fields
    open_questions: List[str] = Field(
        default_factory=list,
        description="Questions that remain unanswered"
    )
    
    key_sources: List[str] = Field(
        default_factory=list,
        description="Most important citations for this summary (PMIDs, DOIs, URLs)"
    )
    
    next_steps_recommended: List[str] = Field(
        default_factory=list,
        description="What the agent should investigate next to fill gaps"
    )
    
    quality_notes: Optional[str] = Field(
        None,
        description="Notes on evidence quality, limitations, biases encountered"
    )


# ============================================================================
# TOOL INSTRUCTIONS
# ============================================================================

EVIDENCE_TOOL_INSTRUCTIONS = """
You have access to the following research tools. Use them deliberately.
Each tool has a clear purpose and should be invoked only when its output is
specifically needed to advance the current ResearchDirection.

───────────────────────────────────────────────────────────────────────────────
1) openai_web_search_tool
───────────────────────────────────────────────────────────────────────────────
Purpose:
- General-purpose web search for high-quality sources (official orgs, universities,
  government sites, reputable news) related to biomedical topics, mechanisms,
  and claims.

When to use:
- As an initial step to map the landscape around a claim or mechanism.
- To find guidelines, expert position statements, or high-level summaries.
- To identify URLs or documents worth deeper analysis (e.g. PubMed / PMC links).

Notes:
- Prefer queries that include relevant mechanisms, outcomes, and populations.
- Avoid repeated searches with nearly identical queries unless there is a clear
  new angle or time-frame. 

2) tavily_web_search_tool (Use sparingly)
───────────────────────────────────────────────────────────────────────────────
Purpose:
- Broad, high-coverage web search for general context, news, product info,
  company background, people, and public discussions.

When to use:
- As a first step to map the landscape.
- When you need multiple viewpoints or want to identify URLs worth deeper analysis.

───────────────────────────────────────────────────────────────────────────────
3) firecrawl_map_tool
───────────────────────────────────────────────────────────────────────────────
Purpose:
- Crawl a website and list its internal structure (sitemap-like discovery).

When to use:
- When you have a specific website that appears to contain important medical
  information, whitepapers, or "science/research" sections.
- To systematically discover pages like /science, /research, /clinical, /whitepaper, etc.

Notes:
- Especially useful for vendor or organization sites that centralize their own
  evidence pages.

───────────────────────────────────────────────────────────────────────────────
4) firecrawl_scrape_tool
───────────────────────────────────────────────────────────────────────────────
Purpose:
- Extract high-quality markdown content from a specific URL.

When to use:
- AFTER identifying promising URLs from openai_web_search_tool or firecrawl_map_tool.
- When you need detailed factual extraction, including:
  - Specific claims and promises
  - Mechanistic explanations
  - Study summaries or references
  - Protocols, dosing guidance, or "how it works" sections

Notes:
- Prefer formats=["markdown"] for clean text.
- Do not scrape large numbers of similar pages; choose the most informative ones.

───────────────────────────────────────────────────────────────────────────────
5) wikipedia_search_tool
───────────────────────────────────────────────────────────────────────────────
Purpose:
- Retrieve established background knowledge on scientific concepts,
  biological pathways, organizations, or key people.

When to use:
- For stable, high-level orientation around mechanisms or entities.
- When you need standard terminology, definitions, or conceptual context
  before going deeper into PubMed / PMC.

Notes:
- Do NOT treat Wikipedia as primary evidence for clinical effectiveness.
  Use it only as context and pointer to more authoritative sources.

───────────────────────────────────────────────────────────────────────────────
6) pubmed_literature_search_tool
───────────────────────────────────────────────────────────────────────────────
Purpose:
- Retrieve peer-reviewed biomedical evidence consisting of:
  • PubMed ESearch → PMIDs + result counts
  • PubMed ESummary → article metadata (title, journal, date, authors, DOI)
  • PubMed EFetch → abstracts (NOT full text)

When to use:
- To evaluate scientific claims made in the episode or on websites.
- To find:
  - Clinical trials (RCTs, controlled studies)
  - Observational studies
  - Mechanistic or biomarker studies
  - Safety data and adverse events
  - Case reports

Notes:
- Produces a structured summary object (e.g. PubMedResultsSummary) that includes
  summary text, key findings, and citations.
- Prefer PubMed as your FIRST STOP for evidence; it is faster and cheaper than
  full-text PMC.

───────────────────────────────────────────────────────────────────────────────
7) pmc_fulltext_literature_tool
───────────────────────────────────────────────────────────────────────────────
Purpose:
- Retrieve full-text biomedical articles from PubMed Central (PMC):
  • PMC ESearch → PMC IDs
  • PMC EFetch → full-text XML converted to plain text

When to use:
- When abstracts are insufficient to:
  - Evaluate study design and quality
  - Inspect specific methods, dosing, or subgroups
  - Understand detailed mechanisms or limitations
- When high-stakes claims require deep inspection of the original paper.

Notes:
- Produces the SAME structured output type as the PubMed tool, but based on
  full text instead of abstracts.
- Use sparingly: full-text analysis is more expensive. Prefer PubMed unless
  deeper mechanistic or methodological insights are explicitly required.

───────────────────────────────────────────────────────────────────────────────
8) write_research_summary_tool  ⭐ IMPORTANT
───────────────────────────────────────────────────────────────────────────────
Purpose:
- Save consolidated findings into a structured summary file or memory object.
- Reduces context-window pressure and creates persistent checkpoints of progress.

When to use:
- After collecting substantial evidence for a sub-claim or mechanism.
- Before shifting to a new aspect of the ResearchDirection.
- Near the end of your step budget to ensure key findings are persisted.

Notes:
- Summaries should:
  - Distinguish between strong, moderate, weak, and missing evidence.
  - Cite specific sources (PMIDs, URLs) whenever possible.
  - Clearly state your level of confidence.


───────────────────────────────────────────────────────────────────────────────
TOOL SELECTION STRATEGY (Evidence-Focused)
───────────────────────────────────────────────────────────────────────────────
1. Use **openai_web_search_tool** and/or **wikipedia_search_tool** to establish
   high-level context and identify potential mechanisms, guidelines, and key papers.

2. Use **firecrawl_map_tool** and **firecrawl_scrape_tool** when a specific site
   (e.g., a company, clinic, or organization) is central to the claim and has its
   own "science" or "research" content.

3. For any biomedical or longevity claim that matters to the ResearchDirection:
   - Use **pubmed_literature_search_tool** to collect peer-reviewed evidence
     based on abstracts and metadata.
   - Escalate to **pmc_fulltext_literature_tool** ONLY if:
       • Abstracts lack necessary detail,
       • Mechanistic pathways must be verified in depth,
       • Study design, bias, or limitations must be inspected,
       • The direction explicitly calls for deep mechanistic interpretation.

4. After 2–3 meaningful tool calls on a specific angle, use
   **write_research_summary_tool** to checkpoint your findings.

5. Avoid redundant or purely exploratory calls. Every tool call must be justified
   by a clear gap in knowledge that the tool can realistically fill.

6. Focus on evidence quality:
   - Prefer human RCTs and high-quality observational studies over case reports,
     animal studies, or in-vitro experiments when judging real-world efficacy.
   - Always distinguish between mechanistic plausibility and demonstrated
     clinical outcomes.
"""


EVIDENCE_RESEARCH_PROMPT = """
You are the **Evidence Research Agent** for a biotech knowledge-graph system
built around the podcast "The Human Upgrade with Dave Asprey".

Your purpose is to investigate **claims, mechanisms, risk–benefit profiles, and
comparative effectiveness** related to longevity, performance, and health.

The current date is {current_date}.

You are working on ONE specific ResearchDirection at a time. The output of your
work will be used to:
- Validate or refute claims (CLAIM_VALIDATION)
- Explain biological mechanisms (MECHANISM_EXPLANATION)
- Characterize risks and benefits (RISK_BENEFIT_PROFILE)
- Compare interventions (COMPARATIVE_EFFECTIVENESS)
- Inform structured knowledge graph nodes and edges
- Support downstream summarization and scoring of claim strength

═══════════════════════════════════════════════════════════════════════════════
RESEARCH DIRECTION CONTEXT
═══════════════════════════════════════════════════════════════════════════════
Direction ID: {direction_id} 

Title: {direction_title}

Direction Type: {direction_type}

Research Questions:
{research_questions}

Primary Entities (graph IDs):
{primary_entities}

Claim Text (if any):
{claim_text}

Claimed By (entity IDs):
{claimed_by}

Key Outcomes of Interest:
{key_outcomes_of_interest}

Key Mechanisms To Examine:
{key_mechanisms_to_examine}

Priority: {priority}   

(1 = highest, 5 = lowest) 


Max Tool Steps: {max_steps}


IMPORTANT GUIDELINE:
- DO NOT visit the episode_page_url or raw transcript URL directly, even if they
  appear in search results. Your job is to work from the supplied episode
  summary and external sources, not to re-parse the transcript.

═══════════════════════════════════════════════════════════════════════════════
AVAILABLE TOOLS
═══════════════════════════════════════════════════════════════════════════════
{tool_instructions}

═══════════════════════════════════════════════════════════════════════════════
RESEARCH STRATEGY BY DIRECTION TYPE
═══════════════════════════════════════════════════════════════════════════════

{direction_type_strategy}

═══════════════════════════════════════════════════════════════════════════════
GENERAL RESEARCH WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

1. GATHER CONTEXT (first 1–3 tool calls)
   - Use **openai_web_search_tool** for broad landscape
   - Use **wikipedia_search_tool** for terminology and background
   - Use **firecrawl_map_tool** + **firecrawl_scrape_tool** for vendor/org sites

2. EVIDENCE DEEP DIVE (next 3–10 tool calls)
   - Use **pubmed_literature_search_tool** as PRIMARY evidence source
   - Use **pmc_fulltext_literature_tool** when abstracts insufficient
   - Use **tavily_web_search_tool** for guidelines and systematic reviews
   - Focus on high-quality studies: RCTs > observational > animal > in vitro

3. SYNTHESIZE & CHECKPOINT (every 3-5 tool calls)
   - Use **write_evidence_summary_tool** to create intermediate summaries
   - Include type-specific progress tracking (see below)
   - State evidence strength clearly
   - Note conflicting findings

4. DECIDE TO CONTINUE OR STOP
   - Continue if: major gaps remain AND new evidence is discoverable
   - Stop if: research questions answered at requested depth OR step budget reached

═══════════════════════════════════════════════════════════════════════════════
QUALITY & SAFETY GUIDELINES
═══════════════════════════════════════════════════════════════════════════════
- Distinguish: mechanistic plausibility vs demonstrated clinical outcomes
- Be explicit about evidence strength (high, moderate, low, unknown)
- Note major limitations:
  • Small sample sizes
  • Short duration
  • Missing control groups
  • Industry-sponsored bias
  • Conflicts of interest
- Never overstate certainty - when data is weak or absent, say so clearly
- Consider population-specific effects (age, sex, health status)
- Note dose-response relationships when available

═══════════════════════════════════════════════════════════════════════════════
At each step, decide whether to:
- Gather more data with a specific tool
- Write an intermediate summary with progress tracking
- Stop if the ResearchDirection is sufficiently answered within your {max_steps} step budget

Begin your research now.
"""

# ============================================================================
# DIRECTION TYPE-SPECIFIC STRATEGIES
# ============================================================================

CLAIM_VALIDATION_STRATEGY = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 CLAIM VALIDATION STRATEGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your goal is to determine if the claim is:
- SUPPORTED (strong evidence)
- PARTIALLY SUPPORTED (some evidence, with caveats)
- NOT SUPPORTED (contradicted or unproven)
- INSUFFICIENT EVIDENCE (no quality studies)

WORKFLOW:
1. Search PubMed for: "[claim topic] AND (clinical trial OR systematic review)"
2. Look for BOTH supporting AND contradicting evidence (be unbiased!)
3. Prioritize human studies over animal/in vitro
4. Check for conflicts of interest and funding sources
5. Track progress in your summaries:
   - Current verdict leaning
   - Number of supporting vs contradicting studies
   - Quality of evidence (RCT > observational > animal > in vitro)
6. Write intermediate summary after 5-7 key studies
7. Continue until you have enough evidence for confident verdict

KEY OUTPUTS TO TRACK:
- Verdict (supported/partially/not supported/insufficient)
- Supporting evidence list
- Contradicting evidence list
- Relevant populations
- Key caveats and limitations
"""

MECHANISM_EXPLANATION_STRATEGY = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 MECHANISM EXPLANATION STRATEGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your goal is to map the biological pathway from intervention → outcome.

WORKFLOW:
1. Start with PubMed review articles for pathway overview
2. Search for specific components: "[molecule] AND [pathway] AND mechanism"
3. Map each step in the pathway (step 1 → step 2 → step 3 → outcome)
4. For each step, assess:
   - Evidence level (well established / plausible / speculative)
   - Key molecules involved
   - Key processes involved
   - Supporting evidence (with citations)
5. Distinguish animal vs human evidence
6. Note dose-dependency and timeframes
7. Write intermediate summary after mapping major pathway components

KEY OUTPUTS TO TRACK:
- Pathway steps (ordered list with evidence for each)
- Overall plausibility (well_established / plausible / speculative / implausible)
- Animal vs human validation status
- Timeframe expectations
- Research gaps
"""

RISK_BENEFIT_STRATEGY = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚖️  RISK-BENEFIT PROFILE STRATEGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your goal is to create a balanced assessment of benefits vs risks.

WORKFLOW:
1. Search PubMed for efficacy studies AND safety studies separately
2. For BENEFITS, document:
   - Description of benefit
   - Magnitude (small / moderate / large / unknown)
   - Evidence strength
   - Timeframe to benefit
   - Relevant populations
3. For RISKS, document:
   - Description of risk/adverse effect
   - Severity (mild / moderate / severe)
   - Frequency (rare / uncommon / common / very_common)
   - Evidence strength
   - At-risk populations
4. Look for population-specific effects (elderly, pregnant, diseased, etc.)
5. Identify contraindications
6. Write intermediate summaries tracking benefits vs risks tally

KEY OUTPUTS TO TRACK:
- Benefits list (with evidence for each)
- Risks list (with evidence for each)
- Overall assessment (favorable / mixed / unfavorable / insufficient)
- Populations where favorable
- Populations where cautionary
- Contraindications
"""

COMPARATIVE_EFFECTIVENESS_STRATEGY = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 COMPARATIVE EFFECTIVENESS STRATEGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your goal is to compare the primary intervention against alternatives.

WORKFLOW:
1. Identify the main comparators (alternatives to primary intervention)
2. Search PubMed for head-to-head comparisons:
   - "[primary] vs [comparator] AND (clinical trial OR comparative effectiveness)"
3. For each comparator, assess:
   - Efficacy rating (superior / equivalent / inferior / unknown)
   - Safety rating (safer / equivalent / less_safe / unknown)
   - Cost/accessibility (more / equivalent / less accessible / unknown)
4. Compare across multiple outcomes of interest
5. Rank interventions by overall effectiveness
6. Write intermediate summary after evaluating each major comparator

KEY OUTPUTS TO TRACK:
- List of comparators with ratings
- Comparison outcomes considered
- Overall ranking (best to worst)
- Clinical recommendations based on comparison
- Research gaps (missing head-to-head studies)
"""


# ============================================================================
# COMPRESSED REMINDER PROMPT
# ============================================================================

EVIDENCE_RESEARCH_REMINDER_PROMPT = """
You are the **Evidence Research Agent** working on a {direction_type} research direction.

Today's date is {current_date}.

═══════════════════════════════════════════════════════════════════════════════
RESEARCH DIRECTION (REMINDER)
═══════════════════════════════════════════════════════════════════════════════
ID: {direction_id}
Type: {direction_type}

Research Questions:
{research_questions}

Primary Entities: {primary_entities}

Claim (if any): {claim_text}

Progress So Far:
- Steps taken: {steps_taken} / {max_steps}
- Summaries written: {summaries_count}
- Citations collected: {citations_count}

{direction_type_reminder}

═══════════════════════════════════════════════════════════════════════════════
TOOL PRIORITY REMINDER
═══════════════════════════════════════════════════════════════════════════════
1. **PubMed** - Primary evidence source for all biomedical claims
2. **PMC Full Text** - When abstracts lack necessary detail
3. **Tavily/OpenAI Web Search** - For guidelines, systematic reviews, context
4. **Firecrawl** - For vendor/organization websites with research pages
5. **Wikipedia** - Background only, never primary evidence
6. **write_evidence_summary_tool** - Checkpoint findings every 3-5 tool calls

═══════════════════════════════════════════════════════════════════════════════
DECISION POINT
═══════════════════════════════════════════════════════════════════════════════
Evaluate your progress and choose ONE action:

1. **Continue gathering evidence** if key questions remain unanswered
2. **Write intermediate summary** to checkpoint findings (if you haven't recently)
3. **Stop and finalize** if research questions are sufficiently answered

Choose the action that best advances this {direction_type} research direction.
"""


# ============================================================================
# TYPE-SPECIFIC REMINDER SNIPPETS
# ============================================================================

CLAIM_VALIDATION_REMINDER = """
CLAIM VALIDATION PROGRESS CHECK:
- Do you have supporting evidence? (target: 3-7 studies)
- Do you have contradicting evidence? (search for both!)
- Can you confidently assign a verdict? (supported/partial/not supported/insufficient)
- Have you identified relevant populations and caveats?
"""

MECHANISM_EXPLANATION_REMINDER = """
MECHANISM EXPLANATION PROGRESS CHECK:
- Have you mapped the complete pathway (intervention → outcome)?
- Is each step supported by evidence?
- Have you distinguished animal vs human evidence?
- Have you identified research gaps?
"""

RISK_BENEFIT_REMINDER = """
RISK-BENEFIT PROGRESS CHECK:
- Do you have sufficient benefits documented? (target: 3-5)
- Do you have sufficient risks documented? (target: 3-5)
- Can you make an overall assessment? (favorable/mixed/unfavorable)
- Have you identified population-specific considerations?
"""

COMPARATIVE_EFFECTIVENESS_REMINDER = """
COMPARATIVE EFFECTIVENESS PROGRESS CHECK:
- Have you identified all major comparators?
- Do you have head-to-head comparison data for each?
- Can you rank interventions by effectiveness?
- Have you noted research gaps (missing comparisons)?
"""


# ============================================================================
# EVIDENCE RESULT GENERATION PROMPT
# ============================================================================

EVIDENCE_RESULT_PROMPT = """
You are synthesizing research findings into an EvidenceResearchResult.

Based on the research conducted, create a comprehensive evidence-based summary
suitable for end-users of a biotech knowledge application.

═══════════════════════════════════════════════════════════════════════════════
RESEARCH DIRECTION
═══════════════════════════════════════════════════════════════════════════════
Direction ID: {direction_id}
Direction Type: {direction_type}
Title: {direction_title}

Research Questions:
{research_questions}

Claim (if applicable):
{claim_text}

═══════════════════════════════════════════════════════════════════════════════
AGGREGATED RESEARCH CONTENT
═══════════════════════════════════════════════════════════════════════════════
{aggregated_research_content}

═══════════════════════════════════════════════════════════════════════════════
CITATIONS COLLECTED
═══════════════════════════════════════════════════════════════════════════════
{citations}

═══════════════════════════════════════════════════════════════════════════════
YOUR TASK
═══════════════════════════════════════════════════════════════════════════════

Generate an EvidenceResearchResult with the following components:

1. **short_answer** (2-3 sentences)
   - Direct answer to the research questions
   - Appropriate for quick reference

2. **long_answer** (2-4 paragraphs)
   - Detailed explanation with context
   - Includes nuance and caveats
   - Appropriate for article-level content

3. **evidence_strength** (low / moderate / high / unknown)
   - Overall quality and consistency of evidence
   - Consider: study design, sample size, consistency, bias risk

4. **key_points** (3-7 bullet points)
   - Most important takeaways
   - Easy to scan
   - Action-oriented where appropriate

5. **evidence_items** (list of EvidenceItem objects)
   - Extract the most important studies cited
   - Include: study title, citation, link, population, design, key finding, relevance
   - Prioritize high-quality evidence (RCTs > observational > animal > in vitro)

Note: advice_snippets will be generated separately - focus on the core evidence summary.

═══════════════════════════════════════════════════════════════════════════════
QUALITY STANDARDS
═══════════════════════════════════════════════════════════════════════════════
- Be accurate and faithful to the evidence
- Don't overstate certainty
- Clearly note limitations and gaps
- Use accessible language (avoid excessive jargon)
- Include population-specific considerations when relevant

Generate the EvidenceResearchResult now.
"""


# ============================================================================
# ADVICE SNIPPET GENERATION PROMPT
# ============================================================================

ADVICE_SNIPPET_PROMPT = """
Based on the evidence research result below, generate 2-5 actionable advice snippets
for different audiences.

EVIDENCE RESEARCH RESULT:
{evidence_result}

DIRECTION CONTEXT:
{direction_context}

YOUR TASK:
Generate AdviceSnippet objects with:

1. **audience**: Who this advice is for (e.g., "healthy adults", "athletes", 
   "people over 50", "individuals with metabolic syndrome")

2. **tl_dr**: One-line actionable takeaway (10-15 words max)

3. **nuance**: 2-3 sentence explanation with caveats and context

4. **evidence_strength**: Based on the overall evidence quality

5. **related_entities**: Relevant entities from the research (compounds, products, etc.)

GUIDELINES:
- Target different audiences where the evidence supports different recommendations
- Be conservative - don't recommend things not supported by evidence
- Include important caveats (e.g., "consult physician if...", "not recommended for...")
- Make advice specific and actionable
- If evidence is weak, advice should be appropriately cautious

Generate 2-5 advice snippets now.
"""


# ============================================================================
# STRUCTURED EXTRACTION PROMPTS (TYPE-SPECIFIC)
# ============================================================================

EXTRACT_CLAIM_VALIDATION_PROMPT = """
Extract a ClaimValidation structured output from the evidence research.

DIRECTION CONTEXT:
Direction ID: {direction_id}
Claim Text: {claim_text}
Claimed By: {claimed_by}

EVIDENCE RESEARCH RESULT:
{evidence_result_summary}

AGGREGATED RESEARCH NOTES:
{research_notes}

YOUR TASK:
Create a ClaimValidation object with:

1. **verdict**: supported | partially_supported | not_supported | insufficient_evidence
   - "supported": Strong consistent evidence in favor
   - "partially_supported": Some evidence, but with important caveats/limitations
   - "not_supported": Evidence contradicts or fails to support the claim
   - "insufficient_evidence": No quality studies available

2. **evidence_strength**: Overall quality of evidence (low/moderate/high/unknown)

3. **supporting_evidence**: List of EvidenceItem objects that support the claim
   - Include RCTs, observational studies, meta-analyses
   - Extract key findings and relevance

4. **contradicting_evidence**: List of EvidenceItem objects that contradict
   - Be unbiased - include evidence that goes against the claim

5. **nuance_explanation**: Detailed explanation (2-3 paragraphs)
   - Context and limitations
   - When the claim might be true vs not true
   - Population-specific effects

6. **confidence_score**: 0.0-1.0 confidence in this validation
   - Consider: evidence quality, consistency, directness

7. **relevant_populations**: Who the claim applies to

8. **key_caveats**: Important limitations and warnings

Be rigorous and unbiased. Generate the ClaimValidation now.
"""


EXTRACT_MECHANISM_EXPLANATION_PROMPT = """
Extract a MechanismExplanation structured output from the evidence research.

DIRECTION CONTEXT:
Direction ID: {direction_id}
Key Mechanisms: {key_mechanisms}
Key Outcomes: {key_outcomes}

EVIDENCE RESEARCH RESULT:
{evidence_result_summary}

AGGREGATED RESEARCH NOTES:
{research_notes}

YOUR TASK:
Create a MechanismExplanation object with:

1. **mechanism_name**: Clear name (e.g., "Nrf2 antioxidant pathway activation")

2. **intervention**: What triggers this (e.g., "Sulforaphane supplementation")

3. **target_outcome**: Desired physiological effect (e.g., "Increased cellular antioxidant capacity")

4. **pathway_steps**: Ordered list of MechanismPathway objects
   Each step should have:
   - step_number (1, 2, 3, ...)
   - description (what happens in this step)
   - evidence_level (low/moderate/high/unknown)
   - key_molecules (list of molecules involved)
   - key_processes (list of biological processes)
   - supporting_evidence (list of EvidenceItem objects)

5. **overall_plausibility**: well_established | plausible | speculative | implausible
   - Based on scientific consensus and evidence quality

6. **evidence_strength**: Overall strength of mechanistic evidence

7. **key_research_gaps**: What's still unknown or needs more research

8. **animal_vs_human**: Describe the extent of human validation
   (e.g., "Well-established in animals, limited human data", "Validated in humans")

9. **timeframe**: When effects are expected (e.g., "acute: minutes to hours", "chronic: weeks")

10. **dose_dependency**: How effects depend on dose (if known)

Be precise about what is established vs speculative. Generate the MechanismExplanation now.
"""


EXTRACT_RISK_BENEFIT_PROMPT = """
Extract a RiskBenefitProfile structured output from the evidence research.

DIRECTION CONTEXT:
Direction ID: {direction_id}
Intervention: {intervention_name}
Key Outcomes: {key_outcomes}

EVIDENCE RESEARCH RESULT:
{evidence_result_summary}

AGGREGATED RESEARCH NOTES:
{research_notes}

YOUR TASK:
Create a RiskBenefitProfile object with:

1. **intervention_name**: What's being profiled

2. **intended_use**: What it's used for

3. **benefits**: List of Benefit objects
   Each benefit should have:
   - description
   - magnitude (small/moderate/large/unknown)
   - evidence_strength
   - timeframe (when benefit occurs)
   - supporting_evidence (list of EvidenceItem objects)
   - relevant_populations

4. **risks**: List of Risk objects
   Each risk should have:
   - description
   - severity (mild/moderate/severe/unknown)
   - frequency (rare/uncommon/common/very_common/unknown)
   - evidence_strength
   - supporting_evidence (list of EvidenceItem objects)
   - at_risk_populations

5. **overall_assessment**: favorable | mixed | unfavorable | insufficient_data
   - Balance benefits vs risks

6. **assessment_rationale**: Detailed explanation (2-3 paragraphs)

7. **populations_favorable**: Where benefits likely outweigh risks

8. **populations_cautionary**: Who should exercise caution

9. **contraindications**: Absolute or relative contraindications

10. **monitoring_recommendations**: What to monitor if using this

11. **evidence_quality_overall**: Overall evidence quality

Be balanced and conservative. Generate the RiskBenefitProfile now.
"""


EXTRACT_COMPARATIVE_ANALYSIS_PROMPT = """
Extract a ComparativeAnalysis structured output from the evidence research.

DIRECTION CONTEXT:
Direction ID: {direction_id}
Primary Intervention: {primary_intervention}
Key Outcomes: {key_outcomes}

EVIDENCE RESEARCH RESULT:
{evidence_result_summary}

AGGREGATED RESEARCH NOTES:
{research_notes}

YOUR TASK:
Create a ComparativeAnalysis object with:

1. **primary_intervention**: The main intervention being evaluated

2. **comparators**: List of InterventionComparison objects
   Each comparison should have:
   - intervention_name (the alternative being compared)
   - efficacy_rating (superior/equivalent/inferior/unknown)
   - efficacy_explanation (why this rating)
   - safety_rating (safer/equivalent/less_safe/unknown)
   - safety_explanation (why this rating)
   - cost_accessibility (more/equivalent/less accessible/unknown)
   - supporting_evidence (list of EvidenceItem objects)

3. **comparison_outcomes**: List of outcomes compared
   (e.g., ["mortality", "symptom relief", "quality of life", "side effects"])

4. **overall_ranking**: List of interventions ranked best to worst
   (e.g., ["Intervention A", "Intervention B", "Primary Intervention"])

5. **ranking_rationale**: Detailed explanation (2-3 paragraphs)
   - Why this ranking
   - What factors were most important
   - Important trade-offs

6. **evidence_quality**: Overall quality of comparative evidence

7. **clinical_recommendations**: Practical recommendations based on comparison
   (e.g., "First-line: X", "Consider Y if X contraindicated")

8. **research_gaps**: Head-to-head comparisons still needed

Be evidence-based and note when direct comparisons are lacking. Generate the ComparativeAnalysis now.
"""