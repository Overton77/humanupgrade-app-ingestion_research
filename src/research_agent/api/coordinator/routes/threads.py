"""Thread management and conversation routes."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import List, Optional, AsyncIterator
import uuid
import json
import asyncio
from datetime import datetime 
from langchain_core.runnables import RunnableConfig 

from research_agent.models.mongo.threads import ConversationThreadDoc, MessageDoc
from research_agent.api.coordinator.schemas.threads import (
    CreateThreadRequest,
    CreateThreadResponse,
    ThreadSummary,
    ThreadDetail,
    ThreadDetailWithStats,
    ThreadStats,
    SendMessageRequest,
    MessageResponse,
)
from research_agent.services.coordinator_agent import (
    get_coordinator_agent,
    generate_thread_title,
)


router = APIRouter(prefix="/api/coordinator/threads", tags=["coordinator-threads"])


@router.post("", response_model=CreateThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(request: CreateThreadRequest):
    """Create a new conversation thread.
    
    Args:
        request: Optional initial message to start the conversation
        
    Returns:
        Thread ID and metadata for the newly created thread
    """
    thread_id = str(uuid.uuid4())
    
    # Generate title from first message or use default
    title = None
    if request.initial_message:
        title = generate_thread_title(request.initial_message)
    else:
        title = "New Conversation"
    
    # Create thread document
    thread = ConversationThreadDoc(
        thread_id=thread_id,
        agent_type="coordinator",
        title=title,
    )
    
    # Add initial message if provided
    if request.initial_message:
        await thread.add_message("user", request.initial_message)
    
    # Save to database
    await thread.save()
    
    return CreateThreadResponse(
        thread_id=thread.thread_id,
        created_at=thread.created_at.isoformat(),
        title=thread.title,
    )


@router.get("", response_model=List[ThreadSummary])
async def list_threads(
    limit: int = 20,
    skip: int = 0,
    agent_type: Optional[str] = "coordinator",
):
    """List conversation threads, most recent first.
    
    Args:
        limit: Maximum number of threads to return
        skip: Number of threads to skip (for pagination)
        agent_type: Filter by agent type (default: coordinator)
        
    Returns:
        List of thread summaries sorted by most recent activity
    """
    # Build query
    if agent_type:
        query = ConversationThreadDoc.find(
            ConversationThreadDoc.agent_type == agent_type
        )
    else:
        query = ConversationThreadDoc.find_all()
    
    # Execute query with sorting and pagination
    threads = await query.sort("-updated_at").skip(skip).limit(limit).to_list()
    
    # Convert to response format
    return [
        ThreadSummary(
            thread_id=thread.thread_id,
            title=thread.title or "Untitled",
            created_at=thread.created_at.isoformat(),
            updated_at=thread.updated_at.isoformat(),
            message_count=thread.get_message_count(),
            last_message_preview=thread.get_last_message_preview(),
        )
        for thread in threads
    ]


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: str,
    include_stats: bool = False,
):
    """Get full thread details with all messages.
    
    Args:
        thread_id: Unique thread identifier
        include_stats: If True, includes aggregate statistics (token usage, models used)
        
    Returns:
        Complete thread information including all messages (and optionally stats)
        
    Raises:
        HTTPException: 404 if thread not found
    """
    thread = await ConversationThreadDoc.find_one(
        ConversationThreadDoc.thread_id == thread_id
    )
    
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {thread_id} not found"
        )
    
    # Convert messages to response format
    def convert_message_content(content):
        """Convert message content to API response format.
        
        Ensures Pydantic models are converted to dicts for JSON serialization.
        """
        if isinstance(content, str):
            return content
        
        # Convert list of content blocks to list of dicts
        result = []
        for block in content:
            if isinstance(block, str):
                result.append(block)
            elif isinstance(block, dict):
                result.append(block)
            elif hasattr(block, 'model_dump'):
                # Convert Pydantic model to dict
                result.append(block.model_dump(exclude_none=True))
            else:
                result.append(block)
        return result
    
    messages = [
        MessageResponse(
            role=msg.role,
            content=convert_message_content(msg.content),
            timestamp=msg.timestamp.isoformat(),
            tool_calls=msg.tool_calls,
            tool_call_id=msg.tool_call_id,
            name=msg.name,
            # Enhanced metadata fields
            id=msg.id,
            additional_kwargs=msg.additional_kwargs if msg.additional_kwargs else None,
            response_metadata=msg.response_metadata,
            usage_metadata=msg.usage_metadata,
            invalid_tool_calls=msg.invalid_tool_calls,
        )
        for msg in thread.messages
    ]
    
    # Build response
    thread_detail = ThreadDetail(
        thread_id=thread.thread_id,
        title=thread.title or "Untitled",
        created_at=thread.created_at.isoformat(),
        updated_at=thread.updated_at.isoformat(),
        messages=messages,
    )
    
    # Optionally include stats
    if include_stats:
        token_stats = thread.get_total_tokens()
        model_info = thread.get_model_info()
        
        stats = ThreadStats(
            total_tokens=token_stats,
            models_used=model_info['models'],
            providers_used=model_info['providers'],
        )
        
        return ThreadDetailWithStats(
            **thread_detail.model_dump(),
            stats=stats,
        )
    
    return thread_detail


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(thread_id: str):
    """Delete a conversation thread.
    
    Args:
        thread_id: Unique thread identifier
        
    Raises:
        HTTPException: 404 if thread not found
    """
    thread = await ConversationThreadDoc.find_one(
        ConversationThreadDoc.thread_id == thread_id
    )
    
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {thread_id} not found"
        )
    
    await thread.delete()


@router.post("/{thread_id}/messages")
async def send_message(thread_id: str, request: SendMessageRequest):
    """Send a message and stream the agent's response.
    
    **Note**: This endpoint uses Server-Sent Events (SSE) and does NOT support
    Human-in-the-Loop (HITL) interrupts. For HITL-enabled conversations with
    research plan approval, use the WebSocket endpoint:
    `WS /api/coordinator/threads/{thread_id}/hitl`
    
    Supports multimodal messages with text and file/image attachments.
    
    Args:
        thread_id: Unique thread identifier
        request: Message content and optional attachments
        
    Returns:
        StreamingResponse with Server-Sent Events containing the agent's response
        
    Raises:
        HTTPException: 404 if thread not found
    """
    # Load thread
    thread = await ConversationThreadDoc.find_one(
        ConversationThreadDoc.thread_id == thread_id
    )
    
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread {thread_id} not found"
        )
    
    # Build message content (multimodal if attachments present)
    if request.attachments:
        # Create content blocks for multimodal message
        content_blocks = [{"type": "text", "text": request.content}]
        
        for attachment in request.attachments:
            block = {"type": attachment.type}
            if attachment.url:
                block["url"] = attachment.url
            if attachment.filename:
                block["filename"] = attachment.filename
            if attachment.mime_type:
                block["mime_type"] = attachment.mime_type
            if attachment.text:
                block["text"] = attachment.text
            content_blocks.append(block)
        
        await thread.add_message("user", content_blocks)
    else:
        # Simple text message
        await thread.add_message("user", request.content)
    
    # Stream agent response
    return StreamingResponse(
        stream_agent_response(thread, request.content),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        },
    )


async def stream_agent_response(
    thread: ConversationThreadDoc,
    user_message: str,
) -> AsyncIterator[str]:
    """Stream agent response as Server-Sent Events.
    
    Args:
        thread: Conversation thread document
        user_message: The user's message to respond to
        
    Yields:
        SSE-formatted strings containing response chunks
    """
    try:
        # Get agent (returns CompiledStateGraph from create_agent)
        agent = get_coordinator_agent()     

        

        

        
        
        # Get conversation history
        messages = await thread.get_langchain_messages()  

        thread_id: str = thread.thread_id 
 

      


        config: RunnableConfig = { 
            "configurable": {"thread_id": thread.thread_id}
        }  

        current_state = await agent.aget_state(config=config)  

        print(f"Current state: {current_state}")

        

    
        # TODO: Should we use langgraph persistence to pass in the full message history or rely on our Mongo Represenation 
        
        # Accumulate full response
        full_response = ""
        
        # Send thinking event
        yield f"data: {json.dumps({'type': 'thinking'})}\n\n"
        await asyncio.sleep(0.01)
        
        # Stream agent response using astream with "messages" mode
        # This will yield message chunks as they're generated 

        async for chunk in agent.astream(
            {"messages": messages},
            stream_mode="messages",  
            config=config,
        ):
            # chunk is a tuple of (message, metadata)
            if isinstance(chunk, tuple):
                message, metadata = chunk
            else:
                message = chunk
            
            # Check if this is an AI message with content
            if hasattr(message, 'content') and message.content:
                # Extract text content
                if isinstance(message.content, str):
                    content_text = message.content
                elif isinstance(message.content, list):
                    # Handle structured content
                    content_text = ""
                    for item in message.content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            content_text += item.get("text", "")
                        elif isinstance(item, str):
                            content_text += item
                else:
                    content_text = str(message.content)
                
                if content_text:
                    full_response += content_text
                    # Send content chunk
                    yield f"data: {json.dumps({'type': 'content', 'content': content_text})}\n\n"
                    await asyncio.sleep(0.01)
            
            # Check for tool calls
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool_call': tool_call})}\n\n"
                    await asyncio.sleep(0.01)
        
        # If no streaming chunks were generated, fall back to invoke
        if not full_response:
            result = await agent.ainvoke({"messages": messages})
            result_messages = result.get("messages", [])
            
            if result_messages:
                last_message = result_messages[-1]
                if hasattr(last_message, 'content'):
                    full_response = last_message.content
                    
                    # Send in chunks for better UX
                    chunk_size = 50
                    for i in range(0, len(full_response), chunk_size):
                        chunk = full_response[i:i + chunk_size]
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
                        await asyncio.sleep(0.01)
        
        # Save assistant message to thread (will be replaced with LangGraph sync)
        if full_response:
            await thread.add_message("assistant", full_response)
        
        # Sync messages from LangGraph state to MongoDB
        # This ensures we capture all the rich metadata (tokens, model info, etc.)
        try:
            final_state = await agent.aget_state(config)
            if final_state and final_state.values.get("messages"):
                # Sync from LangGraph state, replacing all messages to ensure consistency
                await thread.sync_from_langgraph_state(
                    final_state.values["messages"],
                    replace=True
                )
        except Exception as sync_error:
            # Log sync error but don't fail the request
            print(f"Warning: Failed to sync messages from LangGraph: {sync_error}")
        
        # Send completion event
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
    except Exception as e:
        # Send error event
        error_msg = str(e)
        yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"
        
        # Log error (in production, use proper logging)
        print(f"Error streaming agent response: {error_msg}")
