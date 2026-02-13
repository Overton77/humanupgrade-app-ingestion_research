from typing import Any, Dict, List
from datetime import datetime

try:
    from bson.objectid import ObjectId
    from bson import Decimal128
    HAS_BSON = True
except ImportError:
    HAS_BSON = False

def _jsonable(obj: Any) -> Any:
    """Best-effort conversion to JSON-serializable types."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    # Handle MongoDB ObjectId
    if HAS_BSON and isinstance(obj, ObjectId):
        return str(obj)
    # Handle MongoDB Decimal128
    if HAS_BSON and isinstance(obj, Decimal128):
        return float(obj.to_decimal())
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(x) for x in obj]
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    # LangChain messages often have model_dump in v2; fallback:
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    # Last resort: string repr
    return str(obj)


def sanitize_mongo_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a MongoDB document (with ObjectIds, Decimal128, etc.) to a JSON-serializable dict.
    This is specifically for documents returned from PyMongo that need to be stored in LangGraph state.
    """
    if doc is None:
        return {}
    return _jsonable(doc)


def snapshot_to_dict(snap: Any) -> Dict[str, Any]:
    """
    Convert a LangGraph StateSnapshot to a JSONable dict.
    """
    # snap.config is a RunnableConfig-like dict
    cfg = getattr(snap, "config", {}) or {}
    values = getattr(snap, "values", {}) or {}
    next_ = getattr(snap, "next", None)
    created_at = getattr(snap, "created_at", None)

    return {
        "config": _jsonable(cfg),
        "checkpoint_id": _jsonable(cfg.get("configurable", {}).get("checkpoint_id")),
        "checkpoint_ns": _jsonable(cfg.get("configurable", {}).get("checkpoint_ns")),
        "thread_id": _jsonable(cfg.get("configurable", {}).get("thread_id")),
        "next": _jsonable(next_),
        "values": _jsonable(values),
        "created_at": _jsonable(created_at),
    }
