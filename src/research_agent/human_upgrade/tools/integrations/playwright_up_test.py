# research_agent/human_upgrade/tools/integrations/playwright_proxy.py
import asyncio
import os

from fastmcp import FastMCP
from fastmcp.client.transports import StdioTransport


def build_proxy() -> FastMCP:
    backend = StdioTransport(
        command="npx",
        args=["@playwright/mcp@latest"],
        # Optional: pass env through explicitly (helps on Windows sometimes)
        env=os.environ.copy(),
    )
    return FastMCP.as_proxy(backend, name="playwright-proxy")


async def main():
    proxy = build_proxy()
    await proxy.run_async(transport="http", host="127.0.0.1", port=8932)


if __name__ == "__main__":
    asyncio.run(main())
