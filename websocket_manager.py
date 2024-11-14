from typing import Dict, List
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, identifier: str):
        if identifier not in self.active_connections:
            self.active_connections[identifier] = []
        self.active_connections[identifier].append(websocket)

    def disconnect(self, websocket: WebSocket, identifier: str):
        if identifier in self.active_connections:
            self.active_connections[identifier] = [conn for conn in self.active_connections[identifier] if conn != websocket]
            if not self.active_connections[identifier]:
                del self.active_connections[identifier]
            print("socket disconnected")

    async def send_json_to_identifier(self, content: dict, identifier: str):
        if identifier in self.active_connections:
            for connection in self.active_connections[identifier]:
                await connection.send_json(content)


manager = ConnectionManager()
