"""
sub_agent_prompt_builders.py

Tidy prompt factory for FULL_ENTITIES_BASIC sub-agent instance types.

- Builds BOTH Initial and Reminder prompts per agent type.
- Injects current date/time (America/New_York) into every prompt.
- Includes compact, high-signal tool-usage guidance snippets (not full schemas).
- Reminder prompts are state-aware and include a stronger "NEXT" inflection-point instruction.
- Adds slice-specific snippet for PersonBioAndAffiliationsAgent and ProductSpecAgent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import  Callable, Dict, List,  Optional 
from zoneinfo import ZoneInfo


from research_agent.structured_outputs.research_plans_outputs import (
    AgentInstancePlanWithSources,
    AgentType,
)
from research_agent.utils.default_tools_by_agent_type import (
    FULL_ENTITIES_BASIC_DEFAULT_TOOL_MAP,
)
from research_agent.graphs.state.agent_instance_state import WorkerAgentState


# ---------------------------
# Constants: shared blocks
# ---------------------------

LOOP_CONTRACT = """
You are a specialized research sub-agent running inside a multi-agent LangGraph workflow (WorkerAgentState).
Your scope is narrow and explicit: fulfill ONLY your assigned objective + slice.

Starter sources are SEEDS, not the boundary of the search space.
You MUST expand beyond them if success criteria are not met.

Operating loop (repeat until success criteria are satisfied OR tool_budget is reached):
1) Call think_tool FIRST to set focus, targets (if any), open questions, and a 1–4 step plan.
   - Also update progress_ledger to mark outputs as in_progress.
2) Discover URLs:
   - tavily_map_research to discover internal pages on authoritative domains.
   - tavily_search_research to discover additional authoritative pages beyond starter sources.
3) Fill gaps with extraction:
   - tavily_extract_research on best URLs using query="MISSING_FIELDS: ..." (gap-driven extraction).
4) Checkpoint frequently (write to files, not to chat/state):
   - Write incremental checkpoint files after each meaningful sub-objective or discovery.
   - Keep messages short; store evidence + structured outputs in checkpoint files.
5) Re-plan briefly with think_tool when switching focus or after checkpointing.

Hard rules:
- Facts must be source-anchored; do not speculate.
- Keep state small: control-plane only. Evidence lives in files.
- Prefer ONE tool call → checkpoint → reassess (avoid long tool chains without checkpointing).
""".strip()


TOOL_SNIPPET_FILES = """
Checkpointing (workspace files):
- Use agent_checkpoint_write (preferred) or agent_write_file to checkpoint findings.
- Default location: checkpoints/
- Checkpoint triggers:
  (a) you discover canonical pages (About/Team/Press/Docs/Shop),
  (b) you complete a sub-objective,
  (c) you have >10 key facts or any key table/list.
- Keep checkpoint files small and structured; cite URLs in the file.
- If continuing work, use agent_read_file to avoid duplication and to extend existing checkpoints.
""".strip()

TOOL_SNIPPET_TAVILY_CORE = """
Tool use guidance (Tavily tools):
- tavily_search_research(query=..., max_results=3-6, search_depth="basic|advanced", topic="general|news", include_domains=[...], output_mode="summary|raw")
  - Use for discovery across the broader search space (starter_sources are seeds).
  - Prefer output_mode="summary" (citations), use "raw" when URLs/lists get lost.

- tavily_extract_research(urls=[...], query="MISSING_FIELDS: ...", chunks_per_source=2-4, extract_depth="basic|advanced", output_mode="summary|raw")
  - Always pass a gap-driven query listing missing fields.
  - Use advanced extract_depth for dense pages (manuals, long About pages).
""".strip()

TOOL_SNIPPET_TAVILY_MAP = """
Tool use guidance (Tavily Map):
- tavily_map_research(url=..., instructions="find about/team/press/docs/shop", max_depth=1-2)
  - Use on authoritative domains to discover internal pages.
  - Keep max_depth low; increase only if navigation is weak.
