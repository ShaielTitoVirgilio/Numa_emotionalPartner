# app/routes/diag_router.py
"""
Diagnóstico de la FORMA del stream del LLM, corriendo DENTRO del servidor.

Por qué existe: los logs del modo llamada (2026-08-18) muestran que el texto
del LLM llega en lote — 69 chunks en 74ms (~900 chunks/seg), imposible para
generación en vivo. El mismo modelo, proveedor y pin de provider, llamado
desde una máquina de desarrollo (scripts/diag_ttft_streaming.py), da ~845ms de
TTFT y 40 chunks repartidos en ~520ms: streamea bien.

O sea que el lote se arma en algún punto entre el proveedor y nuestro proceso,
y desde afuera las causas posibles se ven idénticas. Este endpoint corre el
MISMO experimento pero desde adentro de Railway, que es lo único que las
separa.

CÓMO LEER EL RESULTADO — tres hipótesis, y el experimento las distingue:

  1. Prefill (el prompt real es enorme: ~29 módulos + memorias + perfil).
     → Se ve como: TTFT crece mucho con prompt_chars, pero el spread se
       mantiene parecido entre variantes. El tiempo se va ANTES del primer
       token, y el texto igual gotea.

  2. Entorno (red/proxy de Railway, o nuestro proceso sin CPU para drenar).
     → Se ve como: spread ~0 en TODAS las variantes, incluso con el prompt
       chico. El lote se arma pase lo que pase.

  3. Backpressure del cliente (el celular en red móvil tarda en recibir, se
     bloquea el yield, dejamos de leer del LLM y los chunks se acumulan).
     → Se ve como: acá gotea BIEN en todas las variantes, pero producción
       sigue mostrando lote. Este endpoint no le escribe a ningún cliente
       — solo lee el stream y mide — así que si acá gotea y en /chat/stream
       no, el problema está en el camino de escritura al cliente.

Hace llamadas REALES al LLM (gasta tokens, poco). Va detrás de ADMIN_KEY por
header, igual que los /admin/* de feedback_router.

NO loguea ni devuelve contenido de mensajes: solo tamaños y tiempos.

═══════════════════════════════════════════════════════════════════════
RESULTADOS MEDIDOS EN RAILWAY (staging) — 2026-08-18
═══════════════════════════════════════════════════════════════════════

    /admin/diag-stream-real       TTFT 596-646ms   9.9-23.0 ms/chunk
    /admin/diag-stream-real-sse   TTFT 552-1080ms  9.1-11.1 ms/chunk
    /chat/stream (produccion)     TTFT 2154-4438ms 1.1-3.1 ms/chunk

Los dos de diagnóstico usan EL MISMO generate_response_stream, EL MISMO
prompt de construir_prompt (38276 chars), EL MISMO contenedor y la misma
caché (10734/10737 tokens). El "-sse" además va dentro de una
StreamingResponse yieldeando por oración, igual que /chat/stream.

O sea que quedan descartados, con medición y no por deducción: el modelo, el
reasoning, el tamaño y el contenido del prompt, el cacheo, la red de Railway,
los middlewares, el buffer de streaming, y la propia StreamingResponse.

Lo único que /chat/stream tiene y estos no:
  1. El CLIENTE REAL (el celular en red móvil) del otro lado. Con el
     generador sincrónico de _stream_chat_respuesta, cada yield espera a que
     el event loop escriba al cliente antes de volver a pedir el próximo
     chunk. Si el cliente es lento, dejamos de leer del LLM y los chunks se
     apilan en el socket → se leen después de golpe. Explica el lote (1-3
     ms/chunk) de forma directa.
  2. El historial de conversación (~1000 tokens más, y sin cachear: la caché
     cubre el prefijo del system prompt, no lo que se agrega después).
  3. La concurrencia de una llamada real (subidas de audio de 100-230KB al
     STT entre turno y turno).

PRÓXIMO PASO SUGERIDO (no implementado): desacoplar la lectura del LLM de la
escritura al cliente — leer el stream en una tarea aparte que llene una cola,
y que el generador que responde consuma de esa cola. Así un cliente lento no
puede frenar la lectura del LLM, y las oraciones están listas para hablarse
apenas se generan, que es justo lo que el modo llamada necesita.
"""
import hmac
import json
import statistics
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import config
from app.core.llm import get_client, extra_body_for, max_tokens_for_provider
from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt
from app.streaming_buffer import BufferStreamingMensaje

