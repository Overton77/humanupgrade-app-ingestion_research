from __future__ import annotations

import json
import os
from dataclasses import dataclass
from glob import glob
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from graphql_client.client import Client
from graphql_client.input_types import (
    MediaLinkInput,
    # business
    BusinessCreateRelationsInput,
    BusinessUpdateRelationFieldsInput,
    BusinessExecutiveNestedInput,
    BusinessProductNestedInput,
    # product
    ProductCreateWithIdsInput,
    ProductUpdateWithIdsInput,
    # person
    PersonCreateInput,
    PersonUpdateInput,
    # compound
    CompoundCreateWithIdsInput,
    CompoundUpdateWithIdsInput,
    # case study
    CaseStudyCreateWithOptionalIdsInput,
    CaseStudyUpdateWithOptionalIdsInput,
    # episode relations
    EpisodeUpdateRelationFieldsInput,
)
from graphql_client.enums import CaseStudySourceType


# -----------------------------------------------------------------------------
# Normalization utilities
# -----------------------------------------------------------------------------

def norm(s: Optional[str]) -> str:
    return " ".join((s or "").strip().split()).lower()

def dedupe(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for x in items:
        x2 = (x or "").strip()
        if not x2:
            continue
        k = norm(x2)
        if k not in seen:
            seen.add(k)
            out.append(x2)
    return out

def to_media_links(urls: Iterable[str]) -> List[MediaLinkInput]:
    """
    Your schema requires MediaLinkInput.url (and description may be required/optional).
    We always pass description="" to be safe.
    """
    if not urls:
        return []
    return [MediaLinkInput(url=u, description="", posterUrl=None) for u in dedupe(urls)]


def clean_url(url: Optional[str]) -> Optional[str]:
    """
    Clean URL value for GraphQL input.
    Returns None if url is None or empty string, which will cause the field to be omitted.
    Schema expects string | undefined, not null.
    """
    if not url:
        return None
    url_str = url.strip()
    return url_str if url_str else None

def parse_price_to_float(p: Any) -> Optional[float]:
    if p is None:
        return None
    if isinstance(p, (int, float)):
        return float(p)
    if isinstance(p, str):
        s = p.strip()
        if not s:
            return None
        # "$125.95" -> 125.95
        s = s.replace("$", "").replace(",", "")
        try:
            return float(s)
        except Exception:
            return None
    return None

def is_duplicate_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in (
        "duplicate key",
        "e11000",
        "already exists",
        "unique constraint",
        "conflict",
    ))

def map_case_study_source_type(v: Optional[str]) -> CaseStudySourceType:
    """
    Maps source type string to CaseStudySourceType enum.
    Normalizes various input formats (clinical-trial, clinical_trial, clinicaltrial, etc.)
    and defaults to article if unknown or None.
    
    Valid values: pubmed, clinicaltrial, article, other
    """
    if not v:
        return CaseStudySourceType.article
    
    # Normalize: lowercase and replace dashes/underscores
    normalized = norm(v).replace("-", "").replace("_", "")
    
    # Map normalized values to enum (enum attributes are now lowercase)
    if normalized == "pubmed":
        return CaseStudySourceType.pubmed
    elif normalized == "clinicaltrial":
        return CaseStudySourceType.clinicaltrial
    elif normalized == "article":
        return CaseStudySourceType.article
    elif normalized == "other":
        return CaseStudySourceType.other
    else:
        # Default to article for unknown values
        return CaseStudySourceType.article


# -----------------------------------------------------------------------------
# GraphQL lookups
# -----------------------------------------------------------------------------

async def get_business_id_by_name(gql: Client, name: str) -> Optional[str]:
    r = await gql.business_by_name(name=name)
    node = getattr(r, "business_by_name", None)
    return node.id if node else None

async def get_person_id_by_name(gql: Client, name: str) -> Optional[str]:
    r = await gql.person_by_name(name=name)
    node = getattr(r, "person_by_name", None)
    return node.id if node else None

async def get_product_id_by_name(gql: Client, name: str) -> Optional[str]:
    r = await gql.product_by_name(name=name)
    node = getattr(r, "product_by_name", None)
    return node.id if node else None

