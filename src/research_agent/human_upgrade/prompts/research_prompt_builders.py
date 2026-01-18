from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langgraph.types import Command


# ============================================================
# IMPORTANT: plan shape in AgentState (EXACT)
# ============================================================
# plan = {
#   "chosen": <dict from chosenDirection.model_dump()>,
#   "required_fields": [<enum values as strings>]
# }
# ============================================================


# -----------------------------
# Helpers (NO fallbacks; exact keys)
# -----------------------------

def _objective(plan: Dict[str, Any]) -> str:
    return plan["chosen"]["objective"]

def _required_fields(plan: Dict[str, Any]) -> List[str]:
    return list(plan["required_fields"])

def _format_required_fields(fields: List[str]) -> str:
    return "\n".join([f"- {f}" for f in fields])

def _chosen_direction_targets(direction_type: str, chosen: Dict[str, Any]) -> str:
    """
    Uses the exact keys defined by your OutputA models:
      - GUEST: guestCanonicalName
      - BUSINESS: businessNames
      - PRODUCT: productNames
      - COMPOUND: compoundNames
      - PLATFORM: platformNames
    """
    if direction_type == "GUEST":
        return f"- Guest: {chosen['guestCanonicalName']}"
    if direction_type == "BUSINESS":
        return "- Businesses: " + ", ".join(chosen["businessNames"])
    if direction_type == "PRODUCT":
        return "- Products: " + ", ".join(chosen["productNames"])
    if direction_type == "COMPOUND":
        return "- Compounds: " + ", ".join(chosen["compoundNames"])
    if direction_type == "PLATFORM":
        return "- Platforms: " + ", ".join(chosen["platformNames"])
    return "- Targets: (unknown direction_type)"

def _format_starter_sources(chosen: Dict[str, Any], limit: int = 8) -> str:
    """
    StarterSource shape is exact:
      {url, sourceType, usedFor, reason, confidence}
    """
    starter = chosen["starterSources"]
    if not starter:
        return "None provided."

    lines: List[str] = []
    for i, s in enumerate(starter[:limit], start=1):
        url = s["url"]
        stype = s["sourceType"]
        used_for = ", ".join(s["usedFor"])
        reason = s["reason"]
        conf = s["confidence"]
        lines.append(
            f"{i}. {url}\n"
            f"   - sourceType: {stype}\n"
            f"   - usedFor: {used_for}\n"
            f"   - confidence: {conf}\n"
            f"   - reason: {reason}"
        )
    if len(starter) > limit:
        lines.append(f"...and {len(starter) - limit} more starter sources.")
    return "\n".join(lines)

def _format_scope_and_risks(chosen: Dict[str, Any]) -> str:
    scope = chosen.get("scopeNotes")
    risks = chosen["riskFlags"]
    scope_text = scope if scope else "None."
    risks_text = "\n".join([f"- {r}" for r in risks]) if risks else "None."
    return f"""Scope notes:
{scope_text}

Risk flags:
{risks_text}
"""

def _recent_file_refs(state: Dict[str, Any], limit: int = 6) -> str:
    refs = state.get("file_refs") or []
    if not refs:
        return "None yet."

    tail = refs[-limit:]
    lines: List[str] = []
    for r in tail:
        file_path = getattr(r, "file_path", None) or (r.get("file_path") if isinstance(r, dict) else None) or "unknown"
        desc = getattr(r, "description", None) or (r.get("description") if isinstance(r, dict) else None) or ""
        entity_key = getattr(r, "entity_key", None) or (r.get("entity_key") if isinstance(r, dict) else None) or ""
        suffix = f" ({entity_key})" if entity_key else ""
        if desc:
            lines.append(f"- {file_path}{suffix} — {desc}")
        else:
            lines.append(f"- {file_path}{suffix}")
    return "\n".join(lines)


# -----------------------------
# Prompt builders
# -----------------------------

