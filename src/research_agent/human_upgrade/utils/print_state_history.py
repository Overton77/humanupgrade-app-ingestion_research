from typing import Any, Dict, Iterable, Optional, List
from langchain_core.runnables import RunnableConfig
import asyncio
from research_agent.human_upgrade.utils.graph_namespaces import make_thread_id_from_episode_url, base_config, with_checkpoint_ns, NS_PARENT
from research_agent.human_upgrade.entity_research_graphs import make_research_parent_graph 
from research_agent.human_upgrade.utils.windows_event_loop_fix import ensure_selector_event_loop_on_windows 



def _safe_keys(d: Any) -> List[str]:
    if isinstance(d, dict):
        return sorted(list(d.keys()))
    return []

def _preview_values(values: Dict[str, Any], max_items: int = 8) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in list(values.keys())[:max_items]:
        v = values.get(k)
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, list):
            out[k] = f"list(len={len(v)})"
        elif isinstance(v, dict):
            out[k] = f"dict(keys={len(v)})"
        else:
            out[k] = type(v).__name__
    return out

def print_state_history(
    graph,
    config: RunnableConfig,
    *,
    limit: int = 30,
    show_values_preview: bool = True,
) -> None:
    """
    Print state history for a given graph+config. History is reverse chronological (newest first).
    """
    states = list(graph.get_state_history(config))  # ✅ no await
    if not states:
        print("No state history found for config:", config)
        return

    print(f"\n=== State history (newest first). total={len(states)} showing={min(limit, len(states))} ===")
    for i, snap in enumerate(states[:limit]):
        cfg = getattr(snap, "config", {}) or {}
        conf = (cfg.get("configurable") or {})
        checkpoint_id = conf.get("checkpoint_id")
        checkpoint_ns = conf.get("checkpoint_ns")
        thread_id = conf.get("thread_id")
        next_ = getattr(snap, "next", None)

        print(f"\n[{i}] thread_id={thread_id}")
        print(f"    checkpoint_ns={checkpoint_ns}")
        print(f"    checkpoint_id={checkpoint_id}")
        print(f"    next={next_}")

        if show_values_preview:
            values = getattr(snap, "values", {}) or {}
            print(f"    state_keys={_safe_keys(values)[:20]}")
            print(f"    preview={_preview_values(values)}")

if __name__ == "__main__":   
    ensure_selector_event_loop_on_windows()
    async def main():
        test_run_episode = "https://daveasprey.com/1296-qualia-greg-kelly/"
        thread_id = make_thread_id_from_episode_url(test_run_episode)

        cfg_base = base_config(thread_id=thread_id, user_id="dev")
        cfg_parent = with_checkpoint_ns(cfg_base, NS_PARENT)

        parent_graph = await make_research_parent_graph(cfg_parent)

        print_state_history(parent_graph, cfg_parent, limit=100)

    asyncio.run(main()) 