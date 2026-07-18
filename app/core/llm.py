"""
Helpers para llamar a los LLM del backend de forma uniforme.

Hay DOS proveedores, ambos OpenAI-compatible (mismo SDK, distinta base_url):
  - "openrouter" → chat principal (config.CHAT_MODEL, hoy GPT-5.6 Luna)
  - "groq"       → fallback del chat + clasificadores internos (crisis
                   verifier, context router, insight del dashboard) + Whisper

`get_client(provider)` devuelve el cliente cacheado; nadie más instancia
OpenAI(...) a mano.

Sobre el razonamiento (aplica a los dos proveedores): los modelos razonadores
gastan tokens en un bloque de "reasoning" que CUENTA contra max_tokens. Si no
se controla, el reasoning se come el presupuesto y el JSON sale truncado.
  - En Groq (gpt-oss/qwen): reasoning_effort por familia + headroom fijo.
  - En OpenRouter: algunos modelos (GPT-5.6 Pro, Grok, Claude Fable) tienen el
    razonamiento OBLIGATORIO — mandar reasoning.enabled=false da 400. Se pide
    esfuerzo bajo (los no-razonadores lo ignoran) y headroom generoso.
    Validado en eval_multimodelo (jul 2026).
"""
from __future__ import annotations

import re

from openai import OpenAI

from app.core.config import config

# ══════════════════════════════════════════════════════════════
# Registro de clientes por proveedor
# ══════════════════════════════════════════════════════════════

_BASES: dict[str, tuple[str, str]] = {
    # provider → (base_url, nombre del atributo de config con la API key)
    "groq":       ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1",   "OPENROUTER_API_KEY"),
}

_clients: dict[str, OpenAI] = {}


def get_client(provider: str) -> OpenAI:
    """Cliente OpenAI-compatible cacheado para "groq" u "openrouter"."""
    cliente = _clients.get(provider)
    if cliente is None:
        base_url, key_attr = _BASES[provider]
        cliente = OpenAI(api_key=getattr(config, key_attr), base_url=base_url)
        _clients[provider] = cliente
    return cliente

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


def get_chat_targets() -> list[tuple[OpenAI, str, str]]:
    """Objetivos del chat principal, en orden de intento.

    Devuelve pares (cliente, proveedor, modelo): primero el primario
    (CHAT_PROVIDER/CHAT_MODEL) y después el fallback (CHAT_FALLBACK_*) si
    está configurado y es distinto.
    """
    primario = (config.CHAT_PROVIDER, config.CHAT_MODEL)
    targets = [(get_client(primario[0]), primario[0], primario[1])]
    respaldo = (config.CHAT_FALLBACK_PROVIDER, config.CHAT_FALLBACK_MODEL)
    if respaldo[1] and respaldo != primario:
        targets.append((get_client(respaldo[0]), respaldo[0], respaldo[1]))
    return targets


def get_groq_text_model() -> str:
    """Modelo de texto en Groq para el insight del dashboard (única pieza
    interna que sigue en Groq desde 2026-07-18; el verificador de crisis se
    movió a OpenRouter, ver get_crisis_verifier_target). Desacoplado a
    propósito del modelo del chat: cambiar CHAT_MODEL no toca esto."""
    return config.GROQ_MODEL


def get_crisis_verifier_target() -> tuple[OpenAI, str, str]:
    """Objetivo (cliente, proveedor, modelo) del verificador de crisis
    (confirmar_riesgo_real). Separado de get_chat_targets a propósito: es un
    clasificador de seguridad, no el chat — puede moverse sin tocar CHAT_*."""
    return (
        get_client(config.CRISIS_VERIFIER_PROVIDER),
        config.CRISIS_VERIFIER_PROVIDER,
        config.CRISIS_VERIFIER_MODEL,
    )


def get_router_model() -> str:
    """Modelo chico del clasificador de contexto (de config / .env)."""
    return config.GROQ_MODEL_ROUTER


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


# ══════════════════════════════════════════════════════════════
# Variantes por proveedor (para el chat multi-proveedor)
# ══════════════════════════════════════════════════════════════

# Headroom para OpenRouter: no sabemos a priori cuánto reasoning gasta cada
# modelo (y varios lo tienen obligatorio), así que es generoso. 600 base +
# 1000 = 1600, el número validado en eval_multimodelo con GPT-5.6/Grok/Fable.
_OPENROUTER_HEADROOM = 1000


def extra_body_for(provider: str | None, model: str | None = None) -> dict:
    """extra_body correcto según proveedor.

    OpenRouter: parámetro unificado `reasoning.effort=low` — los modelos con
    razonamiento obligatorio (Grok, Claude Fable, GPT-5.6 Pro) lo aceptan
    (enabled=false les da 400) y los no-razonadores lo ignoran.
    Groq (o proveedor desconocido): la lógica por familia de siempre.
    """
    if provider == "openrouter":
        return {"reasoning": {"effort": "low"}}
    return reasoning_extra_body(model)


def max_tokens_for_provider(base: int, provider: str | None, model: str | None = None) -> int:
    """max_tokens con el headroom de reasoning que corresponde al proveedor."""
    if provider == "openrouter":
        return base + _OPENROUTER_HEADROOM
    return max_tokens_for(base, model)


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
