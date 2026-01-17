from pydantic import BaseModel, Field
from typing import Optional

class FileReference(BaseModel): 
    file_path: str = Field(..., description="The path to the file") 
    description: Optional[str] = Field(None, description="The description of the file")  
    bundle_id: str = Field(..., description="The bundle id of the file") 
    entity_key: str = Field(..., description="The entity key of the file") 