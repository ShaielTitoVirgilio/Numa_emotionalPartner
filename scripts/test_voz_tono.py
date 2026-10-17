"""
Verifica el tono de voz del modo llamada (app/voz_tono.py + su uso en
_stream_chat_respuesta).

Lo que se verifica:
  1. Cada tono sale con la emoción y la velocidad acordadas (sensible 0.9,
     tranqui 1.0).
  2. Risa: un "jaja" del LLM se vuelve [laughter], una sola risa por turno, y
     en "sensible" no hay risa.
  3. Pausas solo en mensajes largos.
  4. Con riesgo el tono es "sensible" diga lo que diga el router.
  5. El tono provisorio (antes del router) usa el mensaje y el turno anterior.
  6. En el stream: las oraciones llevan `voz`, cambian al tono del router
     apenas contesta, el turno NO espera al router, y el chat escrito no
     cambia.

Correr con: venv/bin/python scripts/test_voz_tono.py
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import BackgroundTasks

import app.routes.chat_router as cr
from app.voz_tono import ArmadorVoz, tono_desde_router, tono_provisorio

fallos = 0
_pool = ThreadPoolExecutor(max_workers=4)


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


# ── 1. Parámetros por tono ───────────────────────────────────────────────
v = ArmadorVoz("sensible").armar("Te entiendo.")
check("sensible: sympathetic a 0.9", v["emotion"] == "sympathetic" and v["speed"] == 0.9, str(v))
v = ArmadorVoz("tranqui").armar("Te entiendo.")
check("tranqui: calm a 1.0", v["emotion"] == "calm" and v["speed"] == 1.0, str(v))
v = ArmadorVoz("euforico").armar("¡Qué golazo!")
check("eufórico: excited y más rápido", v["emotion"] == "excited" and v["speed"] > 1.1, str(v))
v = ArmadorVoz("tranqui").armar("¿Y cómo te fue?")
check("pregunta en tranqui suena curiosa", v["emotion"] == "curious", str(v))
v = ArmadorVoz("raro").armar("Hola.")
check("tono desconocido cae a tranqui", v["tono"] == "tranqui", str(v))

# ── 2. Risa ──────────────────────────────────────────────────────────────
a = ArmadorVoz("alegre")
v1 = a.armar("Jajaja, qué bueno.")
v2 = a.armar("Jaja, posta.")
check("un jaja se vuelve risa real", v1["transcript"].startswith("[laughter]") and "aja" not in v1["transcript"].lower(), v1["transcript"])
check("una sola risa por turno", "[laughter]" not in v2["transcript"] and "jaja" not in v2["transcript"].lower(), v2["transcript"])
a = ArmadorVoz("risa")
v1 = a.armar("Me imagino la cara de todos.")
check("tono risa arranca riéndose aunque el LLM no escriba jaja", v1["transcript"].startswith("[laughter] "), v1["transcript"])
check("tono risa no se ríe dos veces", "[laughter]" not in a.armar("Contame más.")["transcript"])
v = ArmadorVoz("sensible").armar("Te entiendo, jaja, es mucho.")
check("en sensible no hay risa", "[laughter]" not in v["transcript"] and "jaja" not in v["transcript"].lower(), v["transcript"])
check("y no quedan comas dobles", ", ," not in v["transcript"] and ",," not in v["transcript"], v["transcript"])
v = ArmadorVoz("tranqui").armar("Jaja, qué bueno.")
check("una risa en tranqui va con emoción alegre", v["emotion"] == "happy", str(v))
v = ArmadorVoz("tranqui").armar("Mirá <emotion value=\"angry\"/> esto [music].")
check("el texto del LLM no puede meter etiquetas", "<" not in v["transcript"] and "[" not in v["transcript"], v["transcript"])
v = ArmadorVoz("sensible").armar("Jaja.")
check("una oración que era solo jaja no queda vacía", v["transcript"].strip() != "", repr(v["transcript"]))

# ── 3. Pausas ────────────────────────────────────────────────────────────
a = ArmadorVoz("tranqui")
cortas = [a.armar(o)["transcript"] for o in ["Hola.", "¿Cómo andás?"]]
check("mensaje corto: sin pausas", not any("<break" in t for t in cortas), str(cortas))
a = ArmadorVoz("tranqui")
largas = [a.armar(o)["transcript"] for o in ["Una.", "Dos.", "Tres.", "Cuatro."]]
check("mensaje largo: pausa desde la tercera", "<break" not in largas[1] and largas[2].startswith("<break time=\"300ms\"/>"), str(largas))
a = ArmadorVoz("tranqui")
a.armar("x" * 130)
check("tras una oración larga, la segunda ya lleva pausa", a.armar("Dos.")["transcript"].startswith("<break"))
a = ArmadorVoz("sensible")
for o in ["Uno.", "Dos."]:
    a.armar(o)
check("en sensible la pausa es más larga", "450ms" in a.armar("Tres.")["transcript"])

# ── 4. Riesgo → sensible ─────────────────────────────────────────────────
check("router con riesgo implícito → sensible aunque pida risa",
      tono_desde_router({"ok": True, "tono_voz": "risa", "senal_riesgo": "implicita"}, 0.0) == "sensible")
check("crisis por keywords → sensible",
      tono_desde_router({"ok": True, "tono_voz": "alegre", "senal_riesgo": "none"}, 0.4) == "sensible")
check("euforia sobre tristeza → sensible",
      tono_desde_router({"ok": True, "tono_voz": "euforico", "senal_riesgo": "none", "estado_emocional": "triste_vacio"}, 0.0) == "sensible")
check("router que falló → None (sigue el provisorio)", tono_desde_router({"ok": False}, 0.0) is None)
check("router sin tono_voz se deduce del estado",
      tono_desde_router({"ok": True, "senal_riesgo": "none", "estado_emocional": "buenas_noticias"}, 0.0) == "alegre")
check("router normal respeta su tono",
      tono_desde_router({"ok": True, "tono_voz": "curioso", "senal_riesgo": "none", "estado_emocional": "metas"}, 0.0) == "curioso")

# ── 5. Tono provisorio ───────────────────────────────────────────────────
check("provisorio: crisis → sensible", tono_provisorio(0.4, None, "hola", "risa") == "sensible")
check("provisorio: jaja del usuario → risa", tono_provisorio(0.0, None, "jajaja me caí de la bici") == "risa")
check("provisorio: 'jaja, nadie me quiere' → sensible", tono_provisorio(0.0, None, "jaja bueno, igual nadie me quiere") == "sensible")
check("provisorio: 'aprobé!' → eufórico", tono_provisorio(0.0, None, "APROBÉ!!! no lo puedo creer") == "euforico")
check("provisorio: hereda el tono anterior", tono_provisorio(0.0, None, "y bueno, eso", "curioso") == "curioso")
check("provisorio: una risa anterior no se arrastra", tono_provisorio(0.0, None, "sí", "risa") == "alegre")
check("provisorio: mood triste anterior → sensible", tono_provisorio(0.0, "triste_vacio", "sí") == "sensible")
check("provisorio: sin datos → tranqui", tono_provisorio(0.0, None, "sí") == "tranqui")

# ── 6. En el stream ──────────────────────────────────────────────────────
ORACIONES = ["Jaja, qué bueno que me lo cuentes. ", "Me imagino tu cara. ", "¿Y después qué pasó? "]


def _stream_falso(**kwargs):
    for o in ORACIONES:
        time.sleep(0.15)
        yield ("mensaje", o)
    yield ("metadata", {
        "mood": "happy", "suggested_action": None, "memories": [],
        "_llm": {"provider": "test", "model": "test", "fallback": False,
                 "ok": True, "cut": False, "latency_ms": 300.0},
    })


def _turno(fut_router, ultimo="me caí de la bici adelante de todos", previo=None):
    return {
        "conversation": [cr.Message(role="user", content=ultimo)],
        "crisis_score": 0.0, "ultimo_mensaje": ultimo, "hoy": cr.date.today(),
        "memorias_vigentes": [], "ids_a_desactivar": [], "evento_proactivo": None,
        "tema_abierto": None, "memoria_ctx_id": None, "preguntas_seguidas": 0,
        "ultimo_modulo_critico": False, "familia_apertura_previa": None,
        "previo_cierre_presencia": False, "system_prompt": "prompt",
        "_tiempos": {}, "_router": {}, "crisis_confirmada": False,
        "_fut_router_paralelo": fut_router, "estado_local": None,
        "tono_voz_previo": previo,
    }


def correr(fut_router, modo_llamada=True, **kw):
    log = {}

    def _log(evento, **k):
        if evento == "chat_turn":
            log.update(k)

    with patch.object(cr.llm, "generate_response_stream", _stream_falso), \
         patch.object(cr, "log_event", _log), \
         patch.object(cr, "_procesar_memorias_turno", side_effect=lambda m, *a, **k: m), \
         patch.object(cr, "_disparar_tareas_turno", lambda bt, **k: None), \
         patch.object(cr, "etiquetar_request", return_value=None), \
         patch.object(cr.feedback_repo, "save_crisis_log", return_value=None):
        eventos = [json.loads(l) for l in cr._stream_chat_respuesta(
            _turno(fut_router, **kw), "u1", BackgroundTasks(), modo_llamada=modo_llamada)]
    return eventos, log


def _fut(tono, demora=0.0, senal="none"):
    def _tarea():
        time.sleep(demora)
        return ({"ok": True, "estado_emocional": "neutral", "senal_riesgo": senal,
                 "pide_ejercicio": False, "pregunta_app": False,
                 "pregunta_capacidades": False, "tono_voz": tono}, demora * 1000)
    return _pool.submit(_tarea)


# Router rápido: todas las oraciones con su tono.
fut = _fut("risa", demora=0.0)
time.sleep(0.05)
eventos, log = correr(fut)
deltas = [e for e in eventos if e["type"] == "delta"]
check("cada delta de la llamada lleva `voz`", deltas and all("voz" in d for d in deltas), str(deltas[:1]))
check("con el router a tiempo, todo sale con su tono", all(d["voz"]["tono"] == "risa" for d in deltas), str([d["voz"]["tono"] for d in deltas]))
check("el texto que se muestra no cambia", deltas[0]["text"].startswith("Jaja"), deltas[0]["text"])
final = next(e for e in eventos if e["type"] == "final")
check("el final devuelve el tono para el turno siguiente", final.get("tono_voz") == "risa", str(final))
check("se loguea la fuente del tono", log.get("tono_voz_fuente") == "router" and log.get("oraciones_antes_del_router") == 0,
      f"fuente={log.get('tono_voz_fuente')} antes={log.get('oraciones_antes_del_router')}")

# Router que llega a la mitad: arranca provisorio y cambia.
eventos, log = correr(_fut("euforico", demora=0.2), ultimo="hola", previo="tranqui")
tonos = [e["voz"]["tono"] for e in eventos if e["type"] == "delta"]
check("antes del router usa el provisorio y después cambia",
      tonos[0] == "tranqui" and tonos[-1] == "euforico", str(tonos))

# Router que llega DESPUÉS de todas las oraciones (el caso medido en la
# realidad): se emiten con el provisorio y, antes del final, llega un evento
# `voz` con todas rearmadas con el tono del router.
t_deltas = []
_orig_evento = cr._evento_ndjson


def _evento_cronometrado(obj):
    if obj.get("type") == "delta":
        t_deltas.append(time.perf_counter())
    return _orig_evento(obj)


inicio = time.perf_counter()
with patch.object(cr, "_evento_ndjson", _evento_cronometrado):
    eventos, log = correr(_fut("euforico", demora=1.0), ultimo="hola", previo="tranqui")
tipos = [e["type"] for e in eventos]
check("las oraciones salen sin esperar al router", t_deltas and t_deltas[-1] - inicio < 1.0,
      f"última a los {(t_deltas[-1] - inicio)*1000:.0f}ms")
check("con el router tarde, las oraciones salen con el provisorio",
      all(e["voz"]["tono"] == "tranqui" for e in eventos if e["type"] == "delta"))
check("llega un evento `voz` antes del final", "voz" in tipos and tipos.index("voz") < tipos.index("final"), str(tipos))
voz_ev = next((e for e in eventos if e["type"] == "voz"), {"voces": []})
check("el evento `voz` trae todas las oraciones con el tono del router",
      len(voz_ev["voces"]) == 3 and all(v["tono"] == "euforico" for v in voz_ev["voces"]), str(voz_ev)[:200])
check("los índices del evento `voz` coinciden con los de los deltas",
      [v["indice"] for v in voz_ev["voces"]] == [e["voz"]["indice"] for e in eventos if e["type"] == "delta"] == [0, 1, 2])
check("y el final devuelve el tono del router", next(e for e in eventos if e["type"] == "final").get("tono_voz") == "euforico")
check("se loguea el tono tardío", log.get("tono_voz_tardio") is True and log.get("tono_voz_fuente") == "router",
      f"tardio={log.get('tono_voz_tardio')} fuente={log.get('tono_voz_fuente')}")

# Router que dice lo mismo que el provisorio: no hace falta mandar nada.
eventos, log = correr(_fut("tranqui", demora=0.6), ultimo="hola", previo="tranqui")
check("si el tono no cambió, no se manda evento `voz`", not any(e["type"] == "voz" for e in eventos))

# Router lentísimo: la espera tiene techo.
inicio = time.perf_counter()
eventos, log = correr(_fut("alegre", demora=5.0), ultimo="hola")
dur = time.perf_counter() - inicio
check("la espera al router tiene techo", dur < 0.5 + cr._ESPERA_TONO_ROUTER_S + 0.5, f"tardó {dur*1000:.0f}ms")
check("router que no llega: todo con el provisorio y sin evento `voz`",
      log.get("tono_voz_fuente") == "provisorio" and not any(e["type"] == "voz" for e in eventos),
      f"fuente={log.get('tono_voz_fuente')}")


# Una o dos oraciones: no se espera nada (la app ya pidió las dos primeras).
def _stream_una(**kwargs):
    yield ("mensaje", "Qué bueno. ")
    yield ("metadata", {"mood": "happy", "suggested_action": None, "memories": [],
                        "_llm": {"provider": "test", "model": "test", "fallback": False,
                                 "ok": True, "cut": False, "latency_ms": 10.0}})


# correr() toma _stream_falso por nombre al ejecutarse: se cambia un rato.
_orig_stream = _stream_falso
_stream_falso = _stream_una
inicio = time.perf_counter()
eventos, log = correr(_fut("alegre", demora=3.0), ultimo="hola")
dur = time.perf_counter() - inicio
_stream_falso = _orig_stream
# "Qué bueno." son ~1s de audio: la espera tiene que quedar adentro de eso.
check("con una oración corta la espera no pasa de lo que dura hablarla", dur < 0.9, f"tardó {dur*1000:.0f}ms")


def _stream_dos(**kwargs):
    yield ("mensaje", "Qué bueno. ")
    yield ("mensaje", "¿Y después? ")
    yield ("metadata", {"mood": "happy", "suggested_action": None, "memories": [],
                        "_llm": {"provider": "test", "model": "test", "fallback": False,
                                 "ok": True, "cut": False, "latency_ms": 10.0}})


_stream_falso = _stream_dos
inicio = time.perf_counter()
eventos, log = correr(_fut("alegre", demora=3.0), ultimo="hola")
dur = time.perf_counter() - inicio
_stream_falso = _orig_stream
# "Qué bueno. ¿Y después?" son ~1.8s de audio más ~0.6s hasta que empieza a
# sonar: la espera (estimada por lo bajo) tiene que quedar adentro de eso.
check("con dos oraciones cortas la espera no pasa de lo que duran", dur < 2.0, f"tardó {dur*1000:.0f}ms")


def _stream_dale(**kwargs):
    yield ("mensaje", "Dale. ")
    yield ("metadata", {"mood": "neutral", "suggested_action": None, "memories": [],
                        "_llm": {"provider": "test", "model": "test", "fallback": False,
                                 "ok": True, "cut": False, "latency_ms": 10.0}})


_stream_falso = _stream_dale
inicio = time.perf_counter()
eventos, log = correr(_fut("alegre", demora=3.0), ultimo="hola")
dur = time.perf_counter() - inicio
_stream_falso = _orig_stream
check("un 'Dale.' casi no espera (el mic se abre enseguida)", dur < 0.7, f"tardó {dur*1000:.0f}ms")

# Router que llega mientras Numa dice una oración corta: el final trae su tono.
_stream_falso = _stream_una
eventos, log = correr(_fut("curioso", demora=0.3), ultimo="hola", previo="tranqui")
_stream_falso = _orig_stream
check("en una respuesta corta el final igual trae el tono del router",
      next(e for e in eventos if e["type"] == "final").get("tono_voz") == "curioso",
      str(next(e for e in eventos if e["type"] == "final")))

# Chat escrito: sin cambios.
eventos, log = correr(_fut("risa"), modo_llamada=False)
check("el chat escrito no manda `voz`", not any("voz" in e for e in eventos if e["type"] == "delta"))
check("el chat escrito no manda tono en el final", "tono_voz" not in next(e for e in eventos if e["type"] == "final"))

print()
print("TODO OK" if not fallos else f"{fallos} FALLO(S)")
sys.exit(1 if fallos else 0)
