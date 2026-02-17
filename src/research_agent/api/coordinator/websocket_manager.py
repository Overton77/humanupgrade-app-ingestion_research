"""WebSocket Manager for Human-in-the-Loop (HITL) notifications.

This manager handles WebSocket connections for real-time HITL approval workflows,
enabling bidirectional communication between the backend and frontend for research
plan approval decisions.
"""

from fastapi import WebSocket
from typing import Dict, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)


class HITLWebSocketManager:
    """Manages WebSocket connections for HITL notifications.
    
    This manager:
    - Maintains active WebSocket connections per thread
    - Sends interrupt notifications to connected clients
    - Waits for user decisions with configurable timeout
    - Handles connection lifecycle and cleanup
    """
    
    def __init__(self):
        # thread_id -> WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}
        # thread_id -> decision future (for waiting)
        self.pending_decisions: Dict[str, asyncio.Future] = {}
    
    async def connect(self, thread_id: str, websocket: WebSocket):
        """Accept and register a new WebSocket connection.
        
        Args:
            thread_id: Unique thread identifier
            websocket: WebSocket connection to register
        """
        await websocket.accept()
        self.active_connections[thread_id] = websocket
        logger.info(f"WebSocket connected for thread {thread_id}")
    
    def disconnect(self, thread_id: str):
        """Disconnect and clean up a WebSocket connection.
        
        Args:
            thread_id: Unique thread identifier
        """
        self.active_connections.pop(thread_id, None)
        # Cancel pending decision if exists
        if thread_id in self.pending_decisions:
            future = self.pending_decisions.pop(thread_id)
            if not future.done():
                future.cancel()
        logger.info(f"WebSocket disconnected for thread {thread_id}")
    
    def is_connected(self, thread_id: str) -> bool:
        """Check if a WebSocket is connected for a thread.
        
        Args:
            thread_id: Unique thread identifier
            
        Returns:
            True if connected, False otherwise
        """
        return thread_id in self.active_connections
    
    async def send_json(self, thread_id: str, data: dict):
        """Send JSON data to a connected WebSocket.
        
        Args:
            thread_id: Unique thread identifier
            data: JSON-serializable data to send
            
        Raises:
            RuntimeError: If no connection exists for the thread
        """
        if thread_id not in self.active_connections:
            raise RuntimeError(f"No WebSocket connection for thread {thread_id}")
        
        ws = self.active_connections[thread_id]
        await ws.send_json(data)
    
    async def send_interrupt(self, thread_id: str, interrupt_data: dict):
        """Send interrupt notification to client.
        
        Args:
            thread_id: Unique thread identifier
            interrupt_data: Interrupt data from LangGraph (action_requests, review_configs)
        """
        if thread_id in self.active_connections:
            ws = self.active_connections[thread_id]
            await ws.send_json({
                "type": "interrupt",
                "interrupt_data": interrupt_data,
            })
            logger.info(f"Sent interrupt notification for thread {thread_id}")
        else:
            logger.warning(f"Cannot send interrupt - no connection for thread {thread_id}")
    
    async def wait_for_decision(self, thread_id: str, timeout: float = 300) -> dict:
        """Wait for user decision with timeout.
        
        Args:
            thread_id: Unique thread identifier
            timeout: Timeout in seconds (default: 300 = 5 minutes)
            
        Returns:
            Decision dict with format: {"decisions": [{"type": "approve|edit|reject", ...}]}
            If timeout occurs, returns auto-reject decision
            
        Raises:
            asyncio.CancelledError: If the wait is cancelled (e.g., connection lost)
        """
        future = asyncio.Future()
        self.pending_decisions[thread_id] = future
        logger.info(f"Waiting for decision on thread {thread_id} (timeout: {timeout}s)")
        
        try:
            decision = await asyncio.wait_for(future, timeout=timeout)
            logger.info(f"Received decision for thread {thread_id}: {decision.get('decisions', [{}])[0].get('type')}")
            return decision
        except asyncio.TimeoutError:
            # Auto-reject after timeout
            logger.warning(f"Decision timeout for thread {thread_id} - auto-rejecting")
            return {
                "decisions": [{
                    "type": "reject",
                    "message": "Timeout - no decision received within 5 minutes"
                }]
            }
        finally:
            self.pending_decisions.pop(thread_id, None)
    
    def submit_decision(self, thread_id: str, decision: dict):
        """Submit user decision to resume agent.
        
        Args:
            thread_id: Unique thread identifier
            decision: Decision dict with format: {"decisions": [...]}
        """
        if thread_id in self.pending_decisions:
            future = self.pending_decisions[thread_id]
            if not future.done():
                future.set_result(decision)
                logger.info(f"Decision submitted for thread {thread_id}")
            else:
                logger.warning(f"Decision already submitted for thread {thread_id}")
        else:
            logger.warning(f"No pending decision for thread {thread_id}")


# Global manager instance
hitl_manager = HITLWebSocketManager()
