from __future__ import annotations
from pathlib import Path
import re

BASE_DIR = Path("agent_outputs")

def sanitize(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s)
    return s[:120] if len(s) > 120 else s

def workspace_for(*parts: str) -> Path:
    safe = [sanitize(p) for p in parts if p]
    p = BASE_DIR.joinpath(*safe)
    p.mkdir(parents=True, exist_ok=True)
    return p
