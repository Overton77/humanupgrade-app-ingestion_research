from typing import List

def _dedupe_keep_order(urls: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for u in urls or []:
        if not u:
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out 




def _take(urls: List[str], n: int) -> List[str]:
    return (urls or [])[: max(0, n)]
