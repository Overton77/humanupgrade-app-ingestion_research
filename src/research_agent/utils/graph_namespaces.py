import hashlib
from langchain_core.runnables import RunnableConfig

# Use __ as delimiter to avoid LangGraph subgraph parsing quirks with ":".
DELIM = "__"

def make_thread_id_from_episode_url(url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"episode{DELIM}{h}"

# Top-level namespaces
NS_DIRECTIONS = f"entity_intel{DELIM}candidates_and_directions"
NS_PARENT = f"entity_intel{DELIM}parent"

def ns_bundle(bundle_id: str) -> str:
    return f"{NS_PARENT}{DELIM}bundle{DELIM}{bundle_id}"

def ns_direction(bundle_id: str, direction_type: str) -> str:
    return f"{NS_PARENT}{DELIM}bundle{DELIM}{bundle_id}{DELIM}direction{DELIM}{direction_type}"

def base_config(*, thread_id: str, user_id: str = "dev") -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id, "user_id": user_id}}

def with_checkpoint_ns(config: RunnableConfig, checkpoint_ns: str) -> RunnableConfig:
    c = dict(config or {})
    cfg = dict(c.get("configurable", {}))
    cfg["checkpoint_ns"] = checkpoint_ns
    c["configurable"] = cfg
    return c 

def ns_plan(plan_id: str) -> str:
    # optional: if later you want plan-level checkpoint namespaces
    return f"{NS_PARENT}{DELIM}plan{DELIM}{plan_id}"

def plan_thread_id(episode_url: str, plan_id: str) -> str:
    base = make_thread_id_from_episode_url(episode_url)
    return f"{base}{DELIM}plan{DELIM}{plan_id}"