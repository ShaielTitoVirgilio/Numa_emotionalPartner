from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Literal, Optional
from app.ai import process_chat
from app.auth_service import register_user, login_user, get_user_profile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI(
    title="Numa Emotional Partner API",
    version="1.0.0"
)

# ==========================
# MODELOS CHAT
# ==========================

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    conversation: List[Message]

class ChatResponse(BaseModel):
    message: str
    mood: str
    suggested_action: Optional[str] = None
    risk_level: Optional[str] = None

# ==========================
# MODELOS AUTH
# ==========================

class RegisterRequest(BaseModel):
    email: str
    password: str
    nombre: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ==========================
# ROUTES
# ==========================

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join("frontend", "index.html"))

@app.post("/register")
def register_endpoint(request: RegisterRequest):
    try:
        user = register_user(request.email, request.password, request.nombre)
        return {"message": "Usuario creado correctamente", "user_id": user.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/login")
def login_endpoint(request: LoginRequest):
    try:
        result = login_user(request.email, request.password)
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.get("/profile/{user_id}")
def profile_endpoint(user_id: str):
    try:
        profile = get_user_profile(user_id)
        return profile
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    result = process_chat(
        conversation=[m.dict() for m in request.conversation]
    )
    return result