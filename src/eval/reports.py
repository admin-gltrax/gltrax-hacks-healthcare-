"""Serve the committed eval reports (docs/evals/*.json) to /gym, with one sample
transcript per gym persona read from the run's recording. Cached by file mtime."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

_CACHE: dict[str, tuple[float, dict]] = {}
NAMES = ("gym-report", "judges", "reader", "voice", "reviewer-strong-standard", "reviewer-full", "reviewer-thin")


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    m = path.stat().st_mtime
    hit = _CACHE.get(str(path))
    if hit and hit[0] == m:
        return hit[1]
    data = json.loads(path.read_text())
    _CACHE[str(path)] = (m, data)
    return data


def samples(recording: Path) -> list[dict]:
    """One completed call per persona kind (a successful one if there is one), transcript included."""
    hit = _CACHE.get(str(recording))
    if hit and hit[0] == recording.stat().st_mtime:
        return hit[1]["samples"]
    best: dict[str, dict] = {}
    with gzip.open(recording, "rt") as f:
        for line in f:
            r = json.loads(line)
            if "error" in r:
                continue
            k = r["kind"]
            if k not in best or (r["success"] and not best[k]["success"]):
                best[k] = {key: r[key] for key in ("id", "kind", "success", "safe", "safety", "outcome", "reference", "reached",
                                                   "menu_path", "hold_minutes", "seconds", "transcript") if key in r}
    out = [best[k] for k in sorted(best)]
    _CACHE[str(recording)] = (recording.stat().st_mtime, {"samples": out})
    return out


def latest(evals: Path) -> dict:
    out = {k.replace("-", "_"): _load(evals / f"{k}.json") for k in NAMES}
    gym = out.get("gym_report")
    if gym:
        rec = evals.parents[1] / "recordings" / "gym" / f"{gym['run']}.jsonl.gz"
        out["gym_samples"] = samples(rec) if rec.exists() else []
    return out
