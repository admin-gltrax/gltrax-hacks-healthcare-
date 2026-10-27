"""NPPES NPI Registry connector: every provider of one specialty in one metro.

    python -m src.directory.nppes --metro phoenix --specialty cardiology

NPPES is the public, keyless registry of every US provider (identity, specialty
taxonomy, practice addresses, phone). It says nothing about insurance networks;
payer directories add that later, joined on NPI.

API limits that shape this module: at most 200 results per page and a skip of
at most 1000, so one query returns at most 1200 rows. A query that hits the cap
is split by ZIP3 prefix. Metro membership is decided from each provider's
practice locations, not from the API's own address filter, because many
providers practise at several addresses.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..schemas import Address, Provider

API = "https://npiregistry.cms.hhs.gov/api/"
PAGE = 200
MAX_SKIP = 1000

# NUCC taxonomy codes -> the description NPPES searches on.
TAXONOMIES: dict[str, dict[str, str]] = {
    "cardiology": {
        "207RC0000X": "Cardiovascular Disease",
        "207RI0011X": "Interventional Cardiology",
        "207RC0001X": "Clinical Cardiac Electrophysiology",
        "207RA0001X": "Advanced Heart Failure and Transplant Cardiology",
    },
}


@dataclass(frozen=True)
class Metro:
    name: str
    state: str
    zip3: tuple[str, ...]  # ZIP prefixes that make up the metro
    exclude_zips: frozenset[str] = frozenset()  # ZIPs under those prefixes that lie outside it

    def contains(self, a: Address) -> bool:
        return a.state == self.state and a.zip[:3] in self.zip3 and a.zip not in self.exclude_zips


# Phoenix-Mesa-Chandler MSA = Maricopa + Pinal counties. ZIP3 850-853 covers it,
# minus the Yuma, La Paz, Pima, Yavapai, Mohave and Gila ZIPs that share those
# prefixes. A few Pinal towns under 856/857 (Oracle, San Manuel) are left out.
_PHX_EXCLUDE = frozenset(
    "85333 85336 85347 85349 85350 85352 85356 85364 85365 85366 85367 85369"  # Yuma County
    " 85325 85328 85334 85344 85346 85348 85357 85359 85371"  # La Paz County
    " 85321 85341"  # Pima County (Ajo, Lukeville)
    " 85324 85332 85362"  # Yavapai County
    " 85360"  # Mohave County
    " 85135 85192".split()  # Gila County (Hayden, Winkelman)
)
METROS: dict[str, Metro] = {
    "phoenix": Metro("Phoenix-Mesa-Chandler, AZ", "AZ", ("850", "851", "852", "853"), _PHX_EXCLUDE),
}


class NppesError(RuntimeError):
    pass


class QueryTooBroad(NppesError):
    pass


async def search(client: httpx.AsyncClient, **params: str) -> list[dict]:
    """All pages of one NPPES query. Raises QueryTooBroad if it hits the 1200-row cap."""
    rows: list[dict] = []
    for skip in range(0, MAX_SKIP + 1, PAGE):
        r = await client.get(API, params={"version": "2.1", "enumeration_type": "NPI-1", "limit": PAGE, "skip": skip, **params})
        r.raise_for_status()
        data = r.json()
        if data.get("Errors"):
            raise NppesError(f"NPPES rejected {params}: {data['Errors']}")
        rows += data.get("results", [])
        if data.get("result_count", 0) < PAGE:
            return rows
    raise QueryTooBroad(f"more than {MAX_SKIP + PAGE} results for {params}")


def _address(a: dict) -> Address:
    line = " ".join(x for x in (a.get("address_1", ""), a.get("address_2", "")) if x).strip()
    return Address(line=line, city=a.get("city", "").title(), state=a.get("state", ""), zip=a.get("postal_code", "")[:5])


def to_provider(row: dict, metro: Metro, codes: dict[str, str]) -> Provider | None:
    """Normalize one NPPES result; None if inactive, off-specialty or outside the metro."""
    basic = row.get("basic", {})
    if basic.get("status", "A") != "A":
        return None
    taxes = [t for t in row.get("taxonomies", []) if t.get("code") in codes]
    if not taxes:
        return None  # the text search matched something else (e.g. a pediatric taxonomy)

    primary_loc = [a for a in row.get("addresses", []) if a.get("address_purpose") == "LOCATION"]
    locations: list[Address] = []
    for a in primary_loc + row.get("practiceLocations", []):
        addr = _address(a)
        if metro.contains(addr) and addr not in locations:
            locations.append(addr)
    if not locations:
        return None

    first = next((a for a in primary_loc if _address(a) in locations), None)
    phone = (first or {}).get("telephone_number") or next(
        (a.get("telephone_number") for a in row.get("practiceLocations", []) if _address(a) == locations[0]), None
    )
    main = next((t for t in taxes if t.get("primary")), taxes[0])
    name = " ".join(x for x in (basic.get("first_name", ""), basic.get("last_name", "")) if x).title()
    return Provider(
        npi=row["number"],
        name=name,
        credential=basic.get("credential") or None,
        specialty=codes[main["code"]],
        taxonomy_codes=sorted({t["code"] for t in taxes}),
        address=locations[0],
        locations=locations,
        phone=phone,
        source="nppes",
        source_updated=basic.get("last_updated"),
    )


async def fetch_metro(metro: Metro, specialty: str, client: httpx.AsyncClient | None = None) -> list[Provider]:
    codes = TAXONOMIES[specialty]
    own = client is None
    client = client or httpx.AsyncClient(timeout=30)
    rows: dict[str, dict] = {}
    try:
        for desc in codes.values():
            try:
                found = await search(client, taxonomy_description=desc, state=metro.state)
            except QueryTooBroad:
                found = []
                for z in metro.zip3:
                    found += await search(client, taxonomy_description=desc, state=metro.state, postal_code=f"{z}*")
            for row in found:
                rows.setdefault(row["number"], row)
    finally:
        if own:
            await client.aclose()
    providers = [p for row in rows.values() if (p := to_provider(row, metro, codes))]
    return sorted(providers, key=lambda p: (p.address.city, p.name))


def snapshot(metro_key: str, specialty: str, providers: list[Provider]) -> dict:
    return {
        "metro": METROS[metro_key].name,
        "specialty": specialty,
        "source": "NPPES NPI Registry API v2.1 (public domain)",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(providers),
        "providers": [p.model_dump() for p in providers],
    }


async def amain(args) -> None:
    providers = await fetch_metro(METROS[args.metro], args.specialty)
    out = Path(args.out or f"data/directory/{args.metro}-{args.specialty}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot(args.metro, args.specialty, providers), indent=1) + "\n")
    print(f"wrote {out}: {len(providers)} providers")
    for k, n in Counter(p.specialty for p in providers).most_common():
        print(f"  {n:4d}  {k}")
    print("  top cities:", ", ".join(f"{c} {n}" for c, n in Counter(p.address.city for p in providers).most_common(8)))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--metro", choices=sorted(METROS), default="phoenix")
    p.add_argument("--specialty", choices=sorted(TAXONOMIES), default="cardiology")
    p.add_argument("--out")
    asyncio.run(amain(p.parse_args()))


if __name__ == "__main__":
    main()
