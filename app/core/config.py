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
    # Distinto del chat escrito a propósito. Lo que manda en una llamada no es
    # la latencia mediana sino la PEOR: un turno que tarda 3s rompe la
    # sensación de conversación aunque el resto sean rápidos. Medido con
    # scripts/bench_modelos_ttft.py (16 muestras por modelo, prompt real de
    # ~39k chars, ronda robin para que un bache de red no sesgue a uno solo):
    #
    #     modelo             mediana   p90 (n=16)   p90 (n=24)   chars
    #     gpt-5.6-luna         817ms      3156ms       1911ms      150
    #     gpt-chat-latest     1028ms      1065ms       1332ms      108
    #     gpt-5.6-terra        929ms      1101ms          —         92
    #     gpt-4o-mini          701ms      1064ms          —        108
    #
    # ES UN CANJE, no una victoria limpia, y conviene tenerlo claro: se pagan
    # ~200ms de mediana para ganar entre 600 y 2100ms de p90 (la cola de luna
    # varía bastante entre corridas). Se eligió así porque lo reportado en
    # dispositivo real fue "a veces tarda un montón", que es cola y no mediana;
    # y de paso chat-latest genera respuestas más cortas (108 vs 150 chars),
    # que en voz es menos tiempo hablando.
    #
    # Descartados: gpt-4o-mini era el más rápido pero falló 1/20 en registro
    # rioplatense (eval_multimodelo.py) — inaceptable. terra pasó la eval
    # mecánica pero responde notoriamente más frío y llegó a malinterpretar un
    # mensaje ("El personaje se parece mucho a mi" → "¿A quién te referís?").
    #
    # Si al usarlo se siente peor que luna, revertir es cambiar esta variable
    # de entorno: no hay nada más atado a la decisión.
    #
    # El chat ESCRITO sigue en CHAT_MODEL sin cambios: ahí 3s de cola no se
    # sienten igual, y no hay motivo para tocar lo que funciona.
    CHAT_PROVIDER_LLAMADA: str = os.getenv("CHAT_PROVIDER_LLAMADA", "openrouter")
    CHAT_MODEL_LLAMADA: str = os.getenv("CHAT_MODEL_LLAMADA", "openai/gpt-chat-latest")

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