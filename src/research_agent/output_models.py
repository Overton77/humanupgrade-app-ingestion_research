from typing import Optional, Literal, Union, List  
from pydantic import BaseModel, Field 


class GuestInfoModel(BaseModel):
    name: str = Field(
        ...,
        description="Full name of the primary guest for this episode."
    )
    description: str = Field(
        ...,
        description="1–2 sentence bio describing who the guest is and why they are relevant to this episode."
    )
    company: Optional[str] = Field(
        default=None,
        description="Company or organization most associated with the guest in this episode, if mentioned."
    )
    product: Optional[str] = Field(
        default=None,
        description="Key product, program, or offering associated with the guest in this episode, if mentioned."
    )


class TranscriptSummaryOutput(BaseModel):
    summary: str = Field(
        ...,
        description="A concise, episode-specific summary emphasizing human performance and longevity takeaways."
    )
    guest_information: GuestInfoModel = Field(
        ...,
        description="Structured information about the primary guest for this episode."
    )  



ResearchType = Literal["general", "medical", "casestudy"] 

class ResearchDirection(BaseModel):
    id: str
    topic: str
    description: str  
    overview: str              # what to investigate
    research_type: ResearchType   # "general" / "medical" / "casestudy"
    depth: Literal["shallow", "medium", "deep"] = "shallow"    
    priority: int = 1
    max_steps: int = 5    


    

class ResearchDirectionOutput(BaseModel):  

    research_directions: List[ResearchDirection] = Field(
        ...,
        description="The directions of the research to be conducted."
    )  

    