async def get_compound_id_by_name(gql: Client, name: str) -> Optional[str]:
    r = await gql.compound_by_name(name=name)
    node = getattr(r, "compound_by_name", None)
    return node.id if node else None

async def filter_existing_product_names(gql: Client, product_names: List[str]) -> List[str]:
    """
    Filter product names to only include those that exist in the database.
    Returns a list of product names that were found.
    """
    if not product_names:
        return []
    existing_names: List[str] = []
    for name in product_names:
        if not name or not name.strip():
            continue
        pid = await get_product_id_by_name(gql, name)
        if pid:
            existing_names.append(name)
    return existing_names

async def filter_existing_compound_names(gql: Client, compound_names: List[str]) -> List[str]:
    """
    Filter compound names to only include those that exist in the database.
    Returns a list of compound names that were found.
    """
    if not compound_names:
        return []
    existing_names: List[str] = []
    for name in compound_names:
        if not name or not name.strip():
            continue
        cid = await get_compound_id_by_name(gql, name)
        if cid:
            existing_names.append(name)
    return existing_names

async def get_episode_id_by_page_url(gql: Client, page_url: str) -> Optional[str]:
    r = await gql.episode_by_page_url(page_url=page_url)
    node = getattr(r, "episode_by_page_url", None)
    return node.id if node else None

async def find_case_study_id_by_url_or_title(gql: Client, url: Optional[str], title: str) -> Optional[str]:
    """
    Fallback until you add caseStudyByUrl/title:
    paginate caseStudies and match.
    """
    t_title = norm(title)
    t_url = (url or "").strip()

    offset = 0
    limit = 50
    while True:
        page = await gql.case_studies(limit=limit, offset=offset)
        rows = getattr(page, "case_studies", [])
        if not rows:
            return None

        for cs in rows:
            if t_url and ((getattr(cs, "url", None) or "").strip() == t_url):
                return cs.id
            if norm(getattr(cs, "title", "") or "") == t_title:
                return cs.id

        if len(rows) < limit:
            return None
        offset += limit


# -----------------------------------------------------------------------------
# Aggregation structures (merging duplicates)
# -----------------------------------------------------------------------------

@dataclass
class AggPerson:
    name: str
    is_guest: bool = False
    bio: Optional[str] = None
    role: Optional[str] = None
    business_name: Optional[str] = None
    affiliations: List[str] = None  # type: ignore[assignment]
    media_links: List[str] = None   # type: ignore[assignment]

    def __post_init__(self):
        self.affiliations = self.affiliations or []
        self.media_links = self.media_links or []

@dataclass
class AggBusiness:
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    media_links: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        self.media_links = self.media_links or []

@dataclass
class AggCompound:
    name: str
    description: Optional[str] = None
    aliases: List[str] = None  # type: ignore[assignment]
    media_links: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        self.aliases = self.aliases or []
        self.media_links = self.media_links or []

@dataclass
class AggProduct:
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    ingredients: List[str] = None  # type: ignore[assignment]
    source_url: Optional[str] = None
    business_name: Optional[str] = None
    media_links: List[str] = None  # type: ignore[assignment]
    compounds: List[AggCompound] = None  # type: ignore[assignment]

    def __post_init__(self):
        self.ingredients = self.ingredients or []
        self.media_links = self.media_links or []
        self.compounds = self.compounds or []

@dataclass
class AggCaseStudy:
    title: str
    summary: str
    url: Optional[str] = None
    source_type: Optional[str] = None
    related_compound_names: List[str] = None  # type: ignore[assignment]
    related_product_names: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        self.related_compound_names = self.related_compound_names or []
        self.related_product_names = self.related_product_names or []