router = APIRouter()

_llm = LLMClient()

# Prompt de prueba. No usa construir_prompt() a propósito: eso necesitaría un
# usuario real y traería memorias de verdad al diagnóstico. Se rellena con
# texto neutro hasta el tamaño que interesa medir, que es lo único que le
# importa al prefill.
_BASE = (
    "Sos Numa, una compañera emocional en español rioplatense. "
    "Respondé cálido y concreto, sin listas. "
)
_RELLENO = (
    "Guía interna: acompañá sin dar consejos no pedidos, validá lo que la "
    "persona siente, no minimices, no uses lenguaje clínico ni tecnicismos. "
)
_MENSAJE = "Uf, hoy fue un día durísimo en el trabajo. Estoy agotada."


def _validar_admin_key(provided: Optional[str]) -> None:
    """Misma validación que feedback_router: tiempo constante, por header, y
    se rechaza si el server no tiene ADMIN_KEY configurada."""
    expected = config.ADMIN_KEY or ""
    if not expected or not provided or not hmac.compare_digest(str(provided), expected):
        raise HTTPException(status_code=401, detail="No autorizado")


def _prompt_de(chars: int) -> str:
    """Prompt neutro de aproximadamente `chars` caracteres."""
    if chars <= len(_BASE):
        return _BASE
    repeticiones = (chars - len(_BASE)) // len(_RELLENO) + 1
    return (_BASE + _RELLENO * repeticiones)[:chars]


def _medir(cliente, proveedor: str, modelo: str, prompt: str) -> Dict[str, Any]:
    """Una llamada en streaming, midiendo la llegada de CADA chunk."""
    inicio = time.perf_counter()
    marcas: List[float] = []   # ms desde el inicio, uno por chunk de texto
    chars = 0

    stream = cliente.chat.completions.create(
        model=modelo,
        temperature=0.7,
        max_tokens=max_tokens_for_provider(600, proveedor, modelo),
        stream=True,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": _MENSAJE},
        ],
        extra_body=extra_body_for(proveedor, modelo),
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content or ""
        if not delta:
            continue
        marcas.append((time.perf_counter() - inicio) * 1000)
        chars += len(delta)

    total_ms = (time.perf_counter() - inicio) * 1000
    if not marcas:
        return {"prompt_chars": len(prompt), "error": "sin texto en la respuesta",
                "total_ms": round(total_ms, 1)}

    # Huecos entre chunks: es lo que distingue "goteando" de "todo junto"
    # mejor que el spread solo, que un único chunk tardío puede inflar.
    huecos = [b - a for a, b in zip(marcas, marcas[1:])] or [0.0]
    return {
        "prompt_chars": len(prompt),
        "ttft_ms": round(marcas[0], 1),
        "ultimo_token_ms": round(marcas[-1], 1),
        "spread_ms": round(marcas[-1] - marcas[0], 1),
        "total_ms": round(total_ms, 1),
        "chunks": len(marcas),
        "respuesta_chars": chars,
        "hueco_mediano_ms": round(statistics.median(huecos), 2),
        "hueco_max_ms": round(max(huecos), 2),
        # El número que resume todo: cuántos ms tardó en llegar cada chunk en
        # promedio, contando solo desde el primero. Generando en vivo da
        # decenas de ms; en lote da menos de ~3ms.
        "ms_por_chunk": round((marcas[-1] - marcas[0]) / max(1, len(marcas) - 1), 2),
    }


