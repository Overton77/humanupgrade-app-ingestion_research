from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Tuple
import os
from urllib.parse import urlparse

import aioboto3
from mypy_boto3_s3 import S3Client
from dotenv import load_dotenv

load_dotenv()

AWS_PROFILE = os.getenv("AWS_PROFILE")
AWS_REGION = os.getenv("AWS_REGION")

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")


@asynccontextmanager
async def get_s3_client() -> AsyncIterator[S3Client]:
    """
    Yield an aioboto3 S3 client configured from env vars.

    Env vars used:
    - AWS_PROFILE (optional)
    - AWS_REGION
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY

    Usage:

        async with get_s3_client() as s3:
            resp = await s3.list_buckets()
    """
    # Session will use any combination of profile + explicit keys + region.
    session = aioboto3.Session(
        profile_name=AWS_PROFILE or None,
        aws_access_key_id=AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
        region_name=AWS_REGION or None,
    )

    async with session.client("s3") as client:
        yield client


def parse_s3_url(s3_url: str) -> Tuple[str, str]:
    """
    Parse an S3 HTTPS URL like:

        https://biohack-agent-transcripts-us-east-2.s3.amazonaws.com/transcripts-text/aa4b0d2449c576a8.txt

    Returns:
        (bucket_name, key)
    """
    parsed = urlparse(s3_url)

    # Example netloc: "biohack-agent-transcripts-us-east-2.s3.amazonaws.com"
    host_parts = parsed.netloc.split(".")
    if not host_parts:
        raise ValueError(f"Invalid S3 URL: {s3_url}")

    bucket = host_parts[0]  # "biohack-agent-transcripts-us-east-2"
    key = parsed.path.lstrip("/")  # "transcripts-text/aa4b0d2449c576a8.txt"

    if not bucket or not key:
        raise ValueError(f"Could not parse bucket/key from S3 URL: {s3_url}")

    return bucket, key


async def get_transcript_text_from_s3_url(s3_url: str) -> str:
    """
    Given an S3 HTTPS URL stored in s3TranscriptUrl, download and return the text.

    Example s3_url:
        https://biohack-agent-transcripts-us-east-2.s3.amazonaws.com/transcripts-text/aa4b0d2449c576a8.txt
    """
    bucket, key = parse_s3_url(s3_url)

    async with get_s3_client() as s3:
        resp = await s3.get_object(Bucket=bucket, Key=key)
        body = resp["Body"]  # StreamingBody (async)
        data: bytes = await body.read()

    return data.decode("utf-8")
