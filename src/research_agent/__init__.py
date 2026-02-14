"""
Research Agent Package

CRITICAL: Windows Event Loop Fix
---------------------------------
This must be the FIRST thing that happens when importing research_agent.
Psycopg (async PostgreSQL driver) cannot use ProactorEventLoop on Windows.
We set the event loop policy immediately to ensure SelectorEventLoop is used.
"""
import sys

# Set event loop policy BEFORE any async imports or operations
if sys.platform.startswith("win"):
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
