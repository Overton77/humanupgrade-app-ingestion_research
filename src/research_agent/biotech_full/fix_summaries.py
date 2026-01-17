import asyncio
import ast
import json
from typing import Any, Dict, List, Optional, Tuple 
import os     
import re 

from bson import ObjectId
from bson.errors import InvalidId

from research_agent.retrieval.async_mongo_client import get_episodes_by_urls, episodes_collection


def _coerce_to_python(value: Any) -> Any:
    """
    summaryDetailed might be:
      - already a List[dict]
      - a JSON string
      - a Python repr string (what you pasted)
    Convert to a Python object when possible.
    """
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str):
        return value

    s = value.strip()
    if not s:
        return s

    # Try JSON first
    try:
        return json.loads(s)
    except Exception:
        pass

    # Fall back to Python literal (handles single quotes, True/False, etc.)
    try:
        return ast.literal_eval(s)
    except Exception:
        return value  # give up; caller will treat as unparseable


def extract_final_text_summary(summary_detailed: Any) -> Optional[str]:
    """
    Extract the final assistant text from the stored agent trace.
    We look for the last item where type == "text" and it has a "text" field.
    """
    obj = _coerce_to_python(summary_detailed)

    if isinstance(obj, dict):
        # Sometimes people store {"messages":[...]} style; handle it.
        if "messages" in obj and isinstance(obj["messages"], list):
            obj = obj["messages"]

    if not isinstance(obj, list):
        return None

    # scan from end for the last textual message blob
    for item in reversed(obj):
        if isinstance(item, dict) and item.get("type") == "text":
            txt = item.get("text")
            if isinstance(txt, str) and txt.strip():
                return txt.strip()

        # sometimes tool frameworks store {"content": "..."} or nested
        if isinstance(item, dict) and item.get("role") in ("assistant", "ai"):
            content = item.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

    return None


async def update_episode_summary_detailed(mongo_episode_id: Any, summary_detailed: str) -> None:
    """
    Save the final article-like summary into episode.summaryDetailed and persist to Mongo.
    """
    try:
        oid = ObjectId(mongo_episode_id)
    except (InvalidId, TypeError):
        oid = mongo_episode_id  # non-ObjectId _id

    await episodes_collection.update_one(
        {"_id": oid},
        {"$set": {"summaryDetailed": summary_detailed}},
    )


async def fix_summary_detailed_for_urls(episode_urls: List[str]) -> Tuple[List[str], List[str]]:
    """
    For each episode:
      - read current summaryDetailed (agent trace string)
      - extract final text
      - write it back to summaryDetailed
    Returns (updated_urls, skipped_urls).
    """
    episodes = await get_episodes_by_urls(episode_urls)

    updated: List[str] = []
    skipped: List[str] = []

    for ep in episodes:
        url = (ep.get("episodePageUrl") or "").strip()
        if not url:
            skipped.append("(missing episodePageUrl)")
            continue

        current = ep.get("summaryDetailed")

        final_text = extract_final_text_summary(current)
        if not final_text:
            skipped.append(url)
            continue

        # Optional: avoid rewriting if it already looks "clean"
        # (comment out if you want to force overwrite)
        if isinstance(current, str) and current.strip() == final_text:
            updated.append(url)
            continue

        await update_episode_summary_detailed(ep.get("_id"), final_text)
        updated.append(url)

    # Also include any URLs that were requested but not found in Mongo
    found_urls = { (ep.get("episodePageUrl") or "").strip() for ep in episodes }
    for u in episode_urls:
        if u.strip() and u.strip() not in found_urls:
            skipped.append(u.strip())

    return updated, skipped


# ---- Run it ----

episode_urls: list[str] = [
    "https://daveasprey.com/1303-nayan-patel/",
    "https://daveasprey.com/1302-nathan-bryan/",
    "https://daveasprey.com/1301-ewot/",
    "https://daveasprey.com/1296-qualia-greg-kelly/",
    "https://daveasprey.com/1295-ben-azadi/",
    "https://daveasprey.com/1293-darin-olien/",
    "https://daveasprey.com/1292-amitay-eshel-young-goose/",
    "https://daveasprey.com/1291-mte-jeff-boyd/",
    "https://daveasprey.com/1289-josh-axe/",
    "https://daveasprey.com/1330-energybits/",
    "https://daveasprey.com/1327-jim-murphy/",
    "https://daveasprey.com/1323-sulforaphane-curcumin-and-new-glp-1-drugs-biohacking-for-longevity/",
    "https://daveasprey.com/1315-stemregen/",
    "https://daveasprey.com/1311-biolongevity-labs/",
    "https://daveasprey.com/1352-roxiva/",
    "https://daveasprey.com/1353-vinia-bioharvest/",
]


async def main() -> None:
    updated, skipped = await fix_summary_detailed_for_urls(episode_urls)
    print(f"\n✅ Updated {len(updated)} episodes:")
    for u in updated:
        print("  -", u)

    print(f"\n⚠️ Skipped {len(skipped)} episodes (unparseable or not found):")
    for u in skipped:
        print("  -", u)


def _safe_filename_from_url(url: str) -> str:
    """
    Turn https://daveasprey.com/1296-qualia-greg-kelly/ into 1296-qualia-greg-kelly.txt
    """
    slug = url.strip().rstrip("/").split("/")[-1] or "episode"
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-")
    return f"{slug}.txt"


async def export_episode_summaries_to_txt(
    episode_urls: List[str],
    output_dir: str = "exports/summary_detailed_txt",
) -> None:
    """
    Fetch episodes by URL and write episode.summaryDetailed into one .txt file per episode.
    Skips missing/empty summaries and prints what happened.
    """
    os.makedirs(output_dir, exist_ok=True)

    episodes = await get_episodes_by_urls(episode_urls)

    found_urls = {(ep.get("episodePageUrl") or "").strip() for ep in episodes}
    for u in episode_urls:
        if u.strip() and u.strip() not in found_urls:
            print(f"⚠️ Not found in Mongo: {u}")

    wrote = 0
    skipped = 0

    for ep in episodes:
        url = (ep.get("episodePageUrl") or "").strip()
        if not url:
            skipped += 1
            print("⚠️ Skipped episode with missing episodePageUrl")
            continue

        summary = ep.get("summaryDetailed")
        if not isinstance(summary, str) or not summary.strip():
            skipped += 1
            print(f"⚠️ Skipped (missing/empty summaryDetailed): {url}")
            continue

        filename = _safe_filename_from_url(url)
        path = os.path.join(output_dir, filename)

        # Optional header for quick inspection
        content = f"EPISODE_URL: {url}\nMONGO_ID: {ep.get('_id')}\n\n{summary.strip()}\n"

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        wrote += 1
        print(f"✅ Wrote: {path}")

    print(f"\nDone. Wrote {wrote} files. Skipped {skipped} episodes.")

if __name__ == "__main__":
    # asyncio.run(main())  
    asyncio.run(export_episode_summaries_to_txt(episode_urls))
