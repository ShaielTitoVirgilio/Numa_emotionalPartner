
import random
import re
from typing import Optional, TypedDict

# ══════════════════════════════════════════════════════════════
# TIPOS
# ══════════════════════════════════════════════════════════════

class CrisisResult(TypedDict):
    detected: bool
    category: Optional[str]          # None si no hay crisis
    message: str                      # respuesta para mostrar al usuario
    resources: list[str]              # recursos de ayuda
    log_level: str                    # "none" | "low" | "medium" | "high" | "critical"
    score: float                      # 0.0-1.0 — señal continua para el routing de módulos


# ══════════════════════════════════════════════════════════════
# NORMALIZACIÓN
# El texto y las frases se comparan sin tildes (pero conservando la ñ),
# así "como me mato" matchea igual que "cómo me mato".
# ══════════════════════════════════════════════════════════════

_TABLA_TILDES = str.maketrans("áéíóúüÁÉÍÓÚÜ", "aeiouuAEIOUU")


def _normalizar(texto: str) -> str:
    return texto.lower().strip().translate(_TABLA_TILDES)


# ══════════════════════════════════════════════════════════════
# EXCLUSIONES — expresiones cotidianas que NO son crisis.
# Se "neutralizan" (se borran del texto) ANTES de evaluar las frases
# de riesgo, para eliminar los falsos positivos sistemáticos:
#   "el finde me corto el pelo"            → no es autolesión
#   "me corto con el cuchillo cocinando"   → no es autolesión
#   "me lastimo el tobillo jugando"        → no es autolesión
#   "sobredosis de vitaminas/cafeína"      → no es método suicida
#   "mi abuela tuvo una sobredosis"        → tercera persona
#   "me quiero morir de la vergüenza"      → hipérbole
#   "este mundo de hipócritas"             → figurativo
#   "me mato estudiando"                   → hipérbole de esfuerzo
# Escritas ya normalizadas (sin tildes, con ñ).
# ══════════════════════════════════════════════════════════════

_EXCLUSIONES = [re.compile(p) for p in [
    # Cortes cotidianos (pelo, uñas...) — lista cerrada de objetos benignos
    # para NO neutralizar "me corto las venas" / "los brazos".
    r"\bme cort(o|e|aba) (el|la|las|los) (pelo|cabello|flequillo|barba|uñas|puntas|jopo|rulos)\b",
    r"\bme cort(o|e|aba) con (el|la|un|una) \w+",
    # Lesiones accidentales con parte del cuerpo (excluida la muñeca)
    r"\bme golpe(o|e|aba|teo) (el|la|las|los) \w+",
    r"\bme lastim(o|e|aba) (el|la|los|las|un|una) (tobillo|pie|pies|rodilla|rodillas|mano|manos|dedo|dedos|codo|hombro|espalda|cuello|brazo|pierna|piernas)\b",
    r"\bme quem(o|e|aba) (con|el|la|las|los) \w+",
    # Hipérboles cotidianas de "morir"
    r"\b(me quiero morir|quiero morirme|quiero morir|me muero|me estoy muriendo)( de| del| de la| de el)? (risa|verguenza|hambre|frio|calor|sueño|amor|ganas|aburrimiento|ternura|ansiedad por verte|curiosidad)\w*",
    r"\bno doy mas de (la )?risa\b",
    # Sobredosis inocuas o de terceros
    r"\bsobredosis de (vitamina\w*|azucar|cafeina|cafe|mate|chocolate|trabajo|series|futbol|netflix)\b",
    r"\b(mi|tu|su) \w+( \w+)? (tuvo|tomo|toma|sufrio|sufre|tiene|tenia) (una )?sobredosis\b",
    # "este mundo de hipócritas" y similares — figurativo, no ideación
    r"\b(en )?(este|un) mundo de \w+",
    # Hipérbole de esfuerzo
    r"\bme mat(o|e) (estudiando|trabajando|entrenando|laburando|limpiando|cocinando|en el gimnasio|en el gym)\b",
]]


def _neutralizar_exclusiones(texto: str) -> str:
    for patron in _EXCLUSIONES:
        texto = patron.sub(" ", texto)
    return texto


# ══════════════════════════════════════════════════════════════
# FRASES DE DETECCIÓN
# Ordenadas de más a menos específicas. Se evalúan en orden:
# la primera categoría que matchea gana.
# Escritas ya normalizadas (sin tildes, con ñ).
# ══════════════════════════════════════════════════════════════

