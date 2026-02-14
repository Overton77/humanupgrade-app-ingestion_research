"""
Test Windows Event Loop Fix

Verifies that the Windows event loop policy is correctly set to WindowsSelectorEventLoopPolicy
to ensure compatibility with psycopg (async PostgreSQL driver).

The fix is applied at package initialization (research_agent/__init__.py) and should
work regardless of how the package is imported (CLI, script, or direct import).
"""
import sys
import asyncio
import pytest


class TestWindowsEventLoopFix:
    """Test that the Windows event loop policy is correctly configured."""
    
    def test_event_loop_policy_is_selector_on_windows(self):
        """
        Verify that WindowsSelectorEventLoopPolicy is set on Windows.
        
        This is critical for psycopg compatibility - ProactorEventLoop
        cannot be used with async psycopg operations.
        """
        if not sys.platform.startswith("win"):
            pytest.skip("Test only applies to Windows")
        
        # Import research_agent package to trigger __init__.py
        import research_agent
        
        # Get the current event loop policy
        policy = asyncio.get_event_loop_policy()
        
        # Verify it's WindowsSelectorEventLoopPolicy
        assert isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy), (
            f"Expected WindowsSelectorEventLoopPolicy but got {type(policy).__name__}. "
            "This will cause psycopg to fail with 'Psycopg cannot use the ProactorEventLoop' error."
        )
    
    def test_event_loop_is_selector_event_loop_on_windows(self):
        """
        Verify that the actual event loop created is SelectorEventLoop.
        
        This tests that not only is the policy set correctly, but that
        loops created from this policy are the correct type.
        """
        if not sys.platform.startswith("win"):
            pytest.skip("Test only applies to Windows")
        
        # Import research_agent package to trigger __init__.py
        import research_agent
        
        # Create a new event loop using the policy
        loop = asyncio.new_event_loop()
        
        try:
            # Verify it's a SelectorEventLoop (not ProactorEventLoop)
            assert isinstance(loop, asyncio.SelectorEventLoop), (
                f"Expected SelectorEventLoop but got {type(loop).__name__}. "
                "This will cause psycopg to fail."
            )
        finally:
            loop.close()
    
    @pytest.mark.asyncio
    async def test_psycopg_compatible_event_loop(self):
        """
        Verify that the event loop can be used with psycopg.
        
        This is a smoke test that checks the running event loop is compatible.
        We don't actually test psycopg connection (that requires a DB),
        but we verify the event loop type is correct.
        """
        if not sys.platform.startswith("win"):
            pytest.skip("Test only applies to Windows")
        
        # Import research_agent package to trigger __init__.py
        import research_agent
        
        # Get the running event loop
        loop = asyncio.get_running_loop()
        
        # On Windows with our fix, this should be a SelectorEventLoop
        assert not isinstance(loop, asyncio.ProactorEventLoop), (
            "Event loop is ProactorEventLoop! This will cause psycopg to fail. "
            "The fix in research_agent/__init__.py may not be working."
        )
        
        # It should be a SelectorEventLoop
        assert isinstance(loop, asyncio.SelectorEventLoop), (
            f"Expected SelectorEventLoop but got {type(loop).__name__}"
        )


class TestCrossplatformCompatibility:
    """Test that the fix doesn't break non-Windows platforms."""
    
    def test_non_windows_platforms_unchanged(self):
        """
        Verify that non-Windows platforms are not affected by the fix.
        
        The fix should only apply to Windows, other platforms should use
        their default event loop policy.
        """
        if sys.platform.startswith("win"):
            pytest.skip("Test only applies to non-Windows platforms")
        
        # Import research_agent package
        import research_agent
        
        # On non-Windows, policy should be the default
        policy = asyncio.get_event_loop_policy()
        
        # Should NOT be WindowsSelectorEventLoopPolicy
        assert not isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy), (
            "WindowsSelectorEventLoopPolicy should only be set on Windows"
        )


def test_package_imports_successfully():
    """
    Verify that the package can be imported without errors.
    
    This is a basic smoke test to ensure our __init__.py changes
    don't break package imports.
    """
    try:
        import research_agent
        assert research_agent is not None
    except Exception as e:
        pytest.fail(f"Failed to import research_agent package: {e}")


def test_taskiq_broker_imports_successfully():
    """
    Verify that the taskiq broker can be imported.
    
    This simulates what happens when the taskiq CLI imports the broker.
    If the event loop fix is working, this should succeed without errors.
    """
    try:
        from research_agent.infrastructure.queue.taskiq_broker import broker
        assert broker is not None
    except Exception as e:
        pytest.fail(f"Failed to import taskiq broker: {e}")


@pytest.mark.asyncio
async def test_langgraph_persistence_can_initialize():
    """
    Integration test: Verify that LangGraph persistence can initialize.
    
    This is the code path that was failing with the ProactorEventLoop error.
    We don't actually connect to a database (that requires env setup),
    but we verify that the imports work and the event loop is compatible.
    """
    if not sys.platform.startswith("win"):
        pytest.skip("Test only applies to Windows")
    
    try:
        # Import research_agent first to apply the fix
        import research_agent
        
        # This import path was in the error traceback
        from research_agent.infrastructure.storage.postgres.langgraph_persistence import (
            get_persistence
        )
        
        # If we get here without ImportError, the modules can be loaded
        assert get_persistence is not None
        
        # Verify event loop is correct type
        loop = asyncio.get_running_loop()
        assert isinstance(loop, asyncio.SelectorEventLoop), (
            "Event loop must be SelectorEventLoop for psycopg compatibility"
        )
        
    except ImportError as e:
        # This is OK - we might not have all dependencies installed
        pytest.skip(f"Could not import persistence module: {e}")
    except Exception as e:
        pytest.fail(f"Unexpected error: {e}")
