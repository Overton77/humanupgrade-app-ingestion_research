from firecrawl import AsyncFirecrawl  
from tavily import AsyncTavilyClient 
import asyncio  
from langchain_community.tools import WikipediaQueryRun 
from langchain_community.utilities import WikipediaAPIWrapper   
from langchain.messages import ToolMessage     
from langchain.tools import tool, ToolRuntime
from typing import TypedDict  
from typing import Literal, List, Dict , Optional 
from langchain.agents.middleware import wrap_tool_call 





wikipedia_tool = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())   


@wrap_tool_call  
async def handle_tool_call_error(request, handler): 
    """   
    Handle the error of the tool call precipitating a retry. 
    """ 

    try: 
        return await handler(request) 

    except Exception as e: 
        return ToolMessage( 
            content=f"Tool Error: Please check your input and try again. {str(e)}", 
            tool_call_id=request.tool_call["id"]
        )




@tool(description="Get all of the urls from a base url") 
async def firecrawl_map(runtime: ToolRuntime, url: str, limit: int = 30, sitemap: Literal["include", "exclude"] = "include") -> List[str]:  
    pass 


