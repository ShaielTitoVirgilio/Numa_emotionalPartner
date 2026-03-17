# app/speech_service.py
import os
import requests

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
ELEVEN_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

def speech_to_text(audio_bytes: bytes, filename: str) -> str:
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
    }

    files = {
        "file": (filename, audio_bytes),
    }

    data = {
        "model_id": "scribe_v1",
        "language": "es",
    }

    res = requests.post(
        ELEVEN_STT_URL,
        headers=headers,
        files=files,
        data=data,
        timeout=30,
    )

    res.raise_for_status()
    return res.json()["text"]