def aggregate_extracted_entities(extracted_entities: Dict[str, Any]) -> Tuple[
    Dict[str, AggBusiness],
    Dict[str, AggPerson],
    Dict[str, AggProduct],
    Dict[str, AggCompound],
    Dict[str, AggCaseStudy],
]:
    businesses: Dict[str, AggBusiness] = {}
    people: Dict[str, AggPerson] = {}
    products: Dict[str, AggProduct] = {}
    compounds: Dict[str, AggCompound] = {}
    case_studies: Dict[str, AggCaseStudy] = {}

    # Businesses
    for b in extracted_entities.get("businesses", []) or []:
        name = norm(b.get("name"))
        if not name:
            continue
        cur = businesses.get(name)
        # Normalize website: empty string or None -> None, otherwise keep the URL
        website_val = b.get("website")
        if website_val:
            website_val = website_val.strip()
            if not website_val:
                website_val = None
        else:
            website_val = None
            
        if not cur:
            businesses[name] = AggBusiness(
                name=name,
                description=b.get("description") or None,
                website=website_val,
                media_links=dedupe(b.get("media_links", []) or []),
            )
        else:
            cur.description = cur.description or (b.get("description") or None)
            # Use the new website if current is None/empty, otherwise keep current
            if not cur.website and website_val:
                cur.website = website_val
            cur.media_links = dedupe(list(cur.media_links) + (b.get("media_links", []) or []))

    # People (merge duplicates by name)
    for p in extracted_entities.get("people", []) or []:
        name = norm(p.get("name"))
        if not name:
            continue
        cur = people.get(name)
        if not cur:
            people[name] = AggPerson(
                name=name,
                is_guest=bool(p.get("is_guest", False)),
                bio=p.get("bio") or None,
                role=p.get("role") or None,
                business_name=norm(p.get("business_name")) or None,
                affiliations=dedupe(p.get("affiliations", []) or []),
                media_links=dedupe(p.get("media_links", []) or []),
            )
        else:
            cur.is_guest = cur.is_guest or bool(p.get("is_guest", False))
            cur.bio = cur.bio or (p.get("bio") or None)
            cur.role = cur.role or (p.get("role") or None)
            cur.business_name = cur.business_name or (norm(p.get("business_name")) or None)
            cur.affiliations = dedupe(list(cur.affiliations) + (p.get("affiliations", []) or []))
            cur.media_links = dedupe(list(cur.media_links) + (p.get("media_links", []) or []))

    # Products + nested compounds
    for pr in extracted_entities.get("products", []) or []:
        name = norm(pr.get("name"))
        if not name:
            continue

        pr_price = parse_price_to_float(pr.get("price"))
        pr_business_name = norm(pr.get("business_name")) or None

        # collect nested compounds
        nested_compounds: List[AggCompound] = []
        for c in pr.get("compounds", []) or []:
            cn = norm(c.get("name"))
            if not cn:
                continue
            nested_compounds.append(
                AggCompound(
                    name=cn,
                    description=c.get("description") or None,
                    aliases=dedupe(c.get("aliases", []) or []),
                    media_links=dedupe(c.get("media_links", []) or []),
                )
            )

        cur = products.get(name)
        if not cur:
            products[name] = AggProduct(
                name=name,
                description=pr.get("description") or None,
                price=pr_price,
                ingredients=dedupe(pr.get("ingredients", []) or []),
                source_url=pr.get("source_url") or None,
                business_name=pr_business_name,
                media_links=dedupe(pr.get("media_links", []) or []),
                compounds=nested_compounds,
            )
        else:
            cur.description = cur.description or (pr.get("description") or None)
            cur.price = cur.price if cur.price is not None else pr_price
            cur.source_url = cur.source_url or (pr.get("source_url") or None)
            cur.business_name = cur.business_name or pr_business_name
            cur.ingredients = dedupe(list(cur.ingredients) + (pr.get("ingredients", []) or []))
            cur.media_links = dedupe(list(cur.media_links) + (pr.get("media_links", []) or []))

            # merge compounds by name
            existing = {c.name: c for c in cur.compounds}
            for nc in nested_compounds:
                if nc.name not in existing:
                    cur.compounds.append(nc)
                    existing[nc.name] = nc
                else:
                    ec = existing[nc.name]
                    ec.description = ec.description or nc.description
                    ec.aliases = dedupe(list(ec.aliases) + list(nc.aliases))
                    ec.media_links = dedupe(list(ec.media_links) + list(nc.media_links))

    # Global compounds (from products)
    for pr in products.values():
        for c in pr.compounds:
            cur = compounds.get(c.name)
            if not cur:
                compounds[c.name] = AggCompound(
                    name=c.name,
                    description=c.description,
                    aliases=dedupe(c.aliases),
                    media_links=dedupe(c.media_links),
                )
            else:
                cur.description = cur.description or c.description
                cur.aliases = dedupe(list(cur.aliases) + list(c.aliases))
                cur.media_links = dedupe(list(cur.media_links) + list(c.media_links))

    # Case studies (dedupe by url if present else title)
    for cs in extracted_entities.get("case_studies", []) or []:
        title = (cs.get("title") or "").strip()
        if not title:
            continue
        url = (cs.get("url") or None)
        key = norm(url) if url else f"title:{norm(title)}"
        cur = case_studies.get(key)
        if not cur:
            case_studies[key] = AggCaseStudy(
                title=norm(title),  # you asked for standardized lowercase
                summary=cs.get("summary") or "",
                url=url,
                source_type=cs.get("source_type") or None,
                related_compound_names=dedupe([norm(x) for x in (cs.get("related_compound_names", []) or [])]),
                related_product_names=dedupe([norm(x) for x in (cs.get("related_product_names", []) or [])]),
            )
        else:
            # keep first summary; but merge relations
            cur.related_compound_names = dedupe(list(cur.related_compound_names) + [norm(x) for x in (cs.get("related_compound_names", []) or [])])
            cur.related_product_names = dedupe(list(cur.related_product_names) + [norm(x) for x in (cs.get("related_product_names", []) or [])])

    return businesses, people, products, compounds, case_studies


