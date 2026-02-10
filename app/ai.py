import os
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
from app.prompt import OSO_PROMPT
from typing import List, Dict

# 🗂️ Cargar .env correctamente
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# 🔑 Ahora SÍ existe la API key
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise RuntimeError("GROQ_API_KEY no encontrada")

# 🤖 Cliente Groq (DESPUÉS de cargar el .env)
client = Groq(api_key=api_key)

def hablar_con_oso(texto_usuario: str, historial: List[Dict[str, str]] = None) -> str:
    # 🧠 Construir mensajes con historial
    mensajes = [
        { "role": "system", "content": OSO_PROMPT }
    ]
    
    # 🧠 Agregar historial si existe
    if historial:
        mensajes.extend(historial)
    else:
        # Si no hay historial, solo agregar el mensaje actual
        mensajes.append({ "role": "user", "content": texto_usuario })
    
    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=mensajes,
        temperature=0.7,
        max_tokens=120,
    )

    respuesta = completion.choices[0].message.content

    if not respuesta:
        return "Estoy acá contigo."

    return respuesta.strip()