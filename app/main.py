# app/main.py

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Literal, Optional, Dict, Any
from app.auth_service import register_user, login_user, get_user_profile
from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt
from app.memory_service import get_recent_memories, MEMORY_WINDOW_DAYS_DEFAULT
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, StreamingResponse
import os
import json
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request
from app.crisis_detector import detectar_crisis, log_crisis_event

limiter = Limiter(key_func=get_remote_address)


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
        import time 
        max_intentos = 5
        for intento in range(max_intentos):
            try:
                existing = supabase.table("users_profiles") \
                    .select("id").eq("id", request.user_id).execute()

                if not existing.data:
                    supabase.table("users_profiles").insert({
                        "id": request.user_id,
                        "onboarding_completo": False,
                        "nombre": ""
                    }).execute()
                break
            except Exception as e:
                if intento < max_intentos - 1:
                    time.sleep(0.8 * (intento + 1))
                else:
                    raise e

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
            "pronombres":          resp.get(2),
            "etapa_vida":          resp.get(3),
            "que_le_pesa":         resp.get(4),
            "como_reacciona":      resp.get(5),
            "prefiere_respuestas": resp.get(6),
            "preferencias_extra":  resp.get(7),
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
    
# ============================================
# PARCHE PARA main.py — agregar al final del archivo
# antes del último bloque de código o al final de las rutas
#
# Copiar y pegar este bloque en main.py de Numa
# ============================================

# ── Modelo de request ──────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    user_id: Optional[str] = None
    texto: Optional[str] = None
    categoria: Optional[str] = "general"
    rating: Optional[int] = None
    audio_base64: Optional[str] = None
    audio_mime: Optional[str] = None

# ── Endpoint ───────────────────────────────────────────────────────────────────

@app.post("/feedback")
def feedback_endpoint(req: FeedbackRequest):
    """
    Guarda feedback de testers: texto libre + audio opcional (base64).
    El audio se guarda directamente en la BD para el MVP.
    Para producción: subir a Supabase Storage y guardar la URL.
    """
    try:
        from app.supabase_client import supabase

        row = {
            "user_id":      req.user_id,
            "texto":        req.texto,
            "categoria":    req.categoria or "general",
            "rating":       req.rating,
            "audio_base64": req.audio_base64,
            "audio_mime":   req.audio_mime,
            "app_version":  "mvp-1",
        }

        # Filtrar campos None para no romper constraints
        row = {k: v for k, v in row.items() if v is not None}

        supabase.table("user_feedback").insert(row).execute()

        # Log útil en desarrollo
        print(f"✅ Feedback recibido — cat:{req.categoria} rating:{req.rating} "
              f"texto:{bool(req.texto)} audio:{bool(req.audio_base64)}")

        return {"ok": True}

    except Exception as e:
        # Fallback: no romper la UX si algo falla en la BD
        print(f"⚠️ Error guardando feedback: {e}")
        return {"ok": True, "warning": str(e)}


# ── Endpoint de lectura (para vos) ─────────────────────────────────────────────
# GET /admin/feedback?limit=50
# Requiere la API key en el header X-Admin-Key para protegerlo mínimamente.
# Cambiar el valor de ADMIN_KEY por algo secreto.

ADMIN_KEY = "numa-admin-2024"  # ← cambialo por algo tuyo

