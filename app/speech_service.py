# app/speech_service.py
import io
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

def speech_to_text(audio_bytes: bytes, filename: str) -> str:
    # Whisper acepta un file-like object en memoria, no hace falta tocar disco
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename or "audio.webm"

    transcript = client.audio.transcriptions.create(
        file=audio_file,
        model="whisper-large-v3-turbo",
        language="es",
    )

    return transcript.text