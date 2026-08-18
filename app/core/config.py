import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")

    # ── Entorno de despliegue ───────────────────────────────────────────
    # "production" (la app real) o "staging" (NumaDev, para probar sin tocar
    # datos de usuarios reales). Cambia el nombre con el que la PWA se instala
    # en el celular y muestra un cartelito en pantalla, para que NUNCA quede
    # duda de en cuál de las dos estás. El default es "production" a propósito:
    # si alguien olvida setear la variable, lo peor que pasa es que staging se
    # vea como producción, no al revés.
    APP_ENTORNO: str = os.getenv("APP_ENTORNO", "production")

    @property
    def es_produccion(self) -> bool:
        return self.APP_ENTORNO.strip().lower() == "production"

    # ── Observabilidad (Sentry) ─────────────────────────────────────────
    # Sin DSN, Sentry no se inicializa y la app corre igual (local/tests).
    # La config de privacidad vive en app/core/observability.py: el contenido
    # de las conversaciones NO se reporta nunca.
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    SENTRY_ENVIRONMENT: str = os.getenv("SENTRY_ENVIRONMENT", "production")
    SENTRY_TRACES_SAMPLE_RATE: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0"))

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

    # ── Modelo del MODO LLAMADA (voz) ──────────────────────────────────
    # Vacío = usa CHAT_MODEL, o sea el mismo que el chat escrito. El mecanismo
    # queda porque sirve, pero HOY NO SE USA. Por qué:
    #
    # Se probó gpt-chat-latest, elegido por latencia de cola (p90 1332ms contra
    # 1911-3156ms de luna, medido con scripts/bench_modelos_ttft.py). Se
    # revirtió por dos motivos que pesan más que esos ~600ms:
    #
    #   1. COSTO: 25x. Con los tokens reales de un turno (11.674 de entrada,
    #      10.900 cacheados, 150 de salida) da USD 0.0138 por turno contra
    #      0.00055 de luna — una llamada de 20 turnos pasa de 1 centavo a 28.
    #
    #   2. ES UN ALIAS MÓVIL. chat-latest "siempre resuelve al último modelo
    #      Instant usado en ChatGPT": OpenAI lo cambia sin avisar. Las evals de
    #      calidad y seguridad que se le corran vencen solas, y el
    #      comportamiento puede cambiar de un día para el otro sin release
    #      nuestro. Para una app de salud mental eso no es aceptable, y
    #      descalifica al modelo aunque fuese gratis.
    #
    # Costo por turno de los candidatos medidos (mismos tokens reales):
    #     gpt-5.6-luna      USD 0.00055   (1x)     p90 1911-3156ms
    #     gpt-4o-mini       USD 0.00102   (1.9x)   p90 1064ms
    #     gpt-5.6-terra     USD 0.00553   (10x)    p90 1101ms
    #     gpt-chat-latest   USD 0.01382   (25x)    p90 1332ms
    #
    # Si algún día se quiere volver a atacar la latencia por acá, el ÚNICO
    # candidato con relación costo/beneficio razonable es gpt-4o-mini: 1.9x de
    # costo y el mejor p90. Pero falló 1/20 en registro rioplatense (tuteo) en
    # eval_multimodelo.py, así que antes hay que correr una eval de calidad más
    # grande y ver si es un caso aislado o un problema sistemático.
    CHAT_PROVIDER_LLAMADA: str = os.getenv("CHAT_PROVIDER_LLAMADA", "openrouter")
    CHAT_MODEL_LLAMADA: str = os.getenv("CHAT_MODEL_LLAMADA", "")

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

    # ── Context router: proveedor configurable (2026-07-28) ─────────────
    # qwen/qwen3-32b fue decomisionado por Groq el 17/07 y ningún candidato de
    # Groq igualó su 0/25 en eval_seguridad_router.py. Se desacopla del
    # GROQ_MODEL_ROUTER de arriba (que queda legacy) para poder probar/usar un
    # modelo en OpenRouter (ej. Gemini 3 Flash Preview, ya validado 10/10 en
    # eval_crisis_verifier.py contra las mismas trampas de hipérbole) sin tocar
    # las otras piezas que siguen en Groq.
    CONTEXT_ROUTER_PROVIDER: str = os.getenv("CONTEXT_ROUTER_PROVIDER", "groq")
    CONTEXT_ROUTER_MODEL: str = os.getenv("CONTEXT_ROUTER_MODEL", GROQ_MODEL_ROUTER)
    # Si CONTEXT_ROUTER_PROVIDER=openrouter: lista separada por comas de
    # providers OpenRouter permitidos para ESTE modelo puntual (campo
    # `provider.only` de la API). Necesario porque distintos providers detrás
    # del mismo model id en OpenRouter dieron resultados MUY distintos en
    # eval_seguridad_router.py (ej. Alibaba: 11/25 fallas graves; Nebius: 0/25).
    # Vacío = sin pin, OpenRouter balancea libremente entre todos.
    CONTEXT_ROUTER_OPENROUTER_PROVIDERS: str = os.getenv("CONTEXT_ROUTER_OPENROUTER_PROVIDERS", "")


config = Config()