@app.get("/admin/feedback")
def admin_feedback(
    limit: int = 50,
    categoria: Optional[str] = None,
    x_admin_key: Optional[str] = None,
):
    """
    Endpoint para que el equipo vea los feedbacks.
    Uso: GET /admin/feedback?limit=20&categoria=bug
    Header: X-Admin-Key: numa-admin-2024
    """
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")

    try:
        from app.supabase_client import supabase

        query = supabase.table("user_feedback") \
            .select("id, created_at, user_id, texto, categoria, rating, audio_mime, app_version") \
            .order("created_at", desc=True) \
            .limit(limit)

        if categoria:
            query = query.eq("categoria", categoria)

        res = query.execute()
        return {"total": len(res.data), "feedbacks": res.data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/feedback/{feedback_id}/audio")
def admin_feedback_audio(feedback_id: str, x_admin_key: Optional[str] = None):
    """
    Devuelve el audio base64 de un feedback específico.
    Uso: GET /admin/feedback/{id}/audio
    """
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")

    try:
        from app.supabase_client import supabase
        import base64

        res = supabase.table("user_feedback") \
            .select("audio_base64, audio_mime") \
            .eq("id", feedback_id) \
            .single() \
            .execute()

        if not res.data or not res.data.get("audio_base64"):
            raise HTTPException(status_code=404, detail="Audio no encontrado")

        audio_bytes = base64.b64decode(res.data["audio_base64"])
        mime = res.data.get("audio_mime", "audio/webm")

       
        return Response(content=audio_bytes, media_type=mime)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))    


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
@limiter.limit("18/minute")
def chat_endpoint(request: Request, body: ChatRequest, background_tasks: BackgroundTasks):
    try:
        perfil = body.perfil

        # Fallback: si no vino perfil desde el frontend, buscarlo en DB
        if perfil is None and body.user_id:
            try:
                from app.supabase_client import supabase
                perfil_res = supabase.table("users_profiles") \
                    .select("*").eq("id", body.user_id).single().execute()
                perfil = perfil_res.data
            except Exception:
                perfil = None

        # ══════════════════════════════════════════════════════
        # DETECCIÓN DE CRISIS — interceptar ANTES del LLM
        # ══════════════════════════════════════════════════════
        ultimo_mensaje = body.conversation[-1].content if body.conversation else ""

        crisis = detectar_crisis(ultimo_mensaje)

        if crisis["detected"]:
            # Loguear en background (no bloquea la respuesta)
            if crisis["log_level"] in ("critical", "high"):
                try:
                    from app.supabase_client import supabase as _sb
                    background_tasks.add_task(
                        log_crisis_event,
                        _sb,
                        body.user_id,
                        ultimo_mensaje,
                        crisis["category"],
                        crisis["log_level"],
                    )
                except Exception:
                    pass  # nunca romper el flujo

            # Devolver respuesta hardcodeada directamente
            # sin llamar al LLM
            return {
                "message":          crisis["message"],
                "mood":             "sad",          # oso en modo triste/serio
                "suggested_action": None,           # nunca sugerir ejercicio en crisis
                "risk_level":       "high",
                "nueva_memoria":    None,           # no guardar esto como memoria
            }

        # ══════════════════════════════════════════════════════
        # FLUJO NORMAL (sin crisis detectada)
        # ══════════════════════════════════════════════════════

        # Memorias (sesión + DB)
        memorias_sesion = []
        if perfil and "_memorias_sesion" in perfil:
            memorias_sesion = perfil.pop("_memorias_sesion", []) or []

        memorias_vigentes: List[str] = []
        ids_a_desactivar: List[str] = []

        if body.user_id:
            try:
                from app.supabase_client import supabase
                m_db, ids_old = get_recent_memories(
                    supabase=supabase,
                    user_id=body.user_id,
                    days=MEMORY_WINDOW_DAYS_DEFAULT,
                    max_items=8
                )
                memorias_vigentes = (memorias_sesion or []) + m_db
                ids_a_desactivar = ids_old
            except Exception as e:
                print(f"⚠️ No se pudieron cargar memorias: {e}")
                memorias_vigentes = memorias_sesion or []

        # Construir prompt dinámico
        system_prompt = construir_prompt(
            perfil=perfil,
            memorias=memorias_vigentes
        )

        result = llm.generate_response(
            conversation=[m.dict() for m in body.conversation],
            system_prompt=system_prompt,
        )

        memoria_detectada = result.get("memory")

        # Detectar riesgo con el método existente también
        risk_level = "none"
        if body.conversation:
            risk_level = _detectar_riesgo(body.conversation[-1].content)

        # Guardar en DB en background
        if body.user_id and body.conversation:
            background_tasks.add_task(
                _guardar_en_db,
                body.user_id,
                body.conversation[-1].content,
                result["message"],
                memoria_detectada,
            )

        # Desactivar memorias duplicadas viejas
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


# ============================================
# PASO 3 (opcional): endpoint de admin para ver crisis
#
# Agregar al final de main.py junto con los otros /admin endpoints
# ============================================

@app.get("/admin/crisis")
def admin_crisis(
    limit: int = 50,
    solo_pendientes: bool = True,
    x_admin_key: Optional[str] = None,
):
    """
    Ver eventos de crisis detectados.
    GET /admin/crisis?solo_pendientes=true
    Header: X-Admin-Key: tu-clave
    """
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")

    try:
        from app.supabase_client import supabase

        query = supabase.table("crisis_logs") \
            .select("id, created_at, user_id, LEFT(mensaje_usuario, 100), categoria, log_level, revisado") \
            .order("created_at", desc=True) \
            .limit(limit)

        if solo_pendientes:
            query = query.eq("revisado", False)

        res = query.execute()
        return {"total": len(res.data), "eventos": res.data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/admin/crisis/{crisis_id}/revisar")
def admin_marcar_revisado(crisis_id: str, x_admin_key: Optional[str] = None):
    """Marcar un evento de crisis como revisado."""
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="No autorizado")

    try:
        from app.supabase_client import supabase
        supabase.table("crisis_logs").update({"revisado": True}).eq("id", crisis_id).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





    try:
        perfil = body.perfil

        # Fallback: si no vino perfil desde el frontend, buscarlo en DB
        if perfil is None and body.user_id:
            try:
                from app.supabase_client import supabase
                perfil_res = supabase.table("users_profiles") \
                    .select("*").eq("id", body.user_id).single().execute()
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

        if body.user_id:
            try:
                from app.supabase_client import supabase

                m_db, ids_old = get_recent_memories(
                    supabase=supabase,
                    user_id=body.user_id,
                    days=MEMORY_WINDOW_DAYS_DEFAULT,
                    max_items=8
                )

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

        result = llm.generate_response(
            conversation=[m.dict() for m in body.conversation],
            system_prompt=system_prompt,
        )

        memoria_detectada = result.get("memory")

        # Detectar riesgo en el último mensaje del usuario
        risk_level = "none"
        if body.conversation:
            risk_level = _detectar_riesgo(body.conversation[-1].content)

        # Guardar en DB en background (no bloquea la respuesta)
        if body.user_id and body.conversation:
            background_tasks.add_task(
                _guardar_en_db,
                body.user_id,
                body.conversation[-1].content,
                result["message"],
                memoria_detectada,
            )

        # Desactivar duplicadas viejas por category en background
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