# -----------------------------------------------------------------------------
# Upsert implementations
# -----------------------------------------------------------------------------

async def upsert_person(gql: Client, p: AggPerson) -> str:
    name = p.name
    try:
        created = await gql.create_person(
            input=PersonCreateInput(
                name=name,
                role=p.role,
                bio=p.bio,
                media_links=to_media_links(p.media_links),
            )
        )
        return created.create_person.id
    except Exception as e:
        if not is_duplicate_error(e):
            raise
        pid = await get_person_id_by_name(gql, name)
        if not pid:
            raise RuntimeError(f"Duplicate person '{name}' but personByName returned no id") from e
        updated = await gql.update_person(
            input=PersonUpdateInput(
                id=pid,
                name=name,
                role=p.role,
                bio=p.bio,
                media_links=to_media_links(p.media_links),
            )
        )
        node = getattr(updated, "update_person", None)
        return node.id if node else pid


async def upsert_compound(gql: Client, c: AggCompound) -> str:
    name = c.name
    try:
        created = await gql.create_compound(
            input=CompoundCreateWithIdsInput(
                name=name,
                description=c.description,
                aliases=dedupe(c.aliases),
                media_links=to_media_links(c.media_links),
            )
        )
        return created.create_compound.id
    except Exception as e:
        if not is_duplicate_error(e):
            raise
        cid = await get_compound_id_by_name(gql, name)
        if not cid:
            raise RuntimeError(f"Duplicate compound '{name}' but compoundByName returned no id") from e
        updated = await gql.update_compound(
            input=CompoundUpdateWithIdsInput(
                id=cid,
                name=name,
                description=c.description,
                aliases=dedupe(c.aliases),
                media_links=to_media_links(c.media_links),
            )
        )
        node = getattr(updated, "update_compound", None)
        return node.id if node else cid


