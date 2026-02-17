"""Message-related schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class MessageCreate(BaseModel):
    """Schema for creating a new message."""
    role: str = Field(..., description="Message role: user, assistant, or tool")
    content: str = Field(..., description="Message content")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Tool calls made by the assistant"
    )
    tool_call_id: Optional[str] = Field(
        default=None,
        description="ID linking tool response to tool call"
    )
    name: Optional[str] = Field(
        default=None,
        description="Tool name for tool messages"
    )


class MessageRead(BaseModel):
    """Schema for reading a message."""
    role: str
    content: str
    timestamp: datetime
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    
    class Config:
        from_attributes = True
