import re
from datetime import date, timedelta
from difflib import SequenceMatcher

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, UploadFile, File, Depends
from pydantic import BaseModel
from typing import List, Literal, Optional, Dict, Any
from slowapi import Limiter
from app.core.auth import get_current_user_id
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
from app.crisis_detector import detectar_crisis
from app.crisis_verifier import confirmar_riesgo_real
from app.context_router import clasificar_contexto, score_riesgo_router
from app.speech_service import speech_to_text
from app.repositories.user_repository import UserRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.feedback_repository import FeedbackRepository

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


def _quitar_pregunta_final(texto: str) -> str:
    """Recorta la pregunta final del mensaje conservando lo afirmativo.

    Red de seguridad para la regla de preguntas: si el LLM ignora el bloqueo
    del prompt y vuelve a cerrar con pregunta, se corta acá. En vez de borrar
    la oración entera, intenta conservar la parte afirmativa antes del '¿'
    (ej: "Hace días que te sentís así, ¿pasó algo?" → "Hace días que te
    sentís así."). Devuelve "" si el mensaje entero era pregunta (en ese caso
    se deja el original).
    """
    partes = re.split(r"(?<=[.!?…])\s+", texto.strip())
    while partes and partes[-1].rstrip("\"'” ").endswith("?"):
        ultima = partes.pop()
        idx = ultima.find("¿")
        if idx > 0:
            prefijo = ultima[:idx].rstrip(" ,;:—–-")
            if len(prefijo) >= 12:
                if not prefijo.endswith((".", "!", "…")):
                    prefijo += "."
                partes.append(prefijo)
    return " ".join(partes).strip()


