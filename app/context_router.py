# app/context_router.py
"""
Clasificador de contexto (capa 2 del ruteo de módulos).

El ruteo por keywords (`seleccionar_modulos` + los `_detectar_*` de numa_prompt)
es rápido y gratis, pero frágil: solo activa un módulo si el mensaje contiene
las frases exactas de una lista. El lenguaje natural nunca entra completo en una
lista, así que hay contextos donde el módulo correcto NO se carga:
  - "no tengo fecha" / "solo vine a avisarte" → desborde/riesgo que no matchea nada
  - "¿cómo hago con la ideación suicida?"     → pregunta meta, sin frase en 1ª persona
  - un usuario que describe su angustia con palabras propias

Este módulo pasa los últimos mensajes por un LLM chico y barato que devuelve un
vocabulario CONTROLADO (no elige IDs de módulos: clasifica el contexto). El
resultado se MERGEA con las keywords en `seleccionar_modulos`: nunca resta señal,
solo rellena los huecos que el léxico no vio.

FAIL-SAFE POR DISEÑO: ante cualquier error, timeout o JSON inválido devuelve
`{"ok": False}` y el caller sigue con el ruteo por keywords de siempre. El
clasificador solo puede AGREGAR contexto; si se cae, el sistema queda igual que hoy.

IMPORTANTE (asimetría de crisis): este clasificador puede ESCALAR el riesgo hacia
los módulos de crisis del LLM principal (M19/M20), pero NO dispara la respuesta
hardcodeada de emergencia. Ese bypass sigue gobernado por keywords + crisis_verifier
(alta precisión). Acá solo subimos el crisis_score para que el prompt active la
contención — nunca lo bajamos.
"""

import json
import time

from app.core.config import config
from app.core.llm import get_context_router_target, extra_body_for, max_tokens_for_provider

# Presupuesto de la clasificación. OJO: `timeout` del SDK de OpenAI es POR
# INTENTO, no para la operación completa — el techo real es
# timeout × (reintentos + 1) + backoff.
#
# Con los defaults del cliente (max_retries=2) esto NO acotaba nada: una
# clasificación podía tomar 3 intentos y ~13s sin disparar nunca el fail-safe,
# porque el except solo corre cuando fallan TODOS los intentos. En el chat
# escrito eso es espera pura del usuario (el turno bloquea en fut_router.result());
# corre en paralelo al LLM principal, así que no suma latencia al turno,
# pero si tarda de más la señal de riesgo llega tarde o no llega.
#
# Por qué UN SOLO INTENTO y no un reintento (decidido 2026-09-08 con datos):
# el reintento sirve —medido contra producción, de 81 clasificaciones las 2
# que se pasaron de 4s fueron recuperadas por él, o sea ~2.5% de turnos que si
# no caían a keywords— pero se paga donde más se nota. El router corre en
# paralelo al LLM principal (~2s), así que un reintento que arranca recién a
# los 4s hace que /chat, que lo espera bloqueado, sume hasta ~4s al turno del
# usuario. Se eligió el techo firme: 4 segundos y si no llegó, no llegó.
#
# Lo que se acepta a cambio: ese ~2.5% de turnos pierde la capa 2 y se rutea
# solo por keywords. Es una degradación real y conocida, no un empate — pero
# acotada, y el camino de emergencia (keywords + crisis_verifier, con la
# respuesta hardcodeada y los teléfonos) NO depende de esto y sigue intacto.
#
# Contexto de la medición anterior, que sigue valiendo: 2026-08-18 sobre 75
# clasificaciones, qwen3-32b daba mediana 1750ms y p90 3765ms. Bajar el
# timeout por intento para que entren dos adentro de 4s mataría entre el 25% y
# el 50% de los intentos SANOS, así que partir el presupuesto tampoco servía.
_TIMEOUT_SECONDS = 4   # por intento
_REINTENTOS = 0        # un solo intento: techo firme de 4s

# Vocabularios cerrados: tienen que coincidir con lo que espera el merge en
# seleccionar_modulos(). Si agregás un valor acá, agregá el mapeo allá.
_ESTADOS_VALIDOS = {
    "triste_vacio", "ansioso", "abrumado", "enojado",
    "duelo", "buenas_noticias", "metas", "neutral",
}
_RIESGOS_VALIDOS = {"none", "implicita", "explicita"}

