"""Measure the reader agent: Muse Spark vision on the fictional sample documents,
field by field against the ground truth in src/sim/documents.py.

    python scripts/eval_reader.py            # live (needs MODEL_API_KEY); 3 vision requests
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.agents import reader  # noqa: E402
from src.sim.documents import SAMPLES  # noqa: E402


def _eq(a, b) -> bool:
    if isinstance(b, float):
        return isinstance(a, (int, float)) and abs(a - b) < 0.01
    if isinstance(b, str):
        return reader._norm(str(a)) == reader._norm(b)
    if isinstance(b, list):
        return isinstance(a, list) and len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    if isinstance(b, dict):
        return isinstance(a, dict) and all(_eq(a.get(k), v) for k, v in b.items())
    return a == b


async def main() -> int:
    total = right = 0
    for kind, s in SAMPLES.items():
        img = ROOT / "src" / "api" / "static" / "samples" / s["file"]
        url = "data:image/png;base64," + base64.b64encode(img.read_bytes()).decode()
        got = await reader.read(kind, image=url, account="eval")
        for k, want in s["truth"].items():
            ok = _eq(got.get(k), want)
            total, right = total + 1, right + ok
            if not ok:
                print(f"  MISS {kind}.{k}: got {json.dumps(got.get(k))[:160]}")
        print(f"{kind}: read; dropped by validation: {got['_dropped'] or 'nothing'}")
    print(f"field accuracy: {right}/{total} ({100 * right / total:.0f}%)")
    return 0 if right == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
