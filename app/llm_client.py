# app/llm_client.py

import re
import json
import time
from typing import List, Literal, TypedDict, Optional
from openai import OpenAI

from app.core.llm import (
    get_chat_targets,
    extra_body_for,
    max_tokens_for_provider,
    strip_reasoning,
)

Mood = Literal[
    "neutral", "calm", "happy", "excited",
    "stressed", "overwhelmed", "sad", "anxious",
]

class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str

class MemoryItem(TypedDict, total=False):
    content: str
    category: str
    priority: int
    # Opcionales que chat_router valida/clampea antes de persistir:
    event: Optional[dict]   # {"title": str, "date": "YYYY-MM-DD"} — memoria proactiva
    open: bool              # tema abierto pendiente de desenlace
    helped: bool            # recurso que al usuario le hizo bien

class LLMRawResponse(TypedDict):
    message: str
    mood: Mood
    suggested_action: Optional[str]
    memories: List[MemoryItem]


_VALID_MOODS = {"neutral", "calm", "happy", "excited", "stressed", "overwhelmed", "sad", "anxious"}
_VALID_CATEGORIES = {"trabajo", "estudios", "relaciones", "salud", "identidad", "emocional", "hobbies", "vida_cotidiana", "otro"}


def _normalizar_memories(parsed: dict) -> List[MemoryItem]:
    """Acepta el formato nuevo (array "memories") y el viejo (campos sueltos
    "memory"/"memory_category"). Extraído de generate_response para poder
    reusarlo también desde el parseo de metadata del modo streaming — mismo
    código, sin cambios de comportamiento."""
    raw_memories = parsed.get("memories")
    if isinstance(raw_memories, list):
        memories: List[MemoryItem] = []
        for m in raw_memories[:2]:  # máx 2
            if not isinstance(m, dict):
                continue
            content = str(m.get("content") or "").strip()
            if not content:
                continue
            cat = m.get("category")
            cat = cat if cat in _VALID_CATEGORIES else "otro"
            try:
                prio = max(1, min(5, int(m.get("priority") or 3)))
            except (TypeError, ValueError):
                prio = 3
            item: MemoryItem = {"content": content, "category": cat, "priority": prio}
            # Passthrough de metadata que chat_router valida/clampea antes de
            # persistir (_validar_evento, checks `is True`).
            if isinstance(m.get("event"), dict):
                item["event"] = m["event"]
            if m.get("open") is True:
                item["open"] = True
            if m.get("helped") is True:
                item["helped"] = True
            memories.append(item)
        return memories

    # Fallback: formato viejo con campos sueltos
    old_content = str(parsed.get("memory") or "").strip()
    if old_content:
        raw_cat = parsed.get("memory_category")
        cat = raw_cat if raw_cat in _VALID_CATEGORIES else "otro"
        return [{"content": old_content, "category": cat, "priority": 3}]
    return []


# Respuesta de cortesía cuando Groq falla (HTTP 400 por json_validate_failed /
# max tokens ante input adversarial, timeouts, etc.). Antes ese error subía
# como 500 y el usuario veía "Error de conexión".
_FALLBACK_RESPONSE: "LLMRawResponse" = {
    "message": (
        "Perdón, me trabé un segundo procesando eso 🐼 "
        "¿Me lo decís de nuevo, o seguimos por otro lado?"
    ),
    "mood": "neutral",
    "suggested_action": None,
    "memories": [],
}


