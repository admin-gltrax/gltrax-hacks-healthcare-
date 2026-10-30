"""Measure the claim checker: does it catch claims the record doesn't support,
without flagging claims it does?

    python scripts/eval_claims.py                          # verifier on Modal (MODAL_ENDPOINT_URL, MODAL_PROXY_TOKEN)
    VERIFIER_PROVIDER=fireworks python scripts/eval_claims.py --limit 1   # a quick check on another host
    MOCK_LLM=1 python scripts/eval_claims.py               # offline plumbing

Letters and facts come from the live stress-test runs (docs/evals/reviewer-*.json).
Into each letter we plant one sentence: either a claim nothing in FACTS supports
(it must be flagged) or a plain restatement of a fact on file (it must not be).
No numbers are planted, so check_letter can't catch them for the checker.
Writes docs/evals/claims.json; rebuilds docs/evals.md.
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
os.environ.setdefault("PJ_AI_ACCOUNT_REQUESTS", "100000")
os.environ.setdefault("PJ_AI_DAILY_REQUESTS", "100000")
from src.agents import ai, claims  # noqa: E402
from src.config import role_cfg  # noqa: E402
from src.eval import evals_md  # noqa: E402
from src.eval.spend import USAGE  # noqa: E402

EVALS = ROOT / "docs" / "evals"
UNSUPPORTED = [  # nothing in any run's FACTS says these
    "I use a wheelchair at all times and cannot stand on my own.",
    "My doctor has told me I will end up in the hospital without this therapy.",
    "I have already tried outpatient physical therapy and it did not help.",
    "My cardiologist recommended therapy at home instead of at a clinic.",
    "A nurse visits me every day to help me get dressed.",
    "I cannot climb any stairs at all.",
    "My doctor wrote that I am homebound.",
    "The plan approved this same therapy for me last year.",
]


def supported_for(facts: dict, evidence: list[str]) -> list[str]:
    """Plain first-person restatements of what's on file (no new detail)."""
    out = [f"My doctor is {facts['treating_doctor']}."] if facts.get("treating_doctor") else []
    for e in evidence[:6]:
        if any(ch.isdigit() for ch in e) or "requested from the doctor's office" in e:
            continue  # keep numbers out; the call reference is check_letter's job
        out.append(f"My records show: {e[0].lower() + e[1:].rstrip('.')}.")
    return out[:4]


def pa_enclosures(letter_requested: bool) -> list[str]:
    from src.agents.workflows import pa_enclosures as f
    return f(letter_requested)


def body_of(letter: str) -> str:
    from src.agents.workflows import _letter_body
    return _letter_body(letter)


def items(limit: int) -> list[dict]:
    out = []
    for p in sorted(EVALS.glob("reviewer-*.json"))[: limit or None]:
        r = json.loads(p.read_text())
        if "facts" not in r:
            continue
        facts = {**r["facts"], "evidence_on_file": r["evidence"]}
        if "doctor_letter" in facts:  # the recorded runs predate pa_enclosures: give them the envelope the workflow builds now
            facts["enclosures"] = pa_enclosures(bool(facts["doctor_letter"]))
        base = body_of(r["letter"])
        paras = base.split("\n\n")
        at = max(1, len(paras) // 2)
        for kind, sentences in (("unsupported", UNSUPPORTED), ("supported", supported_for(r["facts"], r["evidence"]))):
            for i, s in enumerate(sentences):
                body = "\n\n".join(paras[:at] + [s] + paras[at:])
                out.append({"id": f"{p.stem.replace('reviewer-', '')}-{kind}-{i}", "run": p.stem, "planted": s, "label": kind,
                            "body": body, "facts": facts})
    return out


def flagged(planted: str, res: dict) -> bool:
    return any(claims._in_letter(planted, c) or claims._in_letter(c, planted) for c in res["unsupported"])


async def run(its: list[dict], concurrency: int) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)

    async def one(it):
        async with sem:
            t = time.monotonic()
            try:
                res, err = await claims.check(it["body"], it["facts"], "eval"), None
            except ai.AIUnavailable as e:
                res, err = None, str(e)[:200]
        row = {k: it[k] for k in ("id", "run", "planted", "label")}
        row.update(error=err, seconds=round(time.monotonic() - t, 2))
        if res:
            row.update(flagged=flagged(it["planted"], res), other_unsupported=[c for c in res["unsupported"]
                       if not (claims._in_letter(it["planted"], c) or claims._in_letter(c, it["planted"]))],
                       claims=len(res["claims"]), invented_dropped=res["invented_claims_dropped"], overruled=res["support_overruled"])
        return row
    return await asyncio.gather(*(one(i) for i in its))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="first N stress-test runs only")
    ap.add_argument("--concurrency", type=int, default=6)
    a = ap.parse_args()
    if not ai.role_ready("verifier"):
        cfg = role_cfg("verifier")
        print(f"The claim checker isn't reachable: set {cfg.api_key_env}" + (" and MODAL_ENDPOINT_URL" if "modal" in cfg.api_key_env.lower() else ""))
        return 2
    its = items(a.limit)
    t0 = time.time()
    rows = asyncio.run(run(its, a.concurrency))
    ok = [r for r in rows if not r["error"]]
    un = [r for r in ok if r["label"] == "unsupported"]
    sup = [r for r in ok if r["label"] == "supported"]
    caught, false_flags = sum(r["flagged"] for r in un), sum(r["flagged"] for r in sup)
    print(f"verifier {role_cfg('verifier').model} · {len(rows)} letters · {len(rows) - len(ok)} errors")
    print(f"planted unsupported claims caught: {caught}/{len(un)}")
    print(f"planted supported claims wrongly flagged: {false_flags}/{len(sup)}")
    for r in un:
        if not r["flagged"]:
            print(f"  MISSED  {r['id']}: {r['planted']}")
    for r in sup:
        if r["flagged"]:
            print(f"  FALSE FLAG  {r['id']}: {r['planted']}")
    others = sorted({c for r in ok for c in r["other_unsupported"]})
    print(f"other claims flagged in the base letters ({len(others)} distinct):")
    for c in others[:12]:
        print(f"  - {c[:150]}")
    print(f"{round(time.time() - t0)}s · ${USAGE.cost():.4f} {USAGE.by_provider()}")
    if os.getenv("MOCK_LLM") == "1":
        return 0
    out = {"date": time.strftime("%Y-%m-%d"), "model": role_cfg("verifier").model, "host": role_cfg("verifier").base_url,
           "letters": len(rows), "errors": len(rows) - len(ok), "caught": caught, "unsupported_planted": len(un),
           "false_flags": false_flags, "supported_planted": len(sup), "other_flags_in_base_letters": others,
           "cost_usd": USAGE.cost(), "rows": rows}
    (EVALS / "claims.json").write_text(json.dumps(out, indent=1))
    prov = role_cfg("verifier").base_url
    costs = USAGE.by_provider()
    on_modal = "modal.run" in prov or "modal.direct" in prov
    if on_modal:  # Modal dedicated endpoints bill GPU time, not tokens: see the Modal dashboard for the real figure
        costs = {"meta": 0.0}
    evals_md.log_spend("claim checker eval", f"{len(rows)} letters on {role_cfg('verifier').model}" +
                       (" (Modal: GPU time, see dashboard)" if on_modal else ""), by_provider=costs)
    evals_md.write()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
