from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict
from app.ai import hablar_con_oso

app = FastAPI(title="Numa 🐻")

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def home():
    return FileResponse("frontend/index.html")


class Mensaje(BaseModel):
    texto: str
    historial: List[Dict[str, str]] = []  # 🧠 NUEVO: Recibe historial


@app.post("/chat")
def chat(mensaje: Mensaje):
    respuesta = hablar_con_oso(mensaje.texto, mensaje.historial)  # 🧠 NUEVO
    return { "oso": respuesta }