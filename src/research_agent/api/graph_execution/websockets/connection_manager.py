"""
WebSocket connection manager for graph progress streaming.
"""
import asyncio
from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    """Manage WebSocket connections for progress streaming."""
    
    def __init__(self):
        # run_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, run_id: str):
        """Accept a WebSocket connection and register it for a run."""
        await websocket.accept()
        
        async with self._lock:
            if run_id not in self.active_connections:
                self.active_connections[run_id] = set()
            self.active_connections[run_id].add(websocket)
    
    async def disconnect(self, websocket: WebSocket, run_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if run_id in self.active_connections:
                self.active_connections[run_id].discard(websocket)
                if not self.active_connections[run_id]:
                    del self.active_connections[run_id]
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to specific WebSocket."""
        await websocket.send_text(message)
    
    async def broadcast_to_run(self, run_id: str, message: str):
        """Broadcast message to all connections for a specific run."""
        async with self._lock:
            if run_id in self.active_connections:
                # Create copy to avoid modification during iteration
                connections = list(self.active_connections[run_id])
        
        # Send outside lock to avoid blocking
        for connection in connections:
            try:
                await connection.send_text(message)
            except Exception:
                # Connection may have closed
                await self.disconnect(connection, run_id)


# Global connection manager instance
manager = ConnectionManager()
