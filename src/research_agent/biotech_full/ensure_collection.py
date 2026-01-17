import os
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME") or "human-upgrade"
QDRANT_URL = (os.getenv("QDRANT_URL") or "http://localhost:6333").rstrip("/")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")  # optional (do not use for http unless you want the warning)

VECTOR_SIZE = 1536
DISTANCE = models.Distance.COSINE

# Match your intended config
HNSW = models.HnswConfigDiff(
    m=16,
    ef_construct=128,
    full_scan_threshold=10_000,
)

OPTIMIZERS = models.OptimizersConfigDiff(
    default_segment_number=2,
    indexing_threshold=1,  # forces indexing early for small collections
)

WAL = models.WalConfigDiff(
    wal_capacity_mb=64,
    wal_segments_ahead=0,
)

def get_client() -> QdrantClient:
    # If you're using plain http locally, API key is optional.
    # Supplying an api_key over http triggers a warning but still works.
    kwargs = {"url": QDRANT_URL}
    if QDRANT_API_KEY:
        kwargs["api_key"] = QDRANT_API_KEY
    return QdrantClient(**kwargs)

def _collection_exists(client: QdrantClient, name: str) -> bool:
    cols = client.get_collections()
    return any(c.name == name for c in cols.collections)

def _read_vectors_config(info) -> tuple[Optional[int], Optional[models.Distance], Optional[models.HnswConfigDiff]]:
    """
    Handles both single vector and named vectors.
    Returns (size, distance, hnsw_config) best-effort.
    """
    existing = info.config.params.vectors

    if isinstance(existing, models.VectorParams):
        return existing.size, existing.distance, existing.hnsw_config

    # named vectors (dict-like)
    vmap = existing  # type: ignore[assignment]
    key = "default" if "default" in vmap else next(iter(vmap.keys()))
    vp = vmap[key]
    return vp.size, vp.distance, vp.hnsw_config

def ensure_qdrant_collection(*, recreate_on_mismatch: bool = False) -> None:
    client = get_client()

    desired_vectors = models.VectorParams(
        size=VECTOR_SIZE,
        distance=DISTANCE,
        hnsw_config=HNSW,
    )

    if not _collection_exists(client, COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=desired_vectors,
            optimizers_config=OPTIMIZERS,
            wal_config=WAL,
            on_disk_payload=False,
        )
        print(f"[qdrant] created collection: {COLLECTION_NAME}")
        return

    info = client.get_collection(collection_name=COLLECTION_NAME)
    existing_size, existing_distance, existing_hnsw = _read_vectors_config(info)

    mismatch = (
        existing_size != VECTOR_SIZE
        or existing_distance != DISTANCE
        or (existing_hnsw is None)  # treat missing HNSW as mismatch
        or (existing_hnsw.m != HNSW.m)
        or (existing_hnsw.ef_construct != HNSW.ef_construct)
        or (existing_hnsw.full_scan_threshold != HNSW.full_scan_threshold)
    )

    if mismatch:
        msg = (
            f"[qdrant] collection '{COLLECTION_NAME}' config mismatch:\n"
            f"  existing: size={existing_size}, distance={existing_distance}, hnsw={existing_hnsw}\n"
            f"  desired:  size={VECTOR_SIZE}, distance={DISTANCE}, hnsw={HNSW}\n"
        )
        if not recreate_on_mismatch:
            raise RuntimeError(msg + "Set RECREATE_ON_MISMATCH=1 to recreate (DELETES ALL POINTS).")

        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=desired_vectors,
            optimizers_config=OPTIMIZERS,
            wal_config=WAL,
            on_disk_payload=False,
        )
        print(msg + f"[qdrant] recreated collection (ALL DATA DELETED): {COLLECTION_NAME}")
        return

    print(f"[qdrant] collection OK: {COLLECTION_NAME} (size={existing_size}, distance={existing_distance})")

def ensure_qdrant_payload_indexes() -> None:
    client = get_client()

    def _try_create(field_name: str, schema: models.PayloadSchemaType) -> None:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=schema,
            )
            print(f"[qdrant] created payload index: {field_name}")
        except Exception as e:
            print(f"[qdrant] payload index '{field_name}' may already exist (ok): {e}")

    # keyword indexes
    _try_create("mongo_episode_id", models.PayloadSchemaType.KEYWORD)
    _try_create("episode_url", models.PayloadSchemaType.KEYWORD)
    _try_create("source", models.PayloadSchemaType.KEYWORD)
    _try_create("parent_mongo_episode_id", models.PayloadSchemaType.KEYWORD)

    # optional but recommended for windows
    _try_create("chunk_index", models.PayloadSchemaType.INTEGER)

def main():
    recreate = os.getenv("RECREATE_ON_MISMATCH", "0") == "1"
    ensure_qdrant_collection(recreate_on_mismatch=recreate)
    ensure_qdrant_payload_indexes()

if __name__ == "__main__":
    main()