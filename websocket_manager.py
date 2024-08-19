from typing import Dict
from fastapi import WebSocket
from google.cloud.firestore_v1.base_query import FieldFilter
from firebase_instance import database


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, identifier: str):
        self.active_connections[identifier] = websocket

    def disconnect(self, identifier: str):
        if identifier in self.active_connections:
            del self.active_connections[identifier]
            print("socket disconnected")

    async def send_personal_message(self, message: str, identifier: str):
        if identifier in self.active_connections:
            await self.active_connections[identifier].send_text(message)

    async def send_json_to_identifiers(self, content: dict, identifiers: list[str]):
        for identifier in identifiers:
            if identifier in self.active_connections:
                await self.active_connections[identifier].send_json(content)

    async def send_json_to_identifier(self, content: dict, identifier: str):
        if identifier in self.active_connections:
            await self.active_connections[identifier].send_json(content)

    async def broadcast(self, message: str, exclude: str = None):
        for identifier, connection in self.active_connections.items():
            if identifier != exclude:
                await connection.send_text(message)


manager = ConnectionManager()