async def upsert_business(
    gql: Client,
    b: AggBusiness,
    *,
    products_nested: List[BusinessProductNestedInput],
    executives_nested: List[BusinessExecutiveNestedInput],
) -> str:
    """
    Uses productsNested to create products inline (instead of productNames which requires existing products).
    And ONLY executivesNested if you have role (per your rule).
    """
    name = b.name

    # Always pass arrays, never None (empty arrays if no items)
    execs_array = executives_nested if executives_nested else []
    products_array = products_nested if products_nested else []

    # First, try to find existing business by name
    existing_bid = await get_business_id_by_name(gql, name)
    if existing_bid:
        # Business exists, update it
        # Build update input - only include fields that are not None/empty
        update_dict: Dict[str, Any] = {
            "id": existing_bid,
        }
        if b.description:
            update_dict["description"] = b.description
        # Clean website URL - only include if not None/empty
        website_val = clean_url(b.website)
        if website_val:
            update_dict["website"] = website_val
        if b.media_links:
            update_dict["media_links"] = to_media_links(b.media_links)
        if products_array:
            update_dict["products_nested"] = products_array
        if execs_array:
            update_dict["executives_nested"] = execs_array
        
        updated = await gql.update_business_relations(
            input=BusinessUpdateRelationFieldsInput(**update_dict)
        )
        node = getattr(updated, "update_business_relations", None)
        return node.id if node else existing_bid

    # Business doesn't exist, try to create it
    try:
        # Build create input - only include fields that are not None/empty
        create_dict: Dict[str, Any] = {
            "name": name,
        }
        if b.description:
            create_dict["description"] = b.description
        # Clean website URL - only include if not None/empty
        website_val = clean_url(b.website)
        if website_val:
            create_dict["website"] = website_val
        if b.media_links:
            create_dict["media_links"] = to_media_links(b.media_links)
        if products_array:
            create_dict["products_nested"] = products_array
        if execs_array:
            create_dict["executives_nested"] = execs_array
        
        created = await gql.create_business_with_relations(
            input=BusinessCreateRelationsInput(**create_dict)
        )
        return created.create_business_with_relations.id
    except Exception as e:
        # If creation fails, check if it's a duplicate error and business now exists
        if is_duplicate_error(e):
            # Try to find it again (might have been created in a race condition)
            bid = await get_business_id_by_name(gql, name)
            if bid:
                # Found it, update it
                # Build update input - only include fields that are not None/empty
                update_dict: Dict[str, Any] = {
                    "id": bid,
                }
                if b.description:
                    update_dict["description"] = b.description
                # Clean website URL - only include if not None/empty
                website_val = clean_url(b.website)
                if website_val:
                    update_dict["website"] = website_val
                if b.media_links:
                    update_dict["media_links"] = to_media_links(b.media_links)
                if products_array:
                    update_dict["products_nested"] = products_array
                if execs_array:
                    update_dict["executives_nested"] = execs_array
                
                updated = await gql.update_business_relations(
                    input=BusinessUpdateRelationFieldsInput(**update_dict)
                )
                node = getattr(updated, "update_business_relations", None)
                return node.id if node else bid
        # If it's not a duplicate or we still can't find it, re-raise the original error
        raise


async def upsert_product(
    gql: Client,
    pr: AggProduct,
    *,
    business_id: str,
) -> str:
    """
    Per your new rule: pass ONLY compoundNames (not compoundsNested).
    """
    name = pr.name
    compound_names = dedupe([c.name for c in pr.compounds])
    # Parse price (returns None if not provided or invalid)
    # Schema accepts number | null | undefined, so None is handled correctly
    pr_price = parse_price_to_float(pr.price)

    try:
        # Build product input - only include fields that are not None/empty
        product_create_dict: Dict[str, Any] = {
            "name": name,
            "business_id": business_id,
        }
        if pr.description:
            product_create_dict["description"] = pr.description
        if pr_price is not None:
            product_create_dict["price"] = pr_price
        if pr.ingredients:
            product_create_dict["ingredients"] = dedupe(pr.ingredients)
        if pr.media_links:
            product_create_dict["media_links"] = to_media_links(pr.media_links)
        # Clean source_url - only include if not None/empty
        source_url_clean = clean_url(pr.source_url)
        if source_url_clean:
            product_create_dict["source_url"] = source_url_clean
        if compound_names:
            product_create_dict["compound_names"] = compound_names
        
        created = await gql.create_product(
            input=ProductCreateWithIdsInput(**product_create_dict)
        )
        return created.create_product.id
    except Exception as e:
        if not is_duplicate_error(e):
            raise
        pid = await get_product_id_by_name(gql, name)
        if not pid:
            raise RuntimeError(f"Duplicate product '{name}' but productByName returned no id") from e
        # Build product update input - only include fields that are not None/empty
        product_update_dict: Dict[str, Any] = {
            "id": pid,
            "name": name,
        }
        if pr.description:
            product_update_dict["description"] = pr.description
        if pr_price is not None:
            product_update_dict["price"] = pr_price
        if pr.ingredients:
            product_update_dict["ingredients"] = dedupe(pr.ingredients)
        if pr.media_links:
            product_update_dict["media_links"] = to_media_links(pr.media_links)
        # Clean source_url - only include if not None/empty
        source_url_clean = clean_url(pr.source_url)
        if source_url_clean:
            product_update_dict["source_url"] = source_url_clean
        if compound_names:
            product_update_dict["compound_names"] = compound_names
        
        updated = await gql.update_product(
            input=ProductUpdateWithIdsInput(**product_update_dict)
        )
        node = getattr(updated, "update_product", None)
        return node.id if node else pid


