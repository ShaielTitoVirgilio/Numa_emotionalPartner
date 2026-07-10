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

from app.core.llm import get_client, get_router_model, reasoning_extra_body, max_tokens_for

_TIMEOUT_SECONDS = 4

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
  - explicita: ideación/método/autolesión clara y actual sobre SÍ MISMO/A ("me quiero matar", "cómo me corto"), o pregunta directa sobre cómo dañarse.
  - implicita: desesperanza fuerte, despedidas, "no tiene sentido seguir", "ya no puedo más", "no es posible" dicho con resignación pesada, o preguntar por la ideación suicida en abstracto sin declararla propia todavía. TAMBIÉN cuenta como implicita cuando la persona DECLARA que está con depresión / muy deprimida / en un pozo, sobre todo si aparece junto a aislamiento o soledad ("estoy deprimido y solo", "tengo depresión y me dejan solo"): una depresión declarada merece el registro de cuidado aunque no haya ideación explícita.
  - none: sin señales de riesgo. Un bajón puntual, tristeza pasajera o estar "medio triste" NO es implicita por sí solo; implicita pide o desesperanza, o depresión declarada, o riesgo real.
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

    try:
        bloque = _formatear_conversacion(conversation)
        if not bloque.strip():
            return dict(_RESULTADO_VACIO)

        modelo = get_router_model()
        resp = get_client("groq").chat.completions.create(
            model=modelo,
            temperature=0.0,
            # Los modelos qwen/gpt-oss habilitados en la org son de razonamiento:
            # el reasoning cuenta contra max_tokens. reasoning_extra_body apaga el
            # thinking (effort="none") y max_tokens_for suma headroom, así el JSON
            # no se trunca (era el 400 que daba qwen3.6-27b sin estos ajustes).
            max_tokens=max_tokens_for(120, modelo),
            timeout=_TIMEOUT_SECONDS,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": _PROMPT.format(conversacion=bloque),
            }],
            extra_body=reasoning_extra_body(modelo),
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return _normalizar(data)
    except Exception as e:
        # Fail-safe: el ruteo por keywords sigue funcionando solo.
        print(f"⚠️ Context router no disponible (se usa ruteo por keywords): {e}")
        return dict(_RESULTADO_VACIO)


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
