from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List
from research_agent.human_upgrade.structured_outputs.enums_literals import SourceType

def utc_now() -> datetime:
    """Get the current UTC time."""
    return datetime.now(timezone.utc)

class SourceAttribution(BaseModel):
    """Tracks where a piece of information came from."""
    url: str = Field(..., description="Source URL or identifier (DOI, PMID)")
    source_type: SourceType = Field(
        default="OTHER",
        description="Type of source"
    )
    title: Optional[str] = Field(
        None, 
        description="Title of the source document/page"
    )
    retrieved_at: datetime = Field(
        default_factory=utc_now,
        description="When this source was retrieved"
    )


class TavilyCitation(BaseModel): 
    url: str = Field(..., description="The URL of the source")  
    title: str = Field(..., description="The title of the source")   
    published_date: Optional[str] = Field(None, description="The published date of the source")   
    score: Optional[float] = Field(None, description="The score of the source")    




class TavilyResultsSummary(BaseModel):  
    summary: str = Field(..., description="An extensive  summary of the search results")   
    citations: List[TavilyCitation] = Field(..., description="The citations of the search results")   


class FirecrawlCitation(BaseModel): 
    url: str = Field(..., description="The URL of the source")  
    title: str = Field(..., description="The title of the source")   
    published_date: Optional[str] = Field(None, description="The published date of the source")   
    score: Optional[float] = Field(None, description="The score of the source")    


class FirecrawlResultsSummary(BaseModel):  
    summary: str = Field(..., description="An extensive  summary of the search results")   
    citations: List[FirecrawlCitation] = Field(..., description="The citations of the search results")   


class GeneralCitation(BaseModel): 
    url: str = Field(..., description="The URL of the source")  
    title: str = Field(..., description="The title of the source")    
    description: Optional[str] = Field(None, description="The description of the source")    
    published_date: Optional[str] = Field(None, description="The published date of the source")    
    score: Optional[float] = Field(None, description="The score of the source")    



        