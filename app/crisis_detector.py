
import random
from typing import Optional, TypedDict

# ══════════════════════════════════════════════════════════════
# TIPOS
# ══════════════════════════════════════════════════════════════

class CrisisResult(TypedDict):
    detected: bool
    category: Optional[str]          # None si no hay crisis
    message: str                      # respuesta para mostrar al usuario
    resources: list[str]              # recursos de ayuda
    log_level: str                    # "none" | "low" | "high" | "critical"


# ══════════════════════════════════════════════════════════════
# FRASES DE DETECCIÓN
# Ordenadas de más a menos específicas.
# Se evalúan en orden: la primera que matchea gana.
# ══════════════════════════════════════════════════════════════

# ── Nivel CRÍTICO: métodos concretos ──────────────────────────
# Preguntas sobre cómo hacerlo — requieren respuesta inmediata + recurso

SUICIDE_METHOD_PHRASES = [
    # pastillas / medicamentos
    "qué pastillas me matan", "cuántas pastillas", "pastillas para morir",
    "pastillas para matarme", "qué medicamento mata", "sobredosis de",
    "cuántas me tomo para", "con qué me mato", "cómo me mato",
    "cómo suicidarme", "cómo quitarme la vida", "método para suicidarme",
    "manera de suicidarme", "forma de matarme", "cómo terminar con mi vida",
    "qué puedo tomar para morir", "qué me puedo tomar para morir",
    "cómo colgarme", "cómo ahorcarme", "cómo cortarme las venas",
    "dónde cortarme", "cómo tirarme", "de qué altura me tiro",
    "con qué me puedo cortar", "cómo hacerlo sin que duela",
]

# ── Nivel CRÍTICO: ideación suicida directa ───────────────────

SUICIDAL_IDEATION_PHRASES = [
    "me quiero matar", "me quiero suicidar", "quiero matarme",
    "quiero suicidarme", "quiero morirme", "quiero morir",
    "me voy a matar", "me voy a suicidar", "voy a matarme",
    "voy a suicidarme", "pienso en matarme", "pienso en suicidarme",
    "quiero quitarme la vida", "quiero terminar con mi vida",
    "quiero dejar de existir", "quiero desaparecer para siempre",
    "no quiero seguir viviendo", "no quiero seguir en este mundo",
    "no quiero estar en este mundo", "no quiero seguir existiendo",
    "preferiría estar muerto", "preferiría no existir",
    "estaría mejor muerto", "estarían mejor sin mí",
    "todos estarían mejor sin mí", "sería mejor si no existiera",
    "mejor si no hubiera nacido", "desearía no haber nacido",
    "ya no quiero seguir", "ya no puedo seguir",
    "no tiene sentido seguir viviendo", "para qué seguir viviendo",
]

# ── Nivel ALTO: autolesión ────────────────────────────────────

SELF_HARM_PHRASES = [
    "me corto", "me lastimo", "me hago daño", "me autolesiono",
    "empecé a cortarme", "volví a cortarme", "quiero cortarme",
    "quiero hacerme daño", "quiero lastimarme", "me quemo",
    "me golpeo", "me arranco", "me pellizco fuerte para sentir",
    "me hago daño para sentir algo",
]

# ── Nivel MEDIO-ALTO: desborde emocional severo ───────────────
# No ideación directa pero señal de que la persona está al límite

CRISIS_OVERFLOW_PHRASES = [
    "no aguanto más", "no puedo más con esto", "ya no puedo más",
    "estoy al límite", "llegué al límite", "toqué fondo",
    "no veo salida", "no hay salida", "no encuentro salida",
    "siento que me voy a quebrar", "me estoy quebrando",
    "me estoy destruyendo", "me quiero desaparecer",
    "quiero desaparecer", "quisiera no despertar",
    "ojalá no despierte", "ojalá me durmiera y no despertara",
]


