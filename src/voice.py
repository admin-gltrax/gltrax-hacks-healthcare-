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


# ---------------------------------------------------------------- realtime (the simulated voice call)

REALTIME_URL = "wss://api.meta.ai/v1/asr/realtime"


async def transcribe_pcm24k(pcm: bytes) -> tuple[str, str]:
    """PCM16 mono 24 kHz -> (transcript, how). Tries Meta's realtime ASR (push-to-talk), then falls back
    to file transcription with the same model. `how` says which ran: "realtime" or "file"."""
    if mock_enabled():
        raise TranscribeError("mock mode has no speech")
    try:
        return await _realtime(pcm), "realtime"
    except Exception:  # the realtime socket can be unavailable (proxies, regions); the file route is the same model
        return await transcribe_wav(_wav(pcm, 24000)), "file"


async def _realtime(pcm: bytes) -> str:
    import asyncio

    import websockets
    key = os.getenv("MODEL_API_KEY", "")
    url = os.getenv("VOICE_REALTIME_URL", REALTIME_URL)
    parts: list[str] = []
    async with websockets.connect(url, open_timeout=10, max_size=None) as ws:
        await ws.send(json.dumps({"authorization": {"accessToken": f"Bearer {key}"}, "audioEncoding": "PCM_24KHZ",
                                  "model": os.getenv("VOICE_MODEL", MODEL), "mode": "PUSH_TO_TALK"}))
        for i in range(0, len(pcm), 9600):  # 200 ms frames
            await ws.send(pcm[i:i + 9600])
        await ws.send(json.dumps({"type": "endStream"}))
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), 15)
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                break
            if isinstance(msg, bytes):
                continue
            data = json.loads(msg)
            text = data.get("transcript") or data.get("text") or ""
            if text and data.get("isFinal", data.get("final", True)):
                parts.append(text.strip())
            if data.get("type") in ("endOfStream", "end", "done"):
                break
    if not parts:
        raise TranscribeError("realtime ASR returned nothing")
    return " ".join(parts)


def _wav(pcm: bytes, rate: int) -> bytes:
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()
