from typing import Dict, Set
import json
import asyncio


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set] = {}

    async def connect(self, websocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
        self.active_connections[room_id].add(websocket)

    def disconnect(self, websocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

    async def send_personal_message(self, message: dict, websocket):
        await websocket.send_text(json.dumps(message))

    async def broadcast_to_room(self, message: dict, room_id: str, exclude_websocket=None):
        if room_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[room_id]:
                try:
                    if connection != exclude_websocket:
                        await connection.send_text(json.dumps(message))
                except Exception:
                    disconnected.add(connection)

            # Remove disconnected clients
            for connection in disconnected:
                self.disconnect(connection, room_id)


manager = ConnectionManager()