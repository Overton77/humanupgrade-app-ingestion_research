"""General-purpose conversation thread storage.

This module provides MongoDB models for storing conversational threads
compatible with LangChain's message format. These models are generic and
can be used by any agent or chat interface.
"""

from beanie import Document
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Optional, Any, Union, Literal
import base64
import mimetypes
from pathlib import Path


# Content block types for multimodal messages
class TextContentBlock(BaseModel):
    """Text content block."""
    type: Literal["text"] = "text"
    text: str


class ImageContentBlock(BaseModel):
    """Image content block."""
    type: Literal["image"] = "image"
    url: Optional[str] = None
    base64: Optional[str] = None
    mime_type: Optional[str] = None
    detail: Optional[str] = None  # "low", "high", "auto"


class FileContentBlock(BaseModel):
    """File content block (PDF, etc)."""
    type: Literal["file"] = "file"
    url: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    size: Optional[int] = None  # File size in bytes


ContentBlock = Union[TextContentBlock, ImageContentBlock, FileContentBlock, Dict[str, Any]]


class MessageDoc(BaseModel):
    """Individual message in a conversation (LangChain-compatible format).
    
    Supports multimodal content including text, images, and files.
    Enhanced to align with LangGraph's message structure for better UI rendering.
    
    Attributes:
        role: Message role - "user", "assistant", or "tool"
        content: The message content (can be string or list of content blocks for multimodal)
        tool_calls: Optional list of tool calls made by the assistant
        tool_call_id: Optional ID linking tool response to tool call
        name: Optional tool name for tool messages
        timestamp: When the message was created
        
        # LangGraph-aligned fields for rich metadata
        id: Optional message ID from LangGraph/LLM provider
        additional_kwargs: Extra metadata (provider-specific)
        response_metadata: Model response metadata (model, provider, timing, etc.)
        usage_metadata: Token usage information (input/output tokens, cache info)
        invalid_tool_calls: Failed or malformed tool calls
    """
    role: str  # "user" | "assistant" | "tool"
    content: Union[str, List[ContentBlock]]  # String for simple text, List for multimodal
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # Tool name for tool messages
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Enhanced fields aligned with LangGraph state
    id: Optional[str] = None  # Message ID from LangGraph or LLM provider
    additional_kwargs: Dict[str, Any] = Field(default_factory=dict)  # Provider-specific extras
    response_metadata: Optional[Dict[str, Any]] = None  # Model response info (provider, model, timing)
    usage_metadata: Optional[Dict[str, Any]] = None  # Token usage (input/output tokens, cache)
    invalid_tool_calls: Optional[List[Dict[str, Any]]] = None  # Failed tool calls
    
    def get_text_content(self) -> str:
        """Extract text content from message.
        
        Returns:
            Text content as string, combining all text blocks if multimodal.
        """
        if isinstance(self.content, str):
            return self.content
        
        # Extract text from content blocks
        text_parts = []
        for block in self.content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            elif hasattr(block, "type") and block.type == "text":
                text_parts.append(block.text)
        
        return " ".join(text_parts) if text_parts else ""
    
    def has_attachments(self) -> bool:
        """Check if message has file or image attachments.
        
        Returns:
            True if message contains non-text content blocks.
        """
        if isinstance(self.content, str):
            return False
        
        for block in self.content:
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type in ["image", "file"]:
                    return True
            elif hasattr(block, "type") and block.type in ["image", "file"]:
                return True
        
        return False


