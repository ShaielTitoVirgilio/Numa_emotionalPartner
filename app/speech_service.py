# app/speech_service.py
import io

from app.core.llm import get_client


def speech_to_text(audio_bytes: bytes, filename: str) -> str:
    # Whisper acepta un file-like object en memoria, no hace falta tocar disco
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename or "audio.webm"

    transcript = get_client("groq").audio.transcriptions.create(
        file=audio_file,
        model="whisper-large-v3-turbo",
        language="es",
    )

    return transcript.text