# ══════════════════════════════════════════════════════════════
# RESPUESTAS HARDCODEADAS
# Voz de Numa: amigo cercano, directo, sin drama, sin disclaimer.
# Varias opciones por categoría → se elige una al azar para no
# sonar robotizado en mensajes repetidos.
# ══════════════════════════════════════════════════════════════

# Recursos por país (Argentina primero, luego genérico)
RESOURCES = {
    "argentina": [
        "📞 Centro de Asistencia al Suicida: 135 (gratuito, 24h)",
        "💬 Chat: www.asistenciaalsuicida.org.ar",
    ],
    "uruguay": [
        "📞 Línea de Crisis: 0800 0767 (gratuito, 24h)",
    ],
    "generico": [
        "📞 Si estás en Argentina: 135 (gratuito, 24h)",
        "📞 Si estás en Uruguay: 0800 0767",
        "📞 Si estás en España: 024",
        "📞 Si estás en México: 800 290 0024",
    ],
}

RESPONSES_METHOD = [
    {
        "message": (
            "Eso no te lo puedo responder. No porque no me importe, sino exactamente porque sí me importa.\n\n"
            "Necesito preguntarte algo directo: ¿estás pensando en hacerte daño ahora mismo?"
        ),
        "followup": "Quedate acá. Hay alguien que puede escucharte ahora:",
    },
    {
        "message": (
            "No. Esa información no te la voy a dar.\n\n"
            "Pero sí quiero saber qué está pasando. ¿Qué está pasando realmente?"
        ),
        "followup": "Si estás en un momento muy difícil, hay gente disponible ahora mismo:",
    },
]

RESPONSES_IDEATION = [
    {
        "message": (
            "Escucho que estás en un lugar muy oscuro ahora mismo. "
            "No voy a minimizar eso ni decirte que 'va a pasar'.\n\n"
            "¿Podés contarme qué está pasando? ¿Qué te trajo a este punto?"
        ),
        "followup": "Y mientras hablamos — si en algún momento sentís que necesitás hablar con alguien ahora, esto puede ayudarte:",
    },
    {
        "message": (
            "Lo que me estás diciendo es importante. Muy importante.\n\n"
            "No estoy preparado para acompañarte en esto solo — hay personas "
            "entrenadas para estar con vos en este momento. "
            "¿Me dejás darte un contacto?"
        ),
        "followup": "Son gratuitos y disponibles ahora:",
    },
    {
        "message": (
            "Gracias por decírmelo. En serio. "
            "No sé qué está pasando exactamente, pero sé que algo muy pesado te está aplastando.\n\n"
            "¿Hay alguien cerca tuyo ahora mismo?"
        ),
        "followup": "También hay personas disponibles las 24 horas para acompañarte:",
    },
]

RESPONSES_SELF_HARM = [
    {
        "message": (
            "Eso que me contás me importa. No te voy a juzgar por eso.\n\n"
            "¿Estás lastimado/a ahora mismo? ¿Necesitás atención médica en este momento?"
        ),
        "followup": "Si querés hablar con alguien que entiende esto, acá hay ayuda:",
    },
    {
        "message": (
            "Hacerse daño a veces es la única forma que encontramos de soportar algo que duele demasiado. "
            "No te juzgo.\n\n"
            "¿Me podés contar qué está pasando?"
        ),
        "followup": "Y si en algún momento sentís que necesitás apoyo extra, hay líneas disponibles:",
    },
]

RESPONSES_OVERFLOW = [
    {
        "message": (
            "Para. Respirá.\n\n"
            "Lo que estás sintiendo es real y es mucho. No tenés que manejarlo solo/a."
        ),
        "followup": None,  # No recursos todavía — no es ideación directa
    },
    {
        "message": (
            "Estás acá y me estás hablando. Eso importa.\n\n"
            "¿Qué fue lo que pasó hoy? Contame."
        ),
        "followup": None,
    },
]


