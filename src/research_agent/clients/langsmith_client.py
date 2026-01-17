from langsmith import Client, Cache 
from dotenv import load_dotenv 
import os 
from typing import Literal 
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate  
from typing import Union

load_dotenv() 


def get_langsmith_client(cache: bool = True, max_size: int = 1000, ttl_seconds=3600) -> Client: 
    return Client(api_key=os.getenv("LANGSMITH_API_KEY"), cache=Cache(max_size=max_size, ttl_seconds=ttl_seconds))  

def push_prompt_to_langsmith(type: Literal["ChatPromptTemplate", "PromptTemplate"], prompt: str, name: str): 
    client = get_langsmith_client()  
    prompt_to_push = None 

    if type == "ChatPromptTemplate": 
        prompt_to_push = ChatPromptTemplate.from_template(prompt) 
    elif type == "PromptTemplate":  
        prompt_to_push = PromptTemplate.from_template(prompt)   

    client.push_prompt(name, object=prompt_to_push)  


def pull_prompt_from_langsmith(name: str) -> Union[ChatPromptTemplate, PromptTemplate]:
    client = get_langsmith_client()  
    prompt = client.pull_prompt(name)  
    return prompt 