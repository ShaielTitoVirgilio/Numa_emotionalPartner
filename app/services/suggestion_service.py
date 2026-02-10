from typing import List

SUGGESTIONS_BY_MOOD = {
    "cansado": [
        {"id": "respiracion_1", "label": "Respirar 2 minutos"},
        {"id": "descanso_visual", "label": "Descanso de pantalla"}
    ],
    "ansioso": [
        {"id": "respiracion_4_7_8", "label": "Respiración guiada"},
        {"id": "anclaje_5_4_3_2_1", "label": "Ejercicio de anclaje"}
    ],
    "abrumado": [
        {"id": "lista_1_cosa", "label": "Ordenar una sola cosa"},
        {"id": "pausa_consciente", "label": "Pausa consciente"}
    ],
    "triste": [
        {"id": "escritura_ligera", "label": "Escribir sin filtro"},
        {"id": "auto_compasion", "label": "Ejercicio de autocompasión"}
    ],
}

def get_suggestions(mood: str) -> List[dict]:
    return SUGGESTIONS_BY_MOOD.get(mood, [])
