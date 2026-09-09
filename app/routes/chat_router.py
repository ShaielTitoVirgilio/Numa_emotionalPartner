import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from difflib import SequenceMatcher

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, UploadFile, File, Depends
from pydantic import BaseModel
from typing import List, Literal, Optional, Dict, Any
from slowapi import Limiter
from app.core.auth import get_current_user_id
from app.core.observability import capturar_error, etiquetar_request
from app.core.logging_utils import log_event
from app.core.ratelimit import client_ip
from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt
from app.memory_service import (
    get_recent_memories,
    get_topic_patterns_cached,
    invalidate_patterns_cache,
    get_proactive_memories,
    get_open_topics,
    get_resource_memories,
    elegir_memoria_contextual,
    cerrar_temas_abiertos,
    marcar_evento_followup,
    marcar_proactivo_insertado,
    detectar_evento_con_fecha,
    detectar_tema_abierto,
    detectar_recurso,
    resolver_fecha_relativa,
    parse_fecha_llm,
    get_dias_inactivo,
    get_checkin_hoy_cached,
    MEMORY_WINDOW_DAYS_DEFAULT,
)
from app.crisis_detector import detectar_crisis, respuesta_contencion_generica
from app.crisis_verifier import confirmar_riesgo_real
from app.context_router import clasificar_contexto, score_riesgo_router, resultado_vacio
from app.speech_service import speech_to_text
from app.text_filters import (
    _quitar_pregunta_final,
    _quitar_che,
    _cierra_con_presencia,
    _quitar_cierre_presencia,
    _familia_apertura,
    _aplanar_apertura,
)
from app.streaming_buffer import BufferStreamingMensaje
from fastapi.responses import StreamingResponse
import json
from app.repositories.user_repository import UserRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.feedback_repository import FeedbackRepository
from app.core.errors import NumaError, MENSAJE_GENERICO

router = APIRouter()
limiter = Limiter(key_func=client_ip)
llm = LLMClient()
user_repo = UserRepository()
conversation_repo = ConversationRepository()
feedback_repo = FeedbackRepository()

CATEGORIAS_VALIDAS = {
    "trabajo", "estudios", "relaciones", "salud", "identidad",
    "emocional", "hobbies", "vida_cotidiana", "otro",
}

# Límites server-side: el cliente recorta a 20 mensajes, pero un cliente
# malicioso podía mandar miles (costo de tokens / DoS).
MAX_CONV_MESSAGES = 20
MAX_MSG_CHARS = 4000
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB

# Frases que indican que la memoria afirma algo "de oídas" (diagnóstico no
# confirmado, comentario de terceros) → no merece prioridad alta.
_RE_MEMORIA_DE_OIDAS = re.compile(
    r"(me dijeron que|le dijeron que|cree que tiene|piensa que tiene|"
    r"según le|segun le|alguien le dijo|le comentaron)",
    re.IGNORECASE,
)


# Ventana de validez de un event_date: desde ayer (tolerancia) hasta ~13 meses.
_EVENT_MAX_DIAS_FUTURO = 400


def _validar_evento(raw_event, content: str, hoy: date):
    """Devuelve (event_title, event_date_iso) o (None, None).

    Toma el objeto 'event' que el LLM puso en una memoria, valida la fecha y, si
    no parsea o queda fuera de rango, intenta resolverla heurísticamente desde el
    texto. Así el evento se persiste con fecha real aunque el modelo falle."""
    if not isinstance(raw_event, dict):
        return None, None
    titulo = (raw_event.get("title") or "").strip().rstrip(".")
    if not titulo or len(titulo) < 3:
        return None, None

    fecha = parse_fecha_llm(raw_event.get("date"))
    if fecha is None:
        fecha = resolver_fecha_relativa(content, hoy)
    if fecha is None:
        return None, None

    # Descartar fechas absurdas (pasado lejano o demasiado futuro).
    dias = (fecha - hoy).days
    if dias < -2 or dias > _EVENT_MAX_DIAS_FUTURO:
        return None, None

    return titulo[:120], fecha.isoformat()


def _validar_priority(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, n))


def _validar_category(value) -> str:
    if not value:
        return "otro"
    v = str(value).strip().lower()
    return v if v in CATEGORIAS_VALIDAS else "otro"


def _normalizar_prioridad(content: str, priority: int, crisis_score: float, es_post_ejercicio: bool) -> int:
    """Normaliza la prioridad server-side: el LLM tiende a poner prioridad 5
    a menciones casuales. Prioridad 5 queda reservada a turnos con señal de
    crisis; lo dicho "de oídas" baja a 3; el feedback de un ejercicio es un
    dato menor (máx 2)."""
    p = priority
    if es_post_ejercicio:
        p = min(p, 2)
    if _RE_MEMORIA_DE_OIDAS.search(content):
        p = min(p, 3)
    if crisis_score < 0.35:
        p = min(p, 4)
    return max(1, p)


# ── Dedup difuso de memorias ──────────────────────────────────────────────
# El LLM tiende a re-guardar el mismo hecho reformulado en cada turno
# ("Se sintió criticado por su jefe" / "Se sintió mal por una crítica de su
# jefe"...). El dedup exacto no lo atrapa; acá se compara por similitud.

_TILDES_MEM = str.maketrans("áéíóúüÁÉÍÓÚÜ", "aeiouuAEIOUU")
_STOPWORDS_MEM = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en",
    "y", "o", "a", "al", "que", "se", "su", "sus", "por", "para", "con", "sin",
    "le", "lo", "es", "fue", "esta", "este", "hay", "muy", "mas", "como",
    "usuario", "usuaria", "persona",
}