class ConversationThreadDoc(Document):
    """General-purpose conversation thread storage.
    
    Can be used for any agent/chat interface. Thread identity is based on thread_id.
    Messages follow LangChain's message format for easy integration.
    
    Attributes:
        thread_id: Unique thread identifier (UUID)
        agent_type: Optional agent/application identifier (e.g., 'coordinator')
        created_at: When the thread was created
        updated_at: When the thread was last modified
        messages: List of conversation messages
        title: Thread title (auto-generated or user-defined)
        checkpoint_id: LangGraph checkpoint ID for resuming conversations
        metadata: Custom metadata for specific use cases
    """
    
    # Thread identification
    thread_id: str = Field(..., unique=True, description="Unique thread identifier (UUID)")
    
    # Optional: Agent/application identifier
    agent_type: Optional[str] = Field(
        default=None,
        description="Type of agent/application (e.g., 'coordinator', 'assistant', etc.)"
    )
    
    # Thread metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Conversation messages
    messages: List[MessageDoc] = Field(default_factory=list)
    
    # Thread title (auto-generated or user-defined)
    title: Optional[str] = None
    
    # LangGraph checkpoint ID (for resuming conversations)
    checkpoint_id: Optional[str] = None
    
    # Optional: Custom metadata for specific use cases
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Settings:
        name = "conversation_threads"
        indexes = [
            "thread_id",
            "agent_type",
            "created_at",
            "updated_at",
        ]
    
    async def add_message(
        self,
        role: str,
        content: Union[str, List[ContentBlock]],
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
        # Enhanced LangGraph-aligned fields
        id: Optional[str] = None,
        additional_kwargs: Optional[Dict[str, Any]] = None,
        response_metadata: Optional[Dict[str, Any]] = None,
        usage_metadata: Optional[Dict[str, Any]] = None,
        invalid_tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Add a message to the thread.
        
        Args:
            role: Message role ("user", "assistant", or "tool")
            content: Message content (string or list of content blocks for multimodal)
            tool_calls: Optional list of tool calls
            tool_call_id: Optional tool call ID
            name: Optional tool name
            id: Optional message ID from LangGraph/LLM provider
            additional_kwargs: Extra metadata (provider-specific)
            response_metadata: Model response metadata (model, provider, timing)
            usage_metadata: Token usage information
            invalid_tool_calls: Failed or malformed tool calls
        """
        message = MessageDoc(
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            name=name,
            id=id,
            additional_kwargs=additional_kwargs or {},
            response_metadata=response_metadata,
            usage_metadata=usage_metadata,
            invalid_tool_calls=invalid_tool_calls,
        )
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
        await self.save()
    
    async def sync_from_langgraph_state(
        self,
        langgraph_messages: List[Any],
        replace: bool = False,
    ) -> None:
        """Sync messages from LangGraph state to MongoDB.
        
        This method helps synchronize the two persistence layers (Postgres LangGraph + Mongo).
        It extracts rich metadata from LangGraph messages and stores them in MongoDB.
        
        Args:
            langgraph_messages: Messages from LangGraph state (HumanMessage, AIMessage, ToolMessage, etc.)
            replace: If True, replaces all messages. If False, appends new messages.
        """
        from langchain_core.messages import BaseMessage
        
        if replace:
            self.messages = []
        
        for msg in langgraph_messages:
            # Skip if not a LangChain message
            if not isinstance(msg, BaseMessage):
                continue
            
            # Extract role from message type
            msg_type = type(msg).__name__
            if msg_type == "HumanMessage":
                role = "user"
            elif msg_type == "AIMessage":
                role = "assistant"
            elif msg_type == "ToolMessage":
                role = "tool"
            elif msg_type == "SystemMessage":
                role = "system"
            else:
                role = msg_type.lower().replace("message", "")
            
            # Extract content
            content = msg.content if hasattr(msg, 'content') else str(msg)
            
            # Create message doc
            message_doc = MessageDoc(
                role=role,
                content=content,
                tool_calls=getattr(msg, 'tool_calls', None),
                tool_call_id=getattr(msg, 'tool_call_id', None),
                name=getattr(msg, 'name', None),
                id=getattr(msg, 'id', None),
                additional_kwargs=getattr(msg, 'additional_kwargs', {}),
                response_metadata=getattr(msg, 'response_metadata', None),
                usage_metadata=getattr(msg, 'usage_metadata', None),
                invalid_tool_calls=getattr(msg, 'invalid_tool_calls', None),
            )
            
            self.messages.append(message_doc)
        
        self.updated_at = datetime.utcnow()
        await self.save()
    
    def get_total_tokens(self) -> Dict[str, int]:
        """Calculate total token usage across all messages.
        
        Returns:
            Dictionary with token counts: input_tokens, output_tokens, total_tokens
        """
        input_tokens = 0
        output_tokens = 0
        
        for msg in self.messages:
            if msg.usage_metadata:
                input_tokens += msg.usage_metadata.get('input_tokens', 0)
                output_tokens += msg.usage_metadata.get('output_tokens', 0)
        
        return {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
        }
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about models used in this conversation.
        
        Returns:
            Dictionary with model information from assistant messages
        """
        models_used = set()
        providers_used = set()
        
        for msg in self.messages:
            if msg.role == "assistant" and msg.response_metadata:
                model = msg.response_metadata.get('model') or msg.response_metadata.get('model_name')
                provider = msg.response_metadata.get('model_provider')
                
                if model:
                    models_used.add(model)
                if provider:
                    providers_used.add(provider)
        
        return {
            'models': list(models_used),
            'providers': list(providers_used),
        }
    
    @staticmethod
    def _convert_local_url_to_base64(block: Dict[str, Any]) -> Dict[str, Any]:
        """Convert local file URLs to base64 encoding or extract text content.
        
        OpenAI has specific requirements for file types:
        - Images: Support base64 encoding with type "image"
        - PDFs: Support base64 encoding with type "file"
        - Text files: Must be extracted and sent as type "text" content blocks
        
        This method checks if a content block has a local URL (starts with '/uploads/')
        and converts it appropriately based on the file type.
        
        Args:
            block: Content block dictionary
            
        Returns:
            Updated content block with base64/text content instead of local URL
        """
        # Only process image and file blocks with URLs
        if block.get("type") not in ["image", "file"]:
            return block
        
        url = block.get("url")
        if not url or not url.startswith("/uploads/"):
            # Not a local URL, return as-is
            return block
        
        # Convert relative path to absolute path
        # Assuming uploads are relative to the ingestion directory
        file_path = Path.cwd() / url.lstrip("/")
        
        if not file_path.exists():
            # File doesn't exist, return as-is (will likely cause an error downstream)
            print(f"Warning: File not found: {file_path}")
            return block
        
        try:
            mime_type = block.get("mime_type", "")
            
            # Check if this is a text-based file that OpenAI doesn't support as "file" type
            # OpenAI only supports PDF for "file" type, so we need to extract text content
            text_mime_types = {
                "text/plain",
                "text/markdown", 
                "text/csv",
                "application/json",
            }
            
            if mime_type in text_mime_types:
                # Read text content and convert to text block
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text_content = f.read()
                    
                    filename = block.get("filename", file_path.name)
                    
                    # Return as text content block with filename prefix
                    return {
                        "type": "text",
                        "text": f"[File: {filename}]\n\n{text_content}"
                    }
                except UnicodeDecodeError:
                    # If we can't decode as text, fall through to base64 handling
                    print(f"Warning: Could not decode {file_path} as text, using base64")
            
            # For images and PDFs, use base64 encoding
            with open(file_path, "rb") as f:
                file_data = f.read()
                base64_data = base64.b64encode(file_data).decode("utf-8")
            
            # Create new block with base64 data instead of URL
            new_block = block.copy()
            new_block.pop("url", None)  # Remove URL field
            new_block["base64"] = base64_data
            
            # Ensure mime_type is present (required for base64)
            if "mime_type" not in new_block:
                # Try to guess mime type from file extension
                guessed_mime_type, _ = mimetypes.guess_type(str(file_path))
                if guessed_mime_type:
                    new_block["mime_type"] = guessed_mime_type
            
            return new_block
            
        except Exception as e:
            print(f"Error converting file to base64: {e}")
            return block  # Return original block on error
    
    async def get_langchain_messages(self) -> List[Dict]:
        """Convert stored messages to LangChain format.
        
        Returns:
            List of dicts compatible with LangChain's message format.
        """
        def convert_content(content: Union[str, List[ContentBlock]]) -> Union[str, List[Dict[str, Any]]]:
            """Convert content to LangChain-compatible format.
            
            Converts local file URLs to base64 encoding since OpenAI cannot access local paths.
            
            Args:
                content: Message content (string or list of content blocks)
                
            Returns:
                String or list of dicts (Pydantic models converted to dicts)
            """
            if isinstance(content, str):
                return content
            
            # Convert list of content blocks to list of dicts
            result = []
            for block in content:
                if isinstance(block, str):
                    result.append(block)
                elif isinstance(block, dict):
                    result.append(self._convert_local_url_to_base64(block))
                elif isinstance(block, BaseModel):
                    # Convert Pydantic model to dict
                    block_dict = block.model_dump(exclude_none=True)
                    result.append(self._convert_local_url_to_base64(block_dict))
                else:
                    # Fallback for other types
                    result.append(block)
            return result
        
        return [
            {
                "role": msg.role,
                "content": convert_content(msg.content),
                **({"tool_calls": msg.tool_calls} if msg.tool_calls else {}),
                **({"tool_call_id": msg.tool_call_id} if msg.tool_call_id else {}),
                **({"name": msg.name} if msg.name else {}),
            }
            for msg in self.messages
        ]
    
    def get_message_count(self) -> int:
        """Get total message count.
        
        Returns:
            Number of messages in the thread.
        """
        return len(self.messages)
    
    def get_last_message_preview(self, max_length: int = 100) -> Optional[str]:
        """Get preview of last message.
        
        Args:
            max_length: Maximum length of preview text
            
        Returns:
            Preview of last message content, or None if no messages.
        """
        if not self.messages:
            return None
        
        last_msg = self.messages[-1]
        text_content = last_msg.get_text_content()
        
        if last_msg.has_attachments():
            return f"📎 {text_content[:max_length]}" if text_content else "📎 Attachment"
        
        return text_content[:max_length]
