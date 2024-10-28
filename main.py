# /main.py

import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import app.websocket_routes
from app.chat_endpoints import router as api_router
from app.websocket_routes import router as websocket_router
from app.html_edtor_endpoints import router as html_router


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

# includes WebSocket router
app.include_router(websocket_router)

# html router
app.include_router(html_router)

# this makes the project run as python main.py instead of uvicorn main:app --reload
# uvicorn main:app --reload --host 0.0.0.0 --port 8080

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)


import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        workers=1,  # Stick to 1 worker for single CPU
        limit_concurrency=500,  # Start with this limit
        backlog=100,
        loop="uvloop",  # Use uvloop for better performance
        http="httptools",  # Faster HTTP parsing
        ws_max_size=16777216,  # 16MB max WebSocket message size
        ws_ping_interval=20,  # Keep connections alive
        ws_ping_timeout=30,
    )
