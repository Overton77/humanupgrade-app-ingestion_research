from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage
from langgraph.types import Command


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


def _recent_thought(state: Dict[str, Any]) -> str:
    """Extract the most recent thought/reflection from state."""
    thoughts = state.get("thoughts") or []
    if not thoughts:
        return None
    # Return only the most recent thought
    return thoughts[-1]


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
    current_date = datetime.now().strftime("%Y-%m-%d")

    chosen = plan["chosen"]
    objective = chosen["objective"]
    required_fields = list(plan["required_fields"])

    targets_text = _chosen_direction_targets(direction_type, chosen)

    # Keep requiredFields readable but not huge
    required_fields_text = ", ".join(required_fields[:25]) + (f" … (+{len(required_fields)-25})" if len(required_fields) > 25 else "")

    starter_sources_text = _format_starter_sources(chosen, limit=6)
    scope_risks_text = _format_scope_and_risks(chosen)

    return f"""You are a tool-using research agent. Your job is to gather evidence and write checkpoint reports to the workspace.

Date: {current_date}
Bundle: {bundle_id} | Run: {run_id} | Direction: {direction_type}

TARGETS:
{targets_text}

OBJECTIVE:
{objective}

REQUIRED FIELDS (track progress in the ledger; checkpoints can cover multiple fields):
{required_fields_text}

CONTEXT (if any):
{entity_context or "(none provided)"}

STARTER SOURCES (optional starting points, not exhaustive):
{starter_sources_text}

{scope_risks_text}

OPERATING CONTRACT (follow strictly):
- You are in a tool-calling loop.
- Default workflow: think_tool → tavily_search_research(advanced) → tavily_extract_research(query=missing_fields) → agent_write_file(covered_fields=[...]).
- Write a checkpoint after every 2–3 web calls OR when you have enough evidence for ≥1 requiredField.
- A single checkpoint file MAY cover MULTIPLE requiredFields when evidence overlaps.
- Keep moving: prefer authoritative sources; avoid long detours.
- Web budget guideline: ~{max_web_tool_calls_hint} calls total.

CRITICAL RULES:
1) FIRST action MUST be think_tool (no free-text response).
2) Every tavily_extract_research MUST include query listing the missing fields you want.
3) Every checkpoint MUST call agent_write_file with covered_fields=[...] so the ledger stays correct.

NOW: Call think_tool with:
- entity = primary target name
- required_fields = 1–3 fields you will tackle next (can be multiple)
- next_actions = 1–3 tool-sized steps (e.g., search query, extract, write)
""".strip()

def _format_focus(state: Dict[str, Any]) -> str:
    f = state.get("current_focus") or {}
    ent = (f.get("entity") or "").strip()
    field = (f.get("field") or "").strip()
    if ent or field:
        return f'Current focus: entity="{ent}", field="{field}"'
    return "Current focus: (not set) — pick the next highest-value missing requiredField(s) and call think_tool."


def _format_required_fields_status_compact(
    plan: Dict[str, Any],
    state: Dict[str, Any],
    max_lines: int = 18,
    max_missing_preview: int = 8,
) -> str:
    required = list(plan.get("required_fields") or [])
    rfs = state.get("required_fields_status") or {}

    counts = {"todo": 0, "in_progress": 0, "done": 0, "not_found": 0}
    missing: List[str] = []
    outstanding_lines: List[str] = []

    for f in required:
        entry = rfs.get(f) or {}
        status = entry.get("status", "todo")
        if status not in counts:
            status = "todo"
        counts[status] += 1

        if status in ("todo", "in_progress"):
            missing.append(f)

        if status != "done":
            notes = (entry.get("notes") or "").strip()
            files = entry.get("evidence_files") or []
            files_tail = ", ".join(files[-2:]) if files else ""
            line = f"- {f}: {status}"
            if files_tail:
                line += f" | files: {files_tail}"
            if notes:
                line += f" | notes: {notes}"
            outstanding_lines.append(line)

    missing_preview = ", ".join(missing[:max_missing_preview]) if missing else "(none)"
    outstanding_lines = outstanding_lines[:max_lines]

    return (
        f"Ledger counts: done={counts['done']} | in_progress={counts['in_progress']} | "
        f"todo={counts['todo']} | not_found={counts['not_found']}\n"
        f"Next missing candidates: {missing_preview}\n"
        "Outstanding (non-done):\n"
        + ("\n".join(outstanding_lines) if outstanding_lines else "(none)")
    )
def _cap(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 3] + "..."



def _cap(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


def get_reminder_research_prompt(
    *,
    bundle_id: str,
    run_id: str,
    direction_type: str,
    plan: Dict[str, Any],
    state: Dict[str, Any],
    steps_taken: int,
) -> str:
    current_date = datetime.now().strftime("%Y-%m-%d")
    chosen = plan["chosen"]
    objective = chosen["objective"]

    targets_text = _chosen_direction_targets(direction_type, chosen)
    focus_line = _format_focus(state)
    ledger_block = _format_required_fields_status_compact(plan, state)
    recent_files_block = _recent_file_refs(state, limit=5)

    last_plan = state.get("last_plan") or _recent_thought(state) or ""
    last_plan = _cap(last_plan, 1200)

    urgency = ""
    if steps_taken >= 18:
        urgency = "Urgency: HIGH — stop exploring; fill remaining requiredFields and finalize."
    elif steps_taken >= 12:
        urgency = "Urgency: MED — prioritize direct evidence for missing requiredFields."

    return f"""
RESEARCH REMINDER (tool-calling loop)

Date: {current_date}
Bundle: {bundle_id} | Run: {run_id} | Direction: {direction_type} | Step: {steps_taken}
Objective: {objective}
Targets: {targets_text}
{focus_line}
{urgency}

Progress ledger (update via think_tool; this is the source of truth):
{ledger_block}

Last plan (follow unless ledger suggests better missing fields):
{last_plan}

Recent checkpoint files (do not duplicate; extend coverage):
{recent_files_block}

Guardrails:
- Default workflow: tavily_search_research(advanced) → tavily_extract_research(query=missing_fields) → agent_write_file(checkpoint).
- Write a checkpoint after every 2–3 web calls OR once you can substantiate ≥1 requiredField.
- One checkpoint file MAY cover MULTIPLE requiredFields when evidence overlaps.
- If unsure what to do next: think_tool(entity, required_fields=[...], next_actions=[...]) then execute.

NEXT STEP: Either write a checkpoint now from existing evidence, or run search→extract for the next missing field(s).
""".strip()