_RESULTADO_VACIO = {
    "ok": False,
    "estado_emocional": "neutral",
    "senal_riesgo": "none",
    "pide_ejercicio": False,
    "pregunta_app": False,
    "pregunta_capacidades": False,
}

_PROMPT = """Sos un clasificador de contexto para Numa, una app de apoyo emocional en español rioplatense. NO le respondés al usuario: solo etiquetás el contexto de la charla para decidir qué guía interna activar.

Te paso los últimos mensajes de la conversación. Mirá TODO el contexto (no solo el último mensaje): el tono acumulado, lo que se viene hablando y cómo viene la persona.

Clasificá con este JSON exacto:

{{
  "estado_emocional": uno de ["triste_vacio","ansioso","abrumado","enojado","duelo","buenas_noticias","metas","neutral"],
  "senal_riesgo": uno de ["none","implicita","explicita"],
  "pide_ejercicio": true/false,
  "pregunta_app": true/false,
  "pregunta_capacidades": true/false
}}

Guía:
- estado_emocional: el estado dominante de la persona AHORA. "neutral" si es charla informativa o sin carga emocional clara.
  - triste_vacio: tristeza, vacío, desánimo, soledad, desesperanza.
  - ansioso: ansiedad, nervios, preocupación, estrés agudo, insomnio.
  - abrumado: saturación, "no doy más", demasiadas cosas encima.
  - enojado: bronca, injusticia, frustración con alguien/algo.
  - duelo: SOLO si hay una pérdida concreta (se murió alguien, una mascota, una relación que terminó). NO uses "duelo" para tristeza general.
  - buenas_noticias: logro, alegría, algo que salió bien.
  - metas: planes, proyectos, decisiones a futuro sin carga emocional negativa fuerte.
- senal_riesgo: riesgo de autolesión o suicidio.
  - explicita: ideación/método/autolesión clara y actual sobre SÍ MISMO/A ("me quiero matar", "cómo me corto"), o pregunta directa sobre cómo dañarse. TAMBIÉN es explicita un PLAN CONCRETO CON HORIZONTE TEMPORAL sobre sí mismo/a, aunque no nombre el acto ni el método ("ya tengo todo listo para hacerlo esta noche", "el viernes cuando no haya nadie en casa"): que no diga la palabra no lo hace menos inminente — un plan con fecha es la señal más urgente que existe. OJO: esto vale solo cuando lo que se planea es dañarse. Si la charla deja claro que el plan es otra cosa (una mudanza, una cena, un viaje, una entrega), es "none" — un plan con fecha en un contexto inocuo es simplemente un plan.
  - implicita: desesperanza fuerte, despedidas, "no tiene sentido seguir", "ya no puedo más", "no es posible" dicho con resignación pesada, o preguntar por la ideación suicida en abstracto sin declararla propia todavía. TAMBIÉN cuenta como implicita cuando la persona DECLARA que está con depresión / muy deprimida / en un pozo, sobre todo si aparece junto a aislamiento o soledad ("estoy deprimido y solo", "tengo depresión y me dejan solo"): una depresión declarada merece el registro de cuidado aunque no haya ideación explícita.
  - none: sin señales de riesgo. Un bajón puntual, tristeza pasajera o estar "medio triste" NO es implicita por sí solo; implicita pide o desesperanza, o depresión declarada, o riesgo real.
  NO ES RIESGO, por más que aparezca la palabra — mirá DE QUÉ habla la frase, no qué palabra usa:
    · HIPÉRBOLE / modismo rioplatense: "me quiero morir de vergüenza", "casi me muero de risa", "me mato estudiando", "del embole me tiro por la ventana". Hablan de vergüenza, risa, cansancio o aburrimiento — no de morirse. Son "none", incluso las que nombran un método.
    · TERCEROS: quien está en riesgo es otra persona ("mi hermano tiene ideación suicida"). El que escribe está pidiendo cómo acompañar, no está en riesgo: "none".
    · FICCIÓN / ESTUDIO: escribir un cuento o un guion, o entender el tema para la facultad o el trabajo. Hay distancia, no es sobre sí mismo/a: "none".
    Regla corta: si el sujeto en riesgo NO es quien escribe, o el registro es de chiste, ficción o estudio, es "none".
  ANTE LA DUDA entre "implicita" y "none", elegí "implicita". Es preferible activar contención de más. Mirá el CONTEXTO: en una charla que ya viene pesada (medicación, malestar, ganas de abandonar tratamiento), un mensaje corto y resignado puede ser señal implícita.
- pide_ejercicio: la persona pide (o le vendría bien y lo insinúa) una técnica de respiración, meditación, yoga o relajación para calmarse.
- pregunta_app: pregunta cómo USAR la app o una función concreta de la interfaz (agrandar la letra, modo oscuro, mandar audios, borrar recuerdos, cerrar/eliminar cuenta). NO es esto pedir recomendaciones (series, libros) ni preguntar qué sabe hacer Numa en general.
- pregunta_capacidades: pregunta qué puede HACER Numa además de escuchar/chatear (qué funciones extra tiene, para qué más sirve, "¿qué más podés hacer?", "¿solo escuchás?").

EJEMPLOS (mirá cómo el contexto cambia la lectura):

Mensajes:
Usuario: no me siento bien con los medicamentos y los quiero dejar
Numa: ¿hablaste con tu médico?
Usuario: no es posible
Salida: {{"estado_emocional":"abrumado","senal_riesgo":"implicita","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":false}}

Mensajes:
Usuario: cómo hago con la ideación suicida?
Salida: {{"estado_emocional":"triste_vacio","senal_riesgo":"explicita","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":false}}

Mensajes:
Usuario: hola
Numa: Hola. ¿Cómo venís?
Usuario: estoy con depresión, mis viejos se separaron y me dejan mucho solo en casa
Salida: {{"estado_emocional":"triste_vacio","senal_riesgo":"implicita","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":false}}

Mensajes:
Numa: ¿Cómo estás ahora?
Usuario: ya tengo todo listo para hacerlo esta noche
Salida: {{"estado_emocional":"triste_vacio","senal_riesgo":"explicita","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":false}}

Mensajes:
Numa: ¿Cómo venís con la mudanza?
Usuario: ya tengo todo listo, lo hago mañana temprano
Salida: {{"estado_emocional":"neutral","senal_riesgo":"none","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":false}}

Mensajes:
Usuario: del embole que tengo en la oficina te juro que me tiro por la ventana
Salida: {{"estado_emocional":"neutral","senal_riesgo":"none","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":false}}

Mensajes:
Usuario: estoy escribiendo un cuento donde el personaje se suicida, ¿cómo lo hago creíble?
Salida: {{"estado_emocional":"neutral","senal_riesgo":"none","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":false}}

Mensajes:
Usuario: qué serie me recomendás para el finde?
Salida: {{"estado_emocional":"neutral","senal_riesgo":"none","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":false}}

Mensajes:
Usuario: hay algo más que puedas hacer además de escucharme?
Salida: {{"estado_emocional":"neutral","senal_riesgo":"none","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":true}}

Mensajes:
Usuario: se murió mi perro ayer, lo tuve 14 años
Salida: {{"estado_emocional":"duelo","senal_riesgo":"none","pide_ejercicio":false,"pregunta_app":false,"pregunta_capacidades":false}}

Ahora clasificá esta conversación (el último mensaje es el más reciente):
{conversacion}

Respondé SOLO con el JSON, sin texto extra."""