# ── Nivel CRÍTICO: métodos concretos ──────────────────────────

SUICIDE_METHOD_PHRASES = [
    # pastillas / medicamentos
    "que pastillas me matan", "cuantas pastillas", "pastillas para morir",
    "pastillas para matarme", "que medicamento mata", "sobredosis de",
    "cuantas me tomo para", "con que me mato", "como me mato",
    "como suicidarme", "como quitarme la vida", "metodo para suicidarme",
    "manera de suicidarme", "forma de matarme", "como terminar con mi vida",
    "que puedo tomar para morir", "que me puedo tomar para morir",
    "como colgarme", "como ahorcarme", "como cortarme las venas",
    "como me corto las venas", "me corto las venas", "cortarme las venas",
    "donde cortarme", "como tirarme", "de que altura me tiro",
    "con que me puedo cortar", "como hacerlo sin que duela",
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
    "preferiria estar muerto", "preferiria estar muerta", "preferiria no existir",
    "estaria mejor muerto", "estaria mejor muerta", "estarian mejor sin mi",
    "todos estarian mejor sin mi", "seria mejor si no existiera",
    "mejor si no hubiera nacido", "desearia no haber nacido",
    "ya no quiero seguir", "ya no puedo seguir",
    "no tiene sentido seguir viviendo", "para que seguir viviendo",
    "no le encuentro razon para seguir", "no encuentro razon para seguir",
    "no tengo razon para seguir", "no hay razon para seguir",
    "no tengo razones para seguir",
    # Conjugaciones en pasado: si además hay marcador de tiempo pasado
    # ("cuando era...", "hace años...") se degradan a señal media.
    "pensaba en matarme", "pensaba en suicidarme",
    "queria matarme", "queria morirme", "me queria matar",
    "me quise matar", "intente matarme", "intente suicidarme",
]

# ── Nivel ALTO: autolesión ────────────────────────────────────

SELF_HARM_PHRASES = [
    "me corto", "me lastimo", "me hago daño", "me autolesiono",
    "empece a cortarme", "volvi a cortarme", "quiero cortarme",
    "quiero hacerme daño", "quiero lastimarme", "me quemo",
    "me golpeo", "me arranco", "me pellizco fuerte para sentir",
    "me hago daño para sentir algo",
]

# ── Nivel MEDIO-ALTO: desborde emocional severo ───────────────
# No ideación directa pero señal de que la persona está al límite

CRISIS_OVERFLOW_PHRASES = [
    "no aguanto mas", "no puedo mas con esto", "ya no puedo mas",
    "estoy al limite", "llegue al limite", "toque fondo",
    "no veo salida", "no hay salida", "no encuentro salida",
    "siento que me voy a quebrar", "me estoy quebrando",
    "me estoy destruyendo", "me quiero desaparecer",
    "quiero desaparecer", "quisiera no despertar",
    "ojala no despierte", "ojala me durmiera y no despertara",
]

# ── Nivel MEDIO: desesperanza crónica / anhedonia vital ───────
# Expresiones de hartazgo de vivir o vacío existencial sostenido.
# No son ideación activa, pero indican sufrimiento crónico profundo
# y requieren que el LLM responda con módulo de crisis implícita (M19).

HOPELESSNESS_PHRASES = [
    # Anhedonia vital directa
    "aburrida de vivir", "aburrido de vivir",
    "cansada de vivir", "cansado de vivir",
    "harta de vivir", "harto de vivir",
    "tanta de vivir", "agotada de vivir", "agotado de vivir",
    # "no quiero seguir viviendo así" (distinción de la ideación directa "no quiero seguir viviendo")
    "no quiero seguir viviendo asi", "no quiero seguir viviendo así",
    "no quiero seguir existiendo asi", "no quiero seguir existiendo así",
    # Sin sentido / vacío vital
    "no le encuentro sentido a la vida", "no le veo sentido a la vida",
    "no tiene sentido vivir", "para que vivir", "para qué vivir",
    "vivir no vale la pena", "la vida no vale la pena",
    "no vale la pena seguir", "no vale nada la vida",
    # Sufrimiento sostenido largo plazo (con marcadores de duración)
    "años sintiendome asi", "años sintiéndome así",
    "toda la vida sintiendome", "toda la vida así",
    "siempre me senti asi", "siempre me sentí así",
    "nunca voy a estar bien", "jamas voy a estar bien",
    "nunca cambia nada", "nunca va a cambiar",
]

