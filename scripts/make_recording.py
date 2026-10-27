"""Record a 15-office swarm run for the public replay (recordings/demo.jsonl).

    python scripts/make_recording.py              # real models (needs MODEL_API_KEY)
    MOCK_LLM=1 python scripts/make_recording.py   # scripted models; the replay banner says so

Run it with the real models once the worker prompt is calibrated, review the
result on the dashboard, then commit recordings/demo.jsonl. Judges and teammates
can then watch the replay with no credentials and no spend.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import mock_enabled, role_cfg  # noqa: E402
from src.schemas import Constraints  # noqa: E402
from src.sim.scenarios import DEMO_PATIENT, swarm_demo_scenarios  # noqa: E402
from src.swarm.dispatcher import run_swarm  # noqa: E402
from src.swarm.events import EventBus  # noqa: E402

REQUEST = "I need a cardiologist in network, as soon as possible, but nothing before 9 in the morning."


async def main(out: Path) -> None:
    bus = EventBus()
    c = Constraints()
    bus.publish("patient_request", utterance=REQUEST, constraints=c.model_dump())
    res = await run_swarm(swarm_demo_scenarios(), DEMO_PATIENT, c, bus=bus, k=15, shared_blackboard=True)

    meta = {
        "type": "recording_meta",
        "source": "mock" if mock_enabled() else "meta-model-api",
        "models": None if mock_enabled() else {r: role_cfg(r).model for r in ("worker", "office")},
        "recorded_at": time.strftime("%Y-%m-%d"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        f.write(json.dumps(meta) + "\n")
        for ev in bus.history:
            f.write(json.dumps(ev) + "\n")

    ok = sum(s.success for s in res.scores)
    print(f"wrote {out} ({len(bus.history)} events, source={meta['source']})")
    print(f"success {ok}/{len(res.scores)}, safety {sum(s.safety_ok for s in res.scores)}/{len(res.scores)}, best={res.best.slot_start if res.best else None}")
    if os.getenv("MOCK_LLM") == "1":
        print("NOTE: this is a mock recording. Re-run without MOCK_LLM once the real models are calibrated.")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "recordings" / "demo.jsonl"))