""".strip()

TOOL_SNIPPET_EXA = """
Tool use guidance (Exa):
- exa.search(...) for broad ecosystem discovery (competitors/partners/market category).
- exa.find_similar(url=...) to find adjacent/competing organizations from an official page.
Then use tavily.extract on the best URLs to capture structured evidence.
""".strip()

TOOL_SNIPPET_WIKI = """
Tool use guidance (Wiki):
- wiki.search for canonical names, dates, and cross-checking biographies.
Always corroborate critical details with an official or primary source when possible.
""".strip()

TOOL_SNIPPET_PRODUCT_ESCALATION = """
Product extraction escalation:
- Prefer tavily.extract on official product detail pages.
- Use tavily.crawl only when you need coverage across a section (e.g., /products) and extraction misses pages.
- Escalate to browser.playwright ONLY if required fields (ingredients/pricing/warnings) are blocked by JS, modals, or dynamic rendering.
When escalating, provide precise navigation instructions and what fields to capture.
""".strip()

INFLECTION_NEXT_BLOCK = """
NEXT (inflection point):
Choose ONE of the following, then do it:

A) If missing_fields is non-empty:
   - Make ONE strategic tool call that closes the biggest gap (prefer extract/map over more search),
   - Then checkpoint immediately.

B) If you just filled a meaningful gap:
   - Write a checkpoint file now (agent_checkpoint_write / agent_write_file),
   - Then call think_tool to update ledger + next_actions.

C) If you are stuck or looping:
   - Call think_tool with a revised plan + 1–2 new queries and/or a map instruction.

D) If success criteria are satisfied AND you have written the necessary checkpoint files:
   - Finish with a short completion message stating what files/artifacts you produced.
""".strip()

CHECKPOINT_TEMPLATES: Dict[str, str] = {
    "BusinessIdentityAndLeadershipAgent": """
# Checkpoint: Business Identity & Leadership

## Canonical Identity
- canonical_name:
- domains: []
- headquarters:
- founding_date:
- mission_summary:

## Leadership (source-anchored)
- name | title | source_url

## Operating Posture
- what_they_do:
- who_they_serve:
- positioning (clinical/consumer/research):

## High-Level Timeline
- date | event | source_url

## Sources (URLs)
- ...
""".strip(),

    "PersonBioAndAffiliationsAgent": """
# Checkpoint: People Bios & Affiliations

## People Profiles (source-anchored)
- name:
  - current_title:
  - company_role_context:
  - credentials (explicit only):
  - affiliations:
  - prior_roles:
  - sources: []

## Role/Responsibility Map
- role -> responsibilities (source_url)

## Open gaps / missing fields
- ...
""".strip(),

    "EcosystemMapperAgent": """
# Checkpoint: Ecosystem Map

## Competitors / Substitutes (3–8)
- org | why similar | source_url

## Partners / Platforms
- org | relationship type | evidence source_url

## Market Category Placement
- label | justification | source_url

## Sources (URLs)
- ...
""".strip(),

    "ProductSpecAgent": """
# Checkpoint: Product Specs

## Product (variant-aware)
- product_name:
- variants: []
- price: (currency, cadence, size)
- ingredients/materials:
- dosage/amounts:
- usage directions:
- warnings/contraindications:
- package size / servings:

## Sources (URLs)
- ...
""".strip(),

    "CaseStudyHarvestAgent": """
# Checkpoint: Evidence Artifacts

## Artifacts (each must be source-anchored)
- title:
  - year/date:
  - type:
  - authors/institution:
  - affiliation_label: (company-controlled | independent | academic/registry)
  - supports (product/claim/tech):
  - urls: []

## Sources (URLs)
- ...
""".strip(),
}

# ---------------------------
# Agent metadata (for prompt assembly)
# ---------------------------

@dataclass(frozen=True)
class AgentPromptProfile:
    name: str
    role: str
    outputs: str
    source_focus: str
    tool_snippets: List[str]
    initial_focus_block: str
    reminder_focus_line: str
    # For agents that benefit from slice-specific coaching
    include_slice_hint: bool = False
    slice_hint_label: Optional[str] = None


AGENT_PROFILES: Dict[str, AgentPromptProfile] = {
    "BusinessIdentityAndLeadershipAgent": AgentPromptProfile(
        name="BusinessIdentityAndLeadershipAgent",
        role="Establish organization identity, structure, mission, and operating posture.",
        outputs="EntityBiography, OperatingPostureSummary, HighLevelTimeline",
        source_focus="official_home/about/blog/press + third-party corroboration",
        tool_snippets=[TOOL_SNIPPET_TAVILY_CORE, TOOL_SNIPPET_TAVILY_MAP, TOOL_SNIPPET_WIKI, TOOL_SNIPPET_FILES],
        initial_focus_block="""
