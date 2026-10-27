"""Speech to text for patient intake, via Muse Voice Transcribe.

The Meta Model API transcribes files at POST {base_url}/asr/transcribe: multipart
with a JSON "request" part and an "audio" part. It is not the OpenAI
/audio/transcriptions route. The browser converts its recording to 16 kHz mono
WAV before upload, so "WAV" is the only encoding this module sends.
"""
from __future__ import annotations

import json
import os
import uuid

import httpx

from .config import META_BASE_URL_DEFAULT, mock_enabled

MODEL = "muse-voice-transcribe-1.0"
MAX_WAV_BYTES = 2_000_000  # ~60 s of 16 kHz mono 16-bit audio
MOCK_TRANSCRIPT = "I need a cardiologist in network, as soon as possible, but nothing before 9 in the morning."


class TranscribeError(RuntimeError):
    pass


async def transcribe_wav(wav: bytes) -> str:
    if mock_enabled():
        return MOCK_TRANSCRIPT
    base = os.getenv("VOICE_BASE_URL", os.getenv("META_BASE_URL", META_BASE_URL_DEFAULT)).rstrip("/")
    key = os.getenv("MODEL_API_KEY", "")
    request = {"model": os.getenv("VOICE_MODEL", MODEL), "audioEncoding": "WAV"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{base}/asr/transcribe",
            params={"sessionId": str(uuid.uuid4())},
            headers={"Authorization": f"Bearer {key}"},
            files={"request": (None, json.dumps(request), "application/json"), "audio": ("speech.wav", wav, "audio/wav")},
        )
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            msg = r.text[:200]
        raise TranscribeError(f"transcription failed ({r.status_code}): {msg}")
    return (r.json().get("transcript") or "").strip()