def get_initial_research_prompt(
    *,
    bundle_id: str,
    run_id: str,
    direction_type: str,
    plan: Dict[str, Any],
    entity_context: str = "",
    max_web_tool_calls_hint: int = 18,
) -> str:
    """
    Full first-turn mission prompt. Sent once only.
    Uses EXACT plan keys:
      plan["chosen"] and plan["required_fields"]
    """
    current_date = datetime.now().strftime("%Y-%m-%d")

    chosen = plan["chosen"]
    objective = plan["chosen"]["objective"]
    required_fields = list(plan["required_fields"])

    targets_text = _chosen_direction_targets(direction_type, chosen)
    starter_sources_text = _format_starter_sources(chosen, limit=8)
    scope_risks_text = _format_scope_and_risks(chosen)
    required_fields_text = _format_required_fields(required_fields)

    return f"""# Advanced Biotech Research Agent — Direction Run

Date: {current_date}
Bundle: {bundle_id}
Run: {run_id}
Direction: {direction_type}

## Targets
{targets_text}

## Context
You are an advanced biotech research agent performing evidence-based research to extract structured knowledge.
Your job is to research efficiently, cite sources, and create high-quality checkpoint reports in the file system.

Entity context:
{entity_context or "(none provided)"}

## chosenDirection
Objective:
{objective}

Starter sources (ranked, not exhaustive):
{starter_sources_text}

{scope_risks_text}

## requiredFields (you MUST cover these explicitly in your written reports)
{required_fields_text}

---

# Operating Principles (keep the loop tight)

## Tool-call discipline & stop conditions
- Favor fewer, higher-signal tool calls over many low-signal calls.
- Web tool call budget (guideline): try to stay under ~{max_web_tool_calls_hint} total web calls for this direction.
- Stop unfruitful lines quickly:
  - After 2 searches on the same sub-question without improved evidence: change query strategy (constraints/synonyms/source type).
  - After 3 total attempts on the same missing requiredField with weak evidence: pause that field, record what you tried, and pivot.
  - If a field is genuinely unavailable: explicitly write "NOT FOUND" + what you tried + best proxy sources, then move on.

## Checkpointing (plain-text reports)
- Write intermediate summaries to the file system as you make progress.
- These must be plain text and read like an internal research report with sections.
- Your reports should be so clear that downstream structured extraction is easy:
  - include a section per requiredField (or grouped sections if they naturally cluster)
  - include granular detail and concrete facts/numbers where possible
  - include sources as URLs under each claim/field
  - clearly distinguish confirmed facts vs likely/inferred vs unknown

---

# Tools

## ✅ Reflection tool
think_tool(reflection: str)

Use to:
- plan next 1–3 actions
- identify which requiredFields are still missing
- decide whether to search, extract, map, wiki, or write/edit a report
Use it especially when switching fields or when stuck.

## ✅ Wikipedia tool (fast grounding / disambiguation)
wiki_tool(query: str)

Use when:
- you need quick background on unfamiliar terms/entities
- you need definitions or historical context
- you want to disambiguate names before searching
Do NOT use as the only evidence for novel/controversial claims; use it to guide targeted research.

## ✅ Web research tools (Tavily)

### tavily_search_research
tavily_search_research(
  query: str,
  max_results: int = 5,
  search_depth: "basic" | "advanced" = "basic",
  topic: "general" | "news" | "finance" = "general",
  include_images: bool = False,
  include_raw_content: bool | "markdown" | "text" = False
)

How to write high-signal queries (patterns you SHOULD use):
- Field-driven: "<target> <requiredField>"
- Add authoritative constraints early:
  - site:pubmed.ncbi.nlm.nih.gov
  - site:clinicaltrials.gov
  - site:nih.gov
  - filetype:pdf review
- Add disambiguation terms:
  - synonyms / aliases / brand names
  - affiliation / institution / title
- Add evidence terms:
  - "randomized trial", "systematic review", "meta-analysis"
  - "adverse events", "contraindications", "safety", "dosing"
  - "mechanism of action", "pharmacokinetics", "half-life"

Search workflow:
1) Start with 1–2 high-signal searches (field-driven + constraints).
2) Choose the best 2–4 sources from the results.
3) Extract in a batch (do not keep searching forever).

### tavily_extract_research
tavily_extract_research(
  urls: str | list[str],
  query: str | None = None,
  chunks_per_source: int = 3,
  extract_depth: "basic" | "advanced" = "basic",
  include_images: bool = False,
  include_favicon: bool = False,
  format: "markdown" | "text" = "markdown"
)

Rules:
- Batch 3–5 URLs per call whenever possible.
- Use query to force extraction toward requiredFields:
  - query="Extract facts relevant to requiredFields: {', '.join(required_fields)}. Include numbers/dates. Include limitations. Include citations."
- If extraction is weak, do ONE revised search with better constraints rather than repeatedly extracting random URLs.

### tavily_map_research
tavily_map_research(
  url: str,
  instructions: str | None = None,
  max_depth: int = 1,
  max_breadth: int = 20,
  limit: int = 25
)

Use when:
- you found an authoritative domain and want its internal relevant pages
- instructions should be explicit about what to find (e.g., bios, trials, safety, patents, press, publications)
Avoid mapping unvalidated domains.

---

# File System Tools (checkpointing)

## agent_write_file
agent_write_file(
  filename: str,
  content: str,
  description: str,
  bundle_id: str = "",
  entity_key: str = ""
)

What to write (plain text, detailed, sectioned report):
- Title
- Objective (restated)
- Coverage map: list requiredFields and mark which are covered in this file
- Findings by requiredField (use this exact pattern):
  - requiredField: <fieldName>
    - Evidence: (facts, numbers, dates)
    - Sources: (URLs)
    - Confidence: high/med/low + why
- Gaps / unknowns (explicit)
- Next steps (1–3)

Description MUST be extremely informative (do NOT be vague):
Include:
- target entity(ies)
- direction_type
- which requiredFields are covered
- what evidence types were used (PubMed, trials registry, company site, LinkedIn, patents, etc.)
- what is still missing (if anything)

Good description example:
"Plain-text report for {direction_type} targets. Covers requiredFields: X, Y, Z with evidence from PubMed + ClinicalTrials.gov + official site. Includes quantified outcomes and safety notes. Remaining gaps: <missingFields>."

## agent_read_file(filename: str)
Use to avoid duplicating work.

## agent_edit_file(filename: str, find_text: str, replace_text: str, count: int = -1)
Prefer editing/augmenting existing files over creating duplicates.

## agent_list_outputs
agent_list_outputs()

Use when:
- you are about to conclude/finalize
- you need a reminder of what files exist and what each contains
- you want to confirm the research artifacts you produced

This returns a friendly list of all file_refs with descriptions (plus a quick snapshot of workspace_files if present).

---

# Recommended Loop
1) think_tool: pick the next missing requiredField(s).
2) wiki_tool if grounding/disambiguation is needed.
3) tavily_search_research: 1–2 searches; select 2–4 best sources.
4) tavily_extract_research: batch extract; focus on missing fields.
5) agent_write_file: checkpoint a plain-text report with sections per requiredField.
6) Repeat until requiredFields are covered.

When you believe you're done:
- Call agent_list_outputs() and confirm:
  1) which requiredFields are fully covered
  2) which files you produced (paths + descriptions)
- Then respond with a final confirmation message (no more tool calls unless truly needed).

Start now. Your next action should be think_tool planning the first 1–3 moves.
"""


