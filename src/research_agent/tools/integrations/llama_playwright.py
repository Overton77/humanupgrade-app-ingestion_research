import asyncio
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from llama_index.llms.openai import OpenAI
from llama_index.core.agent.workflow import FunctionAgent 
import os 

# MCP tooling
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec

load_dotenv() 

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") 


class PodcastEpisodes(BaseModel):
    episode_urls: List[str] = Field(description="The URLs of the podcast episodes")


TEST_PROMPT = """
Go to https://daveasprey.com/podcasts. Collect up to 20 unique podcast episode URLs from this page.
Initially, only about 6–10 episodes are visible, so you will need to click the “View More” button one or
more times to load additional episodes. Continue until you have either collected 20 episode URLs or no
more episodes can be loaded. Return the results as a clean list of absolute URLs with no duplicates.
""".strip()


# Docker MCP Gateway (streamable HTTP) endpoint you’re using
MCP_URL = "http://127.0.0.1:8932/mcp"

# If you instead have an SSE endpoint, it would look like:
# MCP_URL = "http://127.0.0.1:8932/sse"


async def main():
    # 1) Connect to MCP server and fetch tools
    # LlamaIndex MCP client + ToolSpec can turn an MCP server into a tool list. :contentReference[oaicite:2]{index=2}
    mcp_client = BasicMCPClient(MCP_URL)
    tool_spec = McpToolSpec(client=mcp_client)
    tools = await tool_spec.to_tool_list_async()

    # Optional: filter tools (uncomment to enable)
    # allowed_tools = {
    #     "browser_navigate",
    #     "browser_snapshot",
    #     "browser_click",
    #     "browser_wait_for",
    # }
    # tools = [t for t in tools if t.metadata.name in allowed_tools]

    print(f"Loaded {len(tools)} MCP tools")

    # 2) Create LlamaIndex agent with OpenAI LLM
    # LlamaIndex shows using FunctionAgent with tools + OpenAI(model=...). :contentReference[oaicite:3]{index=3}
    llm = OpenAI(model="gpt-5-mini")

    agent = FunctionAgent(
        tools=tools,
        llm=llm,
        system_prompt=(
            "You are a browser automation agent. Use the browser tools to navigate, load more content, "
            "and extract the requested URLs. Return only the requested output."
        ),
    )

    # 3) Run the prompt
    response = await agent.run(TEST_PROMPT)

    # response is usually a Response-like object; print text
    print("\n--- Agent response ---\n")
    print(str(response))


if __name__ == "__main__":
    asyncio.run(main())
