"""Text to speech for the simulated voice call. OFF by default.

Meta has no text-to-speech, and whether the hackathon's Official Rules allow a
non-Meta TTS is unconfirmed, so nothing synthesizes speech unless VOICE_TTS says so:

  off      (default) no speech; the voice call refuses to run, and /gym doesn't play audio
  baseten  an open TTS model deployed on Baseten: POST BASETEN_TTS_URL with {"text", "voice"},
           auth "Api-Key $BASETEN_API_KEY"; the reply carries base64 WAV ("audio" or "base64")
  local    the same open-weights model on this machine (Kokoro-82M via kokoro-onnx, Apache-2.0):
           KOKORO_MODEL and KOKORO_VOICES point at the downloaded files
  mock     a quiet tone per word, for the offline tests

Every voice is synthetic and every call is simulated; the UI says so.
"""
from __future__ import annotations

import base64
import io
import os

import numpy as np

RATE = 24000
VOICES = {"pj": "af_heart", "office": "am_michael", "office_2": "bf_emma", "office_3": "am_eric"}


class TTSOff(RuntimeError):
    pass


def mode() -> str:
    return os.getenv("VOICE_TTS", "off").strip().lower()


def label() -> str:
    m = mode()
    return {"baseten": "open TTS on Baseten", "local": "Kokoro-82M (open weights), run locally", "mock": "mock tones"}.get(m, "off")


_LOCAL = None


def synthesize(text: str, voice: str, speed: float = 1.0) -> np.ndarray:
    """Returns int16 mono PCM at 24 kHz."""
    m = mode()
    if m == "mock":
        n = max(1, len(text.split()))
        t = np.arange(int(RATE * 0.12 * n)) / RATE
        return (np.sin(2 * np.pi * (220 if voice == VOICES["pj"] else 330) * t) * 1200).astype(np.int16)
    if m == "local":
        global _LOCAL
        if _LOCAL is None:
            from kokoro_onnx import Kokoro
            _LOCAL = Kokoro(os.environ["KOKORO_MODEL"], os.environ["KOKORO_VOICES"])
        audio, sr = _LOCAL.create(text, voice=voice, speed=speed, lang="en-us")
        return _resample((np.clip(audio, -1, 1) * 32767).astype(np.int16), sr)
    if m == "baseten":
        import httpx
        r = httpx.post(os.environ["BASETEN_TTS_URL"], headers={"Authorization": f"Api-Key {os.environ.get('BASETEN_API_KEY', '')}"},
                       json={"text": text, "voice": voice, "speed": speed}, timeout=120)
        r.raise_for_status()
        data = r.json()
        wav = base64.b64decode(data.get("audio") or data.get("base64") or "")
        import soundfile as sf
        audio, sr = sf.read(io.BytesIO(wav), dtype="int16")
        return _resample(audio if audio.ndim == 1 else audio[:, 0], sr)
    raise TTSOff("Text to speech is off (VOICE_TTS=off) until the hackathon rules on non-Meta TTS are confirmed.")


def _resample(pcm: np.ndarray, sr: int) -> np.ndarray:
    if sr == RATE:
        return pcm
    idx = np.linspace(0, len(pcm) - 1, int(len(pcm) * RATE / sr))
    return np.interp(idx, np.arange(len(pcm)), pcm.astype(np.float32)).astype(np.int16)
