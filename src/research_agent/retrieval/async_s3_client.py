from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
import os 
import aioboto3
from pymongo import AsyncMongoClient 
from mypy_boto3_s3 import S3Client
from pymongo.asynchronous.database import AsyncDatabase  # type: ignore[import]

AWS_PROFILE =  os.getenv("AWS_PROFILE")
AWS_REGION = os.getenv("AWS_REGION")

# Adjust this to your URI (local dev example)
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("HU_DB_NAME")




@asynccontextmanager
async def get_s3_client() -> AsyncIterator[S3Client]:
    """
    Yield an aioboto3 S3 client configured for the admin-dev profile and us-east-2.
    Usage:

        async with get_s3_client() as s3:
            resp = await s3.list_buckets()
    """
    session = aioboto3.Session(
        profile_name=AWS_PROFILE,
        region_name=AWS_REGION,
    )

    async with session.client("s3") as client:
        yield client


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


