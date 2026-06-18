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
    # llama-3.3-70b (y 3.1-8b, llama-4-scout) se decomisionan en Groq. El default
    # es el reemplazo elegido: qwen3-32b → natural/rioplatense, JSON confiable
    # (reasoning_effort="none"), voseo correcto y ~mitad del costo del 70B.
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")


config = Config()