@router.get("/admin/diag-streaming")
def diag_streaming(
    vueltas: int = 2,
    x_admin_key: Optional[str] = Header(None),
):
    """Corre el experimento con tres tamaños de prompt y devuelve los tiempos.

    `vueltas`: la primera puede pagar handshake TLS frío y ensuciar el TTFT
    (medido en dev: 1779ms la primera contra 845ms la segunda, solo por reusar
    la conexión). Con 2 se ve cuánto de la latencia es conexión fría, que es
    una de las cosas que queremos saber.
    """
    _validar_admin_key(x_admin_key)

    vueltas = max(1, min(int(vueltas), 4))  # cota: son llamadas reales al LLM
    proveedor, modelo = config.CHAT_PROVIDER, config.CHAT_MODEL
    cliente = get_client(proveedor)

    # ~0.3k (control), ~4k y ~12k: el prompt real de Numa con módulos,
    # memorias y perfil está en ese orden de magnitud.
    tamanos = [len(_BASE), 4000, 12000]

    resultados: Dict[str, Any] = {
        "proveedor": proveedor,
        "modelo": modelo,
        "vueltas": [],
    }
    for _ in range(vueltas):
        vuelta: List[Dict[str, Any]] = []
        for chars in tamanos:
            try:
                vuelta.append(_medir(cliente, proveedor, modelo, _prompt_de(chars)))
            except Exception as e:
                vuelta.append({"prompt_chars": chars,
                               "error": f"{type(e).__name__}: {str(e)[:160]}"})
        resultados["vueltas"].append(vuelta)

    resultados["como_leerlo"] = {
        "ms_por_chunk_alto": "decenas de ms = el texto gotea (sano)",
        "ms_por_chunk_bajo": "<3ms = llegó en lote",
        "si_gotea_aca_pero_no_en_chat_stream": (
            "el lote se arma en el camino de escritura al cliente "
            "(backpressure del celular), no en el LLM ni en la red de entrada"
        ),
        "si_no_gotea_ni_aca": "es la red/proxy de entrada o el proceso sin CPU para drenar",
    }
    return resultados


# ══════════════════════════════════════════════════════════════════════
# EL EXPERIMENTO QUE FALTA: generate_response_stream, prompt real, en Railway
# ══════════════════════════════════════════════════════════════════════
#
# Lo de arriba llama al SDK derecho con un prompt de relleno. Eso ya mostró que
# el modelo, la red y el entorno están bien (8-17 ms/chunk desde Railway). Pero
# /chat/stream sigue entregando el mensaje de golpe (1-3 ms/chunk), y las dos
# diferencias que quedaban sin probar son:
#
#   (a) el CÓDIGO real — generate_response_stream, con _INSTRUCCION_FORMATO_
#       STREAMING y el prompt de ~38k que arma construir_prompt
#   (b) el CAMINO DE RESPUESTA — hacerlo dentro de una StreamingResponse,
#       yieldeando al cliente, en vez de leer y devolver un JSON al final
#
# Por eso hay DOS endpoints con el mismo cuerpo, que se diferencian solo en (b):
#
#   /admin/diag-stream-real      → lee el stream y devuelve JSON. Aísla (a).
#   /admin/diag-stream-real-sse  → lo mismo DENTRO de StreamingResponse,
#                                  yieldeando por oración igual que
#                                  /chat/stream. Suma (b).
#
# Cómo se lee el par:
#   real gotea + sse gotea      → el código y el entorno están bien; el lote se
#                                 arma recién con el cliente real (el celular
#                                 en red móvil), no reproducible desde curl.
#   real gotea + sse en lote    → lo rompe el yield/StreamingResponse. Ahí sí
#                                 hay algo nuestro que arreglar.
#   real en lote                → es el código con ese prompt en ese entorno,
#                                 y no tiene nada que ver con el cliente.
#
# Igual que el resto del archivo: sin escrituras a la base, sin memorias, sin
# contenido de mensajes en la respuesta. Solo tiempos y tamaños.

_MENSAJE_DIAG = "Uf, hoy fue un día durísimo en el trabajo. Estoy agotada."


def _prompt_realista() -> str:
    """Prompt como el de un turno de modo llamada de verdad.

    Datos inventados a propósito (no toca la base ni memorias reales), pero
    pasando por construir_prompt para que el tamaño y la forma sean los que
    ve /chat/stream: router_hints ok=False es exactamente lo que recibe el
    modo llamada, que corre con el context_router apagado.
    """
    return construir_prompt(
        perfil={"nombre": "Sofi", "edad": 29},
        memorias=[{
            "content": "Sofi trabaja en una agencia y viene con mucha carga",
            "category": "trabajo", "priority": 3,
        }],
        num_interacciones=6,
        patrones=[],
        ultimo_mensaje=_MENSAJE_DIAG,
        mood_actual="stressed",
        router_hints={"ok": False},
    )


