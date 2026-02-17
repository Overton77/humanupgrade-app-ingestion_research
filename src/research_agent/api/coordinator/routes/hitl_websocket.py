"""WebSocket routes for Human-in-the-Loop (HITL) conversations.

This module provides WebSocket endpoints for real-time bidirectional communication
between the backend and frontend, enabling:
- Streaming agent responses
- Interrupt notifications for tool approval
- User decisions (approve/edit/reject)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional
import json
import logging
import asyncio
from langgraph.types import Command
from pydantic import BaseModel

from research_agent.models.mongo.threads import ConversationThreadDoc
from research_agent.api.coordinator.websocket_manager import hitl_manager
from research_agent.services.coordinator_agent import get_coordinator_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coordinator/threads", tags=["coordinator-hitl"])


@router.websocket("/{thread_id}/hitl")
async def hitl_websocket(websocket: WebSocket, thread_id: str):
    """WebSocket endpoint for HITL-enabled conversations.
    
    Handles bidirectional communication for:
    - Streaming agent responses
    - Interrupt notifications when tools require approval
    - User decisions (approve/edit/reject)
    
    Message Types (Client -> Server):
        - send_message: User sends a new message
            {"type": "send_message", "content": "message text"}
        - decision: User submits HITL decision
            {"type": "decision", "decisions": [{"type": "approve|edit|reject", ...}]}
    
    Message Types (Server -> Client):
        - thinking: Agent is processing
        - content: Streaming text content chunk
        - interrupt: Tool requires approval
        - waiting_for_decision: Waiting for user decision
        - resuming: Resuming after decision
        - done: Response complete
        - error: Error occurred
    
    Args:
        websocket: WebSocket connection
        thread_id: Unique thread identifier
    """
    # Verify thread exists
    thread = await ConversationThreadDoc.find_one(
        ConversationThreadDoc.thread_id == thread_id
    )
    if not thread:
        await websocket.close(code=1008, reason="Thread not found")
        logger.warning(f"WebSocket connection rejected - thread {thread_id} not found")
        return
    
    # Connect to manager
    await hitl_manager.connect(thread_id, websocket)
    
    # Track if we're currently streaming (to handle incoming messages during stream)
    streaming_task = None
    
    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "send_message":
                # User sent a new message - stream agent response
                user_message = data.get("content")
                
                if not user_message:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Message content is required"
                    })
                    continue
                
                # Add user message to thread
                await thread.add_message("user", user_message)
                
                # Stream response (with interrupt handling)
                # Run in background so we can continue receiving messages
                if streaming_task and not streaming_task.done():
                    await websocket.send_json({
                        "type": "error",
                        "error": "Already streaming a response"
                    })
                    continue
                
                streaming_task = asyncio.create_task(stream_with_hitl(websocket, thread))
            
            elif message_type == "decision":
                # User submitted HITL decision
                decisions = data.get("decisions")
                
                if not decisions:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Decisions are required"
                    })
                    continue
                
                logger.info(f"Submitting decision for thread {thread_id}: {decisions}")
                hitl_manager.submit_decision(thread_id, {"decisions": decisions})
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "error": f"Unknown message type: {message_type}"
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for thread {thread_id}")
        # Cancel streaming task if running
        if streaming_task and not streaming_task.done():
            streaming_task.cancel()
        hitl_manager.disconnect(thread_id)
    except Exception as e:
        logger.error(f"WebSocket error for thread {thread_id}: {e}", exc_info=True)
        # Cancel streaming task if running
        if streaming_task and not streaming_task.done():
            streaming_task.cancel()
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
        except:
            pass
        hitl_manager.disconnect(thread_id)


async def stream_with_hitl(websocket: WebSocket, thread: ConversationThreadDoc):
    """Stream agent response with HITL interrupt handling.
    
    This function:
    1. Streams agent response chunks to the client
    2. Checks for interrupts after streaming completes
    3. If interrupt found, waits for user decision
    4. Resumes agent with decision and continues streaming
    
    Args:
        websocket: WebSocket connection
        thread: Conversation thread document
    """
    agent = get_coordinator_agent()
    config = {"configurable": {"thread_id": thread.thread_id}}
    messages = await thread.get_langchain_messages()
    
    # Send thinking event
    await websocket.send_json({"type": "thinking"})
    
    full_response = ""
    
    try:
        # Stream agent response
        logger.info(f"Starting agent stream for thread {thread.thread_id}")
        async for chunk in agent.astream(
            {"messages": messages},
            stream_mode="messages",
            config=config,
        ):
            if isinstance(chunk, tuple):
                message, metadata = chunk
            else:
                message = chunk
            
            # Stream content
            if hasattr(message, 'content') and message.content:
                content_text = extract_content_text(message.content)
                if content_text:
                    full_response += content_text
                    await websocket.send_json({
                        "type": "content",
                        "content": content_text
                    })
        
        logger.info(f"Agent stream completed for thread {thread.thread_id}")
        
        # Check for interrupt
        final_state = await agent.aget_state(config)
        
        # Check if there are pending nodes (indicates interrupt)
        if final_state.next and len(final_state.next) > 0:
            logger.info(f"Checking for interrupt in thread {thread.thread_id}, next nodes: {final_state.next}")
            
            # Look for __interrupt__ in state values first
            interrupt_data = final_state.values.get("__interrupt__")
            
            # If not in values, check tasks for interrupts
            if not interrupt_data and final_state.tasks:
                for task in final_state.tasks:
                    if hasattr(task, 'interrupts') and task.interrupts:
                        # Get the first interrupt
                        interrupt_data = task.interrupts[0].value if task.interrupts else None
                        break

            logger.info(f"Interrupt data: {interrupt_data}")
            logger.info(f"Final state tasks: {final_state.tasks}")
            logger.info(f"Final state values keys: {list(final_state.values.keys())}")
            
            if interrupt_data:
                logger.info(f"Interrupt detected for thread {thread.thread_id}")
                
                # HITL middleware returns interrupt as a list of Interrupt objects
                # Each Interrupt has a 'value' field with 'action_requests' and 'review_configs'
                # We need to extract the actual interrupt payload
                if isinstance(interrupt_data, list) and len(interrupt_data) > 0:
                    # Get the first interrupt's value
                    first_interrupt = interrupt_data[0]
                    if hasattr(first_interrupt, 'value'):
                        interrupt_payload = first_interrupt.value
                    else:
                        interrupt_payload = first_interrupt
                else:
                    interrupt_payload = interrupt_data
                
                # Serialize interrupt payload to JSON-compatible format
                serialized_payload = serialize_interrupt_data(interrupt_payload)
                logger.info(f"Interrupt payload (serialized): {serialized_payload}")
                
                # Send interrupt notification
                await hitl_manager.send_interrupt(thread.thread_id, serialized_payload)
                
                # Notify user we're waiting
                await websocket.send_json({
                    "type": "waiting_for_decision",
                    "message": "Waiting for your approval..."
                })
                
                # Wait for user decision (with 5 minute timeout)
                decision = await hitl_manager.wait_for_decision(thread.thread_id, timeout=300)
                
                logger.info(f"Decision received for thread {thread.thread_id}: {decision}")
                
                # Notify user we're resuming
                await websocket.send_json({
                    "type": "resuming",
                    "message": "Resuming with your decision..."
                })
                
                # Resume agent with decision and continue streaming
                async for chunk in agent.astream(
                    Command(resume=decision),
                    stream_mode="messages",
                    config=config,
                ):
                    if isinstance(chunk, tuple):
                        message, metadata = chunk
                    else:
                        message = chunk
                    
                    if hasattr(message, 'content') and message.content:
                        content_text = extract_content_text(message.content)
                        if content_text:
                            full_response += content_text
                            await websocket.send_json({
                                "type": "content",
                                "content": content_text
                            })
                
                logger.info(f"Agent resumed and completed for thread {thread.thread_id}")
        
        # Save assistant response to thread
        if full_response:
            await thread.add_message("assistant", full_response)
        
        # Sync messages from LangGraph state to MongoDB
        # This ensures we capture all the rich metadata (tokens, model info, etc.)
        try:
            final_state = await agent.aget_state(config)
            if final_state and final_state.values.get("messages"):
                await thread.sync_from_langgraph_state(
                    final_state.values["messages"],
                    replace=True
                )
        except Exception as sync_error:
            # Log sync error but don't fail the request
            logger.error(f"Failed to sync messages from LangGraph for thread {thread.thread_id}: {sync_error}")
        
        # Send completion event
        await websocket.send_json({"type": "done"})
        
    except Exception as e:
        logger.error(f"Error streaming agent response for thread {thread.thread_id}: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })


def serialize_interrupt_data(data):
    """Serialize interrupt data to JSON-compatible format.
    
    Handles Pydantic models, lists, dicts, and other types.
    
    Args:
        data: Interrupt data to serialize
        
    Returns:
        JSON-serializable data
    """
    if data is None:
        return None
    
    # Handle Pydantic models
    if isinstance(data, BaseModel):
        return data.model_dump()
    
    # Handle lists
    if isinstance(data, list):
        return [serialize_interrupt_data(item) for item in data]
    
    # Handle dicts
    if isinstance(data, dict):
        return {k: serialize_interrupt_data(v) for k, v in data.items()}
    
    # Handle objects with __dict__
    if hasattr(data, '__dict__'):
        return serialize_interrupt_data(data.__dict__)
    
    # Return as-is for primitives
    return data


def extract_content_text(content) -> str:
    """Extract text from message content.
    
    Handles different content formats:
    - String: Return as-is
    - List of content blocks: Extract text from text blocks
    - Other: Convert to string
    
    Args:
        content: Message content in various formats
        
    Returns:
        Extracted text content
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text = ""
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text += item.get("text", "")
            elif isinstance(item, str):
                text += item
        return text
    return str(content)
