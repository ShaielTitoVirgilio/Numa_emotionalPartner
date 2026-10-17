# app/voz_tono.py
"""
Cómo tiene que SONAR cada oración de Numa en el modo llamada.

El context_router (que ya corre en paralelo al LLM principal en cada turno)
devuelve además un `tono_voz`: cómo debería sonar Numa según cómo viene la
persona. Acá ese tono se traduce, oración por oración, a lo que entiende
Cartesia (sonic-3.6):

  - emotion   → generation_config.emotion (vocabulario cerrado de Cartesia)
  - speed     → generation_config.speed (0.6 a 1.5)
  - [laughter] → risa real dentro del transcript (no "jajaja" leído)
  - <break/>  → pausa al principio de la oración, solo en mensajes largos

El backend arma el pedido y la app lo manda tal cual a Cartesia: así la
lógica de tonos vive en un solo lugar y se puede ajustar sin publicar la app.

POR QUÉ NO SE ESPERA AL ROUTER: en una llamada cada milisegundo antes de la
primera oración es silencio. El router tarda ~1.7s de mediana y a veces llega
después de la primera oración; mientras tanto se usa un tono provisorio
(`tono_provisorio`) a partir de señales que ya están: el puntaje de crisis por
keywords y el mood del turno anterior. Apenas el router contesta, las
oraciones que faltan salen con su tono.

Seguridad: con cualquier señal de riesgo el tono es "sensible", diga lo que
diga el router, y en "sensible" no hay risa (ni siquiera un "jaja" que haya
escrito el LLM).
"""
import re
from typing import Any, Dict, Optional

TONO_POR_DEFECTO = "tranqui"

# Velocidades pedidas por Shaiel: sensible 0.9 (no 0.85), tranqui 1.0.
# Cartesia toma speed como guía: cambios chicos casi no se notan, por eso
# eufórico va claramente arriba.
TONOS: Dict[str, Dict[str, Any]] = {
    "tranqui":  {"emotion": "calm",        "speed": 1.0},
    "sensible": {"emotion": "sympathetic", "speed": 0.9},
    "curioso":  {"emotion": "curious",     "speed": 1.0},
    "alegre":   {"emotion": "happy",       "speed": 1.05},
    "risa":     {"emotion": "happy",       "speed": 1.05},
    "euforico": {"emotion": "excited",     "speed": 1.15},
}

TONOS_VALIDOS = set(TONOS)

# Tonos donde un "jaja" del LLM se convierte en risa real. En "sensible" se
# saca: reírse cuando la persona está mal es justo lo que no se quiere.
_TONOS_CON_RISA = {"tranqui", "curioso", "alegre", "risa", "euforico"}

# Estados del mood anterior / router que piden voz sensible.
_ESTADOS_SENSIBLES = {"triste_vacio", "ansioso", "abrumado", "duelo", "enojado"}

# Pausas al principio de la oración en mensajes largos. Más larga en
# "sensible": ahí el silencio también acompaña.
_PAUSA_MS = 300
_PAUSA_SENSIBLE_MS = 450
# Una oración anterior de este largo ya cuenta como "mensaje largo".
_LARGO_ORACION_LARGA = 110

_RE_JAJA = re.compile(r"\b(?:j[aá]){2,}j?\b|\b(?:j[eé]){2,}j?\b", re.IGNORECASE)
# Lo que pueda parecer una etiqueta de Cartesia en el texto del LLM se saca:
# el único que pone etiquetas en el transcript es este módulo.
_RE_ETIQUETAS = re.compile(r"<[^>]*>|\[[^\]]*\]")
# Emojis: en el chat escrito suman, pero a Cartesia le llegan como texto y o
# los saltea o los lee raro. En voz no van.
_RE_EMOJIS = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF"
    "\U00002B00-\U00002BFF\uFE0F\u200D]+"
)


# Señales instantáneas en el último mensaje del usuario. Son a propósito
# pocas y claras: solo deciden el tono de las oraciones que salen ANTES de
# que conteste el router (que lee el contexto entero y manda después). Lo
# sensible se mira primero: un "jaja, igual nadie me quiere" no es un chiste.
_RE_USUARIO_SENSIBLE = re.compile(
    r"\b(triste|tristeza|sol[oa]\b|angusti|ansios|ansiedad|nervios|llor|deprim|"
    r"miedo|no (doy|puedo) m[aá]s|nadie me|me siento (mal|horrible|vac[ií])|"
    r"extra[nñ]o a|se muri[oó]|falleci|me dej[oó]|estoy mal|re mal|bajón|bajon)",
    re.IGNORECASE,
)
_RE_USUARIO_RISA = re.compile(r"\b(?:j[aeiá]){2,}|\bjsjs|me (muero|mor[ií]) de (la )?risa|me tent[eé]", re.IGNORECASE)
_RE_USUARIO_EUFORIA = re.compile(
    r"\b(aprob[eé]|me recib[ií]|me tomaron|me eligieron|lo logr[eé]|lo conseg|consegu[ií]|"
    r"gan[eé]|ganamos|me dieron el|qued[eé] en|me aceptaron)\b",
    re.IGNORECASE,
)

# Cómo se hereda el tono del turno anterior: la charla cambia de clima
# despacio, así que es el mejor dato que hay antes del router. Pero una risa
# o un festejo no se arrastran al turno siguiente; quedan en alegre.
_HERENCIA = {"risa": "alegre", "euforico": "alegre"}


