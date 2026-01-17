"""
research_ingestion_helpers.py

Idempotent-ish ingestion helpers for your ariadne-codegen Client, using:
- Business: productNames + executivesNested (ONLY if a person has role)
- Product: compoundNames (and optional compoundsNested if you want richer compound creation)
- CaseStudy: productNames + compoundNames + episodePageUrls
- Episode: updateEpisodeRelations using guestIds + sponsorBusinessIds (resolved by name)

Requires your generated graphql_client package (ariadne-codegen output).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from graphql_client.client import Client
from graphql_client.input_types import (
    MediaLinkInput,
    # business
    BusinessCreateRelationsInput,
    BusinessUpdateRelationFieldsInput,
    BusinessExecutiveNestedInput,
    # product
    ProductCreateWithIdsInput,
    ProductUpdateWithIdsInput,
    ProductCompoundNestedInput,
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
# Duck-typed research agent outputs (mirror your pydantic models)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class CompoundOutput:
    name: str
    description: Optional[str] = None
    aliases: List[str] = None  # type: ignore[assignment]
    mechanism_of_action: Optional[str] = None
    media_links: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        object.__setattr__(self, "aliases", self.aliases or [])
        object.__setattr__(self, "media_links", self.media_links or [])


@dataclass(frozen=True)
class ProductOutput:
    name: str
    description: Optional[str] = None
    price: Optional[float] = None
    ingredients: List[str] = None  # type: ignore[assignment]
    compounds: List[CompoundOutput] = None  # type: ignore[assignment]
    source_url: Optional[str] = None
    business_name: Optional[str] = None
    media_links: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        object.__setattr__(self, "ingredients", self.ingredients or [])
        object.__setattr__(self, "compounds", self.compounds or [])
        object.__setattr__(self, "media_links", self.media_links or [])


@dataclass(frozen=True)
class PersonOutput:
    name: str
    is_guest: bool
    bio: Optional[str] = None
    role: Optional[str] = None
    business_name: Optional[str] = None
    affiliations: List[str] = None  # type: ignore[assignment]
    media_links: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        object.__setattr__(self, "affiliations", self.affiliations or [])
        object.__setattr__(self, "media_links", self.media_links or [])


@dataclass(frozen=True)
class BusinessOutput:
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    media_links: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        object.__setattr__(self, "media_links", self.media_links or [])


@dataclass(frozen=True)
class CaseStudyOutput:
    title: str
    summary: str
    url: Optional[str] = None
    source_type: str = "other"  # "pubmed" | "clinical_trial" | "website" | "news" | "other"
    related_compound_names: List[str] = None  # type: ignore[assignment]
    related_product_names: List[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        object.__setattr__(self, "related_compound_names", self.related_compound_names or [])
        object.__setattr__(self, "related_product_names", self.related_product_names or [])


@dataclass(frozen=True)
class ResearchEntities:
    businesses: List[BusinessOutput]
    people: List[PersonOutput]
    products: List[ProductOutput]
    case_studies: List[CaseStudyOutput]
    extraction_notes: Optional[str] = None


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _norm(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()

def _dedupe_str(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for x in items:
        x2 = (x or "").strip()
        if not x2:
            continue
        k = _norm(x2)
        if k not in seen:
            seen.add(k)
            out.append(x2)
    return out

def _to_media_links(urls: List[str]) -> List[MediaLinkInput]:
    # schema: MediaLinkInput(url: str, description: str, posterUrl?: str)
    # you often won't have descriptions during ingestion; use "".
    return [MediaLinkInput(url=u, description="", posterUrl=None) for u in _dedupe_str(urls)]

def _is_duplicate_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in ("duplicate key", "e11000", "already exists", "unique constraint", "conflict"))

def _map_case_study_source_type(v: str) -> Optional[CaseStudySourceType]:
    # CaseStudyCreateWithOptionalIdsInput.source_type is Optional[CaseStudySourceType]
    v2 = _norm(v)
    if not v2:
        return None
    if v2 == "pubmed":
        return CaseStudySourceType.PUBMED if hasattr(CaseStudySourceType, "PUBMED") else CaseStudySourceType.OTHER
    if v2 == "clinical_trial":
        return (
            CaseStudySourceType.CLINICAL_TRIAL
            if hasattr(CaseStudySourceType, "CLINICAL_TRIAL")
            else CaseStudySourceType.OTHER
        )
    if v2 == "website":
        return CaseStudySourceType.WEBSITE if hasattr(CaseStudySourceType, "WEBSITE") else CaseStudySourceType.OTHER
    if v2 == "news":
        return CaseStudySourceType.NEWS if hasattr(CaseStudySourceType, "NEWS") else CaseStudySourceType.OTHER
    return CaseStudySourceType.OTHER if hasattr(CaseStudySourceType, "OTHER") else None


# -----------------------------------------------------------------------------
# Queries (by name / pageUrl)
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

async def get_episode_id_by_page_url(gql: Client, page_url: str) -> Optional[str]:
    r = await gql.episode_by_page_url(page_url=page_url)
    node = getattr(r, "episode_by_page_url", None)
    return node.id if node else None

async def find_case_study_id_by_url_or_title(gql: Client, url: Optional[str], title: str) -> Optional[str]:
    """
    You don't have caseStudyByUrl/title query yet.
    Best available fallback: paginate caseStudies and match by url/title locally.

    This is O(N) and fine for early ingestion while your dataset is small.
    """
    target_title = _norm(title)
    target_url = (url or "").strip()

    offset = 0
    limit = 50
    while True:
        page = await gql.case_studies(limit=limit, offset=offset)
        rows = getattr(page, "case_studies", [])
        if not rows:
            return None

        for cs in rows:
            if target_url and (getattr(cs, "url", None) or "").strip() == target_url:
                return cs.id
            if _norm(getattr(cs, "title", "") or "") == target_title:
                return cs.id

        if len(rows) < limit:
            return None
        offset += limit


# -----------------------------------------------------------------------------
# Core upserts
# -----------------------------------------------------------------------------

async def upsert_person(gql: Client, p: PersonOutput) -> str:
    name = (p.name or "").strip()
    if not name:
        raise ValueError("PersonOutput.name required")

    try:
        created = await gql.create_person(
            input=PersonCreateInput(
                name=name,
                role=(p.role or None),
                bio=(p.bio or None),
                media_links=_to_media_links(p.media_links),
            )
        )
        return created.create_person.id
    except Exception as e:
        if not _is_duplicate_error(e):
            raise
        pid = await get_person_id_by_name(gql, name)
        if not pid:
            raise RuntimeError(f"Duplicate person '{name}' but personByName returned no id") from e
        updated = await gql.update_person(
            input=PersonUpdateInput(
                id=pid,
                name=name,
                role=(p.role or None),
                bio=(p.bio or None),
                media_links=_to_media_links(p.media_links),
            )
        )
        node = getattr(updated, "update_person", None)
        return node.id if node else pid


async def upsert_compound(gql: Client, c: CompoundOutput) -> str:
    name = (c.name or "").strip()
    if not name:
        raise ValueError("CompoundOutput.name required")

    try:
        created = await gql.create_compound(
            input=CompoundCreateWithIdsInput(
                name=name,
                description=(c.description or None),
                aliases=_dedupe_str(c.aliases),
                media_links=_to_media_links(c.media_links),
            )
        )
        return created.create_compound.id
    except Exception as e:
        if not _is_duplicate_error(e):
            raise
        cid = await get_compound_id_by_name(gql, name)
        if not cid:
            raise RuntimeError(f"Duplicate compound '{name}' but compoundByName returned no id") from e
        updated = await gql.update_compound(
            input=CompoundUpdateWithIdsInput(
                id=cid,
                name=name,
                description=(c.description or None),
                aliases=_dedupe_str(c.aliases),
                media_links=_to_media_links(c.media_links),
            )
        )
        node = getattr(updated, "update_compound", None)
        return node.id if node else cid


async def upsert_product(
    gql: Client,
    product: ProductOutput,
    *,
    business_id: str,
    use_compounds_nested: bool = False,
) -> str:
    """
    You requested: "only pass compoundNames".
    By default we do exactly that.

    If you set use_compounds_nested=True, we will ALSO pass compoundsNested with richer compound data
    (but still keep compoundNames). This can help early-stage ingestion.
    """
    name = (product.name or "").strip()
    if not name:
        raise ValueError("ProductOutput.name required")

    compound_names = _dedupe_str([c.name for c in product.compounds if c and (c.name or "").strip()])

    compounds_nested: Optional[List[ProductCompoundNestedInput]] = None
    if use_compounds_nested:
        # optional: enrich compound creation/update path on server using nested data
        compounds_nested = [
            ProductCompoundNestedInput(
                name=(c.name or "").strip() or None,
                description=(c.description or None),
                aliases=_dedupe_str(c.aliases),
                media_links=_to_media_links(c.media_links),
            )
            for c in product.compounds
            if c and (c.name or "").strip()
        ] or None

    try:
        created = await gql.create_product(
            input=ProductCreateWithIdsInput(
                name=name,
                business_id=business_id,
                description=(product.description or None),
                price=product.price,
                ingredients=_dedupe_str(product.ingredients),
                media_links=_to_media_links(product.media_links),
                source_url=(product.source_url or None),
                compound_names=compound_names or None,     # ✅
                compounds_nested=compounds_nested,        # optional
            )
        )
        return created.create_product.id
    except Exception as e:
        if not _is_duplicate_error(e):
            raise
        pid = await get_product_id_by_name(gql, name)
        if not pid:
            raise RuntimeError(f"Duplicate product '{name}' but productByName returned no id") from e
        updated = await gql.update_product(
            input=ProductUpdateWithIdsInput(
                id=pid,
                name=name,
                description=(product.description or None),
                price=product.price,
                ingredients=_dedupe_str(product.ingredients),
                media_links=_to_media_links(product.media_links),
                source_url=(product.source_url or None),
                compound_names=compound_names or None,     # ✅
                compounds_nested=compounds_nested,        # optional
            )
        )
        node = getattr(updated, "update_product", None)
        return node.id if node else pid


async def upsert_business(
    gql: Client,
    b: BusinessOutput,
    *,
    product_names: List[str],
    executives_nested: List[BusinessExecutiveNestedInput],
) -> str:
    """
    Uses:
      - product_names -> BusinessCreateRelationsInput.product_names / BusinessUpdateRelationFieldsInput.product_names
      - executives_nested ONLY (no owner/ownerNames)
    """
    name = (b.name or "").strip()
    if not name:
        raise ValueError("BusinessOutput.name required")

    product_names = _dedupe_str(product_names)

    execs = executives_nested or []
    execs_or_none = execs if execs else None

    try:
        created = await gql.create_business_with_relations(
            input=BusinessCreateRelationsInput(
                name=name,
                description=(b.description or None),
                website=(b.website or None),
                media_links=_to_media_links(b.media_links),
                product_names=product_names or None,           # ✅
                executives_nested=execs_or_none,              # ✅ only if provided
            )
        )
        return created.create_business_with_relations.id
    except Exception as e:
        if not _is_duplicate_error(e):
            raise
        bid = await get_business_id_by_name(gql, name)
        if not bid:
            raise RuntimeError(f"Duplicate business '{name}' but businessByName returned no id") from e

        updated = await gql.update_business_relations(
            input=BusinessUpdateRelationFieldsInput(
                id=bid,
                product_names=product_names or None,          # ✅
                executives_nested=execs_or_none,             # ✅
                description=(b.description or None),
                website=(b.website or None),
                media_links=_to_media_links(b.media_links),
            )
        )
        node = getattr(updated, "update_business_relations", None)
        return node.id if node else bid


async def upsert_case_study(
    gql: Client,
    cs: CaseStudyOutput,
    *,
    episode_page_urls: List[str],
) -> str:
    """
    Uses your added connect-by-name convenience fields:
      - product_names
      - compound_names
      - episode_page_urls (your schema calls it episodePageUrls)
    """
    title = (cs.title or "").strip()
    if not title:
        raise ValueError("CaseStudyOutput.title required")

    product_names = _dedupe_str(cs.related_product_names)
    compound_names = _dedupe_str(cs.related_compound_names)
    episode_page_urls = _dedupe_str(episode_page_urls)

    source_type = _map_case_study_source_type(cs.source_type)

    try:
        created = await gql.create_case_study(
            input=CaseStudyCreateWithOptionalIdsInput(
                title=title,
                summary=cs.summary,
                url=(cs.url or None),
                source_type=source_type,
                episode_page_urls=episode_page_urls or None,   # ✅
                product_names=product_names or None,           # ✅
                compound_names=compound_names or None,         # ✅
            )
        )
        return created.create_case_study.id
    except Exception as e:
        if not _is_duplicate_error(e):
            raise

        existing_id = await find_case_study_id_by_url_or_title(gql, cs.url, title)
        if not existing_id:
            raise RuntimeError(
                f"Duplicate case study '{title}' but could not find it via caseStudies pagination."
            ) from e

        updated = await gql.update_case_study(
            input=CaseStudyUpdateWithOptionalIdsInput(
                id=existing_id,
                title=title,
                summary=cs.summary,
                url=(cs.url or None),
                source_type=source_type,
                episode_page_urls=episode_page_urls or None,   # ✅
                product_names=product_names or None,           # ✅
                compound_names=compound_names or None,         # ✅
            )
        )
        node = getattr(updated, "update_case_study", None)
        return node.id if node else existing_id


# -----------------------------------------------------------------------------
# Episode relations: guestIds + sponsorBusinessIds
# -----------------------------------------------------------------------------

async def attach_episode_guests_and_sponsors(
    gql: Client,
    *,
    episode_page_url: str,
    guest_names: List[str],
    sponsor_business_names: List[str],
) -> None:
    episode_id = await get_episode_id_by_page_url(gql, episode_page_url)
    if not episode_id:
        # episode might not exist yet; skip quietly
        return

    guest_ids: List[str] = []
    for n in _dedupe_str(guest_names):
        pid = await get_person_id_by_name(gql, n)
        if pid:
            guest_ids.append(pid)

    sponsor_business_ids: List[str] = []
    for bn in _dedupe_str(sponsor_business_names):
        bid = await get_business_id_by_name(gql, bn)
        if bid:
            sponsor_business_ids.append(bid)

    await gql.update_episode_relations(
        input=EpisodeUpdateRelationFieldsInput(
            id=episode_id,
            guest_ids=guest_ids or None,
            sponsor_business_ids=sponsor_business_ids or None,
        )
    )


# -----------------------------------------------------------------------------
# Main orchestrator: ingest one episode's ResearchEntities
# -----------------------------------------------------------------------------

async def ingest_entities_for_episode(
    gql: Client,
    entities: ResearchEntities,
    *,
    episode_page_url: str,
    use_compounds_nested: bool = False,
) -> Dict[str, Any]:
    """
    Recommended order:
    1) Upsert people (so guests exist)
    2) Upsert compounds (optional, but helps compoundByName resolve quickly)
    3) Upsert businesses (productNames + executivesNested only)
    4) Upsert products (requires businessId; uses compoundNames)
    5) Upsert case studies (productNames/compoundNames/episodePageUrls)
    6) Attach episode relations (guestIds + sponsorBusinessIds)
    """
    # 1) People
    person_ids: Dict[str, str] = {}
    for p in entities.people:
        if not (p.name or "").strip():
            continue
        pid = await upsert_person(gql, p)
        person_ids[_norm(p.name)] = pid

    # 2) Compounds (optional but useful)
    # Since product upserts only pass compoundNames, this ensures compounds exist/update.
    compound_ids: Dict[str, str] = {}
    for pr in entities.products:
        for c in pr.compounds:
            if not (c.name or "").strip():
                continue
            cid = await upsert_compound(gql, c)
            compound_ids[_norm(c.name)] = cid

    # 3) Businesses (create/update), but only with productNames + executivesNested (role only)
    business_ids: Dict[str, str] = {}
    for b in entities.businesses:
        if not (b.name or "").strip():
            continue

        # products linked by agent to this business
        linked_product_names = [
            pr.name for pr in entities.products
            if pr.business_name and _norm(pr.business_name) == _norm(b.name)
        ]

        # executivesNested only for people with role, and affiliated to this business
        execs: List[BusinessExecutiveNestedInput] = []
        for p in entities.people:
            if not p.role:
                continue
            if p.business_name and _norm(p.business_name) == _norm(b.name):
                execs.append(
                    BusinessExecutiveNestedInput(
                        name=p.name.strip(),
                        role=p.role.strip(),
                        title=p.role.strip(),  # you can refine later if you add separate title
                        media_links=_to_media_links(p.media_links),
                    )
                )

        bid = await upsert_business(
            gql,
            b,
            product_names=linked_product_names,
            executives_nested=execs,
        )
        business_ids[_norm(b.name)] = bid

    # 4) Products (requires businessId)
    product_ids: Dict[str, str] = {}
    for pr in entities.products:
        if not (pr.name or "").strip():
            continue
        if not pr.business_name:
            # If your schema requires businessId (it does), we must skip or choose a fallback.
            # Skipping is safer than attaching to wrong business.
            continue

        business_id = business_ids.get(_norm(pr.business_name))
        if not business_id:
            # If the business wasn't extracted in businesses[], try query by name.
            business_id = await get_business_id_by_name(gql, pr.business_name)

        if not business_id:
            continue  # cannot create product without businessId

        pid = await upsert_product(
            gql,
            pr,
            business_id=business_id,
            use_compounds_nested=use_compounds_nested,
        )
        product_ids[_norm(pr.name)] = pid

    # 5) Case studies
    case_study_ids: List[str] = []
    for cs in entities.case_studies:
        if not (cs.title or "").strip():
            continue
        csid = await upsert_case_study(
            gql,
            cs,
            episode_page_urls=[episode_page_url],
        )
        case_study_ids.append(csid)

    # 6) Attach episode guests + sponsors
    guest_names = [p.name for p in entities.people if p.is_guest and (p.name or "").strip()]

    # If you have better sponsor extraction later, replace this.
    sponsor_business_names = [b.name for b in entities.businesses if (b.name or "").strip()]

    await attach_episode_guests_and_sponsors(
        gql,
        episode_page_url=episode_page_url,
        guest_names=guest_names,
        sponsor_business_names=sponsor_business_names,
    )

    return {
        "episodePageUrl": episode_page_url,
        "businessIds": business_ids,
        "personIds": person_ids,
        "productIds": product_ids,
        "compoundIds": compound_ids,
        "caseStudyIds": case_study_ids,
        "notes": entities.extraction_notes,
    }


# -----------------------------------------------------------------------------
# Client factory using YOUR requested config
# -----------------------------------------------------------------------------

def make_graphql_client_from_env() -> Client:
    """
    Uses:
      graphql_auth_token = os.getenv("GRAPHQL_AUTH_TOKEN")
      graphql_url = os.getenv("GRAPHQL_LOCAL_URL") or "localhost:4000/graphql"
    """
    import os

    graphql_auth_token = os.getenv("GRAPHQL_AUTH_TOKEN")
    graphql_url = os.getenv("GRAPHQL_LOCAL_URL") or "http://localhost:4000/graphql"
    if graphql_url.startswith("localhost"):
        graphql_url = "http://" + graphql_url

    return Client(
        url=graphql_url,
        headers={"Authorization": f"Bearer {graphql_auth_token}"},
    )