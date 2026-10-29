"""The call gym: hundreds of fictional offices vs. PJ's real caller.

    python scripts/call_gym.py --n 10 --pilot          # measure cost per call, project the spend, write nothing big
    python scripts/call_gym.py --n 600 --concurrency 24
    MOCK_LLM=1 python scripts/call_gym.py --n 32       # offline plumbing check

The caller is Muse Spark on Meta. The receptionists default to Muse Spark Open on
Fireworks (OFFICE_PROVIDER, set here unless you set it). Writes
recordings/gym/<run>.jsonl.gz (every transcript) and docs/evals/gym-report.json,
which /gym shows. Refuses a run projected over --max-usd (default $25).
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("OFFICE_PROVIDER", "fireworks")
os.environ.setdefault("PJ_AI_DAILY_REQUESTS", "200000")
os.environ.setdefault("PJ_AI_ACCOUNT_REQUESTS", "200000")

from src.config import role_cfg  # noqa: E402
from src.eval import evals_md  # noqa: E402
from src.eval import gym as runner  # noqa: E402
from src.sim import gym  # noqa: E402


def runner_provider() -> str:
    from src.config import provider_for
    return provider_for("office")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--start", type=int, default=0, help="first persona index (to extend a run)")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--caller-rpm", type=int, default=1500, help="Meta's limit is 3,000 RPM per team; keep headroom")
    ap.add_argument("--office-rpm", type=int, default=600)
    ap.add_argument("--pilot", action="store_true", help="small run: print cost per call and the projection")
    ap.add_argument("--kinds", default="", help="comma-separated persona kinds: re-run only those (a check, not the headline run)")
    ap.add_argument("--project", type=int, default=600, help="calls to project the spend for")
    ap.add_argument("--max-usd", type=float, default=25.0)
    ap.add_argument("--per-call-usd", type=float, default=None, help="measured pilot cost per call, to gate a big run")
    a = ap.parse_args()

    if evals_md.over_limit():
        print(f"refusing: a partner credit is at 70%: {evals_md.spent()}. Ask first.")
        return 3
    if a.per_call_usd is not None and a.per_call_usd * a.n > a.max_usd:
        print(f"refusing: {a.n} calls x ${a.per_call_usd:.4f} = ${a.per_call_usd * a.n:.2f} > ${a.max_usd:.2f}. Ask first.")
        return 3
    personas = gym.make_personas(a.start + a.n, a.seed)[a.start:]
    if a.kinds:
        personas = [p for p in personas if p["kind"] in a.kinds.split(",")]
        a.pilot, a.n = True, len(personas)  # a targeted re-check never replaces the headline report
    cfg = {"caller": role_cfg("caller").model, "office": role_cfg("office").model, "office_host": role_cfg("office").base_url}
    print(f"{a.n} calls · caller {cfg['caller']} (Meta) · receptionists {cfg['office']} · concurrency {a.concurrency}")
    t0, n_done = time.time(), [0]

    def tick(row):
        n_done[0] += 1
        if n_done[0] % 25 == 0 or a.n <= 25:
            flag = "ERR " + row["error"][:60] if "error" in row else ("safe" if row["safe"] else "UNSAFE " + str([k for k, v in row["safety"].items() if not v]))
            print(f"  {n_done[0]:4}/{a.n} {row['kind']:18} {flag}", flush=True)

    rows = asyncio.run(runner.run(personas, a.concurrency, a.caller_rpm, a.office_rpm, on_done=tick))
    wall = round(time.time() - t0, 1)
    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-s{a.seed}-n{a.n}" + ("-pilot" if a.pilot else "")
    rep = runner.report(rows, {"run": run_id, "date": time.strftime("%Y-%m-%d"), "seed": a.seed, "start": a.start, "wall_seconds": wall,
                               "concurrency": a.concurrency, "models": cfg, "caller_prompt_sha": hashlib.sha256((ROOT / "prompts" / "office_caller_v0.txt").read_bytes()).hexdigest()[:12],
                               "mock": os.getenv("MOCK_LLM") == "1"})
    print(runner.markdown(rep))
    per = rep["cost_usd"]["per_call"]
    print(f"\nwall {wall}s · spent ${rep['cost_usd']['total']:.4f} · projected {a.project} calls: ${per * a.project:.2f}")
    out = ROOT / "recordings" / "gym" / ("mock" if os.getenv("MOCK_LLM") == "1" else "")
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / f"{run_id}.jsonl.gz", "wt") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    if not a.pilot and os.getenv("MOCK_LLM") != "1":
        (ROOT / "docs" / "evals").mkdir(parents=True, exist_ok=True)
        (ROOT / "docs" / "evals" / "gym-report.json").write_text(json.dumps(rep, indent=1))
    else:
        (out / f"{run_id}.report.json").write_text(json.dumps(rep, indent=1))
    if os.getenv("MOCK_LLM") != "1":
        evals_md.log_spend("call gym" + (" check" if a.pilot else ""), f"{len(rows)} calls, seed {a.seed}" + (f", kinds {a.kinds}" if a.kinds else ""),
                           by_provider={"meta": rep["cost_usd"]["caller_meta"], runner_provider(): rep["cost_usd"]["office_partner"]})
        evals_md.write()
    print(f"transcripts: {(out / run_id).relative_to(ROOT)}.jsonl.gz")
    return 0 if rep["safety_pass_rate"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
