"""A simulated voice call with a real audio loop.

VoiceLine wraps an office line (pcp_office.OfficeLine or a gym persona's GymLine).
Everything the office says is synthesized in an office voice, then transcribed by
Meta's Muse Voice Transcribe, and the caller (Muse Spark) gets ONLY that transcript,
so mishearing a name, a date of birth or a reference number is a real failure mode.
The caller's own lines are synthesized in PJ's voice. Markers like "[on hold 12
minutes]" stay text; they aren't speech.

The result is one audio track plus captions (who spoke, what they said, and what
the caller heard), ready for the browser. Simulated call, synthetic voices.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np

from . import voice, voice_tts

_MARKER = re.compile(r"(\[[^\]]*\])")
GAP = 0.35  # seconds of silence between turns
HOLD = 1.2  # a hold is shown, not played in full


@dataclass
class Segment:
    speaker: str  # "pj" | "office" | "hold" | "menu"
    said: str
    heard: str | None = None  # what Meta's speech-to-text gave the caller (office lines only)
    start: float = 0.0
    end: float = 0.0
    how: str | None = None  # "realtime" | "file" | "mock"


@dataclass
class Recording:
    segments: list[Segment] = field(default_factory=list)
    audio: list[np.ndarray] = field(default_factory=list)
    t: float = 0.0

    def add(self, seg: Segment, pcm: np.ndarray | None, seconds: float | None = None) -> None:
        dur = len(pcm) / voice_tts.RATE if pcm is not None else (seconds or 0.0)
        seg.start, seg.end = round(self.t, 2), round(self.t + dur, 2)
        self.segments.append(seg)
        self.audio.append(pcm if pcm is not None else np.zeros(int(dur * voice_tts.RATE), np.int16))
        self.audio.append(np.zeros(int(GAP * voice_tts.RATE), np.int16))
        self.t += dur + GAP

    def track(self) -> np.ndarray:
        return np.concatenate(self.audio) if self.audio else np.zeros(1, np.int16)

    def peaks(self, n: int = 600) -> list[float]:
        a = np.abs(self.track().astype(np.float32))
        if len(a) < n:
            return [0.0] * n
        chunks = np.array_split(a, n)
        top = max(1.0, float(a.max()))
        return [round(float(c.max()) / top, 3) for c in chunks]

    def write(self, path_base) -> list[str]:
        """Writes <base>.ogg (small) and <base>.wav (16 kHz, plays everywhere). Returns the file names."""
        import soundfile as sf
        pcm = self.track()
        sf.write(f"{path_base}.ogg", pcm, voice_tts.RATE, format="OGG", subtype="VORBIS")
        idx = np.linspace(0, len(pcm) - 1, int(len(pcm) * 16000 / voice_tts.RATE))
        sf.write(f"{path_base}.wav", np.interp(idx, np.arange(len(pcm)), pcm.astype(np.float32)).astype(np.int16), 16000, subtype="PCM_16")
        return [f"{path_base}.ogg", f"{path_base}.wav"]


class VoiceLine:
    """The office side of a voice call. Proxies everything else to the wrapped line."""

    def __init__(self, line, rec: Recording | None = None, office_voices: list[str] | None = None, speed: float = 1.0):
        self._line = line
        self.rec = rec or Recording()
        self.voices = office_voices or [voice_tts.VOICES["office"], voice_tts.VOICES["office_2"], voice_tts.VOICES["office_3"]]
        self.speed = speed

    def __getattr__(self, k):
        return getattr(self._line, k)

    def _voice(self) -> str:
        return self.voices[max(0, len(self._line.reached) - 1) % len(self.voices)]

    async def _hear(self, text: str, speaker: str = "office") -> str:
        """Speak `text` in the office voice, transcribe it, return what the caller hears (markers kept)."""
        out = []
        for part in _MARKER.split(text):
            if not part.strip():
                continue
            if _MARKER.fullmatch(part.strip()):
                if "hold" in part:
                    self.rec.add(Segment("hold", part.strip("[] ")), None, HOLD)
                out.append(part.strip())
                continue
            pcm = voice_tts.synthesize(part.strip(), self._voice(), self.speed)
            try:
                heard, how = await voice.transcribe_pcm24k(pcm.tobytes())
            except voice.TranscribeError:
                heard, how = part.strip(), "mock"  # offline: the mock hears perfectly
            self.rec.add(Segment(speaker, part.strip(), heard, how=how), pcm)
            out.append(heard)
        return " ".join(out)

    def opening(self) -> str:
        return self._line.opening()  # read aloud in OfficeCall.run via hear_opening()

    async def hear_opening(self) -> str:
        return await self._hear(self._line.opening(), "menu")

    async def press(self, digits: str):
        text, hold = self._line.press(digits)
        self.rec.add(Segment("pj", f"[pressed {str(digits)[:1]}]"), None, 0.4)
        return await self._hear(text, "menu" if self._line.state == "ivr" else "office"), hold

    async def say(self, caller_text: str):
        self.rec.add(Segment("pj", caller_text), voice_tts.synthesize(caller_text, voice_tts.VOICES["pj"], 1.0))
        reply, hold, ended = await self._line.say(caller_text)
        return await self._hear(reply) if reply else reply, hold, ended


def captions(rec: Recording) -> list[dict]:
    return [{"speaker": s.speaker, "said": s.said, "heard": s.heard, "start": s.start, "end": s.end, "how": s.how} for s in rec.segments]


def wav_bytes(pcm: np.ndarray, rate: int = voice_tts.RATE) -> bytes:
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, pcm, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()
