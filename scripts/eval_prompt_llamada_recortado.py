"""
¿El CORE recortado de modo llamada (MODULOS_LLAMADA_OVERRIDE en numa_prompt.py)
degrada el estilo de Numa? Compara respuestas REALES a los mismos mensajes con
el prompt completo (modo_llamada=False, como el chat escrito) vs el recortado
(modo_llamada=True), usando los mismos chequeos automáticos que test_modelo.py
(tuteo, eco, comillas) más un chequeo de la regla de preguntas (el módulo más
grande que se recortó, M04).

No reemplaza una lectura humana — es un primer filtro barato y objetivo antes
de esa lectura. Corre no-streaming (generate_response) para tener el JSON
completo y comparar mensaje a mensaje, lado a lado, en el CSV de salida.

Uso:
    venv/bin/python scripts/eval_prompt_llamada_recortado.py [n] [fijo]
"""
import csv
import os
import random
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt

CSV_ENTRADA = os.path.join(os.path.dirname(__file__), "..", "conversaciones_emparejadas.csv")

_TUTEO = re.compile(
    r"\b(tienes|quieres|puedes|sientes|piensas|haces|crees|debes|necesitas|"
    r"sabes|prefieres|dices|entiendes|conoces|vives|sigues|vienes|"
    r"contigo|vosotros|habéis|tenéis|queréis|sois)\b",
    re.IGNORECASE,
)


def _cargar_mensajes():
    with open(CSV_ENTRADA, newline="", encoding="utf-8-sig") as f:
        filas = [r["mensaje_usuario"] for r in csv.DictReader(f)]
    return [m for m in filas if m and len(m.strip()) > 3]


def _eco(mensaje_usuario: str, respuesta: str) -> bool:
    palabras = mensaje_usuario.lower().split()
    resp = respuesta.lower()
    for i in range(len(palabras) - 4):
        if " ".join(palabras[i:i + 5]) in resp:
            return True
    return False


def _fallas(msg: str, texto: str) -> list:
    f = []
    if _TUTEO.search(texto):
        f.append("TUTEO")
    if _eco(msg, texto):
        f.append("ECO")
    if '"' in texto or "“" in texto or "”" in texto:
        f.append("COMILLAS")
    if texto.count("?") > 1:
        f.append("MULTIPLE_PREGUNTA")
    return f


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    fijo = len(sys.argv) > 2 and sys.argv[2] == "fijo"

    mensajes = _cargar_mensajes()
    seleccion = mensajes[:n] if fijo else random.sample(mensajes, min(n, len(mensajes)))

    client = LLMClient()
    print(f"Probando {len(seleccion)} mensajes reales, completo vs recortado\n" + "=" * 70)

    resumen = {"completo": {"TUTEO": 0, "ECO": 0, "COMILLAS": 0, "MULTIPLE_PREGUNTA": 0},
               "recortado": {"TUTEO": 0, "ECO": 0, "COMILLAS": 0, "MULTIPLE_PREGUNTA": 0}}
    filas_csv = []

    for i, msg in enumerate(seleccion, 1):
        conversation = [{"role": "user", "content": msg}]

        sp_completo = construir_prompt(ultimo_mensaje=msg)
        r_completo = client.generate_response(conversation, sp_completo)
        t_completo = r_completo["message"]
        f_completo = _fallas(msg, t_completo)

        sp_recortado = construir_prompt(ultimo_mensaje=msg, modo_llamada=True)
        r_recortado = client.generate_response(conversation, sp_recortado)
        t_recortado = r_recortado["message"]
        f_recortado = _fallas(msg, t_recortado)

        for f in f_completo:
            resumen["completo"][f] += 1
        for f in f_recortado:
            resumen["recortado"][f] += 1

        marca_c = " ".join(f_completo) or "OK"
        marca_r = " ".join(f_recortado) or "OK"
        print(f"\n[{i}] 👤 {msg}")
        print(f"    completo   [{marca_c:20s}] {t_completo}")
        print(f"    recortado  [{marca_r:20s}] {t_recortado}")

        filas_csv.append({
            "mensaje": msg,
            "completo": t_completo, "fallas_completo": ",".join(f_completo),
            "recortado": t_recortado, "fallas_recortado": ",".join(f_recortado),
        })

    print("\n" + "=" * 70)
    print("RESUMEN DE FALLAS (de %d mensajes):" % len(seleccion))
    for cond in ("completo", "recortado"):
        print(f"  {cond:10s} -> " + " | ".join(f"{k}: {v}" for k, v in resumen[cond].items()))

    salida = os.path.join(os.path.dirname(__file__), "..", "eval_prompt_llamada_resultado.csv")
    with open(salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas_csv[0].keys()))
        w.writeheader()
        w.writerows(filas_csv)
    print(f"\nDetalle lado a lado en {os.path.normpath(salida)}")


if __name__ == "__main__":
    main()
