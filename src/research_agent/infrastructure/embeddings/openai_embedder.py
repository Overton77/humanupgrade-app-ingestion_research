from langchain_openai import OpenAIEmbeddings  
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Sequence, Optional 
from dotenv import load_dotenv 
import os   

load_dotenv() 

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")  

default_embedding_dimension = 1536 

embeddings = OpenAIEmbeddings( 
    model="text-embedding-3-small", 
    dimensions=default_embedding_dimension, 
) 

@dataclass(frozen=True)
class EmbeddingConfig:
    batch_size: int = 128          # tune based on latency/cost
    max_concurrency: int = 4       # tune based on rate limits
    strip_text: bool = True        # remove leading/trailing whitespace


async def create_embeddings_async(
    texts: Sequence[str],
    *,
    embeddings: OpenAIEmbeddings,
    cfg: EmbeddingConfig = EmbeddingConfig(),
) -> List[List[float]]:
    """
    Async embeddings for many texts using LangChain OpenAIEmbeddings.
    Uses aembed_documents() under the hood. :contentReference[oaicite:4]{index=4}
    """
    if not texts:
        return []

    # Normalize inputs
    norm: List[str] = []
    for t in texts:
        t2 = (t or "")
        if cfg.strip_text:
            t2 = t2.strip()
        norm.append(t2)

    # Create index batches
    batches: List[tuple[int, List[str]]] = []
    for start in range(0, len(norm), cfg.batch_size):
        batches.append((start, norm[start : start + cfg.batch_size]))

    sem = asyncio.Semaphore(cfg.max_concurrency)
    out: List[Optional[List[List[float]]]] = [None] * len(batches)

    async def _run_one(i: int, start_idx: int, batch: List[str]) -> None:
        async with sem:
            vecs = await embeddings.aembed_documents(batch)
            out[i] = vecs

    tasks = [
        asyncio.create_task(_run_one(i, start, batch))
        for i, (start, batch) in enumerate(batches)
    ]
    await asyncio.gather(*tasks)

    # Stitch results back in order
    result: List[List[float]] = []
    for vecs in out:
        if vecs is None:
            raise RuntimeError("Embedding batch failed unexpectedly.")
        result.extend(vecs)

    if len(result) != len(texts):
        raise RuntimeError(f"Expected {len(texts)} embeddings, got {len(result)}")

    return result


async def create_query_embedding_async(
    query: str,
    *,
    embeddings: OpenAIEmbeddings,
) -> List[float]:
    """
    Async embedding for a single query using aembed_query(). :contentReference[oaicite:5]{index=5}
    """
    return await embeddings.aembed_query(query.strip())