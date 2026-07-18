import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")

    # ── Chat principal (la respuesta que ve el usuario) ─────────────────
    # Corre en OpenRouter (GPT-5.6 Luna: 0/30 fallas de tuteo/eco/comillas en
    # eval_multimodelo vs 3-4/30 de Llama 70B). Si el primario falla (outage,
    # rate limit, sin crédito), el chat cae al fallback.
    # 2026-07-18: el fallback se movió de Groq/Llama a Gemini 3 Flash Preview en
    # OpenRouter — Llama (70B y el resto) se bloquea en Groq el 2026-07-17, y de
    # paso queda en el mismo proveedor que el primario (un outage de OpenRouter
    # tira ambos, pero ya no dependíamos de que Groq tenga cupo/precio estable).
    # ⚠️ Sin eval todavía: elegido por precio/lineup, falta correr
    # eval_multimodelo.py contra este modelo antes de confiar en él en producción.
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    CHAT_PROVIDER: str = os.getenv("CHAT_PROVIDER", "openrouter")
    CHAT_MODEL: str = os.getenv("CHAT_MODEL", "openai/gpt-5.6-luna")
    CHAT_FALLBACK_PROVIDER: str = os.getenv("CHAT_FALLBACK_PROVIDER", "openrouter")
    CHAT_FALLBACK_MODEL: str = os.getenv("CHAT_FALLBACK_MODEL", "google/gemini-3-flash-preview")

    # ── Verificador de crisis (capa 2, confirma si el riesgo es real) ───
    # 2026-07-18: se movió de Groq/Llama (bloqueado el 17/07) a OpenRouter, mismo
    # modelo que el fallback del chat. Deliberadamente separado de CHAT_FALLBACK_*
    # (aunque hoy apunten al mismo modelo) para poder ajustar cada uno sin que el
    # otro se mueva — es un clasificador de seguridad, no el chat.
    # ⚠️ Sin eval todavía: correr eval_seguridad_router.py / eval_70b_real.py
    # contra este modelo antes de confiar en él en producción (es fail-safe ante
    # error, pero un mal clasificador aumenta falsos positivos/negativos).
    CRISIS_VERIFIER_PROVIDER: str = os.getenv("CRISIS_VERIFIER_PROVIDER", "openrouter")
    CRISIS_VERIFIER_MODEL: str = os.getenv("CRISIS_VERIFIER_MODEL", "google/gemini-3-flash-preview")

    # ── Piezas internas que se quedan en Groq (no son el chat) ──────────
    # Modelo de texto de Groq para el insight del dashboard: texto interno,
    # async, nadie lo espera en vivo — no vale pagar precio de OpenRouter por él.
    # 2026-07-18: repuntado a qwen/qwen3-32b (el mismo que ya corre en el context
    # router) porque Llama se bloquea en Groq el 17/07. Es razonador: core/llm.py
    # ya le apaga el thinking (reasoning_effort="none") y suma headroom.
    # (Antes este mismo valor también alimentaba el verificador de crisis — ver
    # CRISIS_VERIFIER_* arriba, ahora desacoplado.)
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")
    # Modelo del clasificador de contexto (context_router.py): NO responde al
    # usuario, solo decide qué módulos activar leyendo el contexto semántico que
    # los detectores por keywords no alcanzan. Corre en cada turno.
    # ⚠️ Se probó llama-3.1-8b-instant (más barato/rápido) pero FALLA en lo
    # sensible: escala hipérboles ("me quiero morir de la vergüenza", "me mato
    # estudiando") a crisis explícita y se come planes velados ("el finde lo hago
    # y listo" lo leía como buena noticia). Para el core de seguridad de la app se
    # usa qwen/qwen3-32b, que pasó el 100% de la batería (críticos + trampas de
    # falso positivo) de forma consistente. Es razonador: core/llm.py le apaga el
    # thinking (reasoning_effort="none") y suma headroom → JSON limpio y rápido.
    GROQ_MODEL_ROUTER: str = os.getenv("GROQ_MODEL_ROUTER", "qwen/qwen3-32b")


config = Config()