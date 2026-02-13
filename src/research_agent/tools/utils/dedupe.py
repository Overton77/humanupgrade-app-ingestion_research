from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from typing import Optional, Set

def _normalize_url_for_dedupe(
    url: str,
    *,
    drop_fragment: bool = True,
    drop_query: bool = False,
    keep_query_params: Optional[set[str]] = None,
) -> str:
    """
    Normalize URL for dedupe while preserving meaning.

    Defaults:
      - drop_fragment=True: removes #section anchors
      - drop_query=False: keep query by default (safer for Shopify/Woo/etc)
    Optional:
      - keep_query_params: if provided and drop_query=False, keep only these params.
    """
    s = url.strip()
    parts = urlsplit(s)

    fragment = "" if drop_fragment else parts.fragment

    if drop_query:
        query = ""
    elif keep_query_params is not None:
        # keep only whitelisted params (stable canonicalization)
        q = parse_qsl(parts.query, keep_blank_values=True)
        q2 = [(k, v) for (k, v) in q if k in keep_query_params]
        query = urlencode(q2, doseq=True)
    else:
        query = parts.query

    # Normalize scheme/host casing; keep path as-is
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    return urlunsplit((scheme, netloc, parts.path, query, fragment))


def dedupe_urls(
    urls: list[str],
    *,
    drop_fragment: bool = True,
    drop_query: bool = False,
    keep_query_params: Optional[set[str]] = None,
) -> list[str]:
    """
    Dedupe URLs preserving first-seen order.
    """
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if not u:
            continue
        key = _normalize_url_for_dedupe(
            u,
            drop_fragment=drop_fragment,
            drop_query=drop_query,
            keep_query_params=keep_query_params,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out