def _formatear_conversacion(conversation: list, max_mensajes: int = 6) -> str:
    """Arma el bloque de conversación para el prompt: últimos N mensajes,
    etiquetados por rol, recortados para no inflar tokens."""
    recientes = conversation[-max_mensajes:]
    lineas = []
    for m in recientes:
        # Soporta tanto objetos con .role/.content como dicts.
        rol = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
        contenido = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
        if not rol or not contenido:
            continue
        etiqueta = "Usuario" if rol == "user" else "Numa"
        lineas.append(f"{etiqueta}: {str(contenido)[:600]}")
    return "\n".join(lineas)


def _normalizar(data: dict) -> dict:
    """Valida y clampea la salida cruda del LLM contra los vocabularios cerrados.
    Cualquier valor fuera de rango cae al default seguro."""
    estado = data.get("estado_emocional")
    riesgo = data.get("senal_riesgo")
    return {
        "ok": True,
        "estado_emocional": estado if estado in _ESTADOS_VALIDOS else "neutral",
        "senal_riesgo": riesgo if riesgo in _RIESGOS_VALIDOS else "none",
        "pide_ejercicio": bool(data.get("pide_ejercicio")),
        "pregunta_app": bool(data.get("pregunta_app")),
        "pregunta_capacidades": bool(data.get("pregunta_capacidades")),
    }