class LLMClient:
    def __init__(
        self,
        client: Optional[OpenAI] = None,
        model: Optional[str] = None,
        fallback_model: Optional[str] = None,
    ):
        # Por default (sin argumentos): los targets de producción de
        # get_chat_targets() — OpenRouter primario + Groq de respaldo.
        # Los overrides existen para eval scripts que quieren apuntar un
        # cliente/modelo específico reusando este mismo parseo/validación
        # de JSON en vez de reimplementarlo.
        self._client_override = client
        self._model_override = model
        self._fallback_override = fallback_model

    def _targets(self) -> list:
        """Lista de (cliente, proveedor, modelo) a intentar en orden."""
        if self._model_override:
            # Cliente inyectado (evals): proveedor desconocido → None hace que
            # extra_body/max_tokens caigan a la lógica Groq-legacy, salvo que
            # el caller los pase explícitos en generate_response.
            targets = [(self._client_override, None, self._model_override)]
            if self._fallback_override and self._fallback_override != self._model_override:
                targets.append((self._client_override, None, self._fallback_override))
            return targets
        return get_chat_targets()

    def generate_response(
        self,
        conversation: List[ChatMessage],
        system_prompt: str,
        *,
        max_tokens_base: int = 600,
        extra_body: Optional[dict] = None,
    ) -> LLMRawResponse:

        # Primario + fallback (proveedor distinto en producción). Si el
        # primario se cae (outage, rate limit, sin crédito, modelo caído),
        # reintentamos con el fallback antes de rendirnos al mensaje genérico.
        raw = None
        ultimo_error = None
        proveedor_usado = None
        modelo_usado = None
        intento_usado = None
        inicio = time.perf_counter()
        for i, (cliente, proveedor, modelo) in enumerate(self._targets()):
            try:
                completion = cliente.chat.completions.create(
                    model=modelo,
                    temperature=0.7,
                    # 600 base + headroom según proveedor/modelo para que el
                    # bloque de reasoning no trunque el JSON.
                    max_tokens=max_tokens_for_provider(max_tokens_base, proveedor, modelo),
                    response_format={"type": "json_object"},  # Capa 1: fuerza JSON válido a nivel API
                    messages=[
                        {"role": "system", "content": system_prompt},
                        *conversation,
                    ],
                    extra_body=(extra_body if extra_body is not None else extra_body_for(proveedor, modelo)),
                )
                raw = completion.choices[0].message.content or ""
                proveedor_usado, modelo_usado, intento_usado = proveedor, modelo, i
                if i > 0:
                    print(f"ℹ️ LLM: respondió el modelo de backup ({proveedor or '?'}: {modelo})")
                break
            except Exception as e:
                # Caso especial (NO es caída): gpt-oss/qwen a veces responde texto
                # plano sin el wrapper JSON → Groq lo rechaza con json_validate_failed,
                # pero el texto real viene en error.failed_generation. Lo recuperamos
                # en vez de saltar al backup (el modelo SÍ respondió).
                recuperado = _recuperar_failed_generation(e)
                if recuperado is not None:
                    print(f"ℹ️ json_validate_failed ({modelo}): recuperado failed_generation")
                    raw = recuperado
                    proveedor_usado, modelo_usado, intento_usado = proveedor, modelo, i
                    break
                # Caída real (timeout, rate limit, 402, 5xx): probamos el backup.
                ultimo_error = e
                print(f"⚠️ LLM error con {proveedor or '?'}: {modelo}: {e}")

        latencia_ms = round((time.perf_counter() - inicio) * 1000, 1)

        if raw is None:
            print(f"⚠️ LLM: fallaron todos los modelos. Último error: {ultimo_error}")
            resultado = dict(_FALLBACK_RESPONSE)
            resultado["_llm"] = {
                "provider": None, "model": None, "fallback": None,
                "ok": False, "latency_ms": latencia_ms,
            }
            return resultado

        # Defensa: si el modelo de razonamiento filtró el <think> al content,
        # lo quitamos antes de parsear (con json_object normalmente ya viene limpio).
        raw = strip_reasoning(raw)

        # ─────────────────────────────────────────────────────────────
        # PASO 1: intentar parsear el raw completo como JSON puro
        # ─────────────────────────────────────────────────────────────
        parsed = None

        try:
            parsed = json.loads(raw.strip())
        except json.JSONDecodeError:
            pass

        # ─────────────────────────────────────────────────────────────
        # PASO 2: buscar el último { en el texto y parsear desde ahí
        # Usamos rfind para encontrar el bloque JSON aunque haya texto
        # libre antes. Si el JSON está truncado, intentamos repararlo.
        # ─────────────────────────────────────────────────────────────
        if parsed is None:
            last_brace = raw.rfind("{")
            if last_brace != -1:
                json_candidate = raw[last_brace:]
                json_candidate = _reparar_json_truncado(json_candidate)
                try:
                    candidate = json.loads(json_candidate)
                    if "message" in candidate and "mood" in candidate:
                        parsed = candidate
                except json.JSONDecodeError:
                    pass

        # ─────────────────────────────────────────────────────────────
        # PASO 3: fallback total
        # El texto antes del primer { es la respuesta real del modelo
        # ─────────────────────────────────────────────────────────────
        if parsed is None:
            pre_json = raw.split("{")[0].strip()
            parsed = {
                "message": pre_json if pre_json else raw.strip(),
                "mood": "neutral",
                "suggested_action": None,
                "memories": [],
            }

        # ─────────────────────────────────────────────────────────────
        # VALIDACIONES
        # ─────────────────────────────────────────────────────────────
        if parsed.get("mood") not in _VALID_MOODS:
            parsed["mood"] = "neutral"

        message_clean = re.sub(r'\[EJERCICIO:\s*\w+\]', '', str(parsed.get("message", ""))).strip()
        # Capa 3: eliminar cualquier residuo del formato JSON pegado al final del mensaje
        # 1) bloques markdown tipo ```json o ``` que el modelo a veces agrega
        message_clean = re.sub(r'\s*```[\s\S]*$', '', message_clean).strip()
        # 2) JSON crudo (sin requerir whitespace antes del '{', cubre casos como "Hola.{...")
        message_clean = re.sub(r'\{[\s\S]*$', '', message_clean).strip()

        return {
            "message":          message_clean,
            "mood":             parsed["mood"],
            "suggested_action": parsed.get("suggested_action"),
            "memories":         _normalizar_memories(parsed),
            # Metadata operativa para logging (chat_router la lee y no la
            # incluye en la respuesta HTTP). Nunca contenido de la conversación.
            "_llm": {
                "provider": proveedor_usado,
                "model": modelo_usado,
                "fallback": bool(intento_usado) if intento_usado is not None else None,
                "ok": True,
                "latency_ms": latencia_ms,
            },
        }

    def generate_response_stream(
        self,
        conversation: List[ChatMessage],
        system_prompt: str,
        *,
        max_tokens_base: int = 600,
        extra_body: Optional[dict] = None,
        modo_llamada: bool = False,
    ):
        """Generador para el modo streaming. Va devolviendo tuplas:

            ("mensaje", texto_parcial)  — pedacitos del mensaje, EN ORDEN, listos para concatenar
            ("metadata", dict)          — una sola vez, al final: {"mood", "suggested_action", "memories"}

        Diferencias a propósito respecto de generate_response (ver
        docs/plan_streaming_voz.md secciones 3 y 3.4):
          - No fuerza response_format=json_object: le pedimos al modelo (vía
            _INSTRUCCION_FORMATO_STREAMING) que mande el mensaje en texto
            plano PRIMERO y recién después un JSON compacto con la metadata.
            Todo lo que llega antes del primer '{' se trata como mensaje;
            de ahí en más se acumula como el JSON de metadata.
          - El fallback de proveedor (primario → backup) solo se intenta si
            el error pasa ANTES de emitir el primer pedacito de texto. Si el
            stream se corta a mitad de camino, no se reintenta con otro
            proveedor (mostraría un mensaje "Frankenstein" de dos estilos) —
            se corta ahí con una metadata neutra de cortesía.

        `modo_llamada=True` (solo lo usa /chat/stream cuando lo llama la
        llamada de voz, no el chat escrito) suma _INSTRUCCION_MODO_LLAMADA:
        techo de extensión pensado para que se hable, no para que se lea.
        """
        instrucciones = _INSTRUCCION_FORMATO_STREAMING
        if modo_llamada:
            instrucciones += _INSTRUCCION_MODO_LLAMADA
        system_prompt_streaming = system_prompt + instrucciones

        ultimo_error = None
        for i, (cliente, proveedor, modelo) in enumerate(self._targets()):
            ya_emitio_algo = False
            json_crudo: List[str] = []
            vimos_json = False
            inicio_intento = time.perf_counter()
            try:
                stream = cliente.chat.completions.create(
                    model=modelo,
                    temperature=0.7,
                    max_tokens=max_tokens_for_provider(max_tokens_base, proveedor, modelo),
                    stream=True,
                    messages=[
                        {"role": "system", "content": system_prompt_streaming},
                        *conversation,
                    ],
                    extra_body=(extra_body if extra_body is not None else extra_body_for(proveedor, modelo)),
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content or ""
                    if not delta:
                        continue
                    ya_emitio_algo = True
                    if not vimos_json:
                        idx = delta.find("{")
                        if idx == -1:
                            yield ("mensaje", delta)
                        else:
                            if delta[:idx]:
                                yield ("mensaje", delta[:idx])
                            json_crudo.append(delta[idx:])
                            vimos_json = True
                    else:
                        json_crudo.append(delta)

                if i > 0:
                    print(f"ℹ️ LLM stream: respondió el modelo de backup ({proveedor or '?'}: {modelo})")
                metadata = _parsear_metadata_streaming("".join(json_crudo))
                metadata["_llm"] = {
                    "provider": proveedor, "model": modelo, "fallback": i > 0,
                    "ok": True, "cut": False,
                    "latency_ms": round((time.perf_counter() - inicio_intento) * 1000, 1),
                }
                yield ("metadata", metadata)
                return  # este proveedor terminó bien -> no se prueban los siguientes

            except Exception as e:
                ultimo_error = e
                latencia_intento_ms = round((time.perf_counter() - inicio_intento) * 1000, 1)
                if ya_emitio_algo:
                    print(f"⚠️ LLM stream: se cortó a mitad de camino ({proveedor or '?'}: {modelo}): {e}")
                    yield ("metadata", {
                        "mood": _FALLBACK_RESPONSE["mood"],
                        "suggested_action": _FALLBACK_RESPONSE["suggested_action"],
                        "memories": _FALLBACK_RESPONSE["memories"],
                        "_llm": {
                            "provider": proveedor, "model": modelo, "fallback": i > 0,
                            "ok": False, "cut": True, "latency_ms": latencia_intento_ms,
                        },
                    })
                    return
                print(f"⚠️ LLM stream error con {proveedor or '?'}: {modelo}: {e}")
                # sigue probando el próximo target del for

        # Se agotaron todos los targets sin que ninguno llegara a emitir nada.
        print(f"⚠️ LLM stream: fallaron todos los modelos. Último error: {ultimo_error}")
        yield ("mensaje", _FALLBACK_RESPONSE["message"])
        yield ("metadata", {
            "mood": _FALLBACK_RESPONSE["mood"],
            "suggested_action": _FALLBACK_RESPONSE["suggested_action"],
            "memories": _FALLBACK_RESPONSE["memories"],
            "_llm": {"provider": None, "model": None, "fallback": None, "ok": False, "cut": False, "latency_ms": None},
        })


# Instrucción de formato agregada SOLO a la llamada de streaming (no toca
# numa_prompt.py). Reemplaza el contrato "todo un JSON" por "mensaje en texto
# plano primero, JSON compacto de metadata después" — necesario porque
# response_format=json_object no es compatible con emitir texto libre antes
# del '{' (ver docs/plan_streaming_voz.md sección 3.2).
_INSTRUCCION_FORMATO_STREAMING = """

FORMATO DE RESPUESTA (modo streaming — reemplaza el formato JSON de arriba):
Escribí PRIMERO el mensaje para la persona, en texto plano y natural, tal cual se lo dirías en voz alta. Sin comillas, sin llaves, sin JSON, sin markdown.
Cuando termines el mensaje, dejá una línea en blanco y escribí SOLO un JSON compacto de una línea con esta forma exacta:
{"mood": "...", "suggested_action": ..., "memories": [...]}
Usá los mismos valores posibles de mood/suggested_action/memories ya explicados arriba. No repitas el mensaje adentro de ese JSON — ahí van solo mood, suggested_action y memories.
"""

# Solo para el modo llamada (voz), NO para el chat escrito en streaming — los
# dos pasan por generate_response_stream, así que esto se suma aparte y
# condicional (ver modo_llamada arriba), no adentro de numa_prompt.py.
#
# M03_longitud_y_estructura (numa_prompt.py) ya pide corto por defecto y
# permite extenderse si piden explicación/detalle — esto NO lo reemplaza, le
# agrega un TECHO pensado para voz: en una llamada de verdad nadie suelta un
# monólogo de diez oraciones aunque le hayas pedido que cuente algo largo,
# lo dice en tandas cortas. Sin techo, "explicame X" podía generar un párrafo
# entero de una — bien para leer, rarísimo para escuchar.
_INSTRUCCION_MODO_LLAMADA = """

MODO LLAMADA (estás hablando por voz, en vivo, no escribiendo):
Por defecto 1-2 oraciones, como siempre. Si te piden que expliques, cuentes o
detalles algo, podés extenderte hasta un máximo de 5 oraciones — nunca más
que eso, ni siquiera si el tema da para más: en una llamada real nadie dice
un párrafo entero de corrido, se habla en tandas y se deja lugar para que el
otro responda. Si hay más para decir, dejalo para el próximo turno en vez de
volcarlo todo junto.
"""


def _parsear_metadata_streaming(json_crudo: str) -> dict:
    """Parsea el JSON de metadata (mood/suggested_action/memories) que llega
    después del mensaje en modo streaming. Reusa _reparar_json_truncado por
    si el stream se cortó justo en medio de ese JSON de cierre (mismo
    mecanismo que ya protege al modo no-streaming)."""
    parsed = None
    texto = (json_crudo or "").strip()
    if texto:
        try:
            parsed = json.loads(_reparar_json_truncado(texto))
        except json.JSONDecodeError:
            parsed = None
    if not isinstance(parsed, dict):
        parsed = {}

    mood = parsed.get("mood") if parsed.get("mood") in _VALID_MOODS else "neutral"
    return {
        "mood": mood,
        "suggested_action": parsed.get("suggested_action"),
        "memories": _normalizar_memories(parsed),
    }


def _recuperar_failed_generation(e) -> Optional[str]:
    """Extrae `failed_generation` de un error de Groq (json_validate_failed).

    Cuando el modelo (sobre todo gpt-oss) devuelve texto que no es JSON válido,
    Groq tira 400 pero incluye el texto generado en error.failed_generation.
    Lo devolvemos para parsearlo/rescatarlo en vez de perder la respuesta.
    Devuelve None si el error no trae ese campo (otro tipo de fallo → fallback).
    """
    # 1) openai SDK suele exponer el body parseado en e.body
    for body in (getattr(e, "body", None), getattr(e, "response", None)):
        data = body
        if hasattr(body, "json"):
            try:
                data = body.json()
            except Exception:
                data = None
        if isinstance(data, dict):
            fg = data.get("failed_generation")
            if not fg and isinstance(data.get("error"), dict):
                fg = data["error"].get("failed_generation")
            if fg:
                return str(fg)
    # 2) último recurso: rascar el string del error
    m = re.search(r"failed_generation['\"]?\s*[:=]\s*['\"](.+?)['\"]\s*\}?\s*$", str(e), re.DOTALL)
    return m.group(1) if m else None


def _reparar_json_truncado(texto: str) -> str:
    """
    Cierra un JSON que fue cortado por el límite de tokens.
    Cuenta comillas y llaves abiertas y las cierra.
    """
    try:
        json.loads(texto)
        return texto  # ya es válido
    except json.JSONDecodeError:
        pass

    reparado = texto.rstrip()

    # Detectar si hay un string abierto (comillas impares no escapadas)
    in_string = False
    escaped = False
    for ch in reparado:
        if escaped:
            escaped = False
            continue
        if ch == '\\':
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string

    if in_string:
        reparado += '"'

    # Cerrar llaves pendientes
    open_braces = reparado.count("{") - reparado.count("}")
    if open_braces > 0:
        reparado += "}" * open_braces

    return reparado