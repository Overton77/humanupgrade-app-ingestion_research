import os
from qdrant_client import QdrantClient

COLLECTION = "human-upgrade"

client = QdrantClient(url=os.getenv("QDRANT_URL") or "http://localhost:6333")

def get_unique_episode_urls(collection_name: str, batch_size: int = 512) -> set[str]:
    unique: set[str] = set()
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        if not points:
            break

        for p in points:
            payload = p.payload or {}

            # LangChain/QdrantVectorStore commonly nests your metadata like this:
            meta = payload.get("metadata") or {}
            if isinstance(meta, dict):
                url = meta.get("episode_url")
                if isinstance(url, str) and url.strip():
                    unique.add(url.strip())

        if offset is None:
            break

    return unique

urls = get_unique_episode_urls(COLLECTION)
print(f"Unique episode_url count: {len(urls)}")
for u in sorted(urls):
    print(u)