import os
import time
from qdrant_client import QdrantClient
from qdrant_client.http import models

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
COLLECTION = os.getenv("QDRANT_COLLECTION_NAME", "human-upgrade")

def client() -> QdrantClient:
    # If you’re on http://localhost, prefer no api_key to avoid warning (unless server requires it)
    if QDRANT_URL.startswith("http://") and QDRANT_API_KEY:
        print("[warn] API key over HTTP is insecure. Unset QDRANT_API_KEY for local dev or use HTTPS.")
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def main():
    c = client()

    info = c.get_collection(collection_name=COLLECTION)
    print(f"[before] status={info.status} optimizer_status={info.optimizer_status} points={info.points_count} indexed={info.indexed_vectors_count}")

    if info.status != "green":
        raise RuntimeError(
            f"Collection status is {info.status}. Optimizer is failing: {info.optimizer_status}. "
            "Fix Qdrant error first (likely recreate collection / wipe storage)."
        )

    c.update_collection(
        collection_name=COLLECTION,
        optimizers_config=models.OptimizersConfigDiff(
            indexing_threshold=1,
        ),
    )
    print("[patch] indexing_threshold=1")

    # poll
    for i in range(30):
        time.sleep(2)
        info2 = c.get_collection(collection_name=COLLECTION)
        print(f"[poll] status={info2.status} optimizer_status={info2.optimizer_status} points={info2.points_count} indexed={info2.indexed_vectors_count}")

        if info2.status != "green":
            raise RuntimeError(f"Optimizer error while indexing: {info2.optimizer_status}")

    print("[done] Note: indexed_vectors_count may be approximate; verify via search performance.")

if __name__ == "__main__":
    main()