What to extract (priority order):
1) Canonical organization name, domains, HQ (if stated), founding date (if stated), mission.
2) Leadership list (CEO/founder), leadership page link(s), and role titles.
3) Operating posture: what they do + who they serve + how they position (clinical/consumer/research).
4) High-level timeline: founding → major announcements → pivots/rebrands.

Efficiency constraints:
- Prefer official sources first; use third-party sources only to corroborate.
- If the site is complex, run tavily.map on the official root to find About/Press/Team pages.
- Checkpoint early once you have identity + leadership + timeline scaffold.
""".strip(),
        reminder_focus_line="Reminder: Stay within scope (identity + leadership + operating posture + high-level timeline).",
    ),
    "PersonBioAndAffiliationsAgent": AgentPromptProfile(
        name="PersonBioAndAffiliationsAgent",
        role="Enrich people profiles with roles, credentials, affiliations, and prior work.",
        outputs="PeopleProfiles, RoleResponsibilityMap, CredentialAnchors",
        source_focus="official_leadership + scholarly/pub profiles",
        tool_snippets=[TOOL_SNIPPET_TAVILY_CORE, TOOL_SNIPPET_WIKI, TOOL_SNIPPET_FILES],
        initial_focus_block="""
Person priorities:
- Prioritize CEO/founder/executive leadership within your slice.
- Capture: current role/title, tenure clues, prior roles, credentials (degrees/licensure), affiliations (universities, labs, orgs), notable publications or talks.

Extraction pattern:
1) Start with official leadership/team pages and press releases naming leaders.
2) Use targeted tavily.search queries per person:
   "{Full Name} {Company} biography", "{Full Name} LinkedIn", "{Full Name} PhD", "{Full Name} publication"
3) Use tavily.extract with query="MISSING_FIELDS: title, tenure, credentials, affiliations, prior employers".

Quality constraints:
- Separate “current” vs “historical” roles clearly.
- Do not infer credentials; only record what is explicitly stated.
- Checkpoint once you complete 1–2 key profiles (don’t wait until the end).
""".strip(),
        reminder_focus_line="Reminder: Stay within scope (people bios + affiliations). Prioritize CEO/founder.",
        include_slice_hint=True,
        slice_hint_label="People slice",
    ),
    "EcosystemMapperAgent": AgentPromptProfile(
        name="EcosystemMapperAgent",
        role="Map entity position in ecosystem: competitors, partners, market category.",
        outputs="CompetitorSet, PartnerAndPlatformGraph, MarketCategoryPlacement",
        source_focus="press_news + official_platform/about + search-based discovery",
        tool_snippets=[TOOL_SNIPPET_EXA, TOOL_SNIPPET_TAVILY_CORE, TOOL_SNIPPET_FILES],
        initial_focus_block="""
What to produce (tight deliverables):
1) Competitors/substitutes: 3–8 orgs, with 1-line “why similar” + source.
2) Partners/platforms: named integrations, distributors, clinical partners, research partners (with sources).
3) Market category placement: 1–3 labels with justification.

Execution pattern:
- Use exa.find_similar on an official page to discover adjacent orgs.
- Use exa.search for “{company} competitors”, “alternatives”, “partners”, “integrates with”.
- Then tavily.extract on the best official/press pages to get evidence.

Constraints:
- Don’t do product specs; just map relationships and categories.
- Avoid low-quality affiliate listicles unless there’s nothing else; prefer press + official pages.
- Checkpoint after you have a stable competitor list + at least 2 partner edges.
""".strip(),
        reminder_focus_line="Reminder: Stay within scope (competitors/partners/category). Avoid product-spec and deep evidence analysis.",
    ),
    "ProductSpecAgent": AgentPromptProfile(
        name="ProductSpecAgent",
        role="Extract detailed product specifications: ingredients, dosages, usage, pricing, warnings.",
        outputs="ProductSpecs, IngredientOrMaterialLists, UsageAndWarningSnippets",
        source_focus="official_product_detail + official_docs_manuals + help snippets",
        tool_snippets=[TOOL_SNIPPET_TAVILY_CORE, TOOL_SNIPPET_TAVILY_MAP, TOOL_SNIPPET_PRODUCT_ESCALATION, TOOL_SNIPPET_FILES],
        initial_focus_block="""
Non-negotiable fields (prioritize these):
- Ingredients/materials (full list) + amounts/dosages when available
- Price (and what the price corresponds to: size, quantity, subscription vs one-time)
- Usage directions (how/when)
- Warnings/contraindications
- Package size / servings / unit count