def _quitar_che(texto: str) -> str:
    """Saca por completo la muletilla "che" del mensaje del LLM.

    El prompt (M02) ya pide usarla con cuentagotas, pero el LLM la mete por
    inercia en casi cada mensaje (suena a guión). Este filtro la elimina de
    forma determinística y recompone la puntuación y las mayúsculas afectadas.
    No toca "noche", "leche", "coche", etc. (usa límites de palabra).
    """
    if "che" not in texto.lower():
        return texto

    original = texto
    t = texto

    # "che" al inicio de una frase (arranque del texto o tras . ! ? …):
    # "Che, parece..." → "Parece...";  ". Che, ¿estás?" → ". ¿Estás?"
    t = re.sub(
        r"(^|[.!?…]\s+)che\b\s*[,:;]?\s*([¿¡]*)([a-záéíóúñ])",
        lambda m: m.group(1) + m.group(2) + m.group(3).upper(),
        t, flags=re.IGNORECASE,
    )
    # "..., che, ..." en el medio → una sola coma
    t = re.sub(r"\s*,\s*che\b\s*,", ",", t, flags=re.IGNORECASE)
    # "..., che." / "..., che!" al cierre → quita ", che", deja la puntuación
    t = re.sub(r"\s*,\s*che\b", "", t, flags=re.IGNORECASE)
    # cualquier "che" suelto que haya quedado
    t = re.sub(r"\s*\bche\b\s*", " ", t, flags=re.IGNORECASE)

    # Recomponer espacios, puntuación y comas/espacios sueltos al inicio
    t = re.sub(r"\s+([,.;:!?…])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = re.sub(r"^[\s,;:]+", "", t)

    # Si el recorte dejó algo degenerado, mejor el original
    if len(t) < 2:
        return original
    return t


# ── Anti-repetición de cierres de presencia ───────────────────────────────
# El modelo cierra casi cada mensaje con una fórmula de presencia ("estoy acá",
# "te leo", "acá ando"...). Un cierre así está bien de vez en cuando, pero turno
# a turno suena a bot (el usuario del chat que motivó esto detectó el patrón al
# instante). M05 lo desaconseja; esta es la red determinística: si el mensaje
# anterior de Numa YA cerró con presencia y este también, se recorta el cierre
# de este. NO aplica en crisis (ahí "Estoy acá" es un paso válido y buscado).
_PRESENCIA_CIERRE_RE = re.compile(
    r"(?<![\wñ])(?:"
    r"ac[áa]\s+estoy|estoy\s+ac[áa]|ac[áa]\s+ando|ac[áa]\s+andamos|ac[áa]\s+estamos|"
    r"aqu[íi]\s+estoy|ac[áa]\s+me\s+ten[ée]s|"
    r"te\s+leo|te\s+escucho|"
    r"no\s+me\s+voy\s+a\s+ning[úu]n\s+lado|no\s+me\s+muevo|"
    r"cuando\s+quieras\s+seguimos|cuando\s+quieras,\s+seguimos"
    r")(?![\wñ])",
    re.IGNORECASE,
)


def _cierra_con_presencia(texto: str) -> bool:
    """True si alguna de las últimas ~2 oraciones es un cierre CORTO de presencia
    ('Acá estoy.', 'Te leo, sin apuro.'). El límite de longitud evita marcar una
    oración larga con contenido propio que apenas menciona 'te leo'."""
    partes = re.split(r"(?<=[.!?…])\s+", (texto or "").strip())
    for p in partes[-2:]:
        if _PRESENCIA_CIERRE_RE.search(p) and len(p) <= 60:
            return True
    return False


def _quitar_cierre_presencia(texto: str) -> str:
    """Saca las oraciones finales que son solo cierre de presencia, dejando el
    cuerpo con contenido. Devuelve '' si el mensaje era puro cierre."""
    partes = re.split(r"(?<=[.!?…])\s+", (texto or "").strip())
    while partes and _PRESENCIA_CIERRE_RE.search(partes[-1]) and len(partes[-1]) <= 70:
        partes.pop()
    return " ".join(partes).strip()


# ── Anti-tic de apertura repetida ─────────────────────────────────────────
# El modelo, sobre todo al reflejar, se engancha con una misma fórmula de
# apertura ("Sentís que...", "Es como que...") y abre varios mensajes seguidos
# igual. M05 ya lo prohíbe, pero cuando lo desobedece se aplana acá: se quita
# la fórmula y el resto queda como afirmación ("Sentís que todo te pesa." →
# "Todo te pesa."). Solo se aplana si el mensaje ANTERIOR de Numa abrió con la
# MISMA familia — un único uso es una herramienta válida de reflejo.
# "Es como si..." queda afuera a propósito: al sacarlo deja subjuntivo colgado.
_APERTURAS_REPETIBLES = [
    ("sentis_que",  re.compile(r"^\s*sent[ií]s\s+que\s+(.+)$",   re.IGNORECASE | re.DOTALL)),
    ("siento_que",  re.compile(r"^\s*siento\s+que\s+(.+)$",      re.IGNORECASE | re.DOTALL)),
    ("es_como_que", re.compile(r"^\s*es\s+como\s+que\s+(.+)$",   re.IGNORECASE | re.DOTALL)),
    ("parece_que",  re.compile(r"^\s*parece\s+que\s+(.+)$",      re.IGNORECASE | re.DOTALL)),
]


def _familia_apertura(texto: str) -> Optional[str]:
    """Clave de familia si el texto abre con una fórmula repetible, o None."""
    for clave, rx in _APERTURAS_REPETIBLES:
        if rx.match(texto or ""):
            return clave
    return None


def _aplanar_apertura(texto: str) -> str:
    """Quita la fórmula de apertura y capitaliza el resto.
    'Sentís que todo te pesa.' → 'Todo te pesa.'"""
    for _clave, rx in _APERTURAS_REPETIBLES:
        m = rx.match(texto or "")
        if m:
            resto = m.group(1).lstrip()
            if resto:
                return resto[0].upper() + resto[1:]
    return texto


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
        print(f"⚠️ No se pudo cargar el historial: {e}")
        return {"messages": []}


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

        # Límite server-side de tamaño de la conversación
        conversation = body.conversation[-MAX_CONV_MESSAGES:]
        for m in conversation:
            if len(m.content) > MAX_MSG_CHARS:
                m.content = m.content[:MAX_MSG_CHARS]

        perfil = body.perfil

        if perfil is None:
            try:
                perfil = user_repo.get_profile(user_id)
            except Exception:
                perfil = None

        ultimo_mensaje = conversation[-1].content if conversation else ""
        crisis = detectar_crisis(ultimo_mensaje)
        crisis_score = crisis.get("score", 0.0)
        crisis_log_level = crisis.get("log_level", "none")

        if crisis["detected"]:
            # Verificación en dos pasos: las keywords dispararon crítico/alto;
            # un clasificador LLM rápido confirma si el riesgo es real y actual.
            # Fail-safe: ante error o duda, se mantiene la respuesta de emergencia.
            if confirmar_riesgo_real(ultimo_mensaje, crisis["category"] or ""):
                # Respuesta determinística, sin LLM principal.
                background_tasks.add_task(
                    feedback_repo.save_crisis_log,
                    user_id,
                    ultimo_mensaje,
                    crisis["category"],
                    crisis_log_level,
                )
                return {
                    "message":          crisis["message"],
                    "mood":             "sad",
                    "suggested_action": None,
                    "risk_level":       "high",
                    "nuevas_memorias":  None,
                }
            # El verificador descartó riesgo actual (hipérbole/tercero/pasado):
            # se degrada a señal media → el LLM responde con módulos de crisis.
            crisis_score = 0.45
            crisis_log_level = "medium"

        # ── Capa 2: clasificador semántico de contexto ──────────────
        # Corre en cada turno (salvo cuando arriba ya devolvimos la respuesta
        # hardcodeada). Lee el contexto que las keywords no ven y devuelve señales
        # que se mergean en el ruteo de módulos. Puede ESCALAR el riesgo hacia
        # M19/M20 (nunca bajarlo) — pero NO dispara la respuesta hardcodeada:
        # ese bypass sigue siendo exclusivo de keyword + crisis_verifier.
        # Fail-safe: si se cae, router_hints["ok"]=False y el ruteo usa solo keywords.
        router_hints = clasificar_contexto([m.model_dump() for m in conversation])
        if router_hints.get("ok"):
            score_router = score_riesgo_router(router_hints.get("senal_riesgo", "none"))
            if score_router > crisis_score:
                crisis_score = score_router
                # Riesgo que el léxico no había marcado: subimos el nivel de log.
                if crisis_log_level == "none":
                    crisis_log_level = "medium"

        # Señal media (desborde/implícitas/degradadas/router): va al LLM con el
        # módulo de crisis activado. Se loguea igual para trazabilidad del equipo.
        # category cae a "ROUTER_RISK" cuando la señal la aportó solo el clasificador.
        if crisis_score >= 0.35:
            background_tasks.add_task(
                feedback_repo.save_crisis_log,
                user_id,
                ultimo_mensaje,
                crisis.get("category") or "ROUTER_RISK",
                crisis_log_level,
            )

        memorias_sesion: List[Dict[str, Any]] = []
        if perfil and "_memorias_sesion" in perfil:
            raw = perfil.pop("_memorias_sesion", []) or []
            memorias_sesion = [
                m if isinstance(m, dict)
                else {"content": str(m), "priority": 3, "category": "otro"}
                for m in raw
            ]

        memorias_vigentes: List[Dict[str, Any]] = []
        ids_a_desactivar: List[str] = []
        patrones: List[dict] = []

        try:
            m_db, ids_old = get_recent_memories(
                user_id=user_id,
                days=MEMORY_WINDOW_DAYS_DEFAULT,
                max_items=12
            )
            seen = set()
            merged = []
            for m in (memorias_sesion or []) + m_db:
                key = (m.get("content") or "").strip()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(m)
            memorias_vigentes = merged[:15]
            ids_a_desactivar = ids_old
        except Exception as e:
            print(f"⚠️ No se pudieron cargar memorias: {e}")
            memorias_vigentes = memorias_sesion or []

        try:
            patrones = get_topic_patterns_cached(user_id=user_id)
        except Exception as e:
            print(f"⚠️ No se pudieron cargar patrones: {e}")

        # ── Memoria proactiva contextual ─────────────────────────────────
        # Se elige A LO SUMO UNA cosa para traer al prompt (evento con fecha,
        # tema abierto sin resolver, o recurso propio del usuario) según el
        # estado emocional que ya clasificó el router (Qwen). En un momento
        # triste no se pregunta por el partido del finde; sí se puede recordar
        # "correr te despejó la última vez". Solo fuera de contexto de riesgo.
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

                # Solo se consulta lo que la política puede llegar a usar
                # (ver elegir_memoria_contextual) para no sumar queries al turno.
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
                print(f"⚠️ No se pudo elegir memoria contextual: {e}")

        es_inicio_sesion = len(conversation) == 1
        num_interacciones = len(conversation)

        # Primera vez: primer mensaje de la sesión Y sin memorias previas de otras sesiones
        es_primera_vez = (num_interacciones == 1 and not memorias_vigentes)

        # Detectar reenganche: >5 días sin actividad
        dias_inactivo = 0
        if num_interacciones <= 4:
            # Solo consultamos al principio de la sesión para no repetir la llamada
            dias_inactivo = get_dias_inactivo(user_id)

        # ¿El turno anterior estuvo en territorio de crisis? (se mira el score
        # de los últimos 2 mensajes previos del usuario que vienen en el request)
        ultimo_modulo_critico = False
        previos_usuario = [m.content for m in conversation[:-1] if m.role == "user"][-2:]
        for msg_previo in previos_usuario:
            if detectar_crisis(msg_previo).get("score", 0.0) >= 0.35:
                ultimo_modulo_critico = True
                break

        # Respaldo stateless: si la sesión recién empieza (el historial del
        # request no alcanza), mirar crisis_logs — el usuario pudo haber
        # recargado la app justo después de una crisis.
        if not ultimo_modulo_critico and num_interacciones <= 4:
            ultimo_modulo_critico = feedback_repo.hay_crisis_reciente(user_id)

        # Check-in del día (1-4) — cacheado 5 min en memory_service
        checkin_hoy = None
        try:
            checkin_hoy = get_checkin_hoy_cached(user_id)
        except Exception as e:
            print(f"⚠️ No se pudo cargar el check-in: {e}")

        # Últimos 4 mensajes para las detecciones del router de módulos
        historial_reciente = [m.model_dump() for m in conversation[-4:]]

        # Racha de mensajes de Numa terminados en "?": el servidor la cuenta
        # (el modelo no sabe auditar su propio historial) y el prompt recibe
        # la señal ya calculada. Se recalcula en cada turno, así el bloqueo
        # se levanta solo apenas Numa responde sin pregunta.
        mensajes_numa = [m.content for m in conversation if m.role == "assistant"]
        preguntas_seguidas = 0
        for contenido in reversed(mensajes_numa):
            if contenido.rstrip().rstrip('"\'').endswith("?"):
                preguntas_seguidas += 1
            else:
                break

        system_prompt = construir_prompt(
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
            crisis_score=crisis_score,
            ultimo_modulo_critico=ultimo_modulo_critico,
            historial_reciente=historial_reciente,
            mood_actual=body.ultimo_mood,
            ultimo_mensaje=ultimo_mensaje,
            preguntas_seguidas=preguntas_seguidas,
            hoy=hoy,
            evento_proactivo=evento_proactivo,
            tema_abierto=tema_abierto,
            memoria_recurso=memoria_recurso,
            router_hints=router_hints,
        )

        result = llm.generate_response(
            conversation=[m.model_dump() for m in conversation],
            system_prompt=system_prompt,
        )

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
        if familia_actual:
            apertura_previa = None
            for m in reversed(conversation[:-1]):
                if m.role == "assistant":
                    apertura_previa = _familia_apertura(m.content)
                    break
            if apertura_previa == familia_actual:
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
            and _cierra_con_presencia(mensaje_actual)
        ):
            previo_cierre_presencia = False
            for m in reversed(conversation[:-1]):
                if m.role == "assistant":
                    previo_cierre_presencia = _cierra_con_presencia(m.content)
                    break
            if previo_cierre_presencia:
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

        # Validar/clampear metadata de cada memoria antes de persistir.
        # El dedup difuso descarta el mismo hecho reformulado (contra las
        # memorias ya conocidas y contra la otra memoria del mismo turno).
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
            # Respaldo server-side de los flags (como detectar_evento_con_fecha
            # respalda los eventos): el LLM sub-produce open/helped y sin ellos
            # el canal proactivo se queda sin material. Los detectores leen el
            # content ya redactado en tercera persona (vocabulario de M08).
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

        # Sin early-return: reportar el nivel real de señal detectada
        risk_level = "medium" if crisis_score >= 0.35 else "none"

        # Follow-up inteligente (req. 6): si el usuario habló de un evento ya ocurrido,
        # marcarlo followed_up para no volver a preguntar cómo le fue. Si dijo que
        # AÚN no pasó ("es el martes que viene"), se re-fecha y queda abierto.
        background_tasks.add_task(marcar_evento_followup, user_id, ultimo_mensaje, hoy)

        # Ciclo de temas abiertos: si el usuario contó el desenlace de un tema
        # abierto (sin fecha), se cierra para no volver a preguntarle.
        background_tasks.add_task(cerrar_temas_abiertos, user_id, ultimo_mensaje)

        # Cooldown de mención proactiva (req. 8): lo que sea que este turno trajo
        # al prompt (evento, tema abierto o recurso) registra cuándo se insertó,
        # para no insistir en cada mensaje con el mismo tema.
        # Además, lo MENCIONADO cierra su ciclo (regla de producto): un evento ya
        # ocurrido no se re-pregunta ("followup") y un tema abierto ya traído se
        # cierra ("cerrar_tema" — si sigue pendiente, la memoria nueva del turno
        # lo re-captura). Eventos futuros y recursos solo arrancan cooldown.
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
                result["message"],
                memorias_validadas,
                result.get("mood"),
            )
            if ids_a_desactivar:
                background_tasks.add_task(conversation_repo.deactivate_memories, ids_a_desactivar)
            if memorias_validadas:
                invalidate_patterns_cache(user_id)

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
        raise HTTPException(status_code=500, detail=str(e))
