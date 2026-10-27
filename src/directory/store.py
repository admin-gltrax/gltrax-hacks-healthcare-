"""The local provider graph: NPPES providers joined with payer directory claims.

Everything here reads committed snapshots in data/directory/, so the app works
offline and a payer outage never breaks a demo. Refresh the snapshots with
src/directory/nppes.py and src/directory/plannet.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..schemas import NetworkClaim, Provider

DATA = Path(__file__).resolve().parents[2] / "data" / "directory"
DIRECTORY_CONFIDENCE = 0.5  # a directory listing alone; calls raise or lower it


def load_nppes(path: Path) -> tuple[dict, list[Provider]]:
    data = json.loads(path.read_text())
    return {k: v for k, v in data.items() if k != "providers"}, [Provider.model_validate(p) for p in data["providers"]]


def load_providers(metro: str = "phoenix", specialty: str = "cardiology", data_dir: Path = DATA) -> list[Provider]:
    """Providers with `network` filled from the payer snapshot, if there is one."""
    _, providers = load_nppes(data_dir / f"{metro}-{specialty}.json")
    nets_path = data_dir / f"{metro}-{specialty}-networks.json"
    if not nets_path.exists():
        return providers
    claims = json.loads(nets_path.read_text())["claims"]
    for p in providers:
        for payer, cs in claims.get(p.npi, {}).items():
            p.network += [
                NetworkClaim(
                    plan_id=f"{payer}:{c['network_id']}",
                    status="in",
                    confidence=DIRECTORY_CONFIDENCE,
                    last_verified=c.get("last_updated"),
                    source="directory",
                    payer=payer,
                    network_name=c.get("network_name"),
                    accepting_new_patients=c.get("accepting_new_patients"),
                )
                for c in cs
            ]
    return providers


_VIEW_CACHE: dict[tuple, dict] = {}


def directory_view(metro: str = "phoenix", specialty: str = "cardiology", data_dir: Path = DATA, max_names: int = 12) -> dict:
    """Compact, dashboard-ready view of the local graph (cached until the snapshots change)."""
    base, nets = data_dir / f"{metro}-{specialty}.json", data_dir / f"{metro}-{specialty}-networks.json"
    key = (str(base), base.stat().st_mtime, nets.stat().st_mtime if nets.exists() else None, max_names)
    if key in _VIEW_CACHE:
        return _VIEW_CACHE[key]
    meta, _ = load_nppes(base)
    net_meta = json.loads(nets.read_text()) if nets.exists() else {"payers": {}, "fetched_at": None}
    payer_names = {k: v["name"] for k, v in net_meta["payers"].items()}
    rows = []
    for p in load_providers(metro, specialty, data_dir):
        payers: dict[str, dict] = {}
        for c in p.network:
            d = payers.setdefault(c.payer, {"networks": 0, "names": [], "accepting": None})
            d["networks"] += 1
            if c.network_name and len(d["names"]) < max_names:
                d["names"].append(c.network_name)
            if c.accepting_new_patients == "newpt" or d["accepting"] is None:
                d["accepting"] = c.accepting_new_patients
        rows.append({
            "npi": p.npi, "name": p.name, "credential": p.credential, "specialty": p.specialty,
            "line": p.address.line, "city": p.address.city, "zip": p.address.zip, "phone": p.phone,
            "locations": len(p.locations), "payers": payers,
        })
    view = {
        "metro": meta.get("metro"), "specialty": specialty, "count": len(rows),
        "nppes_fetched_at": meta.get("fetched_at"), "networks_fetched_at": net_meta.get("fetched_at"),
        "payers": {k: {"name": payer_names[k], **{f: v[f] for f in ("checked", "listed", "with_networks")}} for k, v in net_meta["payers"].items()},
        "providers": rows,
    }
    _VIEW_CACHE.clear()
    _VIEW_CACHE[key] = view
    return view