Execution pattern (preferred):
1) Start with starter sources and official product pages.
2) If product list pages are unclear: tavily.map on official domain with instructions="find product detail pages, pricing, ingredients, supplement facts, warnings".
3) Use tavily.extract with query="MISSING_FIELDS: ingredients, dosage, price, size, usage, warnings" and chunks_per_source=3.
4) Use tavily.crawl only when you need breadth across a product directory.
5) Escalate to browser.playwright only if required fields are hidden behind JS/modals or dynamic pricing widgets.

Constraints:
- Record pricing precisely (currency, cadence, size). Don’t guess.
- If multiple variants exist, capture variant names + differences.
- Checkpoint after completing 1–2 products fully.
""".strip(),
        reminder_focus_line="Reminder: Stay within scope (product specs). Ingredients + price are highest priority.",
        include_slice_hint=True,
        slice_hint_label="Product slice",
    ),
    "CaseStudyHarvestAgent": AgentPromptProfile(
        name="CaseStudyHarvestAgent",
        role="Harvest evidence artifacts: studies, trials, whitepapers, case studies with affiliation labeling.",
        outputs="EvidenceArtifacts",
        source_focus="company-controlled evidence + independent studies + trials",
        tool_snippets=[TOOL_SNIPPET_TAVILY_CORE, TOOL_SNIPPET_TAVILY_MAP, TOOL_SNIPPET_FILES],
        initial_focus_block="""
Deliverable definition (each artifact must include):
- Title
- Author / institution (and whether company-affiliated)
- Year (or best available date)
- Type (trial, observational, case study, whitepaper, pilot, etc.)
- What it supports (product/claim/technology)
- URL(s) to the primary source

Execution pattern:
1) Start with company-controlled evidence hubs: “science”, “research”, “clinical”, “studies”, “whitepaper”, “evidence”.
2) Use tavily.map on official domain if needed to discover science/evidence pages.
3) Use tavily.search for:
   "{company} clinical trial", "{company} study", "{product} trial", "{company} whitepaper PDF"
4) Extract top pages and capture the artifact metadata + label affiliation:
   - company-controlled vs independent vs academic/clinical registry

