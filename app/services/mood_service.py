from typing import Literal

Mood = Literal[
    "neutral",
    "tranquilo",
    "positivo",
    "entusiasmado",
    "cansado",
    "frustrado",
    "triste",
    "ansioso",
    "abrumado",
    "desmotivado"
]

def infer_mood(text: str) -> Mood:
    t = text.lower()

    # Cansancio / desgaste
    if any(w in t for w in [
        "agotado", "cansado", "quemado", "sin energía",
        "hecho polvo", "reventado", "muerto", "fundido",
        "no doy más", "exhausto"
    ]):
        return "cansado"

    # Ansiedad / nervios
    if any(w in t for w in [
        "ansioso", "ansiedad", "nervioso", "acelerado",
        "inquieto", "no puedo parar", "tenso",
        "preocupado", "con miedo", "incómodo"
    ]):
        return "ansioso"

    # Abrumado / saturado
    if any(w in t for w in [
        "abrumado", "saturado", "pasado", "sobrecargado",
        "muchas cosas", "todo junto", "no llego",
        "me supera", "demasiado"
    ]):
        return "abrumado"

    # Frustración / enojo contenido
    if any(w in t for w in [
        "frustrado", "bronca", "hart", "molesto",
        "enojado", "rompe", "me pudre",
        "siempre lo mismo", "qué bronca"
    ]):
        return "frustrado"

    # Tristeza / bajón
    if any(w in t for w in [
        "triste", "bajón", "mal", "apagado",
        "deprimido", "sin ganas", "vacío",
        "no me siento bien", "medio mal"
    ]):
        return "triste"

    # Positivo / bienestar
    if any(w in t for w in [
        "bien", "mejor", "tranquilo", "contento",
        "en paz", "relajado", "ok", "todo bien",
        "estable"
    ]):
        return "tranquilo"

    # Entusiasmo / energía alta
    if any(w in t for w in [
        "feliz", "genial", "emocionado", "manija",
        "eufórico", "motivado", "con ganas",
        "inspirado", "re copado"
    ]):
        return "entusiasmado"

    # Desmotivación suave
    if any(w in t for w in [
        "desmotivado", "sin rumbo", "meh",
        "me cuesta", "poco ánimo",
        "no tengo ganas de nada"
    ]):
        return "desmotivado"

    return "neutral"