# ── Nivel MEDIO: señales implícitas de riesgo ─────────────────
# Frases que en una conversación pesada indican riesgo sin usar
# las palabras directas. No tienen respuesta hardcodeada: activan
# el módulo de crisis implícita en el prompt (el LLM responde).

IMPLICIT_RISK_PHRASES = [
    "ya lo decidi",
    "no tiene caso seguir", "no tiene caso ya",
    "ya me voy de este mundo",
    "este es mi ultimo mensaje",
    "no quiero hablar mas, solo voy a hacerlo", "solo voy a hacerlo",
    "nadie me va a extrañar", "nadie me extrañaria",
    "ya no importa nada", "nada va a cambiar nunca",
    "adios a todos",
    "ya esta todo dicho",
    "es la ultima vez que hablo",
    "pensando en desaparecer",
    "no se si quiero estar", "no se si quiero seguir",
]

# Score por categoría — alimenta el routing de módulos del prompt:
#   >= 0.60 → M20 (crisis explícita) | 0.35-0.60 → M19 (crisis implícita)
SCORE_POR_CATEGORIA = {
    "SUICIDE_METHOD":    0.95,
    "SUICIDAL_IDEATION": 0.85,
    "SELF_HARM":         0.65,
    "CRISIS_OVERFLOW":   0.45,
    "HOPELESSNESS":      0.42,
    "IMPLICIT_RISK":     0.40,
}


# ══════════════════════════════════════════════════════════════
# MATCHING — límites de palabra + negación + tiempo pasado
# ══════════════════════════════════════════════════════════════

def _compilar_frases(frases: list[str]) -> list[re.Pattern]:
    # Límites de palabra: "me corto" NO matchea dentro de "me cortocircuito".
    return [
        re.compile(r"(?<![\wñ])" + re.escape(f) + r"(?![\wñ])")
        for f in frases
    ]


_PATRONES = {
    "SUICIDE_METHOD":    _compilar_frases(SUICIDE_METHOD_PHRASES),
    "SUICIDAL_IDEATION": _compilar_frases(SUICIDAL_IDEATION_PHRASES),
    "SELF_HARM":         _compilar_frases(SELF_HARM_PHRASES),
    "CRISIS_OVERFLOW":   _compilar_frases(CRISIS_OVERFLOW_PHRASES),
    "HOPELESSNESS":      _compilar_frases(HOPELESSNESS_PHRASES),
    "IMPLICIT_RISK":     _compilar_frases(IMPLICIT_RISK_PHRASES),
}

# Negación inmediatamente antes del match: "no me quiero matar",
# "nunca me cortaria"... (no afecta frases que ya empiezan con "no")
_NEGACION_RE = re.compile(r"\b(no|nunca|jamas|tampoco|ni)\s+(es que\s+)?$")

# Marcadores de tiempo pasado: una mención de crisis pasada no debe disparar
# la respuesta hardcodeada de emergencia. Se degrada a señal media → el LLM
# responde con el módulo de crisis activado (y se loguea igual).
_MARCADORES_PASADO = [
    "hace años", "hace un año", "hace meses", "hace un tiempo", "hace tiempo",
    "cuando era", "cuando tenia", "en aquella epoca", "en aquel momento",
    "en su momento", "el año pasado", "de chico", "de chica", "de adolescente",
    "en mi adolescencia", "llegue a pensar", "llegaba a pensar",
    "en el pasado", "antes pensaba", "antes queria", "una epoca", "ya no pienso",
    "ya supere", "lo supere",
]


def _hay_match(texto: str, patrones: list[re.Pattern]) -> bool:
    """True si alguna frase matchea sin estar negada justo antes."""
    for patron in patrones:
        for m in patron.finditer(texto):
            contexto_previo = texto[max(0, m.start() - 20):m.start()]
            if _NEGACION_RE.search(contexto_previo):
                continue
            return True
    return False


