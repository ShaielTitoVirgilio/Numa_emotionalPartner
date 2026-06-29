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


config = Config()