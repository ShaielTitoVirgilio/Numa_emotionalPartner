# app/main.py

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Literal, Optional, Dict, Any
from app.auth_service import register_user, login_user, get_user_profile
from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt
from app.memory_service import get_recent_memories, MEMORY_WINDOW_DAYS_DEFAULT
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from fastapi.responses import StreamingResponse
import json


app = FastAPI(
    title="Numa Emotional Partner API",
    version="1.0.0"
)


llm = LLMClient()

# ==========================
# DETECCIÓN DE RIESGO
# (antes estaba en chat_service.py)
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

class ChatResponse(BaseModel):
    message: str
    mood: str
    suggested_action: Optional[str] = None
    risk_level: Optional[str] = None
    nueva_memoria: Optional[str] = None

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
# BACKGROUND SURVEY
# ==========================

class SurveyAnswers(BaseModel):
    nps: int
    utilidad: Optional[str] = None
    opinion: Optional[str] = None
    features: Optional[str] = None
    fallas: Optional[str] = None

class SurveyRequest(BaseModel):
    user_id: Optional[str] = None
    session_length_s: int
    message_count: int
    answers: SurveyAnswers

@app.post("/survey")
def survey_endpoint(req: SurveyRequest):
    try:
        # Si tenés Supabase:
        from app.supabase_client import supabase
        supabase.table("surveys").insert({
            "user_id": req.user_id,
            "session_length_s": req.session_length_s,
            "message_count": req.message_count,
            "nps": req.answers.nps,
            "utilidad": req.answers.utilidad,
            "opinion": req.answers.opinion,
            "features": req.answers.features,
            "fallas": req.answers.fallas,
        }).execute()
        return {"ok": True}
    except Exception as e:
        # Fallback (rama sin BD): no rompas la UX
        print("Survey error/disabled:", e, req.model_dump())
        return {"ok": True}




# ==========================
# BACKGROUND TASKS
# ==========================


def _guardar_en_db(user_id: str, mensaje_usuario: str, mensaje_numa: str, memoria: Optional[str]):
    try:
        from app.supabase_client import supabase

        supabase.table("conversations").insert([
            {"user_id": user_id, "role": "user",     "content": mensaje_usuario},
            {"user_id": user_id, "role": "assistant", "content": mensaje_numa},
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

def _desactivar_memorias(ids: List[str]):
    if not ids:
        return
    try:
        from app.supabase_client import supabase
        # Desactiva en lote las que pasamos
        supabase.table("memories").update({"is_active": False}).in_("id", ids).execute()
    except Exception as e:
        print(f"⚠️ Error desactivando memorias: {e}")
# ==========================
# CHAT
# ==========================

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest, background_tasks: BackgroundTasks):
    try:
        perfil = request.perfil

        # Fallback: si no vino perfil desde el frontend, buscarlo en DB
        if perfil is None and request.user_id:
            try:
                from app.supabase_client import supabase
                perfil_res = supabase.table("users_profiles") \
                    .select("*").eq("id", request.user_id).single().execute()
                perfil = perfil_res.data
            except Exception:
                perfil = None

        # ==========================
        # MEMORIAS (sesión + DB): recientes y únicas por tema
        # ==========================
        memorias_sesion = []
        if perfil and "_memorias_sesion" in perfil:
            memorias_sesion = perfil.pop("_memorias_sesion", []) or []

        memorias_vigentes: List[str] = []
        ids_a_desactivar: List[str] = []

        if request.user_id:
            try:
                from app.supabase_client import supabase

                # Traer de DB: activas, últimas N días (21 default), deduplicadas por category
                m_db, ids_old = get_recent_memories(
                    supabase=supabase,
                    user_id=request.user_id,
                    days=MEMORY_WINDOW_DAYS_DEFAULT,  # 21 días por defecto
                    max_items=8                       # límite para el prompt (tokens)
                )

                # Fusionar: primero memorias de sesión (si existen), luego DB
                memorias_vigentes = (memorias_sesion or []) + m_db
                ids_a_desactivar = ids_old

            except Exception as e:
                print(f"⚠️ No se pudieron cargar memorias: {e}")
                memorias_vigentes = memorias_sesion or []

        # ==========================
        # Construir prompt dinámico con perfil + memorias vigentes
        # ==========================
        system_prompt = construir_prompt(
            perfil=perfil,
            memorias=memorias_vigentes
        )

        # ✅ Usar el cliente ya inicializado — no crea conexión nueva
        result = llm.generate_response(
            conversation=[m.dict() for m in request.conversation],
            system_prompt=system_prompt,
        )

        memoria_detectada = result.get("memory")

        # Detectar riesgo en el último mensaje del usuario
        risk_level = "none"
        if request.conversation:
            risk_level = _detectar_riesgo(request.conversation[-1].content)

        # Guardar en DB en background (no bloquea la respuesta)
        if request.user_id and request.conversation:
            background_tasks.add_task(
                _guardar_en_db,
                request.user_id,
                request.conversation[-1].content,
                result["message"],
                memoria_detectada,
            )

        # ⚙️ Desactivar duplicadas viejas por category en background
        if ids_a_desactivar:
            background_tasks.add_task(_desactivar_memorias, ids_a_desactivar)

        return {
            "message":          result["message"],
            "mood":             result["mood"],
            "suggested_action": result.get("suggested_action"),
            "risk_level":       risk_level,
            "nueva_memoria":    memoria_detectada,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))