Constraints:
- Your job is identification + harvesting + labeling, not deep evaluation.
- Avoid product spec extraction unless necessary to link an evidence item to a product.
- Checkpoint after you collect the first 3–5 solid artifacts.
""".strip(),
        reminder_focus_line="Reminder: Stay within scope (evidence artifacts). Focus on finding and labeling studies/trials/case studies.",
    ),
}


# ---------------------------
# Formatting helpers
# ---------------------------

NY_TZ = ZoneInfo("America/New_York")


def _now_block() -> str:
    now = datetime.now(NY_TZ)
    now_local = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    now_iso = now.isoformat()
    return f"Now (America/New_York): {now_local}  (ISO: {now_iso})"


def _fmt_sources(plan: AgentInstancePlanWithSources, limit: int = 6) -> str:
    srcs = plan.starter_sources or []
    if not srcs:
        return "(none)"
    lines: List[str] = []
    for i, s in enumerate(srcs[:limit], start=1):
        lines.append(f"{i}. {s.url} [{getattr(s, 'category', 'unknown')}]")
    if len(srcs) > limit:
        lines.append(f"... (+{len(srcs) - limit} more)")
    return "\n".join(lines)


def _fmt_tools(agent_type_key: str) -> str:
    tools = FULL_ENTITIES_BASIC_DEFAULT_TOOL_MAP.get(agent_type_key, [])
    if not tools:
        return "(none specified)"
    return ", ".join(tools)


def _safe_slice_dump(plan: AgentInstancePlanWithSources) -> str:
    try:
        if plan.slice:
            # pydantic v2 model
            return str(plan.slice.model_dump())
    except Exception:
        pass
    return "(none)"


def _objective_text(plan: AgentInstancePlanWithSources) -> str:
    try:
        if plan.objectives:
            return plan.objectives[0].objective
    except Exception:
        pass
    return "Complete the assigned objective."


def _common_header(state: WorkerAgentState) -> str:
    p = state["agent_instance_plan"]
    today = datetime.now(NY_TZ).strftime("%Y-%m-%d")
    workspace_root = state.get('workspace_root', '') or '_missing_workspace'
    # Normalize display: ensure forward slashes and no leading/trailing slashes
    workspace_display = workspace_root.replace("\\", "/").strip("/")
    return (
        f"Date: {today}\n"
        f"AgentType: {getattr(p, 'agent_type', state.get('agent_type', ''))}\n"
        f"Instance: {getattr(p, 'instance_id', '')}\n"
        f"Stage: {getattr(p, 'stage_id', '')}  SubStage: {getattr(p, 'sub_stage_id', '')}\n"
        f"Workspace: {workspace_display}\n"
        f"Note: All file paths you write will be relative to this workspace under BASE_DIR.\n"
    )


def _slice_hint_block(profile: AgentPromptProfile, plan: AgentInstancePlanWithSources) -> str:
    """
    Adds a short snippet explaining the slice for PeopleBioAndAffiliationsAgent and ProductSpecAgent.
    We avoid assuming schema details; we just surface the slice dump and tell the agent how to treat it.
    """
    if not profile.include_slice_hint:
        return ""
    slice_dump = _safe_slice_dump(plan)
    label = profile.slice_hint_label or "Slice"
    return f"""
{label} guidance:
- Your slice defines the ONLY people/products you should cover. Do not expand beyond it.
- If the slice is partial or unclear, focus first on the highest-priority items inside it (e.g., CEO/founder; top products).
- Slice payload:
{slice_dump}
""".strip()


def _tool_guidance_block(profile: AgentPromptProfile) -> str:
    return "\n\n".join(profile.tool_snippets).strip()


def _state_line(state: WorkerAgentState, key: str, fallback: str = "(none)") -> str:
    val = state.get(key)
    if val is None:
        return fallback
    if isinstance(val, str):
        s = val.strip()
        return s if s else fallback
    return str(val)


def _fmt_recent_files(state: WorkerAgentState, limit: int = 6) -> str:
    recent_files = state.get("file_refs") or []
    if not recent_files:
        return "(none)"
    tail = recent_files[-limit:]
    lines: List[str] = []
    for r in tail:
        if isinstance(r, dict):
            path = r.get("file_path") or r.get("path") or r.get("name") or "(unknown)"
        else:
            path = getattr(r, "file_path", None) or getattr(r, "path", None) or str(r)
        lines.append(f"- {path}")
    return "\n".join(lines)


def _fmt_ledger(state: WorkerAgentState, limit: int = 12) -> str:
    ledger = state.get("progress_ledger") or {}
    if not ledger:
        return "(empty)"
    lines: List[str] = []
    for k, v in list(ledger.items())[:limit]:
        if isinstance(v, dict):
            status = v.get("status", "todo")
        else:
            status = getattr(v, "status", None) or "todo"
        lines.append(f"- {k}: {status}")
    return "\n".join(lines)


def _fmt_recent_actions(state: WorkerAgentState) -> str:
    """
    Best-effort: many implementations store tool logs differently.
    We attempt common keys, otherwise show a short fallback.
    """
    for k in ("recent_actions", "tool_trace", "last_actions", "actions"):
        val = state.get(k)
        if val:
            try:
                if isinstance(val, list):
                    tail = val[-6:]
                    return "\n".join([f"- {str(x)[:240]}" for x in tail])
                return str(val)[:1200]
            except Exception:
                pass
    return "(none)"


# ---------------------------
# Prompt builders (generic skeleton + per-agent overlays)
# --------------------------- 

DEFAULT_MISSING_FIELDS: Dict[str, List[str]] = {
  "BusinessIdentityAndLeadershipAgent": [
    "canonical_name", "domains", "mission", "leadership_roster", "timeline"
  ],
  "ProductSpecAgent": [
    "ingredients", "dosage", "price", "usage", "warnings", "package_size"
  ],
  
}

def build_initial_prompt(state: WorkerAgentState) -> str:
    p = state["agent_instance_plan"]
    agent_type_key = str(getattr(p, "agent_type", state.get("agent_type", "")))
    profile = AGENT_PROFILES.get(agent_type_key)

    # Fallback profile if unknown
    if profile is None:
        profile = AgentPromptProfile(
            name=agent_type_key or "UnknownAgent",
            role="(no profile available)",
            outputs="(unknown)",
            source_focus="(unknown)",
            tool_snippets=[TOOL_SNIPPET_FILES],
            initial_focus_block="(no specific focus guidance available)",
            reminder_focus_line="Reminder: Stay within your assigned scope.",
        )

    objective = _objective_text(p)
    slice_block = _safe_slice_dump(p)
    starter_sources = _fmt_sources(p, limit=6) 

    starter_inputs = p.starter_inputs or " Reason from context what your starting inputs are: the entity or entities you are researching"

    requires_artifacts = ", ".join(getattr(p, "requires_artifacts", None) or []) or "(none)"
    produces_artifacts = ", ".join(getattr(p, "produces_artifacts", None) or []) or "(none)"

    tools_list = _fmt_tools(agent_type_key)
    slice_hint = _slice_hint_block(profile, p)
    tool_guidance = _tool_guidance_block(profile)  

    checkpoint_template = CHECKPOINT_TEMPLATES.get(agent_type_key)
    checkpoint_block = f"\nCheckpoint template:\n{checkpoint_template}\n" if checkpoint_template else ""

    missing_fields = DEFAULT_MISSING_FIELDS.get(agent_type_key, [])
    missing_block = "\n".join([f"- {x}" for x in missing_fields])

    return f"""
{_common_header(state)}{_now_block()}

