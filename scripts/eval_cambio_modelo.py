"""
Eval de CANDIDATOS A REEMPLAZAR CHAT_MODEL (hoy openai/gpt-5.6-luna).

La pregunta que responde este script es la única que importa antes de tocar
CHAT_MODEL: "¿el modelo barato rompe algo, empeora la respuesta o tarda más?".
Un modelo más barato que falle 1 de cada 20 turnos no es más barato.

QUÉ MIDE, TODO EN LA MISMA LLAMADA (por eso es barato de correr)
  1. CONTRATO  — el JSON que el backend espera. Lo mira CRUDO, antes de las
     redes de contención de LLMClient: si el modelo manda mood="triste",
     LLMClient lo pisa con "neutral" y el turno "parece" sano mientras el
     usuario recibe un mood equivocado. Acá eso cuenta como falla.
       · json.loads directo (Capa 1: response_format=json_object)
       · mood ∈ _VALID_MOODS
       · suggested_action ∈ IDs reales del catálogo (o null)
       · memories: lista de 0–2, category del vocabulario, priority int 1–5
       · event: {title, date} con date ISO YYYY-MM-DD
  2. ESTILO    — las reglas de voz de Numa: voseo (no tuteo), sin eco del
     usuario, sin comillas, sin "che", largo de mensaje.
  3. LATENCIA  — ms de la llamada real, no-streaming (= chat escrito).
     Mediana y p90 en RONDA ROBIN: se alterna modelo por modelo en cada
     vuelta para que un bache de red no se lo coma un solo candidato.
  4. COSTO     — usage real (prompt / cached / completion) × precio de
     OpenRouter → USD por 1000 turnos.

QUÉ NO MIDE
  · TTFT / velocidad de streaming (modo llamada) → scripts/bench_modelos_ttft.py
  · Seguridad del router de contexto              → eval_seguridad_router.py
  · El juicio humano sobre "¿esta respuesta está buena?". El CSV de salida
    queda ordenado caso por caso, lado a lado, justamente para leerlo.

SOBRE EL PIN DE PROVEEDOR (importante para DeepSeek)
  gpt-5.6-luna corre en 2 backends (OpenAI/Azure) y el código ya los fija a
  OpenAI por la caché (ver core/llm.py). DeepSeek V4 Flash tiene ~20
  proveedores en OpenRouter, con quantización MEZCLADA (fp4, fp8, unknown):
  sin pin, cada turno es una lotería de calidad, latencia y caché. Por eso
  cada candidato se declara con su pin y se puede correr también "sin pin"
  para ver la dispersión.

Uso:
    venv/bin/python scripts/eval_cambio_modelo.py                 # suite dirigida + 15 reales
    venv/bin/python scripts/eval_cambio_modelo.py 25              # 25 mensajes reales
    venv/bin/python scripts/eval_cambio_modelo.py 15 luna,ds0423  # solo esos candidatos
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import statistics
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.llm import get_client, max_tokens_for_provider
from app.llm_client import (
    _VALID_MOODS,
    _FALLBACK_RESPONSE,
    _reparar_json_truncado,
    strip_reasoning,
)
from app.numa_prompt import construir_prompt
from test_modelo import _TUTEO, _cargar_mensajes, _eco

HOY = dt.date(2026, 8, 18)  # fijo: los casos con fechas relativas deben ser reproducibles

# ══════════════════════════════════════════════════════════════
# Candidatos
# ══════════════════════════════════════════════════════════════
# precio_* en USD por token (OpenRouter, 2026-08-18).
# provider: pin de proveedor. Ver nota de arriba — sin pin, DeepSeek no es
# comparable consigo mismo entre dos corridas.
CANDIDATOS: Dict[str, dict] = {
    "luna": {
        "modelo": "openai/gpt-5.6-luna",
        "provider": {"only": ["openai"]},          # idéntico a producción hoy
        "precio_in": 0.0000002, "precio_cache": 0.00000002, "precio_out": 0.0000012,
    },
    "ds0423": {
        "modelo": "deepseek/deepseek-v4-flash",     # "DeepSeek V4 Flash 0423"
        "provider": {"only": ["deepinfra"], "quantizations": ["fp8"]},
        "precio_in": 0.00000009, "precio_cache": 0.000000018, "precio_out": 0.00000018,
    },
    "ds0731": {
        "modelo": "deepseek/deepseek-v4-flash-0731",
        "provider": {"only": ["deepinfra"], "quantizations": ["fp8"]},
        "precio_in": 0.00000008, "precio_cache": 0.000000016, "precio_out": 0.00000016,
    },
    # Variantes sin pin: sirven para mostrar cuánto se mueve el resultado
    # cuando OpenRouter elige el proveedor. No son candidatos a producción.
    "ds0423_sinpin": {
        "modelo": "deepseek/deepseek-v4-flash",
        "provider": None,
        "precio_in": 0.0000000826, "precio_cache": 0.00000001652, "precio_out": 0.0000001652,
    },
    "ds0731_sinpin": {
        "modelo": "deepseek/deepseek-v4-flash-0731",
        "provider": None,
        "precio_in": 0.00000014, "precio_cache": 0.000000028, "precio_out": 0.00000028,
    },
}
POR_DEFECTO = ["luna", "ds0423", "ds0731"]

# ══════════════════════════════════════════════════════════════
# Vocabularios del contrato (copiados del prompt y del router a propósito:
# si alguien cambia uno y no el otro, este eval tiene que gritar)
# ══════════════════════════════════════════════════════════════
EJERCICIOS_VALIDOS = {
    "respiracion_box", "respiracion_478", "respiracion_balance", "respiracion_suspiro",
    "respiracion_exhale", "respiracion_activante",
    "meditacion_bodyscan", "meditacion_mindfulness", "meditacion_lugar_seguro",
    "meditacion_rio", "meditacion_metta", "meditacion_stop",
    "yoga_cuello", "yoga_ansiedad",
    "lectura_motivacion", "lectura_diaria", "lectura_espiritual", "lectura_autocompasion",
}
CATEGORIAS_VALIDAS = {
    "trabajo", "estudios", "relaciones", "salud", "identidad",
    "emocional", "hobbies", "vida_cotidiana", "otro",
}
_RE_FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_CHE = re.compile(r"\bche\b", re.IGNORECASE)

# ══════════════════════════════════════════════════════════════
# Suite dirigida: un caso por comportamiento que el backend DEPENDE de.
# `espera` son chequeos extra propios del caso (además de los generales).
# ══════════════════════════════════════════════════════════════
CASOS: List[dict] = [
    {
        "id": "memoria_simple",
        "mensaje": "Ayer empecé un laburo nuevo en una agencia de diseño y estoy con los nervios de punta.",
        "kwargs": {},
        "espera": {"min_memorias": 1},
    },
    {
        "id": "evento_con_fecha",
        "mensaje": "El jueves tengo una charla con el decano y me está matando la ansiedad.",
        "kwargs": {},
        # jueves siguiente al 2026-08-18 (martes) = 2026-08-20
        "espera": {"min_memorias": 1, "evento_fecha": "2026-08-20"},
    },
    {
        "id": "sin_memoria",
        "mensaje": "jajaja sí, obvio",
        "kwargs": {"num_interacciones": 5},
        "espera": {"max_memorias": 0},
    },
    {
        "id": "pide_ejercicio",
        "mensaje": "¿Tenés algo para bajar la ansiedad ahora?",
        "kwargs": {"num_interacciones": 4, "mood_actual": "anxious"},
        "espera": {},
    },
    {
        "id": "acepta_ejercicio",
        "mensaje": "dale, hagamos esa",
        "kwargs": {
            "num_interacciones": 6,
            "mood_actual": "anxious",
            "historial_reciente": [
                {"role": "user", "content": "estoy re acelerada, no me puedo quedar quieta"},
                {"role": "assistant", "content": "¿Querés que hagamos la respiración box, un minuto, ahora?"},
            ],
        },
        "espera": {"exige_ejercicio": True},
    },
    {
        "id": "crisis_media_desborde",
        "mensaje": "No doy más, no puedo con nada, siento que me estoy hundiendo y no veo salida.",
        "kwargs": {"crisis_score": 0.5, "mood_actual": "overwhelmed"},
        "espera": {"sin_ejercicio": True, "mood_en": {"overwhelmed", "sad", "anxious", "stressed"}},
    },
    {
        "id": "post_ejercicio",
        "mensaje": "[Post-ejercicio | Respiración Box] Me sentí un poco mejor pero sigo tensa.",
        "kwargs": {"num_interacciones": 7},
        "espera": {"sin_ejercicio": True},
    },
    {
        "id": "duelo",
        "mensaje": "Se murió mi abuela hace una semana y todavía no sé cómo estar en mi propia casa.",
        "kwargs": {"mood_actual": "sad"},
        "espera": {"mood_en": {"sad", "overwhelmed", "neutral", "calm"}},
    },
    {
        "id": "mensaje_minimo",
        "mensaje": "mal",
        "kwargs": {"num_interacciones": 3},
        "espera": {},
    },
    {
        "id": "mensaje_largo",
        "mensaje": (
            "No sé por dónde empezar. En el trabajo me pasaron a un equipo nuevo sin preguntarme, "
            "mi jefa me dijo que era una oportunidad pero en realidad me sacaron del proyecto que me "
            "gustaba. En casa mi hermano está pasando un momento heavy y siento que soy la única que "
            "banca todo. Encima dormí tres horas y hoy tengo que presentar algo que no preparé. "
            "Y lo peor es que ni siquiera puedo decir que estoy mal porque todos están peor que yo."
        ),
        "kwargs": {"mood_actual": "stressed"},
        "espera": {"min_memorias": 1},
    },
    {
        "id": "checkin_bajo",
        "mensaje": "Hoy vengo arrastrando el día.",
        "kwargs": {"checkin_hoy": 2, "checkin_recien_hecho": True},
        "espera": {},
    },
    {
        "id": "evento_proactivo",
        "mensaje": "Hola, ¿cómo va?",
        "kwargs": {
            "num_interacciones": 12,
            "evento_proactivo": {"event_title": "la charla con el decano", "event_date": "2026-08-18",
                                 "content": "Sofi tiene una charla con el decano", "proximidad": "hoy"},
        },
        "espera": {},
    },
    {
        "id": "trampa_tuteo",
        "mensaje": "¿Tú crees que debería decirle lo que siento o mejor me callo?",
        "kwargs": {"num_interacciones": 4},
        "espera": {},
    },
    {
        "id": "fuera_de_rol",
        "mensaje": "Che, escribime una función en Python que ordene una lista de diccionarios por fecha.",
        "kwargs": {"num_interacciones": 4},
        "espera": {"sin_codigo": True},
    },
]

PERFIL = {"nombre": "Sofi", "edad": 29}
MEMORIAS = [{"content": "Sofi trabaja en una agencia y viene con mucha carga",
             "category": "trabajo", "priority": 3}]


# ══════════════════════════════════════════════════════════════
# Una llamada real, con los MISMOS parámetros que producción
# ══════════════════════════════════════════════════════════════
def _llamar(cliente, cand: dict, system_prompt: str, mensaje: str) -> dict:
    extra_body: Dict[str, Any] = {"reasoning": {"effort": "low"}}
    if cand["provider"]:
        extra_body["provider"] = cand["provider"]

    inicio = time.perf_counter()
    completion = cliente.chat.completions.create(
        model=cand["modelo"],
        temperature=0.7,
        max_tokens=max_tokens_for_provider(600, "openrouter", cand["modelo"]),
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": mensaje}],
        extra_body=extra_body,
    )
    latencia = (time.perf_counter() - inicio) * 1000
    uso = getattr(completion, "usage", None)

    def _leer(obj, campo):
        if obj is None:
            return None
        return obj.get(campo) if isinstance(obj, dict) else getattr(obj, campo, None)

    detalles = _leer(uso, "prompt_tokens_details")
    return {
        "raw": completion.choices[0].message.content or "",
        "latencia_ms": latencia,
        "prompt_tokens": _leer(uso, "prompt_tokens") or 0,
        "cached_tokens": _leer(detalles, "cached_tokens") or 0,
        "completion_tokens": _leer(uso, "completion_tokens") or 0,
        "proveedor_real": getattr(completion, "provider", None),
    }


def _parsear(raw: str) -> tuple[dict | None, bool]:
    """(dict, json_directo). json_directo=False significa que hizo falta la
    red de contención de LLMClient — en producción no rompe, pero es una
    señal de que el modelo no respeta response_format."""
    try:
        return json.loads(raw), True
    except (json.JSONDecodeError, TypeError):
        pass
    for intento in (strip_reasoning(raw or ""), _reparar_json_truncado(strip_reasoning(raw or ""))):
        try:
            d = json.loads(intento)
            if isinstance(d, dict):
                return d, False
        except (json.JSONDecodeError, TypeError):
            continue
    return None, False


# ══════════════════════════════════════════════════════════════
# Validación: contrato + estilo
# ══════════════════════════════════════════════════════════════
def _evaluar_respuesta(caso: dict, r: dict) -> dict:
    fallas: List[str] = []
    parsed, json_directo = _parsear(r["raw"])

    if parsed is None:
        return {"fallas": ["JSON_ILEGIBLE"], "mensaje": "", "mood": "", "accion": "",
                "n_memorias": 0, "json_directo": False}
    if not json_directo:
        fallas.append("JSON_NO_DIRECTO")

    mensaje = str(parsed.get("message") or "").strip()
    mood = parsed.get("mood")
    accion = parsed.get("suggested_action")
    memorias = parsed.get("memories")
    espera = caso.get("espera", {})

    # ── CONTRATO ──────────────────────────────────────────────
    if not mensaje:
        fallas.append("MENSAJE_VACIO")
    if mensaje == _FALLBACK_RESPONSE["message"]:
        fallas.append("FALLBACK")
    if mood not in _VALID_MOODS:
        fallas.append(f"MOOD_INVALIDO({mood})")
    if accion is not None and accion not in EJERCICIOS_VALIDOS:
        fallas.append(f"ACCION_INVALIDA({accion})")

    if memorias is None:
        memorias = []
    if not isinstance(memorias, list):
        fallas.append("MEMORIES_NO_LISTA")
        memorias = []
    if len(memorias) > 2:
        fallas.append(f"MEMORIES_DE_MAS({len(memorias)})")

    fechas_evento = []
    for m in memorias:
        if not isinstance(m, dict):
            fallas.append("MEMORIA_NO_DICT")
            continue
        if not str(m.get("content") or "").strip():
            fallas.append("MEMORIA_SIN_CONTENT")
        if m.get("category") not in CATEGORIAS_VALIDAS:
            fallas.append(f"CATEGORIA_INVALIDA({m.get('category')})")
        p = m.get("priority")
        if not isinstance(p, int) or isinstance(p, bool) or not (1 <= p <= 5):
            fallas.append(f"PRIORITY_INVALIDA({p})")
        ev = m.get("event")
        if ev is not None:
            if not isinstance(ev, dict) or not ev.get("title") or not ev.get("date"):
                fallas.append("EVENTO_MAL_FORMADO")
            elif not _RE_FECHA_ISO.match(str(ev["date"])):
                fallas.append(f"EVENTO_FECHA_NO_ISO({ev['date']})")
            else:
                fechas_evento.append(str(ev["date"]))

    # ── EXPECTATIVAS DEL CASO ─────────────────────────────────
    if "min_memorias" in espera and len(memorias) < espera["min_memorias"]:
        fallas.append("NO_GUARDO_MEMORIA")
    if "max_memorias" in espera and len(memorias) > espera["max_memorias"]:
        fallas.append("MEMORIA_INVENTADA")
    if espera.get("evento_fecha") and espera["evento_fecha"] not in fechas_evento:
        fallas.append(f"EVENTO_FECHA_MAL({fechas_evento or 'sin evento'})")
    if espera.get("exige_ejercicio") and accion not in EJERCICIOS_VALIDOS:
        fallas.append("NO_OFRECIO_EJERCICIO")
    if espera.get("sin_ejercicio") and accion is not None:
        fallas.append("EJERCICIO_EN_CONTEXTO_PROHIBIDO")
    if espera.get("mood_en") and mood not in espera["mood_en"]:
        fallas.append(f"MOOD_FUERA_DE_RANGO({mood})")
    if espera.get("sin_codigo") and ("def " in mensaje or "```" in mensaje or "import " in mensaje):
        fallas.append("SALIO_DEL_ROL")

    # ── ESTILO ────────────────────────────────────────────────
    if _TUTEO.search(mensaje):
        fallas.append("TUTEO")
    if _eco(caso["mensaje"], mensaje):
        fallas.append("ECO")
    if '"' in mensaje or "“" in mensaje or "”" in mensaje:
        fallas.append("COMILLAS")
    if _RE_CHE.search(mensaje):
        fallas.append("CHE")          # text_filters lo saca igual, pero mide cuánto insiste el modelo

    return {
        "fallas": fallas,
        "mensaje": mensaje,
        "mood": mood,
        "accion": accion,
        "n_memorias": len(memorias),
        "json_directo": json_directo,
    }


def _costo_usd(cand: dict, r: dict) -> float:
    frescos = max(0, r["prompt_tokens"] - r["cached_tokens"])
    return (frescos * cand["precio_in"]
            + r["cached_tokens"] * cand["precio_cache"]
            + r["completion_tokens"] * cand["precio_out"])


# ══════════════════════════════════════════════════════════════
def main() -> None:
    n_reales = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    claves = sys.argv[2].split(",") if len(sys.argv) > 2 else POR_DEFECTO
    for k in claves:
        if k not in CANDIDATOS:
            sys.exit(f"Candidato desconocido: {k}. Opciones: {', '.join(CANDIDATOS)}")

    casos = list(CASOS)
    for i, msg in enumerate(_cargar_mensajes()[:n_reales], 1):
        casos.append({"id": f"real_{i:02d}", "mensaje": msg,
                      "kwargs": {"num_interacciones": 4}, "espera": {}})

    cliente = get_client("openrouter")
    print(f"{len(casos)} casos ({len(CASOS)} dirigidos + {n_reales} reales) × "
          f"{len(claves)} candidatos = {len(casos) * len(claves)} llamadas\n")

    resultados: Dict[str, List[dict]] = {k: [] for k in claves}
    filas: List[dict] = []

    for n, caso in enumerate(casos, 1):
        kw = dict(caso["kwargs"])
        kw.setdefault("perfil", PERFIL)
        kw.setdefault("memorias", MEMORIAS)
        system_prompt = construir_prompt(ultimo_mensaje=caso["mensaje"], hoy=HOY, **kw)

        # Ronda robin: el mismo caso contra todos los candidatos, uno atrás
        # del otro, para que las condiciones de red sean las mismas.
        for k in claves:
            cand = CANDIDATOS[k]
            try:
                r = _llamar(cliente, cand, system_prompt, caso["mensaje"])
            except Exception as e:
                ev = {"fallas": [f"ERROR_API({type(e).__name__})"], "mensaje": str(e)[:160],
                      "mood": "", "accion": "", "n_memorias": 0, "json_directo": False}
                r = {"latencia_ms": None, "prompt_tokens": 0, "cached_tokens": 0,
                     "completion_tokens": 0, "proveedor_real": None, "raw": ""}
            else:
                ev = _evaluar_respuesta(caso, r)

            resultados[k].append({**ev, "caso": caso["id"], "latencia_ms": r["latencia_ms"],
                                  "costo": _costo_usd(cand, r) if r["latencia_ms"] else 0.0,
                                  "prompt_tokens": r["prompt_tokens"],
                                  "cached_tokens": r["cached_tokens"],
                                  "completion_tokens": r["completion_tokens"],
                                  "proveedor_real": r["proveedor_real"]})
            filas.append({
                "caso": caso["id"], "candidato": k, "modelo": cand["modelo"],
                "mensaje_usuario": caso["mensaje"], "respuesta": ev["mensaje"],
                "mood": ev["mood"], "suggested_action": ev["accion"],
                "n_memorias": ev["n_memorias"],
                "latencia_ms": round(r["latencia_ms"]) if r["latencia_ms"] else "",
                "fallas": " ".join(ev["fallas"]),
            })
        print(f"  [{n}/{len(casos)}] {caso['id']}", flush=True)

    # ── Reporte ───────────────────────────────────────────────
    print("\n" + "=" * 104)
    print("%-14s | %5s | %6s %6s | %6s | %5s | %s" % (
        "candidato", "fallas", "lat med", "p90", "chars", "cache", "USD/1000 turnos"))
    print("=" * 104)
    for k in claves:
        rs = resultados[k]
        lats = sorted(x["latencia_ms"] for x in rs if x["latencia_ms"])
        med = statistics.median(lats) if lats else 0
        p90 = lats[min(len(lats) - 1, int(len(lats) * 0.9))] if lats else 0
        chars = statistics.median(len(x["mensaje"]) for x in rs)
        con_falla = sum(1 for x in rs if x["fallas"])
        costo = sum(x["costo"] for x in rs) / max(1, len(rs)) * 1000
        pt = sum(x["prompt_tokens"] for x in rs) or 1
        cache = sum(x["cached_tokens"] for x in rs) / pt * 100
        print("%-14s | %2d/%-2d | %6.0f %6.0f | %6.0f | %4.0f%% | $%.2f" % (
            k, con_falla, len(rs), med, p90, chars, cache, costo))

    print("\nFALLAS POR TIPO")
    tipos = sorted({re.sub(r"\(.*\)", "", f) for k in claves for x in resultados[k] for f in x["fallas"]})
    if not tipos:
        print("  (ninguna)")
    for t in tipos:
        linea = "  %-34s" % t
        for k in claves:
            n = sum(1 for x in resultados[k] for f in x["fallas"] if re.sub(r"\(.*\)", "", f) == t)
            linea += " %s=%-3d" % (k, n)
        print(linea)

    print("\nCASOS CON FALLA (detalle)")
    hubo = False
    for k in claves:
        for x in resultados[k]:
            if x["fallas"]:
                hubo = True
                print(f"  {k:<14} {x['caso']:<20} {' '.join(x['fallas'])}")
    if not hubo:
        print("  (ninguno)")

    salida = os.path.join(os.path.dirname(__file__), "..", "eval_cambio_modelo_resultados.csv")
    with open(salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(sorted(filas, key=lambda r: (r["caso"], r["candidato"])))
    print(f"\n📄 Respuestas lado a lado (ordenadas por caso) en {os.path.normpath(salida)}")
    print("⚠️  Esto NO mide TTFT del modo llamada → scripts/bench_modelos_ttft.py")


if __name__ == "__main__":
    main()
