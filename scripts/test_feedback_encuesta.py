"""
Verifica POST /feedback con la encuesta por preguntas (columna `respuestas`).

Qué se verifica, y por qué importa:

  1. Una encuesta completa llega al repositorio con `respuestas` limpio y con
     rating/texto copiados desde valoracion/mejora (así /admin/feedback y las
     consultas viejas siguen viendo la valoración y el comentario).
  2. El formulario viejo (solo rating + texto, sin `respuestas`) sigue
     funcionando igual: las apps ya instaladas no se rompen.
  3. Lo que un cliente modificado podría mandar se descarta: claves enormes,
     booleanos, objetos anidados, listas largas, strings gigantes.
  4. `respuestas` con solo `version` (sin ninguna respuesta) se guarda como
     nulo: no existe una encuesta vacía.
  5. rating/texto explícitos del cliente ganan sobre lo derivado de `respuestas`.

No toca Supabase: el repositorio se reemplaza por uno falso.

Correr con: venv/bin/python scripts/test_feedback_encuesta.py
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.routes.feedback_router as fr

fallos = 0


def check(nombre, ok, detalle=""):
    global fallos
    if ok:
        print(f"✅ {nombre}")
    else:
        fallos += 1
        print(f"❌ {nombre}{chr(10) + '   ' + detalle if detalle else ''}")


class RepoFalso:
    def __init__(self):
        self.guardado = None

    def save_feedback(self, data):
        self.guardado = data


def enviar(**campos):
    repo = RepoFalso()
    with patch.object(fr, "feedback_repo", repo):
        res = fr.feedback_endpoint(fr.FeedbackRequest(**campos), user_id="u-1")
    return res, repo.guardado


# 1 ── encuesta completa
res, g = enviar(respuestas={
    "version": 1, "valoracion": 4, "sentir_despues": "algo_mejor",
    "sin_numa": "amigos_familia", "valora": ["privacidad", "ejercicios"],
    "mejora": "  más ejercicios  ",
})
check("encuesta completa: ok", res == {"ok": True}, str(res))
check("respuestas conserva todas las preguntas",
      g["respuestas"] == {"version": 1, "valoracion": 4, "sentir_despues": "algo_mejor",
                          "sin_numa": "amigos_familia", "valora": ["privacidad", "ejercicios"],
                          "mejora": "más ejercicios"}, str(g["respuestas"]))
check("rating sale de valoracion", g["rating"] == 4, str(g["rating"]))
check("texto sale de mejora", g["texto"] == "más ejercicios", str(g["texto"]))
check("el user_id sale del token", g["user_id"] == "u-1")

# 2 ── formulario viejo
res, g = enviar(rating=5, texto="me gusta", rating_recomendaria=3)
check("formulario viejo: sin respuestas", g["respuestas"] is None, str(g))
check("formulario viejo: rating/texto intactos", g["rating"] == 5 and g["texto"] == "me gusta")
check("formulario viejo: rating_recomendaria intacto", g["rating_recomendaria"] == 3)

# 3 ── basura de un cliente modificado
res, g = enviar(respuestas={
    "version": 1,
    "x" * 41: "clave larga",
    "": "clave vacía",
    "bool": True,
    "anidado": {"a": 1},
    "valora": ["a"] * 50,
    "mejora": "y" * 9000,
    "vacio": "   ",
})
r = g["respuestas"]
check("claves enormes/vacías/booleanos/anidados se descartan",
      set(r) == {"version", "valora", "mejora"}, str(set(r)))
check("lista larga se recorta", len(r["valora"]) == fr.MAX_RESPUESTAS_OPCIONES)
check("string gigante se recorta", len(r["mejora"]) == fr.MAX_TEXTO_CHARS)

# 4 ── solo version
res, g = enviar(respuestas={"version": 1})
check("solo version: se guarda nulo", g["respuestas"] is None, str(g))

# 5 ── lo explícito gana
res, g = enviar(rating=2, texto="explícito", respuestas={"valoracion": 5, "mejora": "derivado"})
check("rating explícito gana", g["rating"] == 2, str(g["rating"]))
check("texto explícito gana", g["texto"] == "explícito", str(g["texto"]))

# valoracion fuera de rango no se copia a rating
res, g = enviar(respuestas={"valoracion": 9, "sin_numa": "nada"})
check("valoracion fuera de rango no pisa rating", g["rating"] is None, str(g["rating"]))

print()
print("TODO OK" if fallos == 0 else f"{fallos} FALLO(S)")
sys.exit(1 if fallos else 0)
