# /main.py

import json
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import app.websocket_routes
from app.chat_endpoints import router as api_router
from app.websocket_routes import router as websocket_router
from app.html_edtor_endpoints import router as html_router
from app.order_usim_endpoints import router as usim_router


app = FastAPI()


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = []
    for error in exc.errors():
        error_details.append({"loc": error["loc"], "msg": error["msg"], "type": error["type"]})

    print(f"Validation error details: {error_details}")
    return JSONResponse(status_code=422, content={"detail": error_details})


# inclues API router
app.include_router(api_router)

# includes WebSocket router
app.include_router(websocket_router)

# html router
app.include_router(html_router)

# usim order router
app.include_router(usim_router)

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
