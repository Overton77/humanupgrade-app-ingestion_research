from __future__ import annotations

import os 
import asyncio
from typing import Dict, Any, List, Optional
from pymongo import AsyncMongoClient 
from bson.objectid import ObjectId
from bson.errors import InvalidId
from pymongo.asynchronous.database import AsyncDatabase  # type: ignore[import]
from pymongo.asynchronous.collection import AsyncCollection  # type: ignore[import] 

from dotenv import load_dotenv 

load_dotenv()  



# Adjust this to your URI (local dev example)
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("HU_DB_NAME")






# --- MongoDB (PyMongo Async) --- #

def create_mongo_client() -> AsyncMongoClient:
    """
    Create an AsyncMongoClient.

    Keep this as a singleton at app level (e.g. FastAPI startup)
    and reuse it instead of creating a new one per request.
    """
    client: AsyncMongoClient = AsyncMongoClient(MONGO_URI)
    return client


def get_humanupgrade_db(client: AsyncMongoClient) -> AsyncDatabase:
    """
    Return the 'humanupgrade' AsyncDatabase from the given client.
    """
    db: AsyncDatabase = client[MONGO_DB_NAME]
    return db


_client: AsyncMongoClient = create_mongo_client() 

_humanupgrade_db: AsyncDatabase = get_humanupgrade_db(_client) 

episodes_collection: AsyncCollection = _humanupgrade_db["episodes"]  


EpisodeDoc = Dict[str, Any]

async def get_episodes(
    limit: int = 50,
    offset: int = 0,
) -> List[EpisodeDoc]:
    """
    Fetch a page of episodes using limit/offset pagination.
    """
    cursor = (
        episodes_collection
        .find({})
        .skip(offset)
        .limit(limit)
        .sort("_id", 1)
    )

    episodes: List[EpisodeDoc] = []
    async for doc in cursor:
        episodes.append(doc)
    return episodes  

async def get_episodes_by_urls( 
    urls: list[str]
) -> List[Dict[str, Any]]: 
    query: Dict[str, Any] = {"episodePageUrl": {"$in": urls}}
    cursor = episodes_collection.find(query)
    episodes: List[Dict[str, Any]] = []
    async for doc in cursor:
        episodes.append(doc)
    return episodes   

async def get_episode(
    episode_id: Optional[str] = None,
    episode_page_url: Optional[str] = None,
) -> Optional[EpisodeDoc]:
    """
    Fetch a single episode by MongoDB _id or by episodePageUrl.
    Exactly one of episode_id or episode_page_url must be provided.
    """
    if (episode_id is None) == (episode_page_url is None):
        raise ValueError("Provide exactly one of episode_id or episode_page_url")

    query: Dict[str, Any]

    if episode_id is not None:
        try:
            oid = ObjectId(episode_id)
        except InvalidId:
            raise ValueError(f"Invalid ObjectId: {episode_id}")
        query = {"_id": oid}
    else:
        query = {"episodePageUrl": episode_page_url}

    return await episodes_collection.find_one(query)


# --- Script to export episode summaries --- #

async def get_episodes_with_summaries(
    limit: int = 100,
    offset: int = 0,
) -> List[EpisodeDoc]:
    """
    Fetch episodes that have a webPageSummary with at least 1 character.
    Uses MongoDB $expr with $strLenCP to check string length.
    """
    query: Dict[str, Any] = {
        "$expr": {
            "$gte": [
                {"$strLenCP": {"$ifNull": ["$webPageSummary", ""]}},
                1
            ]
        }
    }
    
    cursor = (
        episodes_collection
        .find(query)
        .skip(offset)
        .limit(limit)
        .sort("_id", 1)
    )
    
    episodes: List[EpisodeDoc] = []
    async for doc in cursor:
        episodes.append(doc)
    return episodes


async def export_episode_summaries(output_file: str = "episode_summaries.txt"):
    """
    Export webPageSummary, episodePageUrl, and _id for all episodes that have
    a non-empty webPageSummary (length >= 1 character).
    """
    print(f"Fetching episodes with non-empty webPageSummary from database...")
    
    # Fetch all episodes with summaries in batches
    all_episodes: List[EpisodeDoc] = []
    batch_size = 100
    offset = 0
    
    while True:
        batch = await get_episodes_with_summaries(limit=batch_size, offset=offset)
        if not batch:
            break
        all_episodes.extend(batch)
        offset += batch_size
        print(f"Fetched {len(all_episodes)} episodes with summaries so far...")
    
    print(f"Total episodes with summaries found: {len(all_episodes)}")
    print(f"Writing to {output_file}...")
    
    with open(output_file, "w", encoding="utf-8") as f:
        for idx, episode in enumerate(all_episodes, 1):
            # Get _id if present
            episode_id = episode.get("_id")
            episode_id_str = str(episode_id) if episode_id else "N/A"
            
            # Get episodePageUrl if present
            episode_url = episode.get("episodePageUrl", "N/A")
            
            # Get webPageSummary (should always exist and be non-empty due to query)
            web_page_summary = episode.get("webPageSummary", "")
            
            # Write episode header
            f.write("=" * 80 + "\n")
            f.write(f"Episode #{idx}\n")
            f.write("=" * 80 + "\n")
            
            # Write ID if present
            if episode_id:
                f.write(f"ID: {episode_id_str}\n")
            
            # Write URL if present
            if episode_url != "N/A":
                f.write(f"URL: {episode_url}\n")
            
            # Write summary
            f.write("-" * 80 + "\n")
            f.write("Summary:\n")
            f.write("-" * 80 + "\n")
            f.write(f"{web_page_summary}\n")
            f.write("\n\n")
    
    print(f"Successfully exported {len(all_episodes)} episodes to {output_file}")


if __name__ == "__main__":
    asyncio.run(export_episode_summaries())