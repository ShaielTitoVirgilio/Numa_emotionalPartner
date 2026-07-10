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
    # rate limit, sin crédito), el chat cae al fallback en Groq — barato,
    # probado y en otro proveedor, así un outage de OpenRouter no tira el chat.
    # Rollback instantáneo: CHAT_PROVIDER=groq + CHAT_MODEL=llama-3.3-70b-versatile
    # en el entorno (Railway) vuelve todo a como estaba, sin deploy.
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    CHAT_PROVIDER: str = os.getenv("CHAT_PROVIDER", "openrouter")
    CHAT_MODEL: str = os.getenv("CHAT_MODEL", "openai/gpt-5.6-luna")
    CHAT_FALLBACK_PROVIDER: str = os.getenv("CHAT_FALLBACK_PROVIDER", "groq")
    CHAT_FALLBACK_MODEL: str = os.getenv("CHAT_FALLBACK_MODEL", "llama-3.3-70b-versatile")

    # ── Piezas internas que se quedan en Groq (no son el chat) ──────────
    # Modelo de texto de Groq para el verificador de crisis y el insight del
    # dashboard: clasificaciones cortas y baratas, no vale pagar precio de
    # GPT-5.6 por ellas. llama-3.3-70b-versatile NO es modelo de razonamiento,
    # así que core/llm.py no le aplica reasoning_effort ni headroom.
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
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