async def upsert_case_study(
    gql: Client,
    cs: AggCaseStudy,
    *,
    episode_page_url: str,
) -> str:
    """
    Uses connect-by-name:
      - productNames (filtered to only existing products)
      - compoundNames (filtered to only existing compounds)
      - episodePageUrls
    """
    title = cs.title
    source_type = map_case_study_source_type(cs.source_type)

    # Filter product and compound names to only include those that exist
    # Skip missing ones instead of throwing errors
    filtered_product_names = await filter_existing_product_names(
        gql, 
        dedupe(cs.related_product_names) if cs.related_product_names else []
    )
    filtered_compound_names = await filter_existing_compound_names(
        gql,
        dedupe(cs.related_compound_names) if cs.related_compound_names else []
    )

    try:
        # Build case study input - only include url if not None/empty
        case_study_create_dict: Dict[str, Any] = {
            "title": title,
            "summary": cs.summary,
            "source_type": source_type,
            "episode_page_urls": [episode_page_url],
        }
        # Clean url - only include if not None/empty
        url_clean = clean_url(cs.url)
        if url_clean:
            case_study_create_dict["url"] = url_clean
        if filtered_product_names:
            case_study_create_dict["product_names"] = filtered_product_names
        if filtered_compound_names:
            case_study_create_dict["compound_names"] = filtered_compound_names
        
        created = await gql.create_case_study(
            input=CaseStudyCreateWithOptionalIdsInput(**case_study_create_dict)
        )
        return created.create_case_study.id
    except Exception as e:
        if not is_duplicate_error(e):
            raise
        existing_id = await find_case_study_id_by_url_or_title(gql, cs.url, title)
        if not existing_id:
            raise RuntimeError(f"Duplicate case study '{title}' but could not find via pagination") from e
        # Build case study update input - only include url if not None/empty
        case_study_update_dict: Dict[str, Any] = {
            "id": existing_id,
            "title": title,
            "summary": cs.summary,
            "source_type": source_type,
            "episode_page_urls": [episode_page_url],
        }
        # Clean url - only include if not None/empty
        url_clean = clean_url(cs.url)
        if url_clean:
            case_study_update_dict["url"] = url_clean
        if filtered_product_names:
            case_study_update_dict["product_names"] = filtered_product_names
        if filtered_compound_names:
            case_study_update_dict["compound_names"] = filtered_compound_names
        
        updated = await gql.update_case_study(
            input=CaseStudyUpdateWithOptionalIdsInput(**case_study_update_dict)
        )
        node = getattr(updated, "update_case_study", None)
        return node.id if node else existing_id


async def attach_episode_guests(gql: Client, *, episode_page_url: str, guest_person_ids: List[str]) -> None:
    episode_id = await get_episode_id_by_page_url(gql, episode_page_url)
    if not episode_id:
        return
    guest_person_ids = dedupe(guest_person_ids)
    if not guest_person_ids:
        return
    await gql.update_episode_relations(
        input=EpisodeUpdateRelationFieldsInput(
            id=episode_id,
            guest_ids=guest_person_ids,
        )
    )


# -----------------------------------------------------------------------------
# Seed runner (reads JSON files + ingests)
# -----------------------------------------------------------------------------

