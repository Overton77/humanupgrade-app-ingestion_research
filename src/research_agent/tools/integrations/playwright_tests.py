import asyncio
from typing import List
from copy import deepcopy

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from research_agent.infrastructure.llm.base_models import gpt_5_mini
from langchain.agents.structured_output import ProviderStrategy
from langchain.agents import create_agent

load_dotenv()

class PodcastEpisodes(BaseModel):
    episode_urls: List[str] = Field(description="The URLs of the podcast episodes")

test_prompt = """Go to https://daveasprey.com/podcasts ..."""

MCP_URL = "http://127.0.0.1:8932/mcp"

client = MultiServerMCPClient(
    {"playwright": {"transport": "http", "url": MCP_URL}}
)

def ensure_object_properties(schema: dict) -> dict:
    s = deepcopy(schema)
    if isinstance(s, dict) and s.get("type") == "object":
        s.setdefault("properties", {})
        s.setdefault("required", [])
    return s

def patch_mcp_tool_metadata(tools):
    for t in tools:
        if hasattr(t, "metadata") and isinstance(t.metadata, dict):
            if "inputSchema" in t.metadata and isinstance(t.metadata["inputSchema"], dict):
                t.metadata["inputSchema"] = ensure_object_properties(t.metadata["inputSchema"])
    return tools

async def run_browser_executor(user_task: str) -> PodcastEpisodes:
    async with client.session("playwright") as session:
        tools = await load_mcp_tools(session)

        # Patch schemas for OpenAI tool validator
        tools = patch_mcp_tool_metadata(tools)

        # Optional: only pass the tools you need
        allow = {"browser_navigate", "browser_snapshot", "browser_click", "browser_wait_for"}
        tools = [t for t in tools if t.name in allow]

        agent = create_agent(
            gpt_5_mini,
            tools=tools,
            response_format=ProviderStrategy(PodcastEpisodes),
        )

        result = await agent.ainvoke({"messages": [{"role": "user", "content": user_task}]})
        return result["structured_response"]



async def run_browser_executor(user_task: str) -> PodcastEpisodes:
    async with client.session("playwright") as session:
        tools = await load_mcp_tools(session)

        # Patch schemas for OpenAI tool validator
        tools = patch_mcp_tool_metadata(tools)

        # Optional: only pass the tools you need
        allow = {"browser_navigate", "browser_snapshot", "browser_click", "browser_wait_for"}
        tools = [t for t in tools if t.name in allow]

        agent = create_agent(
            gpt_5_mini,
            tools=tools,
            response_format=ProviderStrategy(PodcastEpisodes),
        )

        result = await agent.ainvoke({"messages": [{"role": "user", "content": user_task}]})
        return result["structured_response"]
if __name__ == "__main__":
    out = asyncio.run(run_browser_executor(test_prompt))
    print(out.model_dump_json(indent=2))

