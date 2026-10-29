"""Measure Meta's speech-to-text where calls fail: names, dates of birth, reference numbers.

    VOICE_TTS=local KOKORO_MODEL=... KOKORO_VOICES=... python scripts/eval_asr.py --n 60

Each office line is synthesized (open-weights TTS, four voices, some fast) and
transcribed by muse-voice-transcribe-1.0. Reports word error rate and exact
entity accuracy per kind; merges into docs/evals/voice.json. Simulated, synthetic voices.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import voice, voice_tts  # noqa: E402
from src.eval import asr, evals_md  # noqa: E402

VOICES = ["am_michael", "bf_emma", "af_bella", "am_eric"]


_TTS = asyncio.Lock()  # one synthesis at a time: the local model is big; transcription runs in parallel


async def one(u: dict, sem: asyncio.Semaphore) -> dict:
    async with _TTS:
        pcm = await asyncio.to_thread(voice_tts.synthesize, u["text"], VOICES[u["voice"]], u["speed"])
    print(f"  {u['id']} synthesized", flush=True)
    async with sem:
        hyp, how = await voice.transcribe_pcm24k(pcm.tobytes())
    return {**u, "heard": hyp, "how": how, "wer": round(asr.wer(u["text"], hyp), 4), "entity_ok": asr.check(u, hyp),
            "audio_seconds": round(len(pcm) / voice_tts.RATE, 2)}


async def run(us: list[dict]) -> list[dict]:
    sem = asyncio.Semaphore(6)
    return await asyncio.gather(*(one(u, sem) for u in us))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    if voice_tts.mode() == "off":
        print("VOICE_TTS is off. Set VOICE_TTS=local (or baseten) to synthesize the test lines.")
        return 2
    t0 = time.time()
    rows = asyncio.run(run(asr.utterances(a.n)))
    out = {"wer": {}, "entity_accuracy": {}, "by_speed": {}}
    for k in ("name", "dob", "reference"):
        rs = [r for r in rows if r["kind"] == k]
        out["wer"][k] = round(statistics.mean(r["wer"] for r in rs), 4)
        out["entity_accuracy"][k] = round(sum(r["entity_ok"] for r in rs) / len(rs), 4)
    for sp in sorted({r["speed"] for r in rows}):
        rs = [r for r in rows if r["speed"] == sp]
        out["by_speed"][str(sp)] = round(sum(r["entity_ok"] for r in rs) / len(rs), 4)
    secs = sum(r["audio_seconds"] for r in rows)
    print(f"{'kind':10} {'WER':>6} {'entity right':>13}")
    for k in out["wer"]:
        print(f"{k:10} {out['wer'][k] * 100:5.1f}% {out['entity_accuracy'][k] * 100:12.1f}%")
    print("by speed:", out["by_speed"], "· routes:", {h: sum(r["how"] == h for r in rows) for h in ("realtime", "file")})
    for r in rows:
        if not r["entity_ok"]:
            print(f"  MISS {r['kind']:9} said: {r['text']!r}  heard: {r['heard']!r}")
    path = ROOT / "docs" / "evals" / "voice.json"
    prev = json.loads(path.read_text()) if path.exists() else {}
    asr_cost = round(secs / 3600 * 0.18, 4)  # $0.18 per audio hour (Meta docs)
    prev.update({"asr": {**out, "lines": len(rows), "audio_seconds": round(secs, 1), "date": time.strftime("%Y-%m-%d"),
                         "tts": voice_tts.label(), "stt": voice.MODEL, "cost_usd": asr_cost,
                         "routes": {h: sum(r["how"] == h for r in rows) for h in ("realtime", "file")}, "rows": rows},
                 "wer": out["wer"]})
    path.write_text(json.dumps(prev, indent=1))
    evals_md.log_spend("ASR eval", f"{len(rows)} synthesized lines, {round(secs)} s of audio", by_provider={"meta": asr_cost})
    evals_md.write()
    print(f"{round(time.time() - t0)}s · {round(secs)} s of audio · ${asr_cost}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
