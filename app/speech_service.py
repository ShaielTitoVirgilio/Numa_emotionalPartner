# app/speech_service.py
import os
import tempfile
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

def speech_to_text(audio_bytes: bytes, filename: str) -> str:
    # Whisper requiere archivo → guardamos temporalmente
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
        f.write(audio_bytes)
        temp_path = f.name

    with open(temp_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-large-v3-turbo",
            language="es",
        )

    return transcript.text