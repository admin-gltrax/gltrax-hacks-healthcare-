"""Live: the full prior-auth appeal on Meta's models, then the insurer-side
reviewer (Muse Spark Open on partner credits) tries to deny it.

    python scripts/stress_test_appeal.py                    # Rosa's denial letter, full evidence on file
    python scripts/stress_test_appeal.py --thin             # same letter, records stripped: the reviewer should win
    python scripts/stress_test_appeal.py --standard         # start from the generic standard letter (writer revises it)
    python scripts/stress_test_appeal.py --strong --standard   # a file that meets the rules, a letter that doesn't say so
    REVIEWER_PROVIDER=fireworks python scripts/stress_test_appeal.py

Writes docs/evals/reviewer-<scenario>.json (rounds, objections, each revision, cost).
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
os.environ.setdefault("PJ_BACKGROUND", "0")
os.environ.setdefault("PJ_AI_ACCOUNT_REQUESTS", "400")

from src.agents import ai, workflows  # noqa: E402
from src.config import role_cfg  # noqa: E402
from src.eval.spend import USAGE  # noqa: E402
from src.patient.demo import build_demo  # noqa: E402
from src.patient.models import HealthRecord, Patient  # noqa: E402


STRONG = [  # fictional records that speak to each of the plan's four rules
    ("Home health plan of care certified and signed by Dr. Samuel Okafor (physical therapy, 12 visits)", "2026-10-14"),
    ("Physical therapy evaluation: needs a walker and one person's help to leave home; leaving home takes a taxing effort", "2026-10-10"),
    ("Physical therapy evaluation: balance and walking have declined since the fall; skilled therapy can restore them", "2026-10-10"),
    ("Doctor's note: outpatient therapy isn't safe for her right now because of fall risk on stairs and in transit", "2026-10-14"),
]


def rosa(thin: bool, strong: bool = False) -> HealthRecord:
    acct = asyncio.run(build_demo(HealthRecord(patient=Patient(display_name="Alex Rivera"))))
    rec = acct.circle[0].record
    if thin:  # nothing in the records speaks to being homebound or to a plan of care
        rec.items = [i for i in rec.items if i.bucket.value != "clinicals"][:1]
        rec.risk_factors = []
    if strong:
        from src.patient.models import Bucket, HealthItem
        rec.items += [HealthItem(bucket=Bucket("clinicals"), kind="visit", title=t, when=w, source="demo", confidence="confirmed")
                      for t, w in STRONG]
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thin", action="store_true")
    ap.add_argument("--standard", action="store_true")
    ap.add_argument("--strong", action="store_true")
    a = ap.parse_args()
    if a.standard:  # the first draft is the generic template; the reviewer and writer take it from there
        workflows.TEMPLATES["pa_appeal"].run["draft"] = workflows._pa_draft_rules
    if not ai.role_ready("reviewer"):
        print(f"reviewer not ready: set {role_cfg('reviewer').api_key_env}")
        return 2
    t = time.time()
    rec = rosa(a.thin, a.strong)
    wf = workflows.start(rec, "pa_appeal", {"document": {"sample": "denial_letter"}}, account="stress-test")
    secs = round(time.time() - t, 1)
    for s in wf.steps:
        print(f"{s.key:9} {s.status:9} {s.engine or '-':45} {(s.detail or '')[:140]}")
    rv = wf.review
    for r in rv.get("rounds", []):
        print(f"\nround {r['round']}: {r['verdict']}  (made-up rules dropped: {r['invented_rules_dropped']})")
        for o in r["objections"]:
            print(f"  {o['rule_id']} [{o['fix']}] {o['reason']}  -> needs: {o['needs']}")
        if r.get("revision"):
            print(f"  revision accepted: {r['revision']['accepted']}")
    print("\nto-dos:", rv.get("todos"))
    scenario = "-".join(k for k in ("thin", "strong", "standard") if getattr(a, k)) or "full"
    out = {"scenario": scenario, "seconds": secs, "reviewer": role_cfg("reviewer").model,
           "provider": role_cfg("reviewer").base_url, "steps": [s.model_dump() for s in wf.steps], "review": rv,
           "letter": wf.letter, "usage": USAGE.snapshot(), "cost_usd": USAGE.cost(), "cost_by_provider": USAGE.by_provider()}
    path = ROOT / "docs" / "evals" / f"reviewer-{out['scenario']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    print(f"\n{secs}s  cost ${USAGE.cost():.4f}  {USAGE.by_provider()}  -> {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
