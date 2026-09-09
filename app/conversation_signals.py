# app/conversation_signals.py
"""
Señales sobre el RITMO de la conversación, calculadas por el servidor a partir
del historial y pasadas al prompt como dato duro.

Viven acá, sin dependencias (ni base, ni LLM, ni FastAPI), por el mismo motivo
que text_filters.py: son lógica pura que decide cómo se comporta Numa y tiene
que poder testearse sola — ver scripts/test_senales_preguntas.py.

Las dos son espejo una de la otra y juntas forman un control de dos polos. El
sistema tuvo mucho tiempo solo el primero (freno) y ninguno del segundo, y el
resultado fue una Numa que prácticamente dejó de preguntar: nada le devolvía
el permiso una vez que lo perdía.
"""

from typing import List


def _termina_en_pregunta(mensaje: str) -> bool:
    """True si el mensaje cierra con '?', ignorando comillas finales."""
    return (mensaje or "").rstrip().rstrip("\"'").endswith("?")


def contar_preguntas_seguidas(mensajes_numa: List[str]) -> int:
    """FRENO: cuántos mensajes seguidos (desde el final) cerró Numa con '?'.

    Con 1 el prompt pide evitar otra pregunta; con 2 la prohíbe y, si el modelo
    igual pregunta, _quitar_pregunta_final() la recorta (text_filters.py).
    """
    racha = 0
    for contenido in reversed(mensajes_numa or []):
        if _termina_en_pregunta(contenido):
            racha += 1
        else:
            break
    return racha


def contar_turnos_sin_preguntar(mensajes_numa: List[str]) -> int:
    """HABILITACIÓN: cuántos mensajes seguidos (desde el final) viene Numa SIN
    preguntar nada.

    A partir de TURNOS_SIN_PREGUNTAR_PARA_HABILITAR (numa_prompt.py) el prompt
    le devuelve el permiso de preguntar — permiso, no obligación: sin algo
    genuino que entender, una pregunta de relleno es peor que ninguna.
    """
    racha = 0
    for contenido in reversed(mensajes_numa or []):
        if _termina_en_pregunta(contenido):
            break
        racha += 1
    return racha
