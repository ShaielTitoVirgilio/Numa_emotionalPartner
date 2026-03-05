# app/main.py

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Literal, Optional, Dict, Any
from app.auth_service import register_user, login_user, get_user_profile
from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import os
import json
import re

app = FastAPI(
    title="Numa Emotional Partner API",
    version="1.0.0"
)

llm = LLMClient()

# ==========================
# DETECCIÓN DE RIESGO
# ==========================

HIGH_RISK_PHRASES = [
    "no quiero seguir", "no vale la pena", "me quiero morir",
    "no aguanto más", "quiero desaparecer", "ya no puedo más",
    "no tiene sentido seguir", "quiero terminar con todo",
    "no quiero estar acá", "mejor si no existiera",
]

LOW_RISK_PHRASES = [
    "me siento muy mal", "estoy destruido",
    "no sé cuánto más aguanto", "todo está mal", "estoy al límite",
]

def _detectar_riesgo(ultimo_mensaje: str) -> str:
    msg = ultimo_mensaje.lower()
    for phrase in HIGH_RISK_PHRASES:
        if phrase in msg:
            return "high"
    for phrase in LOW_RISK_PHRASES:
        if phrase in msg:
            return "low"
    return "none"

# ==========================
# MODELOS
# ==========================

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    conversation: List[Message]
    user_id: Optional[str] = None
    perfil: Optional[Dict[str, Any]] = None

class RegisterRequest(BaseModel):
    email: str
    password: str
    nombre: str

class LoginRequest(BaseModel):
    email: str
    password: str

class OnboardingAnswer(BaseModel):
    pregunta_numero: int
    pregunta: str
    respuesta: str

class OnboardingRequest(BaseModel):
    user_id: str
    answers: List[OnboardingAnswer]

# ==========================
# ROUTES ESTÁTICAS
# ==========================

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join("frontend", "index.html"))

# ==========================
# AUTH
# ==========================

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

# ==========================
# ONBOARDING
# ==========================