def _normalizar_mem(texto: str) -> str:
    t = texto.lower().translate(_TILDES_MEM)
    t = re.sub(r"[^\w\sñ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _stems_mem(texto: str) -> set:
    # Stem barato (primeras 4 letras) para que "crítica"/"criticado" cuenten igual
    return {
        (w[:4] if len(w) > 4 else w)
        for w in _normalizar_mem(texto).split()
        if w not in _STOPWORDS_MEM
    }


def _es_memoria_duplicada(content: str, existentes: List[str]) -> bool:
    a_norm = _normalizar_mem(content)
    a_stems = _stems_mem(content)
    if not a_norm:
        return True
    for otro in existentes:
        b_norm = _normalizar_mem(otro)
        if not b_norm:
            continue
        if SequenceMatcher(None, a_norm, b_norm).ratio() >= 0.55:
            return True
        b_stems = _stems_mem(otro)
        if a_stems and b_stems:
            jaccard = len(a_stems & b_stems) / len(a_stems | b_stems)
            if jaccard >= 0.5:
                return True
    return False


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class UbicacionData(BaseModel):
    ciudad: Optional[str] = None
    pais: Optional[str] = None
    countryCode: Optional[str] = None


class ChatRequest(BaseModel):
    conversation: List[Message]
    user_id: Optional[str] = None  # ignorado: el user_id sale del token
    perfil: Optional[Dict[str, Any]] = None
    ubicacion: Optional[UbicacionData] = None
    ultimo_mood: Optional[str] = None
    checkin_recien_hecho: Optional[bool] = False


class ImportMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    mood: Optional[str] = None


class ChatImportRequest(BaseModel):
    messages: List[ImportMessage]


class ChatResponse(BaseModel):
    message: str
    mood: str
    suggested_action: Optional[str] = None
    risk_level: Optional[str] = None
    nuevas_memorias: Optional[List[Dict[str, Any]]] = None


@router.post("/speech-to-text")
async def speech_to_text_endpoint(
    file: UploadFile = File(...),
    _user_id: str = Depends(get_current_user_id),
):
    try:
        audio_bytes = await file.read()

        if len(audio_bytes) < 5000:
            raise HTTPException(status_code=400, detail="Audio demasiado corto")
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio demasiado largo")

        text = speech_to_text(audio_bytes, file.filename)
        return {"text": text}

    except HTTPException:
        raise
    except Exception as e:
        capturar_error(e, contexto="speech_to_text")
        print("❌ STT ERROR:", e)
        raise HTTPException(status_code=503, detail="Servicio de transcripción no disponible")


@router.get("/chat/history")
def chat_history(limit: int = 30, user_id: str = Depends(get_current_user_id)):
    """Devuelve los últimos mensajes guardados para rehidratar el chat al
    abrir la app (antes el historial vivía solo en memoria de la página y
    se perdía en cada recarga)."""
    limit = max(1, min(limit, 50))
    try:
        messages = conversation_repo.get_recent_messages(user_id, limit)
        return {"messages": messages}
    except Exception as e:
        capturar_error(e, contexto="chat_history")
        print(f"⚠️ No se pudo cargar el historial: {e}")
        return {"messages": []}


# t_context_router_ms/t_memorias_ms/t_patrones_ms/t_metadatos_ms se solapan a
# propósito (corren en paralelo, ver _preparar_turno) — sumarlos exageraría
# el total real. t_paralelo_ms ya representa el tiempo de pared de ese
# bloque, así que estos 4 quedan afuera de la suma.
_TIEMPOS_EXCLUIDOS_DEL_TOTAL = {"t_context_router_ms", "t_memorias_ms", "t_patrones_ms", "t_metadatos_ms"}

# Ejecutor propio para el context_router en paralelo. A nivel de módulo (no
# adentro de _preparar_turno) porque el ThreadPoolExecutor usado como context
# manager ESPERA a sus tareas al salir del `with` — que es exactamente la
# latencia que se está sacando — y el resultado se consulta más tarde
# (chat_endpoint, después de llamar al LLM principal).
#
# max_workers: son llamadas HTTP a un LLM chico (I/O-bound, los threads pasan
# la mayor parte del tiempo esperando red, no CPU) — sin tope, una ráfaga de
# turnos concurrentes abriría un hilo por turno. 64 porque esto corre en
# TODO /chat (todo el tráfico de producción, no un feature chico).
_EJECUTOR_ROUTER_PARALELO = ThreadPoolExecutor(max_workers=64, thread_name_prefix="router-par")

# Score del router a partir del cual se descarta la respuesta ya generada y
# se corta directo a la contención hardcodeada. 0.6 = "explicita" en
# score_riesgo_router — mismo umbral que separa los módulos M19/M20 en
# numa_prompt.seleccionar_modulos.
UMBRAL_CORTE_LLAMADA = 0.6


def _sumar_tiempos(tiempos: Dict[str, float]) -> float:
    return round(sum(v for k, v in tiempos.items() if k not in _TIEMPOS_EXCLUIDOS_DEL_TOTAL), 1)


def _preparar_turno(body: "ChatRequest", user_id: str, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Todo el trabajo previo a llamar al LLM: límites, crisis, perfil,
    memorias, patrones, memoria proactiva, prompt. Extraído de chat_endpoint
    para poder testear el armado del turno por separado de la llamada al LLM.

    Devuelve un dict. Si la crisis ya se resolvió con la respuesta
    hardcodeada (sin pasar por el LLM): {"crisis_confirmada": True,
    "respuesta_crisis": {...}}. Si no, el resto de las claves que hacen
    falta para llamar al LLM y post-procesar la respuesta.
    """
    # Checkpoints de latencia por etapa — el log "chat_turn" trae
    # t_perfil_ms, t_crisis_verifier_ms, t_context_router_ms, t_memorias_ms,
    # t_patrones_ms, t_proactivo_ms, t_prompt_ms. Es la única forma de saber
    # DÓNDE se va el tiempo de un turno en vez de adivinar.
    tiempos: Dict[str, float] = {}
    _t0 = time.perf_counter()

    def _checkpoint(nombre: str) -> None:
        nonlocal _t0
        ahora = time.perf_counter()
        tiempos[nombre] = round((ahora - _t0) * 1000, 1)
        _t0 = ahora

    # Límite server-side de tamaño de la conversación
    conversation = body.conversation[-MAX_CONV_MESSAGES:]
    for m in conversation:
        if len(m.content) > MAX_MSG_CHARS:
            m.content = m.content[:MAX_MSG_CHARS]

    perfil = body.perfil
    if perfil is None:
        try:
            perfil = user_repo.get_profile(user_id)
        except Exception as e:
            capturar_error(e, contexto="cargar_perfil")
            perfil = None
    _checkpoint("t_perfil_ms")

    ultimo_mensaje = conversation[-1].content if conversation else ""
    crisis = detectar_crisis(ultimo_mensaje)
    crisis_score = crisis.get("score", 0.0)
    crisis_log_level = crisis.get("log_level", "none")
    _checkpoint("t_crisis_keywords_ms")

    if crisis["detected"]:
        # Verificación en dos pasos: las keywords dispararon crítico/alto;
        # un clasificador LLM rápido confirma si el riesgo es real y actual.
        # Fail-safe: ante error o duda, se mantiene la respuesta de emergencia.
        confirmado = confirmar_riesgo_real(ultimo_mensaje, crisis["category"] or "")
        _checkpoint("t_crisis_verifier_ms")
        if confirmado:
            background_tasks.add_task(
                feedback_repo.save_crisis_log,
                user_id, ultimo_mensaje, crisis["category"], crisis_log_level,
            )
            return {
                "crisis_confirmada": True,
                "respuesta_crisis": {
                    "message":          crisis["message"],
                    "mood":             "sad",
                    "suggested_action": None,
                    "risk_level":       "high",
                    "nuevas_memorias":  None,
                },
                "_tiempos": tiempos,
            }
        # El verificador descartó riesgo actual (hipérbole/tercero/pasado):
        # se degrada a señal media → el LLM responde con módulos de crisis.
        crisis_score = 0.45
        crisis_log_level = "medium"

    memorias_sesion: List[Dict[str, Any]] = []
    if perfil and "_memorias_sesion" in perfil:
        raw = perfil.pop("_memorias_sesion", []) or []
        memorias_sesion = [
            m if isinstance(m, dict) else {"content": str(m), "priority": 3, "category": "otro"}
            for m in raw
        ]

    num_interacciones = len(conversation)

    # ultimo_modulo_critico: local/instantáneo (detectar_crisis por keywords
    # sobre los últimos mensajes propios, no pega a ningún servicio) — se
    # calcula ANTES del paralelo de abajo para poder saltear la consulta a
    # Supabase (hay_crisis_reciente) si ya dio positivo.
    ultimo_modulo_critico = False
    previos_usuario = [m.content for m in conversation[:-1] if m.role == "user"][-2:]
    for msg_previo in previos_usuario:
        if detectar_crisis(msg_previo).get("score", 0.0) >= 0.35:
            ultimo_modulo_critico = True
            break

    # ── context_router: EN PARALELO (no bloqueante) con el LLM principal ──
    # Es una llamada a LLM aparte que se come 1.5-2s. Antes se esperaba su
    # resultado antes de armar el prompt, pagando esos 1.5-2s SUMADOS al LLM
    # principal. Medido: el LLM principal solo (TTFT + generación) ya tarda
    # más que el router en la enorme mayoría de los turnos — correrlo en
    # paralelo no acelera al router en sí, pero su tiempo queda "escondido"
    # detrás del LLM principal en vez de sumarse antes. Ver
    # _resolver_router_paralelo_chat() más abajo para cómo se usa el
    # resultado sin arriesgar la detección de riesgo: todavía no se mandó
    # nada al usuario cuando el router contesta, así que SÍ se puede esperar
    # su resultado final antes de devolver la respuesta — solo que esa espera
    # ocurre DESPUÉS del LLM principal, no antes, y normalmente ya está
    # resuelto (es más rápido) así que no cuesta nada extra en la práctica.
    #
    # El router SIEMPRE corre — nunca se salta, solo se deja de esperar ANTES
    # de generar: frases con método o plan que las keywords no matchean
    # ("tengo pastillas y me las voy a tomar todas") solo las agarra el
    # router, y sin él quedarían en score 0.0 sin ningún módulo de crisis.

    # ── Etapas independientes en paralelo ────────────────────────────
    # context_router (una llamada a LLM aparte de la principal, SOLO para
    # rutear módulos) se come 1.5-2s por su cuenta. Ninguna de las 4 etapas
    # de abajo depende de otra (solo la memoria proactiva, más abajo,
    # necesita el resultado de context_router) — correrlas en paralelo evita
    # que memorias/patrones/metadatos agreguen su propio tiempo arriba del
    # router.
    def _tarea_router():
        t0 = time.perf_counter()
        hints = clasificar_contexto([m.model_dump() for m in conversation])
        return hints, round((time.perf_counter() - t0) * 1000, 1)

    def _tarea_memorias():
        t0 = time.perf_counter()
        vigentes, ids_old = memorias_sesion or [], []
        try:
            m_db, ids_old = get_recent_memories(
                user_id=user_id, days=MEMORY_WINDOW_DAYS_DEFAULT, max_items=12
            )
            seen = set()
            merged = []
            for m in (memorias_sesion or []) + m_db:
                key = (m.get("content") or "").strip()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(m)
            vigentes = merged[:15]
        except Exception as e:
            capturar_error(e, contexto="cargar_memorias")
            print(f"⚠️ No se pudieron cargar memorias: {e}")
            vigentes, ids_old = memorias_sesion or [], []
        return vigentes, ids_old, round((time.perf_counter() - t0) * 1000, 1)

    def _tarea_patrones():
        t0 = time.perf_counter()
        pats: List[dict] = []
        try:
            pats = get_topic_patterns_cached(user_id=user_id)
        except Exception as e:
            capturar_error(e, contexto="cargar_patrones")
            print(f"⚠️ No se pudieron cargar patrones: {e}")
        return pats, round((time.perf_counter() - t0) * 1000, 1)

    def _tarea_metadatos():
        t0 = time.perf_counter()
        dias_inactivo_ = 0
        if num_interacciones <= 4:
            dias_inactivo_ = get_dias_inactivo(user_id)
        critico = ultimo_modulo_critico
        # Respaldo stateless: si la sesión recién empieza (el historial del
        # request no alcanza), mirar crisis_logs — el usuario pudo haber
        # recargado la app justo después de una crisis.
        if not critico and num_interacciones <= 4:
            critico = feedback_repo.hay_crisis_reciente(user_id)
        checkin = None
        try:
            checkin = get_checkin_hoy_cached(user_id)
        except Exception as e:
            capturar_error(e, contexto="cargar_checkin")
            print(f"⚠️ No se pudo cargar el check-in: {e}")
        return dias_inactivo_, critico, checkin, round((time.perf_counter() - t0) * 1000, 1)

    # El router se lanza en un ejecutor APARTE, que sobrevive a este bloque:
    # el `with` de abajo espera a sus tareas al salir, que es justo lo que no
    # queremos (ahí se iría la latencia que estamos sacando).
    fut_router_paralelo = _EJECUTOR_ROUTER_PARALELO.submit(_tarea_router)

    _t_paralelo_inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as ejecutor:
        fut_memorias = ejecutor.submit(_tarea_memorias)
        fut_patrones = ejecutor.submit(_tarea_patrones)
        fut_metadatos = ejecutor.submit(_tarea_metadatos)

        # 0.0 = no se esperó acá. El router corre en paralelo y su tiempo
        # real se loguea aparte cuando se resuelve (t_router_paralelo_ms en
        # chat_turn, ver _resolver_router_paralelo_chat).
        router_hints, tiempos["t_context_router_ms"] = resultado_vacio(), 0.0
        memorias_vigentes, ids_a_desactivar, tiempos["t_memorias_ms"] = fut_memorias.result()
        patrones, tiempos["t_patrones_ms"] = fut_patrones.result()
        dias_inactivo, ultimo_modulo_critico, checkin_hoy, tiempos["t_metadatos_ms"] = fut_metadatos.result()
    # Tiempo de PARED del bloque paralelo — es el que importa para el total
    # (sumar los 4 de arriba exageraría, se solapan a propósito).
    tiempos["t_paralelo_ms"] = round((time.perf_counter() - _t_paralelo_inicio) * 1000, 1)
    _t0 = time.perf_counter()  # reengancha _checkpoint(): las etapas de acá para abajo vuelven a ser secuenciales

    # crisis_score acá es SOLO keywords + crisis_verifier (líneas de arriba)
    # — el aporte del router (si escala) se loguea aparte cuando se resuelve,
    # ver _resolver_router_paralelo_chat.
    if crisis_score >= 0.35:
        background_tasks.add_task(
            feedback_repo.save_crisis_log,
            user_id, ultimo_mensaje, crisis.get("category") or "ROUTER_RISK", crisis_log_level,
        )

    # ── Memoria proactiva contextual ─────────────────────────────────
    # Se elige A LO SUMO UNA cosa para traer al prompt (evento con fecha,
    # tema abierto sin resolver, o recurso propio del usuario) según el
    # estado emocional que ya clasificó el router. Solo fuera de contexto de
    # riesgo. router_hints acá SIEMPRE es resultado_vacio() (ok=False) — el
    # router real todavía no contestó — así que esto naturalmente no elige
    # nada basado en estado emocional (solo el evento con fecha, que no
    # depende del router), y se degrada bien.
    hoy = date.today()
    evento_proactivo: Optional[Dict[str, Any]] = None
    tema_abierto: Optional[Dict[str, Any]] = None
    memoria_recurso: Optional[Dict[str, Any]] = None
    memoria_ctx_id: Optional[str] = None
    if crisis_score < 0.35:
        try:
            eventos = get_proactive_memories(user_id=user_id, hoy=hoy)
            evento_top = eventos[0] if eventos else None

            router_ok = bool(router_hints.get("ok"))
            estado_r = router_hints.get("estado_emocional") if router_ok else None

            recursos = (
                get_resource_memories(user_id=user_id)
                if estado_r in ("triste_vacio", "ansioso", "abrumado")
                else []
            )
            temas = (
                get_open_topics(user_id=user_id)
                if (estado_r in ("neutral", "metas", "buenas_noticias") and not evento_top)
                else []
            )

            eleccion = elegir_memoria_contextual(
                estado_emocional=estado_r,
                router_ok=router_ok,
                riesgo_score=crisis_score,
                evento=evento_top,
                temas_abiertos=temas,
                recursos=recursos,
            )
            if eleccion:
                memoria_ctx_id = (eleccion.get("memoria") or {}).get("id")
                if eleccion["tipo"] == "evento":
                    evento_proactivo = eleccion["memoria"]
                elif eleccion["tipo"] == "tema_abierto":
                    tema_abierto = eleccion["memoria"]
                elif eleccion["tipo"] == "recurso":
                    memoria_recurso = eleccion["memoria"]
        except Exception as e:
            capturar_error(e, contexto="memoria_contextual")
            print(f"⚠️ No se pudo elegir memoria contextual: {e}")
    _checkpoint("t_proactivo_ms")

    es_inicio_sesion = len(conversation) == 1
    es_primera_vez = (num_interacciones == 1 and not memorias_vigentes)

    historial_reciente = [m.model_dump() for m in conversation[-4:]]

    mensajes_numa = [m.content for m in conversation if m.role == "assistant"]
    preguntas_seguidas = 0
    for contenido in reversed(mensajes_numa):
        if contenido.rstrip().rstrip('"\'').endswith("?"):
            preguntas_seguidas += 1
        else:
            break

    # Apertura/cierre del ÚLTIMO mensaje de Numa: dependen solo del historial
    # (no del mensaje nuevo, que todavía no existe acá).
    familia_apertura_previa = None
    previo_cierre_presencia = False
    for m in reversed(conversation[:-1]):
        if m.role == "assistant":
            familia_apertura_previa = _familia_apertura(m.content)
            previo_cierre_presencia = _cierra_con_presencia(m.content)
            break

    def _reconstruir_prompt(
        crisis_score_: float,
        router_hints_: Dict[str, Any],
        evento_proactivo_: Optional[Dict[str, Any]],
        tema_abierto_: Optional[Dict[str, Any]],
        memoria_recurso_: Optional[Dict[str, Any]],
    ) -> str:
        """Reconstruye el system_prompt con crisis_score/router_hints/memoria
        proactiva actualizados, manteniendo todo lo demás igual. La usa
        chat_endpoint para REGENERAR la respuesta cuando el context_router
        — resuelto en paralelo, recién después del LLM principal, ver
        _resolver_router_paralelo() — escala el riesgo más de lo que sabían
        las keywords: caso raro, pero cuando pasa, el prompt original no
        tenía los módulos de crisis activados.

        Clausura sobre las variables locales de _preparar_turno a propósito:
        así no hace falta devolverlas todas sueltas solo para este caso raro."""
        return construir_prompt(
            perfil=perfil,
            memorias=memorias_vigentes,
            patrones=patrones,
            es_inicio_sesion=es_inicio_sesion,
            num_interacciones=num_interacciones,
            es_primera_vez=es_primera_vez,
            ubicacion=body.ubicacion.model_dump() if body.ubicacion else None,
            dias_inactivo=dias_inactivo,
            checkin_hoy=checkin_hoy,
            checkin_recien_hecho=bool(body.checkin_recien_hecho),
            crisis_score=crisis_score_,
            ultimo_modulo_critico=ultimo_modulo_critico,
            historial_reciente=historial_reciente,
            mood_actual=body.ultimo_mood,
            ultimo_mensaje=ultimo_mensaje,
            preguntas_seguidas=preguntas_seguidas,
            hoy=hoy,
            evento_proactivo=evento_proactivo_,
            tema_abierto=tema_abierto_,
            memoria_recurso=memoria_recurso_,
            router_hints=router_hints_,
        )

    system_prompt = _reconstruir_prompt(
        crisis_score, router_hints, evento_proactivo, tema_abierto, memoria_recurso,
    )
    _checkpoint("t_prompt_ms")

    return {
        "crisis_confirmada": False,
        "conversation": conversation,
        "system_prompt": system_prompt,
        "crisis_score": crisis_score,
        "ultimo_mensaje": ultimo_mensaje,
        "hoy": hoy,
        "memorias_vigentes": memorias_vigentes,
        "ids_a_desactivar": ids_a_desactivar,
        "evento_proactivo": evento_proactivo,
        "tema_abierto": tema_abierto,
        "_tiempos": tiempos,
        # El router sigue corriendo mientras el LLM principal genera.
        # chat_endpoint lo resuelve bloqueando, después del LLM principal —
        # ver _resolver_router_paralelo().
        "_fut_router_paralelo": fut_router_paralelo,
        # Solo la usa chat_endpoint, para el caso raro de regenerar la
        # respuesta si el router escala el riesgo — ver _reconstruir_prompt().
        "_reconstruir_prompt": _reconstruir_prompt,
        "memoria_ctx_id": memoria_ctx_id,
        "preguntas_seguidas": preguntas_seguidas,
        "ultimo_modulo_critico": ultimo_modulo_critico,
        "familia_apertura_previa": familia_apertura_previa,
        "previo_cierre_presencia": previo_cierre_presencia,
    }


def _resolver_router_paralelo(fut_router_paralelo) -> "tuple[Dict[str, Any], float, Optional[float], Dict[str, Any]]":
    """Resuelve (bloqueando) el future del context_router lanzado en paralelo
    en _preparar_turno. Usado por chat_endpoint DESPUÉS de llamar al LLM
    principal: todavía no se mandó nada al usuario, y en la inmensa mayoría
    de los turnos el router ya terminó para cuando el LLM principal contesta
    (es más rápido), así que este bloqueo no cuesta nada en la práctica.

    Fail-safe: cualquier error (o que nunca se haya lanzado el future) se
    trata como router caído — mismo router_hints "ok=False" que ya maneja
    el resto del código cuando clasificar_contexto falla.

    Devuelve (router_hints, score_router, t_router_paralelo_ms, router_meta).
    score_router es 0.0 si el router no dio señal, falló, o no corrió.
    """
    if fut_router_paralelo is None:
        return resultado_vacio(), 0.0, None, {}
    try:
        hints, t_router_ms = fut_router_paralelo.result()
    except Exception as e:
        capturar_error(e, contexto="router_paralelo_chat")
        return resultado_vacio(), 0.0, None, {}
    meta = hints.pop("_router", None) or {}
    score = score_riesgo_router(hints.get("senal_riesgo", "none")) if hints.get("ok") else 0.0
    return hints, score, t_router_ms, meta


def _resolver_router_paralelo_chat(
    *,
    fut_router_paralelo,
    crisis_score: float,
    ultimo_mensaje: str,
    user_id: str,
    background_tasks: BackgroundTasks,
    reconstruir_prompt,
    llamar_llm,
    evento_proactivo: Optional[Dict[str, Any]],
    tema_abierto: Optional[Dict[str, Any]],
    memoria_ctx_id: Optional[str],
) -> Dict[str, Any]:
    """Decide qué hacer con el resultado FINAL del router (ya resuelto vía
    _resolver_router_paralelo) contra la respuesta que el LLM principal YA
    generó con un prompt armado solo con keywords.

    Tres desenlaces posibles, en orden de gravedad:
      - Riesgo EXPLÍCITO que las keywords no vieron (score >= 0.60, cruzando
        una banda que crisis_score no había cruzado): se descarta lo generado
        y se devuelve la contención hardcodeada — devuelve "respuesta_corte".
      - Riesgo MEDIO que las keywords no vieron (score >= 0.35, cruzando esa
        banda): se regenera con el prompt correcto (los módulos de crisis
        activados) — `llamar_llm(nuevo_prompt)` se invoca UNA vez más.
      - Cualquier otro caso (sin escalada, o escalada que no cruza una banda
        nueva — ej. 0.50 a 0.55, mismos módulos): no hace nada, la respuesta
        original queda como está. Es el caso común, el que gana la latencia.

    El gate es "¿cruza una banda que crisis_score no había cruzado?", no
    "¿el score subió?" — construir_prompt solo cambia de módulo en los cortes
    0.35 y 0.60 (numa_prompt.py, seleccionar_modulos): un salto de 0.50 a 0.55
    no cambiaría nada del prompt, y regenerar ahí sería puro gasto.

    Devuelve un dict: "respuesta_corte" (no-None si hay que devolverla tal
    cual, sin más post-procesamiento), "result" (la respuesta del LLM a usar
    — None si no hubo regeneración), "crisis_score"/"evento_proactivo"/
    "tema_abierto"/"memoria_ctx_id" (actualizados si hubo escalada), y "diag"
    (campos para el log).
    """
    router_hints_par, router_score_par, t_router_paralelo_ms, router_meta_par = (
        _resolver_router_paralelo(fut_router_paralelo)
    )
    diag: Dict[str, Any] = {
        # router_ok separa dos cosas que router_score_paralelo confunde: el
        # score de "sin riesgo" es 0.0, y `0.0 or None` da None — el MISMO
        # valor que cuando el router no contestó. Con solo ese campo, un
        # router muerto se ve igual que una charla tranquila, que es
        # exactamente por qué estuvo caído semanas sin que nadie lo notara
        # (Nebius dejó de servir el modelo y todos los turnos caían a
        # keywords, en silencio). Con router_ok, "false" es inequívoco.
        "router_ok": bool(router_hints_par.get("ok")),
        "router_score_paralelo": router_score_par or None,
        "t_router_paralelo_ms": t_router_paralelo_ms,
        "router_provider": router_meta_par.get("provider"),
        "router_model": router_meta_par.get("model"),
        "router_reintento": router_meta_par.get("reintento") or None,
        "router_accion": None,
    }
    sin_cambios = {
        "respuesta_corte": None, "result": None, "crisis_score": crisis_score,
        "evento_proactivo": evento_proactivo, "tema_abierto": tema_abierto,
        "memoria_ctx_id": memoria_ctx_id, "diag": diag,
    }

    if router_score_par >= UMBRAL_CORTE_LLAMADA and crisis_score < UMBRAL_CORTE_LLAMADA:
        diag["router_accion"] = "corte"
        background_tasks.add_task(
            feedback_repo.save_crisis_log,
            user_id, ultimo_mensaje, "ROUTER_PARALELO_CHAT", "high",
        )
        return {
            "respuesta_corte": {
                "message":          respuesta_contencion_generica(),
                "mood":             "sad",
                "suggested_action": None,
                "risk_level":       "high",
                "nuevas_memorias":  None,
            },
            "result": None,
            "crisis_score": max(crisis_score, router_score_par),
            "evento_proactivo": None, "tema_abierto": None, "memoria_ctx_id": None,
            "diag": diag,
        }

    if router_score_par >= 0.35 and crisis_score < 0.35:
        diag["router_accion"] = "regenero"
        crisis_score = router_score_par
        # La memoria proactiva se eligió con el crisis_score viejo (< 0.35);
        # con el nuevo ya no correspondería mostrarla — se anula para no
        # colarla en un turno de riesgo.
        evento_proactivo = None
        tema_abierto = None
        memoria_ctx_id = None
        background_tasks.add_task(
            feedback_repo.save_crisis_log,
            user_id, ultimo_mensaje, "ROUTER_PARALELO_CHAT", "medium",
        )
        nuevo_prompt = reconstruir_prompt(
            crisis_score, router_hints_par, evento_proactivo, tema_abierto, None,
        )
        return {
            "respuesta_corte": None,
            "result": llamar_llm(nuevo_prompt),
            "crisis_score": crisis_score,
            "evento_proactivo": evento_proactivo, "tema_abierto": tema_abierto,
            "memoria_ctx_id": memoria_ctx_id, "diag": diag,
        }

    return sin_cambios


def _procesar_memorias_turno(
    memorias_llm: List[Dict[str, Any]],
    memorias_vigentes: List[Dict[str, Any]],
    ultimo_mensaje: str,
    hoy: date,
    crisis_score: float,
) -> List[Dict[str, Any]]:
    """Valida/clampea/dedupea las memorias que devolvió el LLM antes de
    persistir. Extraído de chat_endpoint."""
    es_post_ejercicio = ultimo_mensaje.strip().startswith("[Post-ejercicio")
    contenidos_conocidos = [(m.get("content") or "") for m in memorias_vigentes]
    memorias_validadas: List[Dict[str, Any]] = []
    for m in memorias_llm:
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if _es_memoria_duplicada(content, contenidos_conocidos):
            continue
        prioridad = _normalizar_prioridad(
            content,
            _validar_priority(m.get("priority")),
            crisis_score,
            es_post_ejercicio,
        )
        mem: Dict[str, Any] = {
            "content":  content,
            "category": _validar_category(m.get("category")),
            "priority": prioridad,
        }
        # Memoria proactiva: si el LLM marcó un evento con fecha, lo validamos.
        event_title, event_date = _validar_evento(m.get("event"), content, hoy)
        if event_title and event_date:
            mem["event_title"] = event_title
            mem["event_date"] = event_date
        # Tema abierto: solo memorias SIN fecha (el ciclo de los eventos ya
        # lo maneja followed_up). Recurso: algo que el usuario dijo que le
        # hizo bien. Ambos son booleanos del LLM → clampeo estricto.
        if m.get("open") is True and not (event_title and event_date):
            mem["status"] = "open"
        if m.get("helped") is True:
            mem["helped_before"] = True
        # Respaldo server-side de los flags: el LLM sub-produce open/helped y
        # sin ellos el canal proactivo se queda sin material.
        if "status" not in mem and not (event_title and event_date) and detectar_tema_abierto(content):
            mem["status"] = "open"
        if "helped_before" not in mem and detectar_recurso(content):
            mem["helped_before"] = True
        memorias_validadas.append(mem)
        contenidos_conocidos.append(content)

    # Respaldo: si el LLM no guardó ninguna memoria, detectar evento próximo con fecha
    if not memorias_validadas:
        evento = detectar_evento_con_fecha(ultimo_mensaje, hoy)
        if evento:
            memorias_validadas.append(evento)

    return memorias_validadas


def _disparar_tareas_turno(
    background_tasks: BackgroundTasks,
    *,
    user_id: str,
    conversation: List["Message"],
    mensaje_final: str,
    mood: Optional[str],
    memorias_validadas: List[Dict[str, Any]],
    ids_a_desactivar: List[str],
    evento_proactivo: Optional[Dict[str, Any]],
    tema_abierto: Optional[Dict[str, Any]],
    memoria_ctx_id: Optional[str],
    ultimo_mensaje: str,
    hoy: date,
) -> None:
    """Tareas de background que se disparan una vez que hay respuesta final:
    guardar conversación/memorias, follow-up de eventos, cierre de temas
    abiertos, cooldown de mención proactiva. Extraído de chat_endpoint."""
    background_tasks.add_task(marcar_evento_followup, user_id, ultimo_mensaje, hoy)
    background_tasks.add_task(cerrar_temas_abiertos, user_id, ultimo_mensaje)

    if memoria_ctx_id:
        cierre = None
        if evento_proactivo and evento_proactivo.get("bucket") in ("ayer", "reciente"):
            cierre = "followup"
        elif tema_abierto:
            cierre = "cerrar_tema"
        background_tasks.add_task(marcar_proactivo_insertado, memoria_ctx_id, cierre)

    if conversation:
        background_tasks.add_task(
            conversation_repo.save,
            user_id,
            conversation[-1].content,
            mensaje_final,
            memorias_validadas,
            mood,
        )
        if ids_a_desactivar:
            background_tasks.add_task(conversation_repo.deactivate_memories, ids_a_desactivar)
        if memorias_validadas:
            invalidate_patterns_cache(user_id)


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("18/minute")
def chat_endpoint(
    request: Request,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    auth_user_id: str = Depends(get_current_user_id),
):
    try:
        # El user_id viene SIEMPRE del token, nunca del body (IDOR fix)
        user_id = auth_user_id
        # Solo para los logs operativos (Railway) — nunca a Sentry ni junto
        # con contenido de mensajes. Ver docstring de get_current_user_id.
        email = getattr(request.state, "user_email", None)

        turno = _preparar_turno(body, user_id, background_tasks)
        if turno["crisis_confirmada"]:
            log_event(
                "chat_turn", endpoint="/chat", user_id=user_id, email=email,
                crisis_hardcoded=True, risk_level="high", llm_provider=None,
                **turno.get("_tiempos", {}),
            )
            return turno["respuesta_crisis"]

        conversation = turno["conversation"]
        crisis_score = turno["crisis_score"]
        ultimo_mensaje = turno["ultimo_mensaje"]
        hoy = turno["hoy"]
        memorias_vigentes = turno["memorias_vigentes"]
        ids_a_desactivar = turno["ids_a_desactivar"]
        evento_proactivo = turno["evento_proactivo"]
        tema_abierto = turno["tema_abierto"]
        memoria_ctx_id = turno["memoria_ctx_id"]
        preguntas_seguidas = turno["preguntas_seguidas"]
        ultimo_modulo_critico = turno["ultimo_modulo_critico"]

        result = llm.generate_response(
            conversation=[m.model_dump() for m in conversation],
            system_prompt=turno["system_prompt"],
        )

        # ── Router en paralelo: se resuelve DESPUÉS del LLM principal ────
        # El prompt de arriba se armó SIN esperar al router (router_hints
        # ok=False, solo keywords) — ver _preparar_turno. Acá, con el LLM
        # principal ya resuelto, se consulta el resultado FINAL del router
        # (normalmente ya terminó — es más rápido — así que esto no bloquea
        # nada en la práctica) y se decide si hace falta actuar — ver
        # _resolver_router_paralelo_chat().
        resolucion = _resolver_router_paralelo_chat(
            fut_router_paralelo=turno.get("_fut_router_paralelo"),
            crisis_score=crisis_score,
            ultimo_mensaje=ultimo_mensaje,
            user_id=user_id,
            background_tasks=background_tasks,
            reconstruir_prompt=turno["_reconstruir_prompt"],
            llamar_llm=lambda system_prompt: llm.generate_response(
                conversation=[m.model_dump() for m in conversation],
                system_prompt=system_prompt,
            ),
            evento_proactivo=evento_proactivo,
            tema_abierto=tema_abierto,
            memoria_ctx_id=memoria_ctx_id,
        )
        router_diag = resolucion["diag"]

        if resolucion["respuesta_corte"] is not None:
            # Riesgo EXPLÍCITO que las keywords no vieron: log aparte porque
            # acá se corta, el log_event de más abajo no llega a correr.
            log_event(
                "chat_turn", endpoint="/chat", user_id=user_id, email=email,
                crisis_hardcoded=True, risk_level="high", llm_provider=None,
                **router_diag,
                **turno.get("_tiempos", {}),
            )
            return resolucion["respuesta_corte"]

        crisis_score = resolucion["crisis_score"]
        evento_proactivo = resolucion["evento_proactivo"]
        tema_abierto = resolucion["tema_abierto"]
        memoria_ctx_id = resolucion["memoria_ctx_id"]
        if resolucion["result"] is not None:
            # Riesgo MEDIO que las keywords no vieron: se regeneró con el
            # prompt correcto — esta es la respuesta a usar de acá en más.
            result = resolucion["result"]

        # Filtro determinístico del "che": el modelo lo repite como muletilla
        # en casi cada mensaje a pesar del M02; se elimina acá.
        if result.get("message"):
            result["message"] = _quitar_che(result["message"])

        # Anti-tic de apertura: si el modelo abre con la misma fórmula
        # ("Sentís que...", "Es como que...") que su mensaje anterior, la
        # aplanamos a una afirmación. M05 ya lo prohíbe; esto es la red
        # determinística. Solo aplica cuando se repite respecto del turno previo.
        mensaje_actual = result.get("message") or ""
        familia_actual = _familia_apertura(mensaje_actual)
        if familia_actual and familia_actual == turno["familia_apertura_previa"]:
            aplanado = _aplanar_apertura(mensaje_actual)
            if aplanado and aplanado != mensaje_actual and len(aplanado) >= 10:
                result["message"] = aplanado

        # Anti-repetición de cierres de presencia: si el turno anterior de Numa
        # ya cerró con "estoy acá"/"te leo"/etc. y este también, recortamos el
        # de este para que no suene a plantilla. Fuera de crisis (ahí es válido).
        mensaje_actual = result.get("message") or ""
        if (
            crisis_score < 0.35
            and not ultimo_modulo_critico
            and turno["previo_cierre_presencia"]
            and _cierra_con_presencia(mensaje_actual)
        ):
            recortado = _quitar_cierre_presencia(mensaje_actual)
            # Guardia anti-cortante: solo si queda un cuerpo con sustancia.
            if recortado and len(recortado) >= 40 and len(recortado) >= 0.4 * len(mensaje_actual):
                result["message"] = recortado

        # Enforcement de la regla de preguntas: con racha de 2+ el prompt ya
        # prohibió preguntar; si el modelo desobedece igual, se recorta la
        # pregunta final acá. No aplica en contexto de crisis (las preguntas
        # de seguridad nunca se tocan).
        if (
            preguntas_seguidas >= 2
            and crisis_score < 0.35
            and not ultimo_modulo_critico
            and (result.get("message") or "").rstrip().rstrip("\"'” ").endswith("?")
        ):
            recortado = _quitar_pregunta_final(result["message"])
            # Guardia anti-cortante: si el recorte deja un fragmento pobre
            # ("Eso pesa."), mejor dejar la pregunta original que sonar seco.
            if recortado and len(recortado) >= 40 and len(recortado) >= 0.35 * len(result["message"]):
                result["message"] = recortado

        memorias_llm: List[Dict[str, Any]] = result.get("memories") or []
        memorias_validadas = _procesar_memorias_turno(
            memorias_llm, memorias_vigentes, ultimo_mensaje, hoy, crisis_score,
        )

        # Sin early-return: reportar el nivel real de señal detectada
        risk_level = "medium" if crisis_score >= 0.35 else "none"

        llm_info = result.get("_llm") or {}
        etiquetar_request(
            llm_provider=llm_info.get("provider"),
            llm_model=llm_info.get("model"),
        )
        tiempos = turno.get("_tiempos", {})
        t_preparar_turno_ms = _sumar_tiempos(tiempos)
        log_event(
            "chat_turn",
            endpoint="/chat",
            user_id=user_id,
            email=email,
            llm_provider=llm_info.get("provider"),
            llm_model=llm_info.get("model"),
            llm_fallback=llm_info.get("fallback"),
            llm_latency_ms=llm_info.get("latency_ms"),
            mood=result.get("mood"),
            risk_level=risk_level,
            suggested_action=result.get("suggested_action"),
            memorias_nuevas=len(memorias_validadas),
            # Desglose de dónde se va el tiempo ANTES de llamar al LLM
            # principal — ver _checkpoint() en _preparar_turno. Sumado a
            # llm_latency_ms de arriba da el total real del turno.
            t_preparar_turno_ms=t_preparar_turno_ms,
            # router_diag trae router_provider/router_model/router_reintento,
            # y del router en paralelo (ver _resolver_router_paralelo_chat):
            # t_router_paralelo_ms (tiempo real, normalmente solapado con el
            # LLM principal, no sumado), router_score_paralelo, y
            # router_accion (None si no escaló nada — el caso común — o
            # "regenero" si este log ya corresponde a la respuesta regenerada;
            # "corte" nunca llega acá, tiene su propio log_event más arriba).
            **router_diag,
            **tiempos,
        )

        _disparar_tareas_turno(
            background_tasks,
            user_id=user_id,
            conversation=conversation,
            mensaje_final=result["message"],
            mood=result.get("mood"),
            memorias_validadas=memorias_validadas,
            ids_a_desactivar=ids_a_desactivar,
            evento_proactivo=evento_proactivo,
            tema_abierto=tema_abierto,
            memoria_ctx_id=memoria_ctx_id,
            ultimo_mensaje=ultimo_mensaje,
            hoy=hoy,
        )

        return {
            "message":          result["message"],
            "mood":             result["mood"],
            "suggested_action": result.get("suggested_action"),
            "risk_level":       risk_level,
            "nuevas_memorias":  memorias_validadas,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)


def _evento_ndjson(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _stream_ndjson_fijo(payload: Dict[str, Any]):
    """Generador para cuando la respuesta YA está resuelta sin pasar por el
    LLM (crisis confirmada). Mismo contrato NDJSON que el streaming real para
    que el frontend no necesite un código de lectura distinto para ese caso."""
    yield _evento_ndjson({"type": "crisis", "text": payload["message"]})
    yield _evento_ndjson({
        "type": "final",
        "mood": payload["mood"],
        "suggested_action": payload.get("suggested_action"),
        "risk_level": payload.get("risk_level"),
        "nuevas_memorias": payload.get("nuevas_memorias"),
    })


def _stream_chat_respuesta(
    turno: Dict[str, Any], user_id: str, background_tasks: BackgroundTasks, email: Optional[str] = None,
    t_inicio_request: Optional[float] = None,
):
    """Generador principal de /chat/stream: llama al LLM en streaming, va
    filtrando/emitiendo oraciones vía BufferStreamingMensaje y al final
    dispara el mismo post-procesamiento de memorias/background que /chat.

    Puerto de staging, acotado a chat escrito (sin modo_llamada — ChatRequest
    en main no tiene ese campo, así que la retención del buffer queda siempre
    en el default).

    t_inicio_request: perf_counter() tomado al ENTRAR al endpoint. Sirve para
    medir t_primer_delta_ms — ver el bloque de instrumentación más abajo.
    """
    conversation = turno["conversation"]
    crisis_score = turno["crisis_score"]
    ultimo_mensaje = turno["ultimo_mensaje"]
    hoy = turno["hoy"]
    memorias_vigentes = turno["memorias_vigentes"]
    ids_a_desactivar = turno["ids_a_desactivar"]
    evento_proactivo = turno["evento_proactivo"]
    tema_abierto = turno["tema_abierto"]
    memoria_ctx_id = turno["memoria_ctx_id"]
    preguntas_seguidas = turno["preguntas_seguidas"]
    ultimo_modulo_critico = turno["ultimo_modulo_critico"]

    buf = BufferStreamingMensaje(
        familia_apertura_previa=turno["familia_apertura_previa"],
        previo_cierre_presencia=turno["previo_cierre_presencia"],
        preguntas_seguidas=preguntas_seguidas,
        crisis_score=crisis_score,
        ultimo_modulo_critico=ultimo_modulo_critico,
    )

    # ── Instrumentación de latencia PERCIBIDA ────────────────────────
    # llm_latency_ms mide el stream COMPLETO (se calcula recién al parsear el
    # JSON de metadata, que el LLM manda último), así que NO es lo que el
    # usuario siente: para cuando ese número está, el mensaje ya se empezó a
    # revelar hace rato. Estos dos miden lo que realmente importa:
    #
    #   t_primer_delta_ms      → desde que entra el request hasta que sale la
    #                            PRIMERA oración.
    #   t_llm_primer_token_ms  → desde que arranca el generador hasta el primer
    #                            pedazo de texto del LLM.
    llm_chunks = 0
    t_llm_ultimo_token_ms: Optional[float] = None

    t_inicio_stream = time.perf_counter()
    t_primer_delta_ms: Optional[float] = None
    t_llm_primer_token_ms: Optional[float] = None

    def _marcar_primer_delta() -> None:
        nonlocal t_primer_delta_ms
        if t_primer_delta_ms is None:
            base = t_inicio_request if t_inicio_request is not None else t_inicio_stream
            t_primer_delta_ms = round((time.perf_counter() - base) * 1000, 1)

    # ── Vigilancia del context_router en paralelo ─────────────────────
    # El router se lanzó al empezar el turno y sigue corriendo mientras el LLM
    # principal genera. Se consulta SIN bloquear (done()) entre oración y
    # oración: si nunca termina, el turno sigue normal y no cuesta nada.
    fut_router_par = turno.get("_fut_router_paralelo")
    router_par_score = 0.0
    t_router_paralelo_ms: Optional[float] = None
    corte_por_riesgo = False

    def _riesgo_detectado() -> bool:
        """True si el router ya respondió y marcó riesgo explícito.

        No bloquea: si todavía no terminó devuelve False y se sigue
        emitiendo. Ese es el trade-off aceptado de correrlo en paralelo —
        puede llegar tarde, pero llega, y es infinitamente mejor que no
        correrlo (que dejaba las frases con método sin cobertura).
        """
        nonlocal router_par_score, t_router_paralelo_ms, corte_por_riesgo
        if fut_router_par is None or corte_por_riesgo or not fut_router_par.done():
            return False
        try:
            hints, t_router_paralelo_ms = fut_router_par.result()
        except Exception as e:
            capturar_error(e, contexto="router_paralelo")
            return False
        if not hints.get("ok"):
            return False
        router_par_score = score_riesgo_router(hints.get("senal_riesgo", "none"))
        corte_por_riesgo = router_par_score >= UMBRAL_CORTE_LLAMADA
        return corte_por_riesgo

    metadata: Optional[Dict[str, Any]] = None
    try:
        for tipo, valor in llm.generate_response_stream(
            conversation=[m.model_dump() for m in conversation],
            system_prompt=turno["system_prompt"],
        ):
            if tipo == "mensaje":
                ahora = time.perf_counter()
                llm_chunks += 1
                t_llm_ultimo_token_ms = round((ahora - t_inicio_stream) * 1000, 1)
                if t_llm_primer_token_ms is None:
                    t_llm_primer_token_ms = t_llm_ultimo_token_ms
                for oracion in buf.feed(valor):
                    # Se chequea ANTES de emitir, no después: si el router ya
                    # avisó, esta oración no se manda. Lo que ya salió no se
                    # puede deshacer, pero de acá en más se corta.
                    if _riesgo_detectado():
                        break
                    _marcar_primer_delta()
                    yield _evento_ndjson({"type": "delta", "text": oracion})
            else:
                metadata = valor
            if corte_por_riesgo:
                break

        if not corte_por_riesgo:
            for oracion in buf.cerrar():
                if _riesgo_detectado():
                    break
                _marcar_primer_delta()
                yield _evento_ndjson({"type": "delta", "text": oracion})

        # Última chance: el router puede haber terminado justo al final, con
        # el mensaje ya emitido. Igual conviene cortar y mostrar la tarjeta —
        # el usuario dijo algo que necesita los teléfonos a la vista.
        if not corte_por_riesgo and fut_router_par is not None:
            _riesgo_detectado()

        if corte_por_riesgo:
            # Mismo tipo de evento que la crisis por keywords: el cliente ya
            # sabe manejarlo (muestra la tarjeta con los teléfonos tocables
            # en vez del mensaje que se estaba armando).
            yield _evento_ndjson({
                "type": "crisis",
                "text": respuesta_contencion_generica(),
                "origen": "router_paralelo",
            })
    except Exception as e:
        # El stream se cortó a mitad de camino: no se reintenta con otro
        # proveedor para no mostrar un mensaje "Frankenstein". Lo que ya se
        # emitió queda tal cual mostrado; sin evento "final" el frontend lo
        # trata como corte de conexión.
        capturar_error(e, contexto="chat_stream")
        print(f"⚠️ /chat/stream: se cortó el generador: {e}")
        return

    mensaje_final = buf.mensaje_completo()
    metadata = metadata or {"mood": "neutral", "suggested_action": None, "memories": []}

    if corte_por_riesgo:
        # Lo que se guarda como respuesta de Numa es la contención, no el
        # mensaje a medio armar: si no, el historial quedaría con una frase
        # cortada y el turno siguiente arrancaría desde ahí.
        mensaje_final = respuesta_contencion_generica()
        metadata["memories"] = []
        metadata["suggested_action"] = None
        crisis_score = max(crisis_score, router_par_score)
        background_tasks.add_task(
            feedback_repo.save_crisis_log,
            user_id, ultimo_mensaje, "ROUTER_PARALELO_CHAT_STREAM", "high",
        )

    memorias_llm: List[Dict[str, Any]] = metadata.get("memories") or []
    memorias_validadas = _procesar_memorias_turno(
        memorias_llm, memorias_vigentes, ultimo_mensaje, hoy, crisis_score,
    )
    risk_level = "high" if corte_por_riesgo else ("medium" if crisis_score >= 0.35 else "none")

    llm_info = metadata.get("_llm") or {}
    etiquetar_request(
        llm_provider=llm_info.get("provider"),
        llm_model=llm_info.get("model"),
    )
    tiempos = turno.get("_tiempos", {})
    log_event(
        "chat_turn",
        endpoint="/chat/stream",
        user_id=user_id,
        email=email,
        router_paralelo=bool(fut_router_par),
        t_router_paralelo_ms=t_router_paralelo_ms,
        router_score=router_par_score or None,
        router_corte=corte_por_riesgo or None,
        llm_provider=llm_info.get("provider"),
        llm_model=llm_info.get("model"),
        llm_fallback=llm_info.get("fallback"),
        llm_latency_ms=llm_info.get("latency_ms"),
        llm_cut=llm_info.get("cut"),
        # OJO al leer estos dos contra llm_latency_ms: aquél es el stream
        # entero, éstos son hasta el primer delta.
        t_primer_delta_ms=t_primer_delta_ms,
        t_llm_primer_token_ms=t_llm_primer_token_ms,
        t_llm_ultimo_token_ms=t_llm_ultimo_token_ms,
        llm_chunks=llm_chunks,
        mensaje_len=len(mensaje_final),
        prompt_chars=len(turno.get("system_prompt") or ""),
        prompt_tokens=llm_info.get("prompt_tokens"),
        cached_tokens=llm_info.get("cached_tokens"),
        completion_tokens=llm_info.get("completion_tokens"),
        t_preparar_turno_ms=_sumar_tiempos(tiempos),
        **tiempos,
        mood=metadata.get("mood"),
        risk_level=risk_level,
        suggested_action=metadata.get("suggested_action"),
        memorias_nuevas=len(memorias_validadas),
    )

    _disparar_tareas_turno(
        background_tasks,
        user_id=user_id,
        conversation=conversation,
        mensaje_final=mensaje_final,
        mood=metadata.get("mood"),
        memorias_validadas=memorias_validadas,
        ids_a_desactivar=ids_a_desactivar,
        evento_proactivo=evento_proactivo,
        tema_abierto=tema_abierto,
        memoria_ctx_id=memoria_ctx_id,
        ultimo_mensaje=ultimo_mensaje,
        hoy=hoy,
    )

    yield _evento_ndjson({
        "type": "final",
        "mood": metadata.get("mood"),
        "suggested_action": metadata.get("suggested_action"),
        "risk_level": risk_level,
        "nuevas_memorias": memorias_validadas,
    })


@router.post("/chat/stream")
@limiter.limit("18/minute")
def chat_stream_endpoint(
    request: Request,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    auth_user_id: str = Depends(get_current_user_id),
):
    """Como /chat, pero streamea la respuesta en NDJSON en vez de esperar el
    JSON completo — lo usa el chat escrito de numa-mobile para el efecto
    typewriter (ver ChatScreen.tsx)."""
    user_id = auth_user_id
    email = getattr(request.state, "user_email", None)
    # Antes de _preparar_turno a propósito: t_primer_delta_ms tiene que
    # incluir el trabajo previo (memorias, proactivo, prompt), no solo el
    # LLM — es el silencio completo que el usuario ve del lado del servidor.
    t_inicio_request = time.perf_counter()
    try:
        turno = _preparar_turno(body, user_id, background_tasks)
    except Exception:
        # Todavía no se mandó ningún byte de respuesta -> se puede devolver
        # un error HTTP normal, como en /chat.
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)

    if turno["crisis_confirmada"]:
        log_event(
            "chat_turn", endpoint="/chat/stream", user_id=user_id, email=email,
            crisis_hardcoded=True, risk_level="high", llm_provider=None,
            **turno.get("_tiempos", {}),
        )
        generador = _stream_ndjson_fijo(turno["respuesta_crisis"])
    else:
        generador = _stream_chat_respuesta(
            turno, user_id, background_tasks, email=email,
            t_inicio_request=t_inicio_request,
        )

    # background=background_tasks es necesario: a diferencia de devolver un
    # dict (donde FastAPI engancha las tareas solas), acá se devuelve un
    # Response explícito y hay que pasárselo a mano para que corran.
    return StreamingResponse(
        generador,
        media_type="application/x-ndjson",
        background=background_tasks,
    )


# El cliente corta en 10 mensajes de invitado; este es el respaldo server-side
# (con margen para el historial que el cliente reenvía completo).
MAX_GUEST_USER_MESSAGES = 12


@router.post("/chat/guest", response_model=ChatResponse)
@limiter.limit("10/minute")
def chat_guest_endpoint(request: Request, body: ChatRequest):
    """Chat para usuarios sin cuenta (modo invitado de la app).

    Sin perfil, sin memorias y sin persistencia: la conversación vive solo en
    el dispositivo hasta que el usuario se registra (ahí se migra vía
    /chat/import). El pipeline de crisis se mantiene completo — detector,
    verificador y respuesta determinística — porque el riesgo no distingue
    entre registrados e invitados.
    """
    try:
        conversation = body.conversation[-MAX_CONV_MESSAGES:]
        for m in conversation:
            if len(m.content) > MAX_MSG_CHARS:
                m.content = m.content[:MAX_MSG_CHARS]

        num_user_msgs = sum(1 for m in conversation if m.role == "user")
        if num_user_msgs > MAX_GUEST_USER_MESSAGES:
            raise HTTPException(
                status_code=403,
                detail="Límite de mensajes de invitado alcanzado. Creá tu cuenta para seguir hablando.",
            )

        ultimo_mensaje = conversation[-1].content if conversation else ""
        crisis = detectar_crisis(ultimo_mensaje)
        crisis_score = crisis.get("score", 0.0)

        if crisis["detected"]:
            if confirmar_riesgo_real(ultimo_mensaje, crisis["category"] or ""):
                # Sin crisis_log: no hay user_id al que asociarlo.
                log_event(
                    "chat_turn", endpoint="/chat/guest", user_id=None,
                    crisis_hardcoded=True, risk_level="high", llm_provider=None,
                )
                return {
                    "message":          crisis["message"],
                    "mood":             "sad",
                    "suggested_action": None,
                    "risk_level":       "high",
                    "nuevas_memorias":  None,
                }
            crisis_score = 0.45

        router_hints = clasificar_contexto([m.model_dump() for m in conversation])
        if router_hints.get("ok"):
            crisis_score = max(
                crisis_score,
                score_riesgo_router(router_hints.get("senal_riesgo", "none")),
            )

        num_interacciones = len(conversation)
        historial_reciente = [m.model_dump() for m in conversation[-4:]]

        mensajes_numa = [m.content for m in conversation if m.role == "assistant"]
        preguntas_seguidas = 0
        for contenido in reversed(mensajes_numa):
            if contenido.rstrip().rstrip('"\'').endswith("?"):
                preguntas_seguidas += 1
            else:
                break

        system_prompt = construir_prompt(
            perfil=None,
            memorias=[],
            patrones=[],
            es_inicio_sesion=num_interacciones == 1,
            num_interacciones=num_interacciones,
            es_primera_vez=num_interacciones == 1,
            ubicacion=body.ubicacion.model_dump() if body.ubicacion else None,
            crisis_score=crisis_score,
            historial_reciente=historial_reciente,
            mood_actual=body.ultimo_mood,
            ultimo_mensaje=ultimo_mensaje,
            preguntas_seguidas=preguntas_seguidas,
            hoy=date.today(),
            router_hints=router_hints,
        )

        result = llm.generate_response(
            conversation=[m.model_dump() for m in conversation],
            system_prompt=system_prompt,
        )

        if result.get("message"):
            result["message"] = _quitar_che(result["message"])

        llm_info = result.get("_llm") or {}
        log_event(
            "chat_turn",
            endpoint="/chat/guest",
            user_id=None,
            llm_provider=llm_info.get("provider"),
            llm_model=llm_info.get("model"),
            llm_fallback=llm_info.get("fallback"),
            llm_latency_ms=llm_info.get("latency_ms"),
            mood=result.get("mood"),
            risk_level="medium" if crisis_score >= 0.35 else "none",
            suggested_action=result.get("suggested_action"),
        )

        return {
            "message":          result["message"],
            "mood":             result["mood"],
            "suggested_action": result.get("suggested_action"),
            "risk_level":       "medium" if crisis_score >= 0.35 else "none",
            "nuevas_memorias":  None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)


@router.post("/chat/import")
@limiter.limit("3/minute")
def chat_import(
    request: Request,
    body: ChatImportRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Migra al usuario recién registrado la conversación que tuvo como
    invitado, para que Numa no 'olvide' lo que ya hablaron."""
    mensajes = [
        {"role": m.role, "content": m.content[:MAX_MSG_CHARS], "mood": m.mood}
        for m in body.messages[-40:]
        if (m.content or "").strip()
    ]
    if not mensajes:
        return {"ok": True, "imported": 0}
    try:
        conversation_repo.import_messages(user_id, mensajes)
        return {"ok": True, "imported": len(mensajes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=MENSAJE_GENERICO)