def tono_provisorio(
    crisis_score: float,
    estado_local: Optional[str],
    ultimo_mensaje: str = "",
    tono_previo: Optional[str] = None,
) -> str:
    """Tono para las oraciones que salen antes de que el router conteste.

    Orden: riesgo → señales claras del último mensaje → tono del turno
    anterior → mood anterior → tranqui.
    """
    if crisis_score >= 0.35:
        return "sensible"
    msg = ultimo_mensaje or ""
    if _RE_USUARIO_SENSIBLE.search(msg):
        return "sensible"
    if _RE_USUARIO_EUFORIA.search(msg) and "!" in msg:
        return "euforico"
    if _RE_USUARIO_RISA.search(msg):
        return "risa"
    if tono_previo in TONOS_VALIDOS:
        return _HERENCIA.get(tono_previo, tono_previo)
    if estado_local in _ESTADOS_SENSIBLES:
        return "sensible"
    if estado_local == "buenas_noticias":
        return "alegre"
    return TONO_POR_DEFECTO


def tono_desde_router(hints: Dict[str, Any], crisis_score: float) -> Optional[str]:
    """Tono a partir del resultado del router. None si el router falló (ahí
    se sigue con el provisorio)."""
    if not hints or not hints.get("ok"):
        return None
    if crisis_score >= 0.35 or hints.get("senal_riesgo", "none") != "none":
        return "sensible"
    tono = hints.get("tono_voz")
    if tono not in TONOS_VALIDOS:
        # Router viejo o salida rara: se deduce del estado emocional.
        estado = hints.get("estado_emocional")
        if estado in _ESTADOS_SENSIBLES:
            return "sensible"
        if estado == "buenas_noticias":
            return "alegre"
        return TONO_POR_DEFECTO
    # Risa y euforia nunca sobre un fondo pesado, aunque el router las pida.
    if tono in ("risa", "euforico") and hints.get("estado_emocional") in _ESTADOS_SENSIBLES:
        return "sensible"
    return tono


def rearmar(oraciones: list, tono: str) -> list:
    """Vuelve a armar las oraciones ya emitidas de un turno con otro tono
    (cuando el router contesta después de que salieron). Se arman todas en
    orden, con un armador nuevo, para que la risa y las pausas queden igual
    que si el tono hubiera estado desde el principio; la app reemplaza solo
    las que todavía no le pidió a Cartesia."""
    armador = ArmadorVoz(tono)
    armador.fuente = "router"
    return [armador.armar(o) for o in oraciones]


class ArmadorVoz:
    """Arma el pedido a Cartesia de cada oración de UN turno.

    Lleva estado del turno: cuántas oraciones salieron (para las pausas) y si
    Numa ya se rió (una risa por turno alcanza; dos suenan forzadas).
    """

    def __init__(self, tono_inicial: str):
        self.tono = tono_inicial if tono_inicial in TONOS_VALIDOS else TONO_POR_DEFECTO
        self.fuente = "provisorio"
        self._indice = 0
        self._largo_anterior = 0
        self._ya_se_rio = False
        self.tonos_usados: list = []

    def usar_tono_router(self, tono: Optional[str]) -> None:
        if tono and tono in TONOS_VALIDOS:
            self.tono = tono
            self.fuente = "router"

    def armar(self, oracion: str) -> Dict[str, Any]:
        tono = self.tono
        params = TONOS[tono]
        emotion = params["emotion"]
        texto = _RE_EMOJIS.sub("", _RE_ETIQUETAS.sub("", oracion)).strip()

        # Risa: un "jaja" escrito se convierte en risa de verdad (Cartesia lo
        # lee literal si no), y en tono "risa" Numa arranca riéndose aunque el
        # LLM no lo haya escrito.
        hubo_jaja = bool(_RE_JAJA.search(texto))
        if tono in _TONOS_CON_RISA and not self._ya_se_rio and hubo_jaja:
            texto = _RE_JAJA.sub("[laughter]", texto, count=1)
            texto = _RE_JAJA.sub("", texto)
            self._ya_se_rio = True
            # Una risa con voz calma o curiosa suena rara: esa oración va alegre.
            if emotion in ("calm", "curious"):
                emotion = "happy"
        else:
            texto = _RE_JAJA.sub("", texto)
        if tono == "risa" and not self._ya_se_rio:
            texto = "[laughter] " + texto
            self._ya_se_rio = True
        texto = re.sub(r"\s*,(\s*,)+", ",", texto)
        texto = re.sub(r"\s{2,}", " ", texto).strip(" ,")
        texto = re.sub(r"^\[laughter\]\s*[,.]\s*", "[laughter] ", texto)
        if not _RE_ETIQUETAS.sub("", texto).strip(" ,.!?¡¿"):
            # La oración era solo un "jaja" (en tono sensible, o una segunda
            # risa del turno). Cartesia no acepta un texto vacío, y leer
            # "jaja" letra por letra suena peor que una risa corta.
            texto = "[laughter]"

        # Las preguntas en tono tranqui suenan mejor con curiosidad que con
        # calma plana. En los otros tonos se respeta el tono del turno.
        if tono == "tranqui" and texto.endswith("?"):
            emotion = "curious"

        # Pausas solo en mensajes largos: desde la tercera oración, o desde la
        # segunda si la primera ya fue larga. En uno corto una pausa se
        # escucha como un corte.
        largo = self._indice >= 2 or (self._indice == 1 and self._largo_anterior >= _LARGO_ORACION_LARGA)
        if largo:
            ms = _PAUSA_SENSIBLE_MS if tono == "sensible" else _PAUSA_MS
            texto = f'<break time="{ms}ms"/>' + texto

        indice = self._indice
        self._indice += 1
        self._largo_anterior = len(oracion)
        self.tonos_usados.append(tono)
        return {
            # Posición de la oración en el turno: con ella la app sabe cuál
            # reemplazar cuando llega el evento `voz` (tono tardío).
            "indice": indice,
            "transcript": texto,
            "emotion": emotion,
            "speed": params["speed"],
            "tono": tono,
        }
