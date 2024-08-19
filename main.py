# /main.py

import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import app.websocket_routes
from app.endpoints import router as api_router
from app.websocket_routes import router as websocket_router


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

# this makes the project run as python main.py instead of uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
