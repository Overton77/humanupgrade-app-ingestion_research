"""
Wiring tests for entity_candidates_research_directions_graph.

Goal: catch "dangling" node names / edges and enforce that the graph compiles.
"""

def test_entity_candidates_research_directions_graph_compiles(monkeypatch):
    # Import module under test
    from research_agent.human_upgrade import entity_candidates_research_directions_graph as mod

    # Patch persistence nodes to no-ops to avoid DB dependencies during compile.
    async def _noop(_state):
        return {}

    monkeypatch.setattr(mod, "persist_domain_catalogs_node", _noop)
    monkeypatch.setattr(mod, "persist_candidates_node", _noop)
    monkeypatch.setattr(mod, "persist_research_plans_node", _noop)

    builder = mod.build_entity_research_directions_builder()

    # If any node name is dangling / unknown, this should raise.
    graph = builder.compile()

    assert graph is not None


