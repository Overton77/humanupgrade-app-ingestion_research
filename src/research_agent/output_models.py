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


class ResearchDirection(BaseModel): 
    research_topic: str = Field(
        ...,
        description="The direction of the research to be conducted."
    )  

    research_type: Union[Literal["general_web_search", "specific_web_search", "medical_db_search", "wikipedia_search"], List[str]] = Field(
        ...,
        description="The type of research to be conducted."
    )  

    research_depth: Literal["shallow", "medium", "deep"] = Field(
        ...,
        description="The depth of the research to be conducted."
    )    



    

class ResearchDirectionOutput(BaseModel):  

    research_directions: List[ResearchDirection] = Field(
        ...,
        description="The directions of the research to be conducted."
    )  

    