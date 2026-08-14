# app/core/logging_utils.py
"""
Logging estructurado de eventos operativos (una línea JSON por evento a stdout).

Sentry (ver observability.py) solo ve errores — nunca los requests que
terminan bien. Esto llena ese hueco para lo que sí queremos poder buscar en
los logs de Railway sin ir a mirar código: qué endpoint pegó cada usuario,
con qué proveedor/modelo de LLM respondió el chat (primario o fallback),
cuánto tardó, qué mood/risk_level salió. Reemplaza (para estos casos) a los
`print()` sueltos que había repartidos por varios módulos — mismo destino
(stdout, que Railway captura igual), pero como JSON estructurado se puede
filtrar por campo en vez de tener que leer texto libre.

Regla de oro, igual que en observability.py: acá NUNCA va contenido de
mensajes. Sí va el email del usuario (a diferencia de Sentry, que solo recibe
el UUID) — es un log operativo que solo mira el dueño de la app en Railway,
para saber a quién atender si algo falló; no se comparte ni se manda a
ningún tercero.
"""

import json
import time
from typing import Any


def log_event(evento: str, **campos: Any) -> None:
    """Emite una línea JSON a stdout con el evento y los campos dados.

    No lanza nunca: un fallo de logging no debe romper un request real. Los
    valores no serializables (excepciones, UUIDs, etc.) se castean a str.
    """
    payload = {"evento": evento, "ts": round(time.time(), 3), **campos}
    try:
        print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)
    except Exception:
        pass