{LOOP_CONTRACT}

Agent: {profile.name}
Role: {profile.role}
Outputs: {profile.outputs}
Source focus: {profile.source_focus}
Default tools: {tools_list}

Primary objective:
{objective} 

Starter inputs: 
{starter_inputs}


Slice:
{slice_block}

Starter sources:
{starter_sources}



Artifacts:
- Produces: {produces_artifacts}   

{slice_hint}

Tool guidance:
{tool_guidance} 

Checkpoint template (use as a starting structure): 
{checkpoint_block}

{profile.initial_focus_block}

FIRST ACTION (required):
Call think_tool now to set. Do not call search tools before think_tool:
- entity, focus
- next_actions (1–4 tool-sized steps)
- open_questions (if any)
- progress_ledger updates (set outputs to in_progress)
Missing fields (starting defaults):  
{missing_block}
Update missing_fields with think_tool if needed.  
""".strip()




def build_reminder_prompt(state: WorkerAgentState) -> str:
    p = state["agent_instance_plan"]
    agent_type_key = str(getattr(p, "agent_type", state.get("agent_type", "")))
    profile = AGENT_PROFILES.get(agent_type_key)   

    missing_fields = state.get("missing_fields") or []
    missing_block = "\n".join([f"- {x}" for x in missing_fields[:20]]) if missing_fields else "(none)"

    tool_counts = state.get("tool_counts") or {}
    tool_counts_block = ", ".join([f"{k}={v}" for k, v in tool_counts.items()]) if tool_counts else "(none)"

    checkpoint_count = state.get("checkpoint_count", 0)
    last_checkpoint = state.get("last_checkpoint_path") or "(none)"
    visited_count = len(state.get("visited_urls") or [])

    if profile is None:
        profile = AgentPromptProfile(
            name=agent_type_key or "UnknownAgent",
            role="(no profile available)",
            outputs="(unknown)",
            source_focus="(unknown)",
            tool_snippets=[TOOL_SNIPPET_FILES],
            initial_focus_block="(no specific focus guidance available)",
            reminder_focus_line="Reminder: Stay within your assigned scope.",
        )

    focus = state.get("current_focus") or {}
    focus_line = f'Current focus: entity="{focus.get("entity","")}" focus="{focus.get("focus","")}"'

    last_plan = _state_line(state, "last_plan", "(none — use think to set a plan)")
    ledger_block = _fmt_ledger(state)
    recent_files = _fmt_recent_files(state)
    recent_actions = _fmt_recent_actions(state)

    # Compact, agent-specific next-step hints (without duplicating the entire initial prompt)
    agent_next_guidance = _agent_specific_reminder_guidance(agent_type_key)

    return f"""
{_common_header(state)}{_now_block()}

{LOOP_CONTRACT}

{profile.reminder_focus_line}

State cues:
- {focus_line}

Progress ledger:
{ledger_block} 

Tool telemetry:
- steps_taken: {state.get("steps_taken", 0)}
- tool_counts: {tool_counts_block}
- visited_urls: {visited_count}
- checkpoint_count: {checkpoint_count}
- last_checkpoint_path: {last_checkpoint}

Missing fields (gap list):
{missing_block}

Last plan:
{last_plan}

Recent actions:
{recent_actions}

Recent files:
{recent_files}

