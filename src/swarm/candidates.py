"""Step 1 of a swarm: search the real directory before calling anyone.

The real, public directory data (src/directory/) says which Phoenix-area
providers a payer lists in an Arizona network. That is shown as real data. The
calls themselves still go to simulated offices: each simulated office stands in
for one real listing and borrows only its city, never its name, NPI or phone,
so no simulated behavior is ever attributed to a real practice.
"""
from __future__ import annotations

from ..directory.nppes import METROS, TAXONOMIES
from ..directory.store import directory_view

NO_OPEN_DIRECTORY = {"aetna": "Aetna's provider directory needs registered credentials, so it is not in the local data."}


def directory_search(payer: str, metro: str = "phoenix", specialty: str = "cardiology", k: int = 15) -> dict:
    """What the real directory says for this payer, plus up to k anonymized stand-in slots."""
    if metro not in METROS or specialty not in TAXONOMIES:  # values can come from parsed patient text
        return {"available": False, "payer": payer, "reason": f"No directory data for {specialty} in {metro}."}
    try:
        view = directory_view(metro, specialty)
    except FileNotFoundError:
        return {"available": False, "payer": payer, "reason": "No directory snapshot on this server."}
    info = view["payers"].get(payer)
    if info is None:
        return {"available": False, "payer": payer, "reason": NO_OPEN_DIRECTORY.get(payer, f"No directory data for {payer}.")}

    listed = [p for p in view["providers"] if payer in p["payers"]]
    accepting = [p for p in listed if p["payers"][payer]["accepting"] == "newpt"]
    # Prefer listings that say they take new patients; round-robin across cities, busiest first.
    picked: list[dict] = []
    for pool in (accepting, [p for p in listed if p not in accepting]):
        by_city: dict[str, list[dict]] = {}
        for p in sorted(pool, key=lambda p: p["npi"]):
            by_city.setdefault(p["city"], []).append(p)
        queues = sorted(by_city.values(), key=lambda q: (-len(q), q[0]["city"]))
        while len(picked) < k and any(queues):
            for q in queues:
                if q and len(picked) < k:
                    picked.append(q.pop(0))
    return {
        "available": True,
        "payer": payer,
        "payer_name": info["name"],
        "metro": view["metro"],
        "specialty": specialty,
        "providers_total": view["count"],
        "in_network": len(listed),
        "accepting_new_patients": len(accepting),
        "fetched_at": view["networks_fetched_at"],
        # Anonymized on purpose: the simulated stand-ins borrow these cities only.
        "stand_ins": [{"city": p["city"], "accepting": p["payers"][payer]["accepting"] == "newpt"} for p in picked],
    }
