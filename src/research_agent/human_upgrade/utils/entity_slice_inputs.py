from __future__ import annotations

from typing import Any, Dict, List, Tuple

def _chunk(items: List[str], chunk_size: int) -> List[List[str]]:
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _extract_people_and_products(connected_candidates: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    Returns (people_names, product_names) from either:
    - single connected candidates dict (guest/businesses/notes)
    - bundle format: {"connected":[{guest,businesses,notes}, ...], "globalNotes": ...}
    """
    people: List[str] = []
    products: List[str] = []

    def add_person(name: Any) -> None:
        if isinstance(name, str) and name.strip():
            people.append(name.strip())

    def add_product(name: Any) -> None:
        if isinstance(name, str) and name.strip():
            products.append(name.strip())

    # Normalize into list of "connected" entries
    if isinstance(connected_candidates, dict) and "connected" in connected_candidates and isinstance(connected_candidates["connected"], list):
        connected_entries = connected_candidates["connected"]
    else:
        connected_entries = [connected_candidates]

    for entry in connected_entries:
        if not isinstance(entry, dict):
            continue

        # Guest person (common)
        guest = entry.get("guest")
        if isinstance(guest, dict):
            add_person(guest.get("canonicalName") or guest.get("inputName") or guest.get("normalizedName"))

        # Businesses -> products
        businesses = entry.get("businesses", [])
        if not isinstance(businesses, list):
            continue

        for b in businesses:
            if not isinstance(b, dict):
                continue

            # Some structures wrap business in {"business": {...}, "products":[...]}
            # but also allow flat.
            products_list = b.get("products", [])
            if not isinstance(products_list, list):
                continue

            for p in products_list:
                if not isinstance(p, dict):
                    continue
                prod = p.get("product")
                if isinstance(prod, dict):
                    add_product(prod.get("canonicalName") or prod.get("inputName") or prod.get("normalizedName"))

    # Deduplicate while preserving order
    def dedupe(seq: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return dedupe(people), dedupe(products)


def build_slicing_inputs_from_connected_candidates(
    connected_candidates: Dict[str, Any],
    *,
    max_products_per_slice: int = 5,
    max_people_per_slice: int = 5,
) -> Dict[str, Any]:
    """
    Produces the SLICING_INPUTS payload expected by the prompt:
    {
      "max_products_per_slice": 5,
      "max_people_per_slice": 5,
      "product_names": [...],
      "person_names": [...],
      "product_slices": [[...], ...],
      "person_slices": [[...], ...]
    }

    NOTE:
    - If there are zero products/people, slices will be [] (so the LLM creates ZERO instances).
    - Even if <= max, we still produce a single slice (so the contract is consistent and deterministic).
      (This matches your "Create EXACTLY len(...slices)" rule.)
    """
    person_names, product_names = _extract_people_and_products(connected_candidates)

    product_slices = _chunk(product_names, max_products_per_slice) if product_names else []
    person_slices = _chunk(person_names, max_people_per_slice) if person_names else []

    return {
        "max_products_per_slice": max_products_per_slice,
        "max_people_per_slice": max_people_per_slice,
        "product_names": product_names,
        "person_names": person_names,
        "product_slices": product_slices,
        "person_slices": person_slices,
    }