def resultado_vacio() -> dict:
    """El resultado neutro (ok=False): el mismo que devuelve clasificar_contexto()
    ante cualquier error, o sea "no hay capa semántica, ruteá solo por keywords".

    Es público para que un caller pueda SALTEAR el router a propósito (hoy: el
    el fail-safe: ante cualquier error se rutea solo por keywords, sin pagar
    hablada) sin duplicar la forma del dict ni tener que importar la constante
    privada. Devuelve una copia: el caller le hace .pop() encima.
    """
    return dict(_RESULTADO_VACIO)


def clasificar_contexto(conversation: list) -> dict:
    """Clasifica el contexto de la conversación con el LLM chico.

    Devuelve un dict con:
      ok                    → True si la clasificación es válida (False = usar solo keywords)
      estado_emocional      → estado dominante (vocabulario cerrado)
      senal_riesgo          → none | implicita | explicita
      pide_ejercicio        → bool
      pregunta_app          → bool
      pregunta_capacidades  → bool

    Nunca lanza: ante cualquier problema devuelve el resultado vacío con ok=False.
    """
    if not conversation:
        return dict(_RESULTADO_VACIO)

    # Metadata operativa para logging (chat_router la suma a "chat_turn" como
    # router_provider/router_model). Se resuelve ANTES del try para que quede
    # disponible incluso si la llamada al LLM falla o da timeout — ahí es
    # justo cuando más importa saber qué proveedor/modelo fue el lento.
    proveedor = modelo = None
    inicio = time.perf_counter()

    def _con_tiempo(resultado: dict) -> dict:
        latencia = round((time.perf_counter() - inicio) * 1000, 1)
        resultado["_router"] = {
            "provider": proveedor, "model": modelo,
            "latency_ms": latencia,
            # Una clasificación EXITOSA por encima del timeout por intento
            # implica que hubo reintento: un intento suelto que se pasa muere
            # con APITimeoutError. Sin esta marca, en el log no se distingue
            # "el modelo tardó" de "se cortó, reintentó y la segunda entró",
            # que es justo lo que hacía falta saber para elegir el timeout.
            "reintento": latencia > _TIMEOUT_SECONDS * 1000,
        }
        return resultado

    try:
        bloque = _formatear_conversacion(conversation)
        if not bloque.strip():
            return _con_tiempo(dict(_RESULTADO_VACIO))

        cliente, proveedor, modelo = get_context_router_target()
        # Cliente DERIVADO solo para el router: with_options devuelve una copia
        # con su propia política de reintentos, así que el chat principal y el
        # verificador de crisis (que comparten el cliente cacheado de
        # core/llm.py) siguen con los defaults del SDK.
        cliente = cliente.with_options(max_retries=_REINTENTOS)
        extra = extra_body_for(proveedor, modelo)
        if proveedor == "openrouter" and config.CONTEXT_ROUTER_OPENROUTER_PROVIDERS:
            pinned = [p.strip() for p in config.CONTEXT_ROUTER_OPENROUTER_PROVIDERS.split(",") if p.strip()]
            extra = {**extra, "provider": {"only": pinned}}
        resp = cliente.chat.completions.create(
            model=modelo,
            temperature=0.0,
            # El reasoning (si el modelo lo tiene) cuenta contra max_tokens.
            # extra_body_for/max_tokens_for_provider ya saben qué mandarle a
            # cada proveedor (Groq por familia, OpenRouter con reasoning.effort)
            # para que el JSON no se trunque.
            max_tokens=max_tokens_for_provider(120, proveedor, modelo),
            timeout=_TIMEOUT_SECONDS,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": _PROMPT.format(conversacion=bloque),
            }],
            extra_body=extra,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return _con_tiempo(_normalizar(data))
    except Exception as e:
        # Fail-safe: el ruteo por keywords sigue funcionando solo.
        print(f"⚠️ Context router no disponible (se usa ruteo por keywords): {e}")
        return _con_tiempo(dict(_RESULTADO_VACIO))


# Mapeo score de crisis por señal del router. Espeja los umbrales de
# seleccionar_modulos: >=0.60 → M20 explícita | >=0.35 → M19 implícita.
_SCORE_RIESGO_ROUTER = {
    "explicita": 0.60,
    "implicita": 0.35,
    "none": 0.0,
}


def score_riesgo_router(senal_riesgo: str) -> float:
    """Traduce la señal de riesgo del router a un crisis_score comparable con
    el de crisis_detector, para poder tomar el máximo de ambos."""
    return _SCORE_RIESGO_ROUTER.get(senal_riesgo, 0.0)
