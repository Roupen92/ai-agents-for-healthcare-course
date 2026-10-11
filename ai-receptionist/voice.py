"""Text-to-speech via ElevenLabs. One function: text in, mp3 bytes out."""

import os

import requests

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def synthesize_speech(text: str) -> bytes:
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    url = ELEVENLABS_TTS_URL.format(voice_id=voice_id)
    resp = requests.post(
        url,
        headers={
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.4, "similarity_boost": 0.75},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content