def load_seed_files(seed_dir: str) -> List[Dict[str, Any]]:
    files = sorted(glob(os.path.join(seed_dir, "*.json")))
    payloads: List[Dict[str, Any]] = []
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            payloads.append(json.load(f))
    return payloads


def preview_seed_payload(payload: Dict[str, Any]) -> pd.DataFrame:
    ee = payload.get("extracted_entities", {}) or {}
    businesses, people, products, compounds, case_studies = aggregate_extracted_entities(ee)
    rows = [{
        "episode_url": payload.get("episode_url"),
        "businesses": len(businesses),
        "people": len(people),
        "products": len(products),
        "compounds": len(compounds),
        "case_studies": len(case_studies),
    }]
    return pd.DataFrame(rows)


async def ingest_seed_payload(gql: Client, payload: Dict[str, Any]) -> Dict[str, Any]:
    episode_url = payload.get("episode_url") or ""
    ee = payload.get("extracted_entities", {}) or {}

    businesses, people, products, compounds, case_studies = aggregate_extracted_entities(ee)

    # 1) People
    person_name_to_id: Dict[str, str] = {}
    for p in people.values():
        pid = await upsert_person(gql, p)
        person_name_to_id[p.name] = pid

    # 2) Compounds (ensure exist for compoundNames resolution)
    for c in compounds.values():
        await upsert_compound(gql, c)

    # 3) Businesses (create products inline using productsNested; connect executivesNested only if role)
    business_name_to_id: Dict[str, str] = {}
    product_name_to_id: Dict[str, str] = {}
    skipped_products: List[str] = []
    
    for b in businesses.values():
        # productsNested: all products whose business_name matches this business
        linked_products_nested: List[BusinessProductNestedInput] = []
        for pr in products.values():
            if pr.business_name and pr.business_name == b.name:
                # Parse price if available (can be None if not provided or invalid)
                pr_price = parse_price_to_float(pr.price)
                
                # Build product input - only include fields that are not None/empty
                # Schema expects string | undefined, not null, so we omit None values
                product_input_dict: Dict[str, Any] = {
                    "name": pr.name,
                }
                if pr.description:
                    product_input_dict["description"] = pr.description
                if pr.ingredients:
                    product_input_dict["ingredients"] = dedupe(pr.ingredients)
                if pr.media_links:
                    product_input_dict["media_links"] = to_media_links(pr.media_links)
                # Clean source_url - only include if not None/empty
                source_url_clean = clean_url(pr.source_url)
                if source_url_clean:
                    product_input_dict["source_url"] = source_url_clean
                # Only add price field if it's not None
                if pr_price is not None:
                    product_input_dict["price"] = pr_price
                
                linked_products_nested.append(
                    BusinessProductNestedInput(**product_input_dict)
                )

        # executivesNested: people whose business_name matches + have role
        execs: List[BusinessExecutiveNestedInput] = []
        for p in people.values():
            if p.role and p.business_name == b.name:
                execs.append(
                    BusinessExecutiveNestedInput(
                        name=p.name,
                        role=p.role,
                        title=p.role,  # you can refine later
                        media_links=to_media_links(p.media_links),
                    )
                )

        bid = await upsert_business(
            gql,
            b,
            products_nested=linked_products_nested if linked_products_nested else [],
            executives_nested=execs,
        )
        business_name_to_id[b.name] = bid
        
        # Track product names that were created inline and link their compounds
        for pr in products.values():
            if pr.business_name and pr.business_name == b.name:
                # Products are created inline, so we need to query them to get their IDs
                # This is a bit inefficient but necessary since productsNested doesn't return IDs
                try:
                    product_result = await gql.product_by_name(name=pr.name)
                    if hasattr(product_result, "product_by_name") and product_result.product_by_name:
                        product_id = product_result.product_by_name.id
                        product_name_to_id[pr.name] = product_id
                        
                        # Update product with compounds (price is now set via productsNested)
                        compound_names = dedupe([c.name for c in pr.compounds]) if pr.compounds else []
                        
                        # Only update if we have compounds to set (price is already set in nested input)
                        if compound_names:
                            try:
                                await gql.update_product(
                                    input=ProductUpdateWithIdsInput(
                                        id=product_id,
                                        compound_names=compound_names or [],
                                    )
                                )
                            except Exception:
                                # Update failed, but continue
                                pass
                except Exception:
                    # Product might not exist yet or query failed, skip for now
                    pass

    # 4) Products that weren't linked to any business (create separately)
    for pr in products.values():
        if not pr.business_name:
            skipped_products.append(pr.name)
            continue
        
        # Skip if already created inline
        if pr.name in product_name_to_id:
            continue

        business_id = business_name_to_id.get(pr.business_name)
        if not business_id:
            # fallback: query by name
            business_id = await get_business_id_by_name(gql, pr.business_name)

        if not business_id:
            skipped_products.append(pr.name)
            continue

        pid = await upsert_product(gql, pr, business_id=business_id)
        product_name_to_id[pr.name] = pid

    # 5) Case studies
    case_study_ids: List[str] = []
    for cs in case_studies.values():
        csid = await upsert_case_study(gql, cs, episode_page_url=episode_url)
        case_study_ids.append(csid)

    # 6) Attach guests to episode
    guest_ids: List[str] = []
    for p in people.values():
        if p.is_guest:
            pid = person_name_to_id.get(p.name)
            if pid:
                guest_ids.append(pid)
    await attach_episode_guests(gql, episode_page_url=episode_url, guest_person_ids=guest_ids)

    return {
        "episode_url": episode_url,
        "businesses": list(business_name_to_id.keys()),
        "people": list(person_name_to_id.keys()),
        "products": list(product_name_to_id.keys()),
        "skipped_products_no_business": skipped_products,
        "case_studies": [cs.title for cs in case_studies.values()],
    }


