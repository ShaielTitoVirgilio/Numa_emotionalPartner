"""
Script de prueba del modelo de Numa.

Corre mensajes REALES de usuarios (de conversaciones_emparejadas.csv) contra el
prompt y el cliente LLM reales del backend, y reporta fallas automáticamente:
  - Escapes de registro (tuteo / español de España en vez de voseo)
  - Eco: Numa recita / repite el mensaje del usuario
  - Comillas en la respuesta
  - JSON inválido (lo maneja el propio LLMClient, acá solo se observa el resultado)

Uso:
    source venv/bin/activate
    python test_modelo.py            # 8 mensajes al azar
    python test_modelo.py 15         # 15 mensajes
    python test_modelo.py 15 fijo    # primeros 15 (reproducible, no al azar)

Para comparar modelos, exportá GROQ_MODEL antes de correr:
    GROQ_MODEL=qwen/qwen3-32b           python test_modelo.py 10 fijo
    GROQ_MODEL=llama-3.3-70b-versatile  python test_modelo.py 10 fijo
"""
import csv
import random
import re
import sys

from app.core.llm import get_model
from app.llm_client import LLMClient
from app.numa_prompt import construir_prompt

CSV = "conversaciones_emparejadas.csv"

# Formas de tuteo / español neutro-ibérico que NO deberían aparecer (debería ser voseo)
_TUTEO = re.compile(
    r"\b(tienes|quieres|puedes|sientes|piensas|haces|crees|debes|necesitas|"
    r"sabes|prefieres|dices|entiendes|conoces|vives|sigues|vienes|"
    r"contigo|vosotros|habéis|tenéis|queréis|sois)\b",
    re.IGNORECASE,
)


def _cargar_mensajes():
    with open(CSV, newline="", encoding="utf-8-sig") as f:
        filas = [r["mensaje_usuario"] for r in csv.DictReader(f)]
    return [m for m in filas if m and len(m.strip()) > 3]


def _eco(mensaje_usuario: str, respuesta: str) -> bool:
    """True si Numa recita un tramo largo del mensaje del usuario."""
    palabras = mensaje_usuario.lower().split()
    # busca cualquier secuencia de 5+ palabras del usuario dentro de la respuesta
    resp = respuesta.lower()
    for i in range(len(palabras) - 4):
        tramo = " ".join(palabras[i : i + 5])
        if tramo in resp:
            return True
    return False


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    fijo = len(sys.argv) > 2 and sys.argv[2] == "fijo"

    mensajes = _cargar_mensajes()
    seleccion = mensajes[:n] if fijo else random.sample(mensajes, min(n, len(mensajes)))

    client = LLMClient()
    print(f"\n🤖 Modelo activo: {get_model()}")
    print(f"📊 Probando {len(seleccion)} mensajes reales\n" + "=" * 70)

    fallas = {"tuteo": 0, "eco": 0, "comillas": 0}

    for i, msg in enumerate(seleccion, 1):
        system_prompt = construir_prompt(ultimo_mensaje=msg)
        conversation = [{"role": "user", "content": msg}]
        resp = client.generate_response(conversation, system_prompt)
        texto = resp["message"]

        # Chequeos automáticos
        hay_tuteo = bool(_TUTEO.search(texto))
        hay_eco = _eco(msg, texto)
        hay_comillas = '"' in texto or "“" in texto or "”" in texto
        if hay_tuteo:
            fallas["tuteo"] += 1
        if hay_eco:
            fallas["eco"] += 1
        if hay_comillas:
            fallas["comillas"] += 1

        flags = []
        if hay_tuteo:
            flags.append("⚠️ TUTEO")
        if hay_eco:
            flags.append("🔁 ECO")
        if hay_comillas:
            flags.append('❝ COMILLAS')
        marca = "  " + " ".join(flags) if flags else "  ✅"

        print(f"\n[{i}] 👤 {msg}")
        print(f"    🐻 {texto}")
        print(f"    🎭 mood={resp['mood']}{marca}")

    print("\n" + "=" * 70)
    print("RESUMEN DE FALLAS:")
    print(f"  Tuteo / fuera de registro : {fallas['tuteo']}/{len(seleccion)}")
    print(f"  Eco (recita al usuario)   : {fallas['eco']}/{len(seleccion)}")
    print(f"  Comillas en la respuesta  : {fallas['comillas']}/{len(seleccion)}")


if __name__ == "__main__":
    main()
