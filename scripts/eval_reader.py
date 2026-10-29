"""Measure the reader agent: Muse Spark vision on 33 fictional documents (denial
letters, itemized bills, EOBs; src/sim/documents.py), clean and as messy phone
photos, field by field against the ground truth.

    python scripts/make_sample_docs.py        # renders data/reader_eval/*.png first
    python scripts/eval_reader.py             # live: 33 documents x 4 levels = 132 vision requests (needs MODEL_API_KEY)
    python scripts/eval_reader.py --levels clean --limit 6
    MOCK_LLM=1 python scripts/eval_reader.py  # offline plumbing check (the mock reads the truth)

Messiness (PIL, deterministic per document):
  clean    the rendered page
  phone    2 degree tilt, slight blur, a little dim, JPEG quality 70
  messy    -4.5 degree tilt, blur, low light, JPEG quality 40, margins cropped
  harsh    7 degree tilt, heavy blur, very low light, sensor noise, JPEG quality 18, cropped tight
Prints a table and writes docs/evals/reader.json; docs/evals.md is rebuilt from it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PJ_AI_DAILY_REQUESTS", "100000")
os.environ.setdefault("PJ_AI_ACCOUNT_REQUESTS", "100000")
from src.agents import ai, reader  # noqa: E402
from src.config import role_cfg  # noqa: E402
from src.eval import evals_md  # noqa: E402
from src.eval.messy import LEVELS, data_url, messy  # noqa: E402
from src.eval.spend import USAGE  # noqa: E402
from src.sim.documents import SAMPLES, eval_documents  # noqa: E402

DOCS = ROOT / "data" / "reader_eval"


def _eq(a, b) -> bool:
    if isinstance(b, bool):
        return a is b
    if isinstance(b, float):
        return isinstance(a, (int, float)) and abs(a - b) < 0.01
    if isinstance(b, int):
        return isinstance(a, int) and a == b
    if isinstance(b, str):
        return reader._norm(str(a or "")) == reader._norm(b)
    if isinstance(b, list):
        return isinstance(a, list) and len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    if isinstance(b, dict):
        return isinstance(a, dict) and all(_eq(a.get(k), v) for k, v in b.items())
    return a == b


async def read_one(doc: dict, level: str, sem: asyncio.Semaphore) -> dict:
    img = Image.open(doc.get("path") or DOCS / doc["file"])
    url = data_url(messy(img, level, doc["file"]))
    async with sem:
        t = time.monotonic()
        try:
            got = await reader.read(doc["kind"], image=url, account="eval")
            err = None
        except (ai.AIUnavailable, reader.ReadError) as e:
            got, err = {}, str(e)[:200]
    fields = {k: _eq(got.get(k), want) for k, want in doc["truth"].items()}
    return {"file": doc["file"], "kind": doc["kind"], "level": level, "tags": doc.get("tags", []), "fields": fields,
            "misses": {k: got.get(k) for k, ok in fields.items() if not ok}, "dropped": got.get("_dropped", []),
            "error": err, "seconds": round(time.monotonic() - t, 2)}


async def run(docs: list[dict], levels: list[str], concurrency: int) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    return await asyncio.gather(*(read_one(d, lv, sem) for d in docs for lv in levels))


def summarize(rows: list[dict]) -> dict:
    by_level, by_field, by_kind = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in rows:
        for f, ok in r["fields"].items():
            for bucket, key in ((by_level, r["level"]), (by_field, f"{r['kind']}.{f}"), (by_kind, r["kind"])):
                bucket[key][0] += ok
                bucket[key][1] += 1
    right, total = sum(v[0] for v in by_level.values()), sum(v[1] for v in by_level.values())
    fmt = lambda d: {k: {"right": v[0], "total": v[1]} for k, v in d.items()}  # noqa: E731
    return {"overall": round(right / max(1, total), 4), "right": right, "total": total,
            "by_level": fmt({k: by_level[k] for k in LEVELS if k in by_level}), "by_kind": fmt(by_kind), "by_field": fmt(dict(sorted(by_field.items())))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default=",".join(LEVELS))
    ap.add_argument("--limit", type=int, default=0, help="first N documents only")
    ap.add_argument("--concurrency", type=int, default=12)
    a = ap.parse_args()
    if not (DOCS / "denial-01.png").exists():
        print("Render the documents first: python scripts/make_sample_docs.py")
        return 2
    docs = eval_documents()[: a.limit or None]
    if os.getenv("MOCK_LLM") == "1":  # the offline mock reads the three demo samples' truth; score those instead
        docs = [{"kind": k, "file": s["file"], "truth": s["truth"], "path": ROOT / "src" / "api" / "static" / "samples" / s["file"]}
                for k, s in SAMPLES.items()]
    levels = [lv for lv in a.levels.split(",") if lv in LEVELS]
    t0 = time.time()
    rows = asyncio.run(run(docs, levels, a.concurrency))
    s = summarize(rows)
    print(f"{'level':8} {'fields right':>14} {'accuracy':>9}")
    for k, v in s["by_level"].items():
        print(f"{k:8} {v['right']:>6}/{v['total']:<7} {100 * v['right'] / v['total']:8.1f}%")
    print("\nworst fields:")
    for k, v in sorted(s["by_field"].items(), key=lambda kv: kv[1]["right"] / kv[1]["total"])[:8]:
        print(f"  {k:32} {v['right']}/{v['total']}")
    errors = [r for r in rows if r["error"]]
    print(f"\noverall {100 * s['overall']:.1f}% · {len(rows)} reads · {len(errors)} errors · {round(time.time() - t0)}s · ${USAGE.cost():.3f}")
    if os.getenv("MOCK_LLM") == "1":
        return 0
    out = {**s, "date": time.strftime("%Y-%m-%d"), "model": role_cfg("reader").model, "documents": len(docs), "reads": len(rows),
           "levels": levels, "errors": len(errors), "cost_usd": USAGE.cost(), "misses": [r for r in rows if r["misses"]][:60]}
    (ROOT / "docs" / "evals").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "evals" / "reader.json").write_text(json.dumps(out, indent=1, default=str))
    evals_md.log_spend("reader eval", f"{len(rows)} vision reads", USAGE)
    evals_md.write()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
