import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")
    # Modelo de texto de Groq usado en todo el backend (chat, verificador de
    # crisis, insight del dashboard). Se cambia solo acá / en el .env.
    # qwen/qwen3-32b se decomisiona en Groq el 17/07/2026. Migramos a
    # llama-3.3-70b-versatile: sigue activo en Groq, mejor en rioplatense
    # (menos escapes al tuteo) y NO es modelo de razonamiento, así que core/llm.py
    # no le aplica reasoning_effort ni headroom — JSON limpio sin ajustes extra.
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    # Modelo de respaldo: si el primario falla (outage, rate limit, modelo caído),
    # el chat reintenta automáticamente con este antes de rendirse.
    # ⚠️ qwen/qwen3-32b se apaga en Groq el 17/07/2026 — cambiar este backup antes de esa fecha.
    GROQ_MODEL_FALLBACK: str = os.getenv("GROQ_MODEL_FALLBACK", "qwen/qwen3-32b")
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