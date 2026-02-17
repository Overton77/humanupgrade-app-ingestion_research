"""Thread-related request and response schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List, Union, Dict, Any
from datetime import datetime


class CreateThreadRequest(BaseModel):
    """Request to create a new conversation thread."""
    initial_message: Optional[str] = Field(
        default=None,
        description="Optional first message to start the conversation"
    )


class CreateThreadResponse(BaseModel):
    """Response after creating a thread."""
    thread_id: str = Field(..., description="Unique thread identifier")
    created_at: str = Field(..., description="ISO timestamp when thread was created")
    title: Optional[str] = Field(default=None, description="Thread title")


class ThreadSummary(BaseModel):
    """Summary information for a thread in list view."""
    thread_id: str = Field(..., description="Unique thread identifier")
    title: str = Field(..., description="Thread title")
    created_at: str = Field(..., description="ISO timestamp when created")
    updated_at: str = Field(..., description="ISO timestamp when last updated")
    message_count: int = Field(..., description="Number of messages in thread")
    last_message_preview: Optional[str] = Field(
        default=None,
        description="Preview of the last message"
    )


class MessageResponse(BaseModel):
    """Individual message in a thread.
    
    Supports both simple text messages and multimodal messages with content blocks.
    Content can be either a string (for simple messages) or a list of content blocks
    (for multimodal messages with text, images, files, etc).
    
    Enhanced with LangGraph-aligned metadata for rich UI rendering.
    """
    role: str = Field(..., description="Message role: user, assistant, tool, or system")
    content: Union[str, List[Dict[str, Any]]] = Field(
        ..., 
        description="Message content (string for simple messages, list of content blocks for multimodal)"
    )
    timestamp: str = Field(..., description="ISO timestamp when message was created")
    
    # Core message fields
    tool_calls: Optional[List[dict]] = Field(
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
    
    # Enhanced metadata fields (aligned with LangGraph)
    id: Optional[str] = Field(
        default=None,
        description="Message ID from LangGraph or LLM provider"
    )
    additional_kwargs: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Provider-specific metadata"
    )
    response_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Model response metadata (model, provider, timing, status)"
    )
    usage_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Token usage information (input/output tokens, cache info)"
    )
    invalid_tool_calls: Optional[List[dict]] = Field(
        default=None,
        description="Failed or malformed tool calls"
    )


class ThreadDetail(BaseModel):
    """Detailed thread information with all messages."""
    thread_id: str = Field(..., description="Unique thread identifier")
    title: str = Field(..., description="Thread title")
    created_at: str = Field(..., description="ISO timestamp when created")
    updated_at: str = Field(..., description="ISO timestamp when last updated")
    messages: List[MessageResponse] = Field(..., description="All messages in the thread")


class ThreadStats(BaseModel):
    """Thread statistics and metadata."""
    total_tokens: Dict[str, int] = Field(
        ...,
        description="Token usage: input_tokens, output_tokens, total_tokens"
    )
    models_used: List[str] = Field(
        default_factory=list,
        description="List of models used in this conversation"
    )
    providers_used: List[str] = Field(
        default_factory=list,
        description="List of providers used (e.g., 'openai')"
    )


class ThreadDetailWithStats(ThreadDetail):
    """Thread detail with aggregate statistics."""
    stats: ThreadStats = Field(..., description="Conversation statistics")


class ContentBlockRequest(BaseModel):
    """Content block for multimodal messages."""
    type: str = Field(..., description="Block type: text, image, file")
    text: Optional[str] = Field(default=None, description="Text content")
    url: Optional[str] = Field(default=None, description="File/image URL")
    filename: Optional[str] = Field(default=None, description="Original filename")
    mime_type: Optional[str] = Field(default=None, description="MIME type")


class SendMessageRequest(BaseModel):
    """Request to send a message in a thread."""
    content: str = Field(..., description="Message text content")
    attachments: Optional[List[ContentBlockRequest]] = Field(
        default=None,
        description="Optional file/image attachments"
    )


class StreamEvent(BaseModel):
    """Server-Sent Event structure for streaming responses."""
    type: str = Field(..., description="Event type: content, tool_call, done, or error")
    content: Optional[str] = Field(default=None, description="Text content chunk")
    tool_call: Optional[dict] = Field(default=None, description="Tool call information")
    error: Optional[str] = Field(default=None, description="Error message if type is error")


# HITL WebSocket Schemas

class HITLActionRequest(BaseModel):
    """Request for human approval of a tool action."""
    name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(..., description="Tool arguments")
    description: str = Field(..., description="Description of the action requiring approval")


class HITLReviewConfig(BaseModel):
    """Configuration for reviewing a tool action."""
    action_name: str = Field(..., description="Name of the action being reviewed")
    allowed_decisions: List[str] = Field(
        ...,
        description="Allowed decision types: 'approve', 'edit', 'reject'"
    )


class HITLInterruptData(BaseModel):
    """Interrupt data sent when a tool requires approval."""
    action_requests: List[HITLActionRequest] = Field(
        ...,
        description="List of actions requiring approval"
    )
    review_configs: List[HITLReviewConfig] = Field(
        ...,
        description="Review configuration for each action"
    )


class HITLDecision(BaseModel):
    """User decision for a tool action."""
    type: str = Field(..., description="Decision type: 'approve', 'edit', or 'reject'")
    edited_action: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Edited action (for 'edit' type): {name: str, args: dict}"
    )
    message: Optional[str] = Field(
        default=None,
        description="Message explaining the decision (for 'reject' type)"
    )


class HITLDecisionRequest(BaseModel):
    """Request from client submitting a decision."""
    type: str = Field(default="decision", description="Message type")
    decisions: List[HITLDecision] = Field(
        ...,
        description="List of decisions, one per action under review"
    )


class HITLSendMessageRequest(BaseModel):
    """Request from client to send a message via WebSocket."""
    type: str = Field(default="send_message", description="Message type")
    content: str = Field(..., description="Message content")