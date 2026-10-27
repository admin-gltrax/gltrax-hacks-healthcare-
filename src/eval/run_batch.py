"""Batch evaluation CLI.

    python -m src.eval.run_batch --n 40 --split dev --k 8
    python -m src.eval.run_batch --swarm          # the fixed 15-office demo swarm

Each eval call gets its own blackboard (no cross-talk). Results are written to
data/runs/ with the prompt and safety hashes so iterations can be compared.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

from ..agents.worker import DEFAULT_PROMPT
from ..safety import SAFETY_SHA
from ..sim.scenarios import DEMO_PATIENT, make_scenarios, swarm_demo_scenarios
from ..swarm.dispatcher import run_swarm
from ..swarm.events import EventBus
from ..schemas import Constraints


def summarize(scenarios, out) -> dict:
    per: dict[str, list[bool]] = defaultdict(list)
    for s, sc in zip(out.scores, scenarios):
        per[s.persona].append(s.success)
    n = max(1, len(out.scores))
    return {
        "calls": len(out.scores),
        "success_rate": round(sum(s.success for s in out.scores) / n, 3),
        "safety_pass_rate": round(sum(s.safety_ok for s in out.scores) / n, 3),
        "errors": sum(1 for r in out.results if r.error),
        "per_persona": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(per.items())},
        "truth_delta": out.truth,
    }


async def amain(args) -> None:
    prompt_path = Path(args.prompt)
    prompt_text = prompt_path.read_text()
    if args.swarm:
        scenarios, shared = swarm_demo_scenarios(), True
    else:
        scenarios = [s for s in make_scenarios(args.n, seed=args.seed) if args.split == "all" or s.split == args.split]
        shared = False
    constraints = Constraints()
    bus = EventBus()
    t0 = time.time()
    out = await run_swarm(scenarios, DEMO_PATIENT, constraints, bus=bus, k=args.k, shared_blackboard=shared, prompt_text=prompt_text, stagger_s=args.stagger)
    summary = summarize(scenarios, out)
    summary.update(
        elapsed_s=round(time.time() - t0, 1),
        prompt=str(prompt_path),
        prompt_sha=hashlib.sha256(prompt_text.encode()).hexdigest()[:12],
        safety_sha=SAFETY_SHA[:12],
        mode="swarm" if args.swarm else f"eval/{args.split}",
        best=out.best.model_dump() if out.best else None,
    )
    print(json.dumps(summary, indent=2))
    for s in out.scores:
        if not s.success or not s.safety_ok:
            print(f"  FAIL {s.office_id} [{s.persona}]: {'; '.join(s.notes)}")
    run_dir = Path("data/runs")
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (run_dir / f"{stamp}-summary.json").write_text(json.dumps(summary, indent=2))
    (run_dir / f"{stamp}-calls.json").write_text(json.dumps([r.model_dump() for r in out.results], indent=2))
    bus.dump(run_dir / f"{stamp}-events.jsonl")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    p.add_argument("--k", type=int, default=8, help="max concurrent calls")
    p.add_argument("--stagger", type=float, default=0.05)
    p.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    p.add_argument("--swarm", action="store_true", help="run the fixed 15-office demo with a shared blackboard")
    asyncio.run(amain(p.parse_args()))


if __name__ == "__main__":
    main()
