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
