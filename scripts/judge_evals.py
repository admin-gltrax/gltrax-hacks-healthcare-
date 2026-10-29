"""Cross-family judging of gym calls and every appeal on file.

    python scripts/judge_evals.py --calls 96         # a stratified sample of the latest gym run + every appeal
    MOCK_LLM=1 python scripts/judge_evals.py --calls 8

Judges: Muse Spark on Meta ("judge") and Muse Spark Open on Fireworks ("judge_open";
JUDGE_OPEN_PROVIDER=baseten to switch). Writes docs/evals/judges.json; rebuilds docs/evals.md.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PJ_AI_DAILY_REQUESTS", "100000")
os.environ.setdefault("PJ_AI_ACCOUNT_REQUESTS", "100000")
from src.config import role_cfg  # noqa: E402
from src.eval import evals_md, judges  # noqa: E402
from src.eval.spend import USAGE  # noqa: E402

EVALS = ROOT / "docs" / "evals"


def gym_sample(n: int) -> list[dict]:
    rep = json.loads((EVALS / "gym-report.json").read_text())
    rows = [json.loads(x) for x in gzip.open(ROOT / "recordings" / "gym" / f"{rep['run']}.jsonl.gz", "rt")]
    by_kind = defaultdict(list)
    for r in rows:
        if "error" not in r:
            by_kind[r["kind"]].append(r)
    out, i = [], 0
    while len(out) < n and any(by_kind.values()):  # round-robin over personas: an even, stratified sample
        k = sorted(by_kind)[i % len(by_kind)]
        if by_kind[k]:
            out.append(by_kind[k].pop(0))
        i += 1
    return out


def appeals() -> list[dict]:
    """Every appeal letter on file: each stress-test run's first draft, its revisions and its final letter."""
    items = []
    for p in sorted(EVALS.glob("reviewer-*.json")):
        r = json.loads(p.read_text())
        rv = r.get("review") or {}
        if "facts" not in r:
            continue  # older runs didn't save the facts the writer had
        facts = {**r["facts"], "plan_rules": [x["rule"] for x in rv.get("rules", [])], "evidence_on_file": r["evidence"]}
        name = p.stem.replace("reviewer-", "")
        if rv.get("original"):
            items.append(judges.appeal_item(f"appeal-{name}-draft", rv["original"], facts))
        for x in rv.get("rounds", []):
            if x.get("revision"):
                items.append(judges.appeal_item(f"appeal-{name}-revision{x['round']}", x["revision"]["body"], facts))
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calls", type=int, default=96)
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()
    items = [judges.call_item(r) for r in gym_sample(a.calls)] + appeals()
    print(f"{len(items)} items · judges {role_cfg('judge').model} (Meta) and {role_cfg('judge_open').model}")
    t0 = time.time()
    rows = asyncio.run(judges.run(items, a.concurrency))
    ag = judges.agreement(rows)
    print(f"kappa {ag['kappa']:.2f} · agreement {ag['agreement'] * 100:.1f}% · {ag['decisions']} decisions · "
          f"{len(ag['disagreements'])} disagreements · {ag['errors']} errored · {round(time.time() - t0)}s · ${USAGE.cost():.3f}")
    for k, v in ag["per_criterion"].items():
        print(f"  {k:28} kappa {v['kappa'] if v['kappa'] is not None else 'n/a':>6}  agree {v['agreement'] * 100:5.1f}%  "
              f"meta pass {v['meta_pass'] * 100:5.1f}%  open pass {v['open_pass'] * 100:5.1f}%")
    if os.getenv("MOCK_LLM") == "1":
        return 0
    out = {**ag, "date": time.strftime("%Y-%m-%d"), "models": {"meta": role_cfg("judge").model, "open": role_cfg("judge_open").model},
           "rubric": {"call": judges.CALL_RUBRIC, "appeal": judges.APPEAL_RUBRIC}, "cost_usd": USAGE.cost(), "rows": rows}
    (EVALS / "judges.json").write_text(json.dumps(out, indent=1))
    evals_md.log_spend("judges", f"{len(items)} items x 2 judges", USAGE)
    evals_md.write()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
