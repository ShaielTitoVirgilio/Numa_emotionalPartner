# app/text_filters.py
"""
Filtros determinísticos que se le aplican al mensaje de Numa DESPUÉS de que
el LLM respondió (red de seguridad para cuando el modelo desobedece alguna
regla del prompt). Vivían inline en chat_router.py; se movieron acá tal cual
—mismo código, ninguna función tocada— para poder reusarlos también desde
app/streaming_buffer.py sin import circular (streaming_buffer los necesita
para aplicarlos oración por oración a medida que llega el stream del LLM).

chat_router.py sigue siendo el único lugar que DECIDE cuándo llamarlos
(los guards de crisis_score, preguntas_seguidas, etc. quedan ahí).
"""

import re
from typing import Optional


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
