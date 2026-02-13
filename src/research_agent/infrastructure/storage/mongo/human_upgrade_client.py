from __future__ import annotations

import os 

from pymongo import AsyncMongoClient  
from bson.objectid import ObjectId
from bson.errors import InvalidId
from typing import Dict, Any, List, Optional

from pymongo.asynchronous.database import AsyncDatabase  # type: ignore[import]
from pymongo.asynchronous.collection import AsyncCollection  # type: ignore[import]  
from research_agent.infrastructure.storage.mongo.base_client import mongo_client 
from dotenv import load_dotenv 

load_dotenv()  

MONGO_DB_NAME = os.getenv("HU_DB_NAME") 


def get_humanupgrade_db(client: AsyncMongoClient) -> AsyncDatabase:
    """
    Return the 'humanupgrade' AsyncDatabase from the given client.
    """
    db: AsyncDatabase = client[MONGO_DB_NAME]
    return db




humanupgrade_db: AsyncDatabase = get_humanupgrade_db(mongo_client) 

episodes_collection: AsyncCollection = humanupgrade_db["episodes"]   


# TODO: Episode collection helpers while we test. Transitioning to Neo4j right after refactoring 
# TODO: Fast API Server, Rabbit MQ Taskiq Workers and Single and MultiGraph execution flow minimally implemented.  




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