# ══════════════════════════════════════════════════════════════
# DETECTOR PRINCIPAL
# ══════════════════════════════════════════════════════════════

def detectar_crisis(mensaje: str) -> CrisisResult:
    """
    Analiza el último mensaje del usuario.
    Devuelve un CrisisResult con detected=True si hay señal de crisis.

    Orden de evaluación (de más a menos crítico):
      1. SUICIDE_METHOD    → crítico
      2. SUICIDAL_IDEATION → crítico
      3. SELF_HARM         → alto
      4. CRISIS_OVERFLOW   → medio-alto
    """
    texto = mensaje.lower().strip()

    # ── 1. Método suicida ────────────────────────────────────
    if _contiene(texto, SUICIDE_METHOD_PHRASES):
        resp = random.choice(RESPONSES_METHOD)
        return CrisisResult(
            detected=True,
            category="SUICIDE_METHOD",
            message=_formatear(resp, RESOURCES["generico"]),
            resources=RESOURCES["generico"],
            log_level="critical",
        )

    # ── 2. Ideación suicida ──────────────────────────────────
    if _contiene(texto, SUICIDAL_IDEATION_PHRASES):
        resp = random.choice(RESPONSES_IDEATION)
        return CrisisResult(
            detected=True,
            category="SUICIDAL_IDEATION",
            message=_formatear(resp, RESOURCES["generico"]),
            resources=RESOURCES["generico"],
            log_level="critical",
        )

    # ── 3. Autolesión ────────────────────────────────────────
    if _contiene(texto, SELF_HARM_PHRASES):
        resp = random.choice(RESPONSES_SELF_HARM)
        return CrisisResult(
            detected=True,
            category="SELF_HARM",
            message=_formatear(resp, RESOURCES["generico"]),
            resources=RESOURCES["generico"],
            log_level="high",
        )

    # ── 4. Desborde emocional severo ─────────────────────────
    if _contiene(texto, CRISIS_OVERFLOW_PHRASES):
        resp = random.choice(RESPONSES_OVERFLOW)
        return CrisisResult(
            detected=True,
            category="CRISIS_OVERFLOW",
            message=resp["message"],
            resources=[],
            log_level="low",
        )

    # ── Sin crisis ───────────────────────────────────────────
    return CrisisResult(
        detected=False,
        category=None,
        message="",
        resources=[],
        log_level="none",
    )


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _contiene(texto: str, frases: list[str]) -> bool:
    """Retorna True si el texto contiene alguna de las frases."""
    return any(frase in texto for frase in frases)


def _formatear(resp: dict, recursos: list[str]) -> str:
    """
    Arma el mensaje final concatenando el cuerpo principal
    y los recursos si el followup lo indica.
    """
    mensaje = resp["message"]

    if resp.get("followup") and recursos:
        lineas_recursos = "\n".join(recursos)
        mensaje += f"\n\n{resp['followup']}\n{lineas_recursos}"

    return mensaje


# ══════════════════════════════════════════════════════════════
# LOGGING EN BASE DE DATOS (background task)
# ══════════════════════════════════════════════════════════════

def log_crisis_event(
    supabase,
    user_id: Optional[str],
    mensaje_usuario: str,
    category: str,
    log_level: str,
):
    """
    Guarda el evento de crisis en la tabla crisis_logs.
    Llamar desde un BackgroundTask para no bloquear la respuesta.

    La tabla se crea con el SQL de crisis_logs_migration.sql
    """
    try:
        supabase.table("crisis_logs").insert({
            "user_id":         user_id,
            "mensaje_usuario": mensaje_usuario[:500],  # limitar longitud
            "categoria":       category,
            "log_level":       log_level,
        }).execute()
        print(f"🚨 Crisis log: [{log_level}] {category} — user:{user_id}")
    except Exception as e:
        # Nunca romper el flujo por un error de logging
        print(f"⚠️ No se pudo loguear crisis: {e}")