Next-step guidance:
{agent_next_guidance}

{INFLECTION_NEXT_BLOCK}
""".strip()


def _agent_specific_reminder_guidance(agent_type_key: str) -> str:
    """
    Short per-agent guidance for reminder prompts. Keep it concise and operational.
    """
    if agent_type_key == "BusinessIdentityAndLeadershipAgent":
        return """
- If canonical name/domain/mission/leadership page is missing: tavily.search → tavily.extract.
- If you suspect important pages exist but aren’t surfaced: tavily.map the official domain.
- Avoid drifting into product specs or evidence/case studies (belongs to other agents).
""".strip()

    if agent_type_key == "PersonBioAndAffiliationsAgent":
        return """
- If missing leadership roster: extract from official leadership/team pages first.
- If missing credential anchors: tavily.search with tight name+credential terms → tavily.extract on authoritative pages.
- Use wiki.search for cross-checking only; corroborate critical details with official/primary sources.
""".strip()

    if agent_type_key == "EcosystemMapperAgent":
        return """
- If competitor set is weak: exa.find_similar(official_url) → confirm key entries via tavily.extract.
- If partners are missing: search “partnership”, “integrates”, “powered by”, “collaboration”, then extract the best sources.
- Always keep at least one confirming snippet per competitor/partner edge.
""".strip()

    if agent_type_key == "ProductSpecAgent":
        return """
- If missing product detail pages: tavily.map official domain → extract from discovered product URLs.
- If missing ingredients/pricing/warnings: tavily.extract with a strict missing-fields query.
- If content is JS-rendered/hidden (modals, dynamic pricing): escalate to browser.playwright with explicit click-path + fields list.
""".strip()

    if agent_type_key == "CaseStudyHarvestAgent":
        return """
- If official evidence pages aren’t found: tavily.map official domain for “science/research/studies/whitepaper”.
- If independent evidence is missing: tavily.search “trial”, “study”, “publication”, “whitepaper PDF”, then extract primary sources.
- Ensure each artifact has metadata fields + an affiliation label (company vs independent vs academic/registry).
""".strip()

    return "- Choose the most efficient next step based on what is missing; prefer extract/map over broad search."


# ---------------------------
# Backwards-compatible named builders (optional)
# ---------------------------

def build_initial_business_identity(state: WorkerAgentState) -> str:
    return build_initial_prompt(state)

def build_initial_person_bio(state: WorkerAgentState) -> str:
    return build_initial_prompt(state)

def build_initial_ecosystem(state: WorkerAgentState) -> str:
    return build_initial_prompt(state)

def build_initial_product_spec(state: WorkerAgentState) -> str:
    return build_initial_prompt(state)

def build_initial_case_studies(state: WorkerAgentState) -> str:
    return build_initial_prompt(state)

def build_reminder_generic(state: WorkerAgentState) -> str:
    return build_reminder_prompt(state)


# ---------------------------
# Public maps used by the runtime
# ---------------------------

INITIAL_PROMPT_BUILDERS: Dict[str, Callable[[WorkerAgentState], str]] = {
    "BusinessIdentityAndLeadershipAgent": build_initial_business_identity,
    "PersonBioAndAffiliationsAgent": build_initial_person_bio,
    "EcosystemMapperAgent": build_initial_ecosystem,
    "ProductSpecAgent": build_initial_product_spec,
    "CaseStudyHarvestAgent": build_initial_case_studies,
}

REMINDER_PROMPT_BUILDERS: Dict[str, Callable[[WorkerAgentState], str]] = {
    "BusinessIdentityAndLeadershipAgent": build_reminder_generic,
    "PersonBioAndAffiliationsAgent": build_reminder_generic,
    "EcosystemMapperAgent": build_reminder_generic,
    "ProductSpecAgent": build_reminder_generic,
    "CaseStudyHarvestAgent": build_reminder_generic,
}


# ---------------------------
# Convenience: single entrypoints
# ---------------------------

def build_initial_prompt_for_agent_type(agent_type_key: str, state: WorkerAgentState) -> str:
    fn = INITIAL_PROMPT_BUILDERS.get(agent_type_key, build_initial_prompt)
    return fn(state)

def build_reminder_prompt_for_agent_type(agent_type_key: str, state: WorkerAgentState) -> str:
    fn = REMINDER_PROMPT_BUILDERS.get(agent_type_key, build_reminder_prompt)
    return fn(state)


