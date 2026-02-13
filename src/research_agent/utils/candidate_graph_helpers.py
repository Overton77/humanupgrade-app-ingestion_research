from typing import Any, Dict, List 

from research_agent.human_upgrade.structured_outputs.candidates_outputs import EntitySourceResult, OfficialStarterSources, SeedExtraction

def _best_effort_guest_from_seed(seed_extraction: SeedExtraction) -> EntitySourceResult:
    """
    Build an EntitySourceResult-like dict for guest.
    We avoid strict coupling to SeedExtraction shape.
    """
    # Try common shapes
    guests = None
    if hasattr(seed_extraction, "guest_candidates"):
        guests = getattr(seed_extraction, "guest_candidates")
    elif isinstance(seed_extraction, dict):
        guests = seed_extraction.get("guest_candidates")

    if isinstance(guests, list) and guests:
        g0 = guests[0] or {}
        input_name = g0.get("inputName") or g0.get("name") or "unknown"
        normalized = g0.get("normalizedName") or str(input_name).strip().lower()
        type_hint = g0.get("typeHint") or g0.get("type") or "PERSON"
        return {
            "inputName": input_name,
            "normalizedName": normalized,
            "typeHint": type_hint,
            "canonicalName": g0.get("canonicalName"),
            "canonicalConfidence": g0.get("canonicalConfidence"),
            "candidates": g0.get("candidates") or [],
            "notes": g0.get("notes"),
        }

    # Fallback minimal
    return {
        "inputName": "unknown",
        "normalizedName": "unknown",
        "typeHint": "PERSON",
        "canonicalName": None,
        "canonicalConfidence": None,
        "candidates": [],
        "notes": "Guest not found in seed_extraction; placeholder used.",
    }

def _guest_from_official_sources(
    official_sources: OfficialStarterSources,
    seed_extraction: SeedExtraction,
) -> EntitySourceResult:
    """
    Prefer OfficialStarterSources.guests for deterministic, verified guest identity.
    Returns an EntitySourceResult-like dict.
    """
    # Pull guests list robustly
    guests = None
    if hasattr(official_sources, "guests"):
        guests = official_sources.guests
    elif isinstance(official_sources, dict):
        guests = official_sources.get("guests")

    guests = guests or []

    # If no official guests, fallback
    if not guests:
        return _best_effort_guest_from_seed(seed_extraction)

    # Normalize access
    def _to_dict(x: Any) -> Dict[str, Any]:
        return x.model_dump() if hasattr(x, "model_dump") else dict(x)

    guest_dicts = [_to_dict(g) for g in guests]

    # If exactly one, pick it
    if len(guest_dicts) == 1:
        return _official_target_to_entity_source_result(guest_dicts[0])

    # Try seed top guest name match
    seed_guest = _best_effort_guest_from_seed(seed_extraction)
    seed_norm = (seed_guest.get("normalizedName") or "").strip().lower()

    if seed_norm:
        for g in guest_dicts:
            gn = (g.get("normalizedName") or "").strip().lower()
            if gn and (gn == seed_norm or gn in seed_norm or seed_norm in gn):
                return _official_target_to_entity_source_result(g)

    # Otherwise pick by max summed confidence of sources
    def score_official(g: Dict[str, Any]) -> float:
        s = 0.0
        for src in (g.get("sources") or []):
            try:
                s += float(src.get("confidence") or 0.0)
            except Exception:
                pass
        return s

    best = max(guest_dicts, key=score_official)
    return _official_target_to_entity_source_result(best)


def _official_target_to_entity_source_result(target: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert OfficialEntityTargets into EntitySourceResult-like dict.
    Maps OfficialStarterSource -> SourceCandidate.
    """
    sources = target.get("sources") or []

    candidates: List[Dict[str, Any]] = []
    rank = 1
    for src in sources:
        url = src.get("url")
        if not url:
            continue

        # score is confidence; label is src.label
        conf = float(src.get("confidence") or 0.85)

        candidates.append(
            {
                "url": url,
                "label": src.get("label") or "Official source",
                "sourceType": "OFFICIAL",     # SourceType enum value as string
                "rank": rank,
                "score": max(0.0, min(1.0, conf)),
                "signals": src.get("evidence") or [],
                "validationLevel": "ENTITY_MATCH",  # or NAME_ONLY if you prefer
            }
        )
        rank += 1

    input_name = target.get("inputName") or "unknown"
    normalized = target.get("normalizedName") or str(input_name).strip().lower()

    return {
        "inputName": input_name,
        "normalizedName": normalized,
        "typeHint": target.get("typeHint") or "PERSON",
        "canonicalName": target.get("inputName"),  # optional; you can leave None
        "canonicalConfidence": 0.95,
        "candidates": candidates,
        "notes": target.get("notes"),
    }