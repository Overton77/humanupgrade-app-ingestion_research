from tavily import AsyncTavilyClient  
from dotenv import load_dotenv 
import os 

load_dotenv() 

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") 

tavily_api_key = os.getenv("TAVILY_API_KEY") 
async_tavily_client = AsyncTavilyClient(api_key=tavily_api_key) 