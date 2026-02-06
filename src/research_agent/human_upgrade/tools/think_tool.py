from langchain.tools import tool, ToolRuntime   
from research_agent.human_upgrade.logger import logger   
from langchain_core.messages import ToolMessage 
from langgraph.types import Command  
from typing import Literal, List, Optional, Dict, Any, Annotated


LedgerStatus = Literal["todo", "in_progress", "done", "blocked", "not_found"]


def _normalize_ledger_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    status = patch.get("status")
    if status in ("todo", "in_progress", "done", "blocked", "not_found"):
        out["status"] = status

    notes = patch.get("notes")
    if isinstance(notes, str):
        out["notes"] = notes.strip()[:400]

    ev = patch.get("evidence_files")
    if isinstance(ev, list):
        # keep only short-ish strings
        cleaned = [str(x).strip() for x in ev if isinstance(x, (str,))]
        out["evidence_files"] = [x for x in cleaned if x][:50]

    return out


@tool(
    description=(
        "Create a compact next-step plan and optionally update the progress ledger. "
        "Use at start, when switching focus, after writing a checkpoint/final file, or if stuck."
    ),
    parse_docstring=False,
)
def think_tool(
    runtime: ToolRuntime,
    entity: Annotated[
        str,
        "Primary target entity for this planning step (business/person/product). Keep it short."
    ],
    focus: Annotated[
        str,
        "What you are focusing on right now (e.g. 'EntityBiography', 'ProductSpecs', 'EvidenceArtifacts', or a short objective label)."
    ],
    next_actions: Annotated[
        List[str],
        "1–4 concrete tool-sized next steps (search query, extract targets, then write a checkpoint). Each should be executable."
    ],
    targets: Annotated[
        Optional[List[str]],
        "Optional list of specific items in-scope right now (e.g. product names in slice, person names). Keep <= 10."
    ] = None,
    open_questions: Annotated[
        Optional[List[str]],
        "Optional unresolved questions blocking progress; short bullets (<= 10)."
    ] = None,
    ledger_updates: Annotated[
        Optional[Dict[str, Dict[str, Any]]],
        (
            "Optional progress ledger patches keyed by artifact key or objective key. Each patch may include: "
            "{'status': 'todo|in_progress|done|blocked|not_found', 'evidence_files': [paths], 'notes': 'short'}.\n"
            "Examples keys: 'EntityBiography', 'ProductSpecs', 'EvidenceArtifacts', 'Objective:Map competitors'."
        ),
    ] = None,
) -> Command:
    """
    Compact planning + scratchpad + optional ledger updates.

    Writes a ToolMessage with the plan (so the agent sees it),
    and returns Command(update=...) to mutate graph state immediately.
    """

    ent = (entity or "").strip()[:120] or "(unknown)"
    foc = (focus or "").strip()[:160] or "(unspecified)"

    actions = [a.strip() for a in (next_actions or []) if isinstance(a, str) and a.strip()]
    actions = actions[:4]
    actions_block = "\n".join([f"{i+1}) {a}" for i, a in enumerate(actions)]) or "(none)"

    targs = [t.strip() for t in (targets or []) if isinstance(t, str) and t.strip()]
    targs = targs[:10]
    targets_block = ", ".join(targs) if targs else "(none)"

    oq = [q.strip() for q in (open_questions or []) if isinstance(q, str) and q.strip()]
    oq = oq[:10]
    oq_block = "\n".join([f"- {q}" for q in oq]) if oq else "(none)"

    plan_text = (
        f'FOCUS: entity="{ent}"\n'
        f"FOCUS_AREA: {foc}\n"
        f"TARGETS: {targets_block}\n"
        f"NEXT_ACTIONS:\n{actions_block}\n"
        f"OPEN_QUESTIONS:\n{oq_block}"
    )

    # --- apply ledger patches (shallow merge per key) ---
    ledger: Dict[str, Dict[str, Any]] = dict(runtime.state.get("progress_ledger") or {})

    if ledger_updates:
        for key, patch in ledger_updates.items():
            if not isinstance(key, str) or not key.strip():
                continue
            k = key.strip()[:180]
            existing = dict(ledger.get(k) or {"status": "todo", "evidence_files": [], "notes": ""})
            norm = _normalize_ledger_patch(patch if isinstance(patch, dict) else {})

            if "status" in norm:
                existing["status"] = norm["status"]
            if "notes" in norm:
                existing["notes"] = norm["notes"]

            if "evidence_files" in norm:
                cur = list(existing.get("evidence_files") or [])
                for fp in norm["evidence_files"]:
                    if fp not in cur:
                        cur.append(fp)
                existing["evidence_files"] = cur

            ledger[k] = existing
    else:
        # Minimal default behavior: mark current focus as in_progress (unless done/not_found)
        k = foc
        existing = dict(ledger.get(k) or {"status": "todo", "evidence_files": [], "notes": ""})
        if existing.get("status") in ("todo", "in_progress", "blocked"):
            existing["status"] = "in_progress"
        ledger[k] = existing

    updates: Dict[str, Any] = {
        # tool message appended into the agent’s conversation
        "messages": [ToolMessage(content=plan_text, tool_call_id=runtime.tool_call_id)],
        # scratchpad / prompt anchors
        "thoughts": [plan_text],
        "last_plan": plan_text,
        "current_focus": {"entity": ent, "focus": foc},
        "progress_ledger": ledger,
    }

    if open_questions is not None:
        updates["open_questions"] = oq

    return Command(update=updates)