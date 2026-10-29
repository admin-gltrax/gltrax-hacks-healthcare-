"""docs/evals.md: the eval results and the running spend log, rebuilt from
docs/evals/*.json and docs/evals/spend.jsonl by every eval script."""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "docs" / "evals"
SPEND = EVALS / "spend.jsonl"
CREDITS = {"meta": 150.0, "fireworks": 100.0, "baseten": 100.0}  # USD; Meta's is per selected participant
STOP_AT = 0.70  # stop and ask once a partner credit is 70% used


def log_spend(run: str, detail: str, tally=None, by_provider: dict | None = None) -> None:
    EVALS.mkdir(parents=True, exist_ok=True)
    costs = by_provider if by_provider is not None else tally.by_provider()
    with SPEND.open("a") as f:
        f.write(json.dumps({"date": time.strftime("%Y-%m-%d %H:%M"), "run": run, "detail": detail,
                            "usd": {k: round(v, 4) for k, v in costs.items() if v}}) + "\n")


def spent() -> dict[str, float]:
    tot = {k: 0.0 for k in CREDITS}
    if SPEND.exists():
        for line in SPEND.read_text().splitlines():
            for k, v in json.loads(line)["usd"].items():
                tot[k] = tot.get(k, 0.0) + v
    return tot


def over_limit() -> list[str]:
    s = spent()
    return [k for k in ("fireworks", "baseten") if s[k] >= STOP_AT * CREDITS[k]]


def _load(name: str) -> dict | None:
    p = EVALS / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def write() -> Path:
    from .gym import markdown as gym_md
    out = ["# Evals and spend", "", "Every number here comes from a committed run (`docs/evals/*.json`). All data is fictional. "
           "Rebuilt by the eval scripts; don't edit by hand.", ""]
    g = _load("gym-report")
    out += ["## Call gym", ""]
    out += ([f"Run `{g['run']}` on {g['date']}: caller `{g['models']['caller']}` (Meta) vs. receptionists `{g['models']['office']}`. "
             f"Transcripts: `recordings/gym/{g['run']}.jsonl.gz`. Command: `python scripts/call_gym.py --n {g['calls']} --seed {g['seed']}`.", "",
             gym_md(g), ""] if g else ["Not run yet.", ""])
    rv = {k: _load(f"reviewer-{k}") for k in ("full", "thin", "strong-standard")}
    out += ["## Adversarial plan reviewer", "", "| Scenario | Rounds | Final verdict | Revisions | Cost |", "|---|---|---|---|---|"]
    for k, r in rv.items():
        if r and r.get("review", {}).get("rounds") is not None:
            v = r["review"]
            revs = sum(1 for x in v["rounds"] if x.get("revision"))
            out.append(f"| {k} | {len(v['rounds'])} | {'no reason to deny' if v.get('passed') else str(len(v.get('todos', []))) + ' reasons stand'} "
                       f"| {revs} | ${r['cost_usd']:.3f} |")
    out += ["", "Reviewer: Muse Spark Open. Command: `python scripts/stress_test_appeal.py [--thin | --strong --standard]`.", ""]
    j = _load("judges")
    out += ["## Cross-family judges", ""]
    if j:
        out += [f"{j['items']} items judged by `{j['models']['meta']}` (Meta) and `{j['models']['open']}`: "
                f"Cohen's kappa **{j['kappa']:.2f}**, raw agreement {j['agreement'] * 100:.1f}%, "
                f"{len(j['disagreements'])} disagreements listed for human review in `docs/evals/judges.json`.", "",
                "| Rubric item | Kappa | Agreement | Meta pass rate | Open pass rate |", "|---|---|---|---|---|"]
        for k, v in j["per_criterion"].items():
            kappa = "n/a" if v["kappa"] is None else f"{v['kappa']:.2f}"
            out.append(f"| {k.replace('_', ' ')} | {kappa} | {v['agreement'] * 100:.0f}% | {v['meta_pass'] * 100:.0f}% | {v['open_pass'] * 100:.0f}% |")
        out.append("")
    else:
        out += ["Not run yet.", ""]
    rd = _load("reader")
    out += ["## Reader eval", ""]
    if rd:
        out += [f"{rd['documents']} fictional documents x {len(rd['levels'])} messiness levels = {rd['reads']} reads by `{rd['model']}` on {rd['date']}. "
                f"Overall field accuracy **{rd['overall'] * 100:.1f}%**.", "", "| Messiness | Fields right | Accuracy |", "|---|---|---|"]
        out += [f"| {k} | {v['right']}/{v['total']} | {100 * v['right'] / v['total']:.1f}% |" for k, v in rd["by_level"].items()]
        out += ["", "| Field | Right | Accuracy |", "|---|---|---|"]
        out += [f"| {k} | {v['right']}/{v['total']} | {100 * v['right'] / v['total']:.0f}% |" for k, v in rd["by_field"].items()]
        out.append("")
    else:
        out += ["Not run yet.", ""]
    vo = _load("voice")
    out += ["## Voice loop", ""] + ([f"{vo.get('note', '')}", ""] if vo else ["Not run yet.", ""])
    s = spent()
    out += ["## Spend log", "", "Prices in `src/eval/spend.py` (USD per 1M tokens). Rule: stop and ask before any single run projected over $25, "
            "or once either partner credit is 70% used.", "",
            "| Provider | Spent | Credit | Used |", "|---|---|---|---|"]
    out += [f"| {k} | ${s[k]:.2f} | ${c:.0f} | {100 * s[k] / c:.1f}% |" for k, c in CREDITS.items()]
    out += ["", "| When | Run | Detail | Meta | Fireworks | Baseten |", "|---|---|---|---|---|---|"]
    if SPEND.exists():
        for line in SPEND.read_text().splitlines():
            e = json.loads(line)
            u = e["usd"]
            out.append(f"| {e['date']} | {e['run']} | {e['detail']} | ${u.get('meta', 0):.3f} | ${u.get('fireworks', 0):.3f} | ${u.get('baseten', 0):.3f} |")
    path = ROOT / "docs" / "evals.md"
    path.write_text("\n".join(out) + "\n")
    return path
