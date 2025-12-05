from langsmith import Client 
from dotenv import load_dotenv 
import os 
load_dotenv() 




def get_langsmith_client() -> Client: 
    return Client(api_key=os.getenv("LANGSMITH_API_KEY"))  

