from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from socket_instance import sio
from app.endpoints import router as api_router
import app.socket_handlers


app = FastAPI()


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


# inclues API router
app.include_router(api_router)


# creates the combined ASGI app
socket_app = socketio.ASGIApp(sio, app)


# this makes the project run as python main.py instead of uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(socket_app, host="0.0.0.0", port=8000)
