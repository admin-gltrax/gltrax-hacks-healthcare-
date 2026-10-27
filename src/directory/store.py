"""The local provider graph: NPPES providers joined with payer directory claims.

Everything here reads committed snapshots in data/directory/, so the app works
offline and a payer outage never breaks a demo. Refresh the snapshots with
src/directory/nppes.py and src/directory/plannet.py.
"""
from __future__ import annotations

import json
import re
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
    nets = json.loads(nets_path.read_text())
    claims = nets["claims"]
    names = {k: v.get("networks", {}) for k, v in nets["payers"].items()}
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
                    network_name=c.get("network_name") or names.get(payer, {}).get(c["network_id"]),
                    accepting_new_patients=c.get("accepting_new_patients"),
                )
                for c in cs
            ]
    return providers


_STATE_NAMES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT",
    "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA",
    "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
    "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH",
    "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY",
}
_CODES = set(_STATE_NAMES.values()) - {"MA"}  # "MA" alone usually means Medicare Advantage
_NAME_RE = re.compile(r"\b(" + "|".join(sorted(_STATE_NAMES, key=len, reverse=True)) + r")\b")


def network_state(name: str | None) -> str | None:
    """The state a network name explicitly targets, if any (heuristic, from the name only).

    Catches "…from UHC AZ-15 (PPO)", "ARKANSAS PPO-PPA DIRECT", "AZ IFP …" and
    "…Integrated IL"; regional names such as "CHICAGO LOCALPLUS" are not caught.
    """
    if not name:
        return None
    if m := re.search(r"\bfrom UHC ([A-Z]{2})-\d", name):
        return m.group(1)
    if m := _NAME_RE.search(name.upper()):
        return _STATE_NAMES[m.group(1)]
    for m in (re.match(r"([A-Z]{2}) ", name), re.search(r"(?<![A-Za-z])([A-Z]{2})$", name.strip())):
        if m and m.group(1) in _CODES:
            return m.group(1)
    return None


_VIEW_CACHE: dict[tuple, dict] = {}


def directory_view(metro: str = "phoenix", specialty: str = "cardiology", data_dir: Path = DATA, max_names: int = 12, state: str = "AZ") -> dict:
    """Compact, dashboard-ready view of the local graph (cached until the snapshots change).

    Networks whose name targets another state are counted separately: a Phoenix
    patient cannot buy "AARP Medicare Advantage … from UHC NC-23". The snapshot
    keeps them; only this view sets them aside.
    """
    base, nets = data_dir / f"{metro}-{specialty}.json", data_dir / f"{metro}-{specialty}-networks.json"
    key = (str(base), base.stat().st_mtime, nets.stat().st_mtime if nets.exists() else None, max_names)
    if key in _VIEW_CACHE:
        return _VIEW_CACHE[key]
    meta, _ = load_nppes(base)
    net_meta = json.loads(nets.read_text()) if nets.exists() else {"payers": {}, "fetched_at": None}
    payer_names = {k: v["name"] for k, v in net_meta["payers"].items()}
    rows = []
    covered: dict[str, int] = {}
    for p in load_providers(metro, specialty, data_dir):
        payers: dict[str, dict] = {}
        for c in sorted(p.network, key=lambda c: (network_state(c.network_name) != state, c.network_name is None, c.network_name or "")):
            d = payers.setdefault(c.payer, {"networks": 0, "other_state": 0, "names": [], "accepting": None})
            if (tag := network_state(c.network_name)) and tag != state:
                d["other_state"] += 1
                continue
            d["networks"] += 1
            if c.network_name and len(d["names"]) < max_names:
                d["names"].append(c.network_name)
            if c.accepting_new_patients == "newpt" or d["accepting"] is None:
                d["accepting"] = c.accepting_new_patients
        payers = {k: v for k, v in payers.items() if v["networks"]}
        for k in payers:
            covered[k] = covered.get(k, 0) + 1
        rows.append({
            "npi": p.npi, "name": p.name, "credential": p.credential, "specialty": p.specialty,
            "line": p.address.line, "city": p.address.city, "zip": p.address.zip, "phone": p.phone,
            "locations": len(p.locations), "payers": payers,
        })
    view = {
        "metro": meta.get("metro"), "specialty": specialty, "count": len(rows),
        "nppes_fetched_at": meta.get("fetched_at"), "networks_fetched_at": net_meta.get("fetched_at"),
        "payers": {k: {"name": payer_names[k], "checked": v["checked"], "listed": v["listed"], "with_networks": covered.get(k, 0)}
                   for k, v in net_meta["payers"].items()},
        "providers": rows,
    }
    _VIEW_CACHE.clear()
    _VIEW_CACHE[key] = view
    return view
