import sys
import asyncio

def ensure_selector_event_loop_on_windows() -> None:
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())