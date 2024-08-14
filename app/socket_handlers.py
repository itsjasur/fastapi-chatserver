# app/sockets/handlers.py
from socket_instance import sio


@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")


@sio.event
async def message(sid, data):
    print(f"Message from {sid}: {data}")
    await sio.emit("response", {"data": f"Server received: {data}"}, room=sid)


# Add more socket event handlers as needed
