import asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

MCP_URL = "http://127.0.0.1:8932/mcp"

async def main():
    transport = StreamableHttpTransport(url=MCP_URL)

    async with Client(transport) as client:
        # 1) list tools
        tools = await client.list_tools()
        print("Tools:") 

        for t in tools: 
            print(t)

      

if __name__ == "__main__":
    asyncio.run(main())
