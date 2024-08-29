from typing import Dict, List
from fastapi import WebSocket


# class ConnectionManager:
#     def __init__(self):
#         self.active_connections: Dict[str, WebSocket] = {}

#     async def connect(self, websocket: WebSocket, identifier: str):
#         self.active_connections[identifier] = websocket

#     def disconnect(self, identifier: str):
#         if identifier in self.active_connections:
#             del self.active_connections[identifier]
#             print("socket disconnected")

#     async def send_personal_message(self, message: str, identifier: str):
#         if identifier in self.active_connections:
#             await self.active_connections[identifier].send_text(message)

#     async def send_json_to_identifier(self, content: dict, identifier: str):
#         if identifier in self.active_connections:
#             await self.active_connections[identifier].send_json(content)

#     async def broadcast(self, message: str, exclude: str = None):
#         for identifier, connection in self.active_connections.items():
#             if identifier != exclude:
#                 await connection.send_text(message)


# manager = ConnectionManager()


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

    # async def broadcast(self, message: str, exclude: str = None):
    #     for identifier, connections in self.active_connections.items():
    #         if identifier != exclude:
    #             for connection in connections:
    #                 await connection.send_text(message)


manager = ConnectionManager()
