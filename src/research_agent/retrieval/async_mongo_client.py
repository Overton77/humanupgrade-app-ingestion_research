from __future__ import annotations

import os 
from typing import Dict, Any, List, Optional
from pymongo import AsyncMongoClient 
from bson.objectid import ObjectId
from bson.errors import InvalidId
from pymongo.asynchronous.database import AsyncDatabase  # type: ignore[import]
from pymongo.asynchronous.collection import AsyncCollection  # type: ignore[import]



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