@app.post("/onboarding")
def onboarding_endpoint(request: OnboardingRequest):
    try:
        from app.supabase_client import supabase

        existing = supabase.table("users_profiles") \
            .select("id").eq("id", request.user_id).execute()

        if not existing.data:
            supabase.table("users_profiles").insert({
                "id": request.user_id,
                "onboarding_completo": False,
                "nombre": ""
            }).execute()

        rows = [
            {
                "user_id": request.user_id,
                "pregunta_numero": a.pregunta_numero,
                "pregunta": a.pregunta,
                "respuesta": a.respuesta,
            }
            for a in request.answers
        ]
        supabase.table("onboarding_answers").insert(rows).execute()

        resp = {a.pregunta_numero: a.respuesta for a in request.answers}

        perfil_update = {
            "onboarding_completo": True,
            "nombre":              resp.get(1, ""),
            "edad":                resp.get(2),
            "pronombres":          resp.get(3),
            "tono_preferido":      resp.get(5),
            "como_reacciona":      resp.get(6),
            "que_lo_calma":        resp.get(7),
            "prefiere_respuestas": resp.get(8),
            "momento_vida":        resp.get(9),
            "preferencias_extra":  resp.get(10),
        }
        perfil_update = {k: v for k, v in perfil_update.items() if v is not None}

        supabase.table("users_profiles").upsert({
            "id": request.user_id,
            **perfil_update
        }).execute()

        return {"message": "Onboarding guardado correctamente"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==========================
# BACKGROUND TASKS
# ==========================

def _guardar_en_db(user_id: str, mensaje_usuario: str, mensaje_numa: str, memoria: Optional[str]):
    try:
        from app.supabase_client import supabase

        supabase.table("conversations").insert([
            {"user_id": user_id, "role": "user",      "content": mensaje_usuario},
            {"user_id": user_id, "role": "assistant",  "content": mensaje_numa},
        ]).execute()

        if memoria:
            supabase.table("memories").insert({
                "user_id":   user_id,
                "content":   memoria,
                "category":  "chat",
                "source":    "chat",
                "is_active": True,
            }).execute()

    except Exception as e:
        print(f"⚠️ Error en background task: {e}")

# ==========================
# CHAT — streaming
# ==========================

DELIMITER = "---META---"

@app.post("/chat")
async def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks):
    try:
        perfil = request.perfil

        # Fallback: buscar perfil en DB si no vino del frontend
        if perfil is None and request.user_id:
            try:
                from app.supabase_client import supabase
                perfil_res = supabase.table("users_profiles") \
                    .select("*").eq("id", request.user_id).single().execute()
                perfil = perfil_res.data
            except Exception:
                perfil = None

        memorias_sesion = []
        if perfil and "_memorias_sesion" in perfil:
            memorias_sesion = perfil.pop("_memorias_sesion", [])

        system_prompt = construir_prompt(perfil=perfil, memorias=memorias_sesion)

        risk_level = "none"
        if request.conversation:
            risk_level = _detectar_riesgo(request.conversation[-1].content)

        conversation_dicts = [m.dict() for m in request.conversation]

        # Extender el prompt para indicarle al modelo el formato de dos partes
        streaming_system_prompt = system_prompt + """

---

FORMATO DE RESPUESTA OBLIGATORIO:
Respondé en DOS partes separadas por "---META---" en su propia línea:

Parte 1: tu mensaje para el usuario (texto plano, directo, sin JSON, sin tags).
Parte 2: JSON con metadatos.

Ejemplo:
Che, eso suena pesado. ¿Hace cuánto venís así?
---META---
{"mood": "sad", "suggested_action": null, "memory": null}

Ejemplo con ejercicio:
Pará un segundo. Respirá así: 4 adentro, 4 afuera. La usan militares para calmarse rápido.
---META---
{"mood": "stressed", "suggested_action": "respiracion_box", "memory": null}

REGLAS:
- Parte 1: solo el texto para el usuario. Sin IDs, sin JSON, sin tags.
- Parte 2: solo el JSON. Sin texto extra.
- "---META---" debe estar solo en su línea.
"""

        async def event_generator():
            stream = llm.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=300,
                stream=True,
                messages=[
                    {"role": "system", "content": streaming_system_prompt},
                    *conversation_dicts,
                ],
            )

            message_text = ""
            past_delimiter = False
            meta_buffer = ""
            pending = ""

            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""

                if past_delimiter:
                    meta_buffer += delta
                    continue

                pending += delta

                # ¿Encontramos el delimitador?
                if DELIMITER in pending:
                    parts = pending.split(DELIMITER, 1)
                    clean_part = parts[0].strip()
                    if clean_part:
                        message_text += clean_part
                        yield f"data: {message_text}\n\n"
                    meta_buffer = parts[1]
                    past_delimiter = True
                    pending = ""
                    continue

                # ¿El pending termina con un prefijo del delimitador? Esperar más.
                is_prefix = any(
                    DELIMITER.startswith(pending[len(pending)-i:])
                    for i in range(1, min(len(DELIMITER), len(pending)) + 1)
                )
                if is_prefix:
                    continue

                # Seguro de enviar
                if pending:
                    message_text += pending
                    yield f"data: {message_text}\n\n"
                    pending = ""

            # Flush si quedó algo en pending
            if pending and not past_delimiter:
                message_text += pending
                yield f"data: {message_text}\n\n"

            # Parsear metadatos del JSON final
            mood = "neutral"
            suggested_action = None
            nueva_memoria = None

            if meta_buffer.strip():
                try:
                    json_match = re.search(r'\{.*\}', meta_buffer.strip(), re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group(0))
                        mood = parsed.get("mood", "neutral")
                        suggested_action = parsed.get("suggested_action")
                        nueva_memoria = parsed.get("memory")
                except Exception as e:
                    print(f"⚠️ Error parseando meta JSON: {e}")

            # Limpiar tags residuales del mensaje
            message_text = re.sub(r'\[EJERCICIO:\s*\w+\]', '', message_text).strip()

            # Emitir evento de metadatos al frontend
            meta_payload = {
                "mood": mood,
                "suggested_action": suggested_action,
                "risk_level": risk_level,
                "nueva_memoria": nueva_memoria,
                "full_message": message_text,
            }
            yield f"event: meta\ndata: {json.dumps(meta_payload)}\n\n"

            # Guardar en DB sin bloquear la respuesta
            if request.user_id and request.conversation:
                background_tasks.add_task(
                    _guardar_en_db,
                    request.user_id,
                    request.conversation[-1].content,
                    message_text,
                    nueva_memoria,
                )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))