from fastapi import FastAPI
from fastapi import Request
from pydantic import BaseModel
from typing import List, Literal
from app.ai import process_chat
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import time
import os

app = FastAPI(
    title="Numa Emotional Partner API",
    version="1.0.0"
)


# ==========================
# MODELOS
# ==========================

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    conversation: List[Message]


from typing import Optional

class ChatResponse(BaseModel):
    message: str
    mood: str
    suggested_action: Optional[str] = None
    risk_level: Optional[str] = None



# ==========================
# ROUTES
# ==========================

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join("frontend", "index.html"))


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    
    result = process_chat(
        conversation=[m.dict() for m in request.conversation]

    )

    return result

