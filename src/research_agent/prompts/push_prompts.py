from langchain_core.prompts import PromptTemplate, ChatPromptTemplate 

from research_agent.clients.langsmith_client import push_prompt_to_langsmith  

from research_agent.human_upgrade.prompts.candidates_prompts import PROMPT_OUTPUT_A2_CONNECTED_CANDIDATE_SOURCES 
from research_agent.human_upgrade.prompts.seed_prompts import PROMPT_OUTPUT_A_SEED_EXTRACTION
from research_agent.human_upgrade.prompts.research_directions_prompts import PROMPT_OUTPUT_A3_ENTITY_RESEARCH_DIRECTIONS  
from dotenv import load_dotenv  

load_dotenv()   




prompts_dict = {  
    "seed_extraction_prompt": PROMPT_OUTPUT_A_SEED_EXTRACTION,
    "connected_candidate_sources_prompt": PROMPT_OUTPUT_A2_CONNECTED_CANDIDATE_SOURCES,
    "research_directions_prompt": PROMPT_OUTPUT_A3_ENTITY_RESEARCH_DIRECTIONS,
  


}   

def push_prompts_to_langsmith():
    for prompt_name, prompt in prompts_dict.items():
        push_prompt_to_langsmith(type="PromptTemplate", prompt=prompt, name=prompt_name)





if __name__ == "__main__":
    push_prompts_to_langsmith()