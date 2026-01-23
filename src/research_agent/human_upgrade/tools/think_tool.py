from langchain.tools import tool, ToolRuntime   
from research_agent.human_upgrade.logger import logger   
from langchain_core.messages import ToolMessage 
from langgraph.types import Command  
from typing import Literal, List, Optional, Dict, Any, Annotated


FieldStatus = Literal["todo", "in_progress", "done", "not_found"]

# matches your TypedDict but usable as plain dict at runtime
def _normalize_field_entry(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if "status" in d and d["status"] in ("todo", "in_progress", "done", "not_found"):
        out["status"] = d["status"]
    if "evidence_files" in d and isinstance(d["evidence_files"], list):
        out["evidence_files"] = [str(x) for x in d["evidence_files"] if str(x)]
    if "notes" in d and isinstance(d["notes"], str):
        out["notes"] = d["notes"]
    return out


@tool(
    description=(
        "Create a compact next-step plan and update the research ledger. "
        "Use when starting, switching focus, after finishing a checkpoint, or if stuck."
    ),
    parse_docstring=False,
)
def think_tool(
    runtime: ToolRuntime,
    entity: Annotated[
        str,
        "Primary target name for the current planning step (business/person/product/compound). Keep it short and specific."
    ],
    required_fields: Annotated[
        List[str],
        "1+ requiredFields you intend to make progress on next. You may include multiple fields that can be covered by the same evidence/checkpoint."
    ],
    next_actions: Annotated[
        List[str],
        "1–3 concrete tool-sized next steps (e.g., a Tavily search query, an extract with query fields, then write a checkpoint). Keep each action executable."
    ],
    open_questions: Annotated[
        Optional[List[str]],
        "Optional (<=8) unresolved questions blocking progress; short bullets."
    ] = None,
    field_updates: Annotated[
        Optional[Dict[str, Dict[str, Any]]],
        (
            "Optional per-field ledger patches keyed by requiredField. Each value may include: "
            "{'status': 'todo|in_progress|done|not_found', 'evidence_files': [paths], 'notes': 'short'}. "
            "Use to precisely mark multiple fields done/not_found and attach evidence file paths."
        )
    ] = None,
    focus_field: Annotated[
        Optional[str],
        "Optional single requiredField to display as current focus (used for reminders)."
    ] = None,
) -> Command:
    """
    Compact planning + ledger updates.

    Args:
        entity: Entity currently being researched.
        required_fields: 1+ requiredFields being targeted next (can be multiple).
        next_actions: 1–3 tool-call-sized actions.
        open_questions: Optional short bullets (<= 8).
        field_updates: Optional per-field ledger patch:
            {
              "<field>": {"status": "...", "evidence_files": [...], "notes": "..."},
              ...
            }
        focus_field: Optional single requiredField to show as current_focus.field.
    """

    # --- compact plan text (for prompt injection) ---
    rf = [f for f in required_fields if isinstance(f, str) and f.strip()]
    rf = rf[:8]  # keep tight
    actions = [a for a in next_actions if isinstance(a, str) and a.strip()][:3]
    oq = (open_questions or [])[:8]

    actions_block = "\n".join([f"{i+1}) {a}" for i, a in enumerate(actions)]) or "(none)"
    oq_block = "\n".join([f"- {q}" for q in oq]) if oq else "(none)"
    fields_block = ", ".join(rf) if rf else "(none)"

    plan_text = (
        f'FOCUS: entity="{entity}"\n'
        f"TARGET_FIELDS: {fields_block}\n"
        f"NEXT_ACTIONS:\n{actions_block}\n"
        f"OPEN_QUESTIONS:\n{oq_block}"
    )

    # --- ledger update (shallow merge safe by rewriting dict) ---
    rfs = dict(runtime.state.get("required_fields_status") or {})

    # If caller provided explicit field_updates, apply them.
    if field_updates:
        for field, patch in field_updates.items():
            if not isinstance(field, str) or not field.strip():
                continue
            existing = dict(rfs.get(field) or {"status": "todo", "evidence_files": [], "notes": ""})
            norm = _normalize_field_entry(patch if isinstance(patch, dict) else {})
            # merge with some de-dupe for evidence_files
            if "status" in norm:
                existing["status"] = norm["status"]
            if "notes" in norm:
                existing["notes"] = (norm["notes"] or "")[:280]
            if "evidence_files" in norm:
                cur = list(existing.get("evidence_files") or [])
                for fp in norm["evidence_files"]:
                    if fp not in cur:
                        cur.append(fp)
                existing["evidence_files"] = cur
            rfs[field] = existing

    # Otherwise, mark selected required_fields as in_progress (unless already done/not_found)
    else:
        for field in rf:
            existing = dict(rfs.get(field) or {"status": "todo", "evidence_files": [], "notes": ""})
            if existing.get("status") in ("todo", "in_progress"):
                existing["status"] = "in_progress"
            rfs[field] = existing

    # pick display focus field
    focus = (focus_field or (rf[0] if rf else "")).strip()

    updates: Dict[str, Any] = {
        "messages": [ToolMessage(content=plan_text, tool_call_id=runtime.tool_call_id)],
        "thoughts": [plan_text],
        "last_plan": plan_text,
        "current_focus": {"entity": entity, "field": focus},
        "required_fields_status": rfs,
    }
    if open_questions is not None:
        updates["open_questions"] = oq

    return Command(update=updates)