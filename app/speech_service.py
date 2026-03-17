# app/speech_service.py
import os
import requests

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
ELEVEN_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"

def speech_to_text(audio_bytes: bytes, filename: str) -> str:
    print(f"ELEVEN_API_KEY presente: {bool(ELEVEN_API_KEY)}")

    if not ELEVEN_API_KEY:
        raise RuntimeError("ELEVEN_API_KEY no configurada")

    headers = {
        "xi-api-key": ELEVEN_API_KEY,
    }

    files = {
        "file": (filename, audio_bytes, "audio/webm"),  # 👈 CLAVE
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

    print("Eleven status:", res.status_code)
    print("Eleven body:", res.text)

    res.raise_for_status()
    return res.json()["text"]