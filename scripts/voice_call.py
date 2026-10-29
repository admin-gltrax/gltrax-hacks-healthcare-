"""One simulated voice call with a real audio loop: the caller (Muse Spark, Meta) hears
the office (Muse Spark Open receptionist) only through Meta's speech-to-text.

    VOICE_TTS=local KOKORO_MODEL=... KOKORO_VOICES=... python scripts/voice_call.py --kind mishears

Writes src/api/static/voice/call.{ogg,wav} and the captions, waveform and checks into
docs/evals/voice.json. /gym plays it (only when the server has VOICE_TTS on).
Simulated call, synthetic voices, fictional people; no phone network is involved.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("OFFICE_PROVIDER", "fireworks")
os.environ.setdefault("PJ_AI_ACCOUNT_REQUESTS", "1000")
from src import voice_loop, voice_tts  # noqa: E402
from src.agents import ai  # noqa: E402
from src.agents.office_caller import OfficeCall  # noqa: E402
from src.eval import evals_md  # noqa: E402
from src.eval.spend import USAGE  # noqa: E402
from src.sim import gym  # noqa: E402


async def call(persona: dict) -> tuple[dict, OfficeCall, voice_loop.VoiceLine]:
    caller, office = ai.llm("caller", "voice"), ai.llm("office", "voice")
    line = voice_loop.VoiceLine(gym.GymLine(persona, office))
    c = OfficeCall(persona["practice"], persona["phone"], persona["purpose"], "", persona["who"], caller, office, max_turns=30, line=line)
    return await c.run(), c, line


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="mishears")
    ap.add_argument("--seed", type=int, default=21)
    a = ap.parse_args()
    if voice_tts.mode() == "off":
        print("VOICE_TTS is off. Set VOICE_TTS=local (or baseten) to make the voices.")
        return 2
    persona = next(p for p in gym.make_personas(64, a.seed) if p["kind"] == a.kind)
    t0 = time.time()
    result, c, line = asyncio.run(call(persona))
    score = gym.score(persona, result, c)
    out_dir = ROOT / "src" / "api" / "static" / "voice"
    out_dir.mkdir(parents=True, exist_ok=True)
    line.rec.write(out_dir / "call")
    caps = voice_loop.captions(line.rec)
    misheard = [x for x in caps if x["heard"] and x["heard"].strip().lower() != x["said"].strip().lower()]
    path = ROOT / "docs" / "evals" / "voice.json"
    prev = json.loads(path.read_text()) if path.exists() else {}
    prev["call"] = {"date": time.strftime("%Y-%m-%d"), "persona": {k: persona[k] for k in ("id", "kind", "practice", "purpose", "who")},
                    "tts": voice_tts.label(), "stt": "muse-voice-transcribe-1.0", "routes": sorted({x["how"] for x in caps if x["how"]}),
                    "caller": ai.model_for("caller"), "office": ai.model_for("office"), "audio": ["/voice/call.ogg", "/voice/call.wav"],
                    "seconds": round(line.rec.t, 1), "captions": caps, "peaks": line.rec.peaks(), "misheard_lines": len(misheard),
                    "result": {k: result[k] for k in ("reference", "reached", "ok", "menu_path")}, "truth_reference": line.reference,
                    "safety": score["safety"], "success": score["success"], "cost_usd": USAGE.cost()}
    prev["note"] = ("Simulated call, synthetic voices. The caller heard the office only through Meta's speech-to-text "
                    f"({'realtime' if 'realtime' in prev['call']['routes'] else 'file transcription, per line'}). "
                    f"Voices: {voice_tts.label()}.")
    path.write_text(json.dumps(prev, indent=1))
    evals_md.log_spend("voice call", f"1 call ({a.kind}), {round(line.rec.t)} s of audio", USAGE)
    evals_md.write()
    print(f"{round(line.rec.t)} s of audio · {len(caps)} segments · {len(misheard)} lines heard differently · reference "
          f"{result['reference']} (truth {line.reference}) · safe {score['safe']} · success {score['success']} · "
          f"{round(time.time() - t0)}s · ${USAGE.cost():.3f}")
    for x in caps:
        if x["speaker"] in ("office", "menu", "pj"):
            print(f"  {x['start']:6.1f} {x['speaker']:6} {x['said'][:110]}" + (f"\n{'':14}heard: {x['heard'][:110]}" if x in misheard else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
