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
"""
import hmac
import statistics
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException

from app.core.config import config
from app.core.llm import get_client, extra_body_for, max_tokens_for_provider

router = APIRouter()

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