def get_reminder_research_prompt(
    *,
    bundle_id: str,
    run_id: str,
    direction_type: str,
    plan: Dict[str, Any],
    recent_files_block: str,
    steps_taken: int,
) -> str:
    """
    Compact reminder prompt injected on subsequent turns.
    Uses EXACT plan keys:
      plan["chosen"] and plan["required_fields"]
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    objective = plan["chosen"]["objective"]
    required_fields = list(plan["required_fields"])
    required_fields_text = ", ".join(required_fields)

    urgency = ""
    if steps_taken >= 18:
        urgency = "Urgency: HIGH — stop exploring; fill remaining requiredFields and finalize."
    elif steps_taken >= 12:
        urgency = "Urgency: MED — prioritize direct evidence for missing requiredFields."

    return f"""Research loop reminder.

Date: {current_date}
Bundle: {bundle_id} | Run: {run_id} | Direction: {direction_type} | Step: {steps_taken}
Objective: {objective}
requiredFields: {required_fields_text}
{urgency}

Recent files (do not duplicate; edit/extend if needed):
{recent_files_block}

Query tactics (use these to improve signal fast):
- Field-driven: "<target> <missing requiredField>"
- Add authority constraints: site:pubmed.ncbi.nlm.nih.gov, site:clinicaltrials.gov, site:nih.gov, filetype:pdf
- Add evidence terms: "systematic review", "meta-analysis", "randomized trial", "adverse events", "contraindications"
- Add disambiguation: synonyms / aliases / brand names / affiliation
- Stop quickly: after 2 searches without better evidence, change strategy or pivot fields

Tool quick reference:
- think_tool(reflection)
- wiki_tool(query)
- tavily_search_research(query, max_results=5, search_depth="basic|advanced", topic="general|news|finance")
- tavily_extract_research(urls=[...], query=None, chunks_per_source=3, extract_depth="basic|advanced")
- tavily_map_research(url, instructions=None, max_depth=1, limit=25)
- agent_write_file(filename, content, description, bundle_id, entity_key)
- agent_read_file(filename)
- agent_edit_file(filename, find_text, replace_text, count=-1)
- agent_list_outputs()

Decision points (pick ONE and act now):
1) Write a checkpoint report:
   - If you can cover any requiredFields with evidence, write a plain-text sectioned report now.
2) Think/refocus:
   - If you’re unsure what’s missing or what to do next, run think_tool and choose the next 1–3 actions.
3) Gather targeted evidence:
   - If specific requiredFields are missing, do the smallest possible search/extract to fill them, then write a checkpoint.
4) Conclude/finalize:
   - If most/all requiredFields are satisfied:
     a) call agent_list_outputs()
     b) confirm which requiredFields are covered
     c) confirm which files you produced (paths + descriptions)
     d) respond with a final confirmation message
5) Pivot away from an unfruitful thread:
   - If repeated searches/extracts aren’t improving evidence, stop that line and pivot to a different missing requiredField.
"""