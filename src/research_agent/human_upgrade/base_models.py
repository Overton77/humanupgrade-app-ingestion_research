from langchain_openai import ChatOpenAI  
from langchain.chat_models import BaseChatModel
from dotenv import load_dotenv  

import os 


load_dotenv() 

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") 



gpt_5_mini: BaseChatModel = ChatOpenAI(  
    model="gpt-5-mini",
    temperature=0.0,
    max_retries=2, 
    use_responses_api=True, 
) 

gpt_5_nano: BaseChatModel = ChatOpenAI(   
    model="gpt-5-nano", 
    temperature=0.0, 
    max_retries=2,  
    use_responses_api=True,  
) 

gpt_5: BaseChatModel = ChatOpenAI(    
    model="gpt-5",  
    temperature=0.0,
    max_retries=2,
    use_responses_api=True,
) 

gpt_4_1: BaseChatModel = ChatOpenAI(   
    model="gpt-4.1",
    temperature=0.0,
    max_retries=2,
    use_responses_api=True,
)