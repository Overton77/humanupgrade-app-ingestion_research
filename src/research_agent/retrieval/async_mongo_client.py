from __future__ import annotations

import os 

from pymongo import AsyncMongoClient 

from pymongo.asynchronous.database import AsyncDatabase  # type: ignore[import]



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


