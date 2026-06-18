"""
Helpers para llamar a los modelos de texto de Groq de forma uniforme.

El modelo se define en una sola variable (`config.GROQ_MODEL`). Algunos modelos
de Groq son de razonamiento (familia gpt-oss): gastan tokens en un bloque de
"reasoning" que CUENTA contra max_tokens. Si no se controla, el reasoning se
come el presupuesto y el JSON sale truncado → Groq devuelve 400
"Failed to validate JSON". Por eso, para esos modelos:
  - forzamos reasoning_effort="low" (reasoning corto, ~60 tokens)
  - sumamos headroom a max_tokens para que el JSON entre completo
"""
from __future__ import annotations

import re

from app.core.config import config

# Margen extra de tokens para el bloque de reasoning de los modelos razonadores.
_REASONING_HEADROOM = 320

# Familias de modelos de razonamiento en Groq y su reasoning_effort óptimo para
# respuestas JSON cortas. El reasoning cuenta contra max_tokens; si no se controla
# trunca el JSON → 400. Valores afinados empíricamente:
#   gpt-oss → "low"  (razona poco pero igual algo; suficiente para JSON)
#   qwen    → "none" (apaga el thinking → rápido y JSON limpio)
_REASONING_EFFORT = {
    "gpt-oss": "low",
    "qwen":    "none",
}


def get_model() -> str:
    """Modelo de texto activo (de config / .env)."""
    return config.GROQ_MODEL


def _reasoning_key(model: str | None = None) -> str | None:
    """Devuelve la familia razonadora a la que pertenece el modelo, o None."""
    m = (model or config.GROQ_MODEL or "").lower()
    for fam in _REASONING_EFFORT:
        if fam in m:
            return fam
    return None


def is_reasoning_model(model: str | None = None) -> bool:
    """True para modelos de razonamiento (gpt-oss, qwen)."""
    return _reasoning_key(model) is not None


def reasoning_extra_body(model: str | None = None) -> dict:
    """extra_body para la llamada a Groq. Vacío para modelos no-razonadores.
    extra_body garantiza que el parámetro llegue a Groq sin depender de la
    versión del SDK de OpenAI."""
    fam = _reasoning_key(model)
    return {"reasoning_effort": _REASONING_EFFORT[fam]} if fam else {}


def max_tokens_for(base: int, model: str | None = None) -> int:
    """Suma headroom de reasoning al max_tokens cuando el modelo lo necesita."""
    return base + _REASONING_HEADROOM if is_reasoning_model(model) else base


# Defensa extra: si algún día se cambia reasoning_format a "raw", el modelo
# podría pegar el razonamiento antes del JSON. Esto lo limpia.
_RE_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_RE_HARMONY = re.compile(r"<\|channel\|>.*?<\|message\|>", re.DOTALL)


def strip_reasoning(texto: str) -> str:
    """Quita bloques de razonamiento (<think>…</think> o canales harmony) si
    aparecieran en el content. Inofensivo cuando el content ya es JSON limpio."""
    if not texto:
        return texto
    t = _RE_THINK.sub("", texto)
    t = _RE_HARMONY.sub("", t)
    return t.strip()