def _es_contexto_pasado(texto: str) -> bool:
    return any(marca in texto for marca in _MARCADORES_PASADO)


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

    Pipeline:
      0. Normalizar (minúsculas, sin tildes) y neutralizar exclusiones
         (hipérboles, cortes de pelo, tercera persona, figurativo).
      1. SUICIDE_METHOD    → crítico  (detected=True, respuesta hardcodeada)
      2. SUICIDAL_IDEATION → crítico  (detected=True, respuesta hardcodeada)
      3. SELF_HARM         → alto     (detected=True, respuesta hardcodeada)
      4. CRISIS_OVERFLOW   → medio    (detected=False — va al LLM con módulo de crisis implícita)
      5. IMPLICIT_RISK     → medio    (detected=False — ídem)

    Si un match crítico/alto viene en contexto de tiempo pasado ("hace años
    me quería matar") se degrada a señal media: lo maneja el LLM con el
    módulo de crisis activado, sin la respuesta de emergencia hardcodeada.

    El campo `score` siempre se devuelve y alimenta el routing de módulos
    del prompt, incluso cuando no hay early-return.
    """
    texto = _neutralizar_exclusiones(_normalizar(mensaje))

    # ── 1. Método suicida ────────────────────────────────────
    if _hay_match(texto, _PATRONES["SUICIDE_METHOD"]):
        if _es_contexto_pasado(texto):
            return _resultado_medio("SUICIDE_METHOD")
        resp = random.choice(RESPONSES_METHOD)
        return CrisisResult(
            detected=True,
            category="SUICIDE_METHOD",
            message=_formatear(resp, RESOURCES["generico"]),
            resources=RESOURCES["generico"],
            log_level="critical",
            score=SCORE_POR_CATEGORIA["SUICIDE_METHOD"],
        )

    # ── 2. Ideación suicida ──────────────────────────────────
    if _hay_match(texto, _PATRONES["SUICIDAL_IDEATION"]):
        if _es_contexto_pasado(texto):
            return _resultado_medio("SUICIDAL_IDEATION")
        resp = random.choice(RESPONSES_IDEATION)
        return CrisisResult(
            detected=True,
            category="SUICIDAL_IDEATION",
            message=_formatear(resp, RESOURCES["generico"]),
            resources=RESOURCES["generico"],
            log_level="critical",
            score=SCORE_POR_CATEGORIA["SUICIDAL_IDEATION"],
        )

    # ── 3. Autolesión ────────────────────────────────────────
    if _hay_match(texto, _PATRONES["SELF_HARM"]):
        if _es_contexto_pasado(texto):
            return _resultado_medio("SELF_HARM")
        resp = random.choice(RESPONSES_SELF_HARM)
        return CrisisResult(
            detected=True,
            category="SELF_HARM",
            message=_formatear(resp, RESOURCES["generico"]),
            resources=RESOURCES["generico"],
            log_level="high",
            score=SCORE_POR_CATEGORIA["SELF_HARM"],
        )

    # ── 4. Desborde emocional severo → al LLM con M19 ────────
    if _hay_match(texto, _PATRONES["CRISIS_OVERFLOW"]):
        return CrisisResult(
            detected=False,
            category="CRISIS_OVERFLOW",
            message="",
            resources=[],
            log_level="medium",
            score=SCORE_POR_CATEGORIA["CRISIS_OVERFLOW"],
        )

    # ── 5. Señales implícitas → al LLM con M19 ───────────────
    if _hay_match(texto, _PATRONES["IMPLICIT_RISK"]):
        return CrisisResult(
            detected=False,
            category="IMPLICIT_RISK",
            message="",
            resources=[],
            log_level="medium",
            score=SCORE_POR_CATEGORIA["IMPLICIT_RISK"],
        )

    # ── 6. Desesperanza crónica / anhedonia vital → LLM con M19 ──
    # "aburrida de vivir", "cansada de vivir", "nunca voy a estar bien"...
    # Sufrimiento sostenido sin ideación activa: no bypassea el LLM,
    # pero sí activa los módulos de crisis implícita para respuesta cálida.
    if _hay_match(texto, _PATRONES["HOPELESSNESS"]):
        return CrisisResult(
            detected=False,
            category="HOPELESSNESS",
            message="",
            resources=[],
            log_level="medium",
            score=SCORE_POR_CATEGORIA["HOPELESSNESS"],
        )

    # ── Sin crisis ───────────────────────────────────────────
    return CrisisResult(
        detected=False,
        category=None,
        message="",
        resources=[],
        log_level="none",
        score=0.0,
    )


def _resultado_medio(category: str) -> CrisisResult:
    """Señal degradada: el LLM responde con módulo de crisis (M19/M20),
    sin respuesta hardcodeada. Se usa para menciones en tiempo pasado."""
    return CrisisResult(
        detected=False,
        category=category,
        message="",
        resources=[],
        log_level="medium",
        score=0.45,
    )


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

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
        print(f"🚨 Crisis log: [{log_level}] {category}")
    except Exception as e:
        # Nunca romper el flujo por un error de logging
        print(f"⚠️ No se pudo loguear crisis: {e}")