async def load_one_seed_file(gql: Client, seed_file: str) -> Dict[str, Any]:
    with open(seed_file, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return await ingest_seed_payload(gql, payload)


async def seed_one_entity_file(gql: Client, filename: str) -> Dict[str, Any]:
    """
    Convenience function to seed a single entity file from the entities_seed directory.
    
    Args:
        gql: GraphQL client instance
        filename: Just the filename (e.g., "nathan_bryan.json") or full path
        
    Returns:
        Dictionary with ingestion results (episode_url, businesses, people, products, etc.)
    
    Example:
        result = await seed_one_entity_file(gql, "nathan_bryan.json")
    """
    # If filename is already a full path, use it directly
    if os.path.isabs(filename) or os.path.sep in filename:
        seed_file_path = filename
    else:
        # Otherwise, construct path relative to entities_seed directory
        # Assuming this file is in research_agent/, entities_seed is in research_agent/entities_seed/
        current_dir = os.path.dirname(os.path.abspath(__file__))
        entities_seed_dir = os.path.join(current_dir, "entities_seed")
        seed_file_path = os.path.join(entities_seed_dir, filename)
    
    if not os.path.exists(seed_file_path):
        raise FileNotFoundError(f"Seed file not found: {seed_file_path}")
    
    return await load_one_seed_file(gql, seed_file_path)


async def seed_from_directory(gql: Client, seed_dir: str) -> pd.DataFrame:
    payloads = load_seed_files(seed_dir)

    # quick preview
    preview_df = pd.concat([preview_seed_payload(p) for p in payloads], ignore_index=True)
    print(preview_df.head(10))

    results: List[Dict[str, Any]] = []
    for p in payloads:
        results.append(await ingest_seed_payload(gql, p))

    return pd.DataFrame(results)


# -----------------------------------------------------------------------------
# Client factory (matches your env setup)
# -----------------------------------------------------------------------------

def make_client_from_env() -> Client:
    graphql_auth_token = os.getenv("GRAPHQL_AUTH_TOKEN")
    graphql_url = os.getenv("GRAPHQL_LOCAL_URL") or "http://localhost:4000/graphql"
    if graphql_url.startswith("localhost"):
        graphql_url = "http://" + graphql_url

    return Client(
        url=graphql_url,
        headers={"Authorization": f"Bearer {graphql_auth_token}"},
    )
