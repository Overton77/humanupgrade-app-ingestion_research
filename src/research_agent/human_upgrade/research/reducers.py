# Annotated with operators does these right 

from __future__ import annotations
from typing import Any, Dict, List, Set


def merge_dict(a: Dict[str, Any] | None, b: Dict[str, Any] | None) -> Dict[str, Any]:
    """Shallow merge; right wins."""
    out = dict(a or {})
    out.update(b or {})
    return out


def merge_dict_of_lists(a: Dict[str, List[Any]] | None, b: Dict[str, List[Any]] | None) -> Dict[str, List[Any]]:
    out: Dict[str, List[Any]] = dict(a or {})
    for k, v in (b or {}).items():
        out.setdefault(k, [])
        out[k].extend(v or [])
    return out


def union_sets(a: Set[str] | None, b: Set[str] | None) -> Set[str]:
    return set(a or set()) | set(b or set())