def _medir_stream_real(system_prompt: str):
    """GENERADOR que consume generate_response_stream midiendo chunk por chunk.

    Va emitiendo ("oracion", texto) a medida que el buffer las libera, y al
    final ("fin", mediciones). Tiene que ser generador y no una función que
    devuelve todo junto: la variante SSE necesita yieldear CADA oración en el
    momento en que aparece, que es justamente la condición que se está
    probando. Si acumulara y emitiera al final, streamearía de mentira y el
    experimento no distinguiría nada.
    """
    buf = BufferStreamingMensaje(
        familia_apertura_previa=None,
        previo_cierre_presencia=False,
        preguntas_seguidas=0,
        crisis_score=0.0,
        ultimo_modulo_critico=False,
        retencion=0,           # igual que el modo llamada
    )

    inicio = time.perf_counter()
    marcas_chunk: List[float] = []      # llegada de cada chunk del LLM
    marcas_yield: List[float] = []      # cada oración emitida al cliente
    chars = 0
    meta: Optional[dict] = None

    for tipo, valor in _llm.generate_response_stream(
        conversation=[{"role": "user", "content": _MENSAJE_DIAG}],
        system_prompt=system_prompt,
        modo_llamada=True,
    ):
        if tipo == "mensaje":
            marcas_chunk.append((time.perf_counter() - inicio) * 1000)
            chars += len(valor)
            for oracion in buf.feed(valor):
                marcas_yield.append((time.perf_counter() - inicio) * 1000)
                yield ("oracion", oracion)
        else:
            meta = valor

    for oracion in buf.cerrar():
        marcas_yield.append((time.perf_counter() - inicio) * 1000)
        yield ("oracion", oracion)

    total_ms = (time.perf_counter() - inicio) * 1000
    if not marcas_chunk:
        yield ("fin", {"error": "sin texto", "total_ms": round(total_ms, 1),
                       "prompt_chars": len(system_prompt)})
        return

    huecos = [b - a for a, b in zip(marcas_chunk, marcas_chunk[1:])] or [0.0]
    uso = (meta or {}).get("_llm", {})
    yield ("fin", {
        "prompt_chars": len(system_prompt),
        "ttft_ms": round(marcas_chunk[0], 1),
        "ultimo_token_ms": round(marcas_chunk[-1], 1),
        "spread_ms": round(marcas_chunk[-1] - marcas_chunk[0], 1),
        "total_ms": round(total_ms, 1),
        "chunks": len(marcas_chunk),
        # EL número: decenas de ms = gotea; <3ms = vino en lote.
        "ms_por_chunk": round(
            (marcas_chunk[-1] - marcas_chunk[0]) / max(1, len(marcas_chunk) - 1), 2),
        "hueco_mediano_ms": round(statistics.median(huecos), 2),
        "hueco_max_ms": round(max(huecos), 2),
        "oraciones_emitidas": len(marcas_yield),
        "primer_yield_ms": round(marcas_yield[0], 1) if marcas_yield else None,
        "respuesta_chars": chars,
        "prompt_tokens": uso.get("prompt_tokens"),
        "cached_tokens": uso.get("cached_tokens"),
        "completion_tokens": uso.get("completion_tokens"),
    })


def _consumir(system_prompt: str) -> Dict[str, Any]:
    """Corre el generador descartando las oraciones y devuelve las mediciones."""
    for tipo, valor in _medir_stream_real(system_prompt):
        if tipo == "fin":
            return valor
    return {"error": "el generador no emitió mediciones"}


@router.get("/admin/diag-stream-real")
def diag_stream_real(vueltas: int = 2, x_admin_key: Optional[str] = Header(None)):
    """Variante SIN cliente: aísla el código + el prompt real en este entorno."""
    _validar_admin_key(x_admin_key)
    vueltas = max(1, min(int(vueltas), 4))
    sp = _prompt_realista()
    return {
        "variante": "sin_streaming_al_cliente",
        "modelo": config.CHAT_MODEL,
        "prompt_chars": len(sp),
        "vueltas": [_consumir(sp) for _ in range(vueltas)],
    }


@router.get("/admin/diag-stream-real-sse")
def diag_stream_real_sse(x_admin_key: Optional[str] = Header(None)):
    """Variante CON StreamingResponse: mismo cuerpo, pero yieldeando cada
    oración al cliente en el momento, igual que /chat/stream. Las mediciones
    van en la última línea NDJSON."""
    _validar_admin_key(x_admin_key)
    sp = _prompt_realista()

    def generador():
        for tipo, valor in _medir_stream_real(sp):
            if tipo == "oracion":
                # Solo el largo, nunca el texto: mismo criterio de privacidad
                # que el resto del archivo.
                yield json.dumps({"type": "delta", "chars": len(valor)}) + "\n"
            else:
                yield json.dumps({"type": "diag", **valor}, ensure_ascii=False) + "\n"

    return StreamingResponse(generador(), media_type="application/x-ndjson")
