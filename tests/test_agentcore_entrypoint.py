"""
Tests for AWS AgentCore Entrypoint

Run with:
    pytest tests/test_agentcore_entrypoint.py -v
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any


class MockContext:
    """Mock AgentCore context object"""
    def __init__(self, session_id: str = "test-session-123"):
        self.session_id = session_id
        self.invocation_time = "2026-01-20T00:00:00Z"


@pytest.fixture
def mock_episode_data() -> Dict[str, Any]:
    """Mock episode data from MongoDB"""
    return {
        "_id": "test-episode-id",
        "episodePageUrl": "https://daveasprey.com/test-episode/",
        "webPageSummary": "Test episode summary about biotech topics",
        "guestName": "Dr. Test Guest",
    }


@pytest.fixture
def mock_research_directions() -> Dict[str, Any]:
    """Mock research directions output from Stage 1"""
    return {
        "bundles": [
            {
                "bundleId": "test-bundle-1",
                "guestDirection": {
                    "chosenDirection": {"name": "Dr. Test Guest"},
                    "requiredFields": ["professional_background", "expertise"],
                },
            }
        ]
    }


class TestAgentCoreEntrypoint:
    """Test suite for AgentCore entrypoint"""
    
    @patch('agentcore_entrypoint.get_episode')
    @patch('agentcore_entrypoint.entity_research_directions_subgraph')
    async def test_stage1_candidates_extraction(
        self,
        mock_subgraph,
        mock_get_episode,
        mock_episode_data
    ):
        """Test Stage 1: Candidate extraction and research directions"""
        from agentcore_entrypoint import run_stage1_candidates
        
        # Setup mocks
        mock_get_episode.return_value = mock_episode_data
        mock_subgraph.ainvoke = AsyncMock(return_value={
            "seed_extraction": {"guest_candidates": ["Guest 1", "Guest 2"]},
            "candidate_sources": {"connected": []},
            "research_directions": {"bundles": []},
        })
        
        # Execute
        result = await run_stage1_candidates(mock_episode_data)
        
        # Assertions
        assert "seed_extraction" in result
        assert "candidate_sources" in result
        assert "research_directions" in result
    
    
    @patch('agentcore_entrypoint.BundlesParentGraph')
    async def test_stage2_research_execution(
        self,
        mock_parent_graph,
        mock_episode_data,
        mock_research_directions
    ):
        """Test Stage 2: Research execution across bundles"""
        from agentcore_entrypoint import run_stage2_research
        
        # Setup mocks
        mock_parent_graph.ainvoke = AsyncMock(return_value={
            "final_reports": [],
            "file_refs": [],
            "completed_bundle_ids": ["test-bundle-1"],
        })
        
        # Execute
        result = await run_stage2_research(
            mock_episode_data,
            mock_research_directions
        )
        
        # Assertions
        assert "final_reports" in result
        assert "file_refs" in result
        assert "completed_bundle_ids" in result
    
    
    @patch('agentcore_entrypoint.get_episode')
    @patch('agentcore_entrypoint.entity_research_directions_subgraph')
    @patch('agentcore_entrypoint.BundlesParentGraph')
    async def test_full_workflow_integration(
        self,
        mock_parent_graph,
        mock_subgraph,
        mock_get_episode,
        mock_episode_data,
        mock_research_directions
    ):
        """Test full workflow: Stage 1 → Stage 2"""
        from agentcore_entrypoint import run_full_workflow
        
        # Setup mocks
        mock_get_episode.return_value = mock_episode_data
        
        mock_subgraph.ainvoke = AsyncMock(return_value={
            "seed_extraction": Mock(
                guest_candidates=["Guest 1"],
                business_candidates=[],
            ),
            "candidate_sources": Mock(connected=[]),
            "research_directions": Mock(bundles=[]),
        })
        
        mock_parent_graph.ainvoke = AsyncMock(return_value={
            "final_reports": [],
            "file_refs": [],
            "completed_bundle_ids": ["bundle-1"],
        })
        
        # Execute
        result = await run_full_workflow(
            "https://daveasprey.com/test-episode/"
        )
        
        # Assertions
        assert result["status"] == "success"
        assert "stage1" in result
        assert "stage2" in result
        assert result["episode_url"] == "https://daveasprey.com/test-episode/"
    
    
    def test_entrypoint_full_workflow_routing(self):
        """Test AgentCore entrypoint routes to full workflow"""
        from agentcore_entrypoint import agent_invocation
        
        payload = {
            "workflow": "full",
            "episode_url": "https://daveasprey.com/test-episode/",
        }
        context = MockContext()
        
        with patch('agentcore_entrypoint.run_full_workflow') as mock_workflow:
            mock_workflow.return_value = {"status": "success", "test": "data"}
            
            # Execute
            result = agent_invocation(payload, context)
            
            # Assertions
            assert result["status"] == "success"
            assert result["session_id"] == "test-session-123"
    
    
    def test_entrypoint_stage1_routing(self):
        """Test AgentCore entrypoint routes to Stage 1"""
        from agentcore_entrypoint import agent_invocation
        
        payload = {
            "workflow": "stage1",
            "episode_url": "https://daveasprey.com/test-episode/",
        }
        context = MockContext()
        
        with patch('agentcore_entrypoint.get_episode') as mock_get_episode, \
             patch('agentcore_entrypoint.run_stage1_candidates') as mock_stage1:
            
            mock_get_episode.return_value = {"test": "data"}
            mock_stage1.return_value = {"seed_extraction": {}}
            
            # Execute
            result = agent_invocation(payload, context)
            
            # Assertions
            assert result["status"] == "success"
            assert result["stage"] == "stage1_only"
    
    
    def test_entrypoint_missing_episode_url(self):
        """Test error handling when episode_url is missing"""
        from agentcore_entrypoint import agent_invocation
        
        payload = {"workflow": "full"}
        context = MockContext()
        
        # Execute
        result = agent_invocation(payload, context)
        
        # Assertions
        assert "error" in result
        assert "episode_url" in result["error"]
    
    
    def test_entrypoint_invalid_workflow_type(self):
        """Test error handling for invalid workflow type"""
        from agentcore_entrypoint import agent_invocation
        
        payload = {
            "workflow": "invalid",
            "episode_url": "https://test.com/",
        }
        context = MockContext()
        
        # Execute
        result = agent_invocation(payload, context)
        
        # Assertions
        assert "error" in result
        assert "invalid" in result["error"].lower()
        assert "valid_types" in result


@pytest.mark.integration
class TestAgentCoreIntegration:
    """Integration tests (require AgentCore dev server)"""
    
    @pytest.mark.skip(reason="Requires AgentCore dev server")
    def test_invoke_via_agentcore_cli(self):
        """Test invocation via agentcore CLI"""
        import subprocess
        
        payload = {
            "workflow": "stage1",
            "episode_url": "https://daveasprey.com/1296-qualia-greg-kelly/",
        }
        
        result = subprocess.run(
            ["agentcore", "invoke", "--dev", str(payload)],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        assert "success" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

