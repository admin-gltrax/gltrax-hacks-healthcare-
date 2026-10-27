"""Payer provider directories (DaVinci PDex Plan-Net, FHIR R4): which networks
each payer's directory says a provider is in.

    python -m src.directory.plannet --metro phoenix --specialty cardiology

Starts from the NPPES snapshot (src/directory/nppes.py) and asks each payer about
those NPIs only, instead of crawling a whole state: find the Practitioner by NPI
(or by name, then match the NPI, where the payer cannot search identifiers), then
read its PractitionerRoles, whose network-reference extensions name the networks.
Writes data/directory/<metro>-<specialty>-networks.json. The app reads that
snapshot (src/directory/store.py) and never calls the payers at request time.

All three payers below are public and need no account (checked 2026-10-27).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx

from ..schemas import Provider
from .nppes import TAXONOMIES

NPI_SYSTEM = "http://hl7.org/fhir/sid/us-npi"
NETWORK_EXT = "http://hl7.org/fhir/us/davinci-pdex-plan-net/StructureDefinition/network-reference"
NEWPATIENTS_EXT = "http://hl7.org/fhir/us/davinci-pdex-plan-net/StructureDefinition/newpatients"
MAX_PAGES = 10  # per search; a single practitioner never needs more
ID_BATCH = 20


@dataclass(frozen=True)
class Payer:
    key: str
    name: str
    base_url: str
    lookup: Literal["identifier", "name"]  # how to find a Practitioner by NPI
    batch_ids: bool = False  # Organization?_id=a,b,c returns all of them
    page_size: int | None = None  # _count to send, where the server honors it


PAYERS: dict[str, Payer] = {
    "uhc": Payer("uhc", "UnitedHealthcare", "https://flex.optum.com/fhirpublic/R4", "identifier", batch_ids=True, page_size=100),
    "cigna": Payer("cigna", "Cigna", "https://fhir.cigna.com/ProviderDirectory/v1", "name"),
    "humana": Payer("humana", "Humana", "https://fhir.humana.com/api", "identifier", page_size=100),
}


class Fhir:
    """Small FHIR search client: retries transient failures, follows next links."""

    def __init__(self, payer: Payer, client: httpx.AsyncClient, concurrency: int = 6, retries: int = 3):
        self.payer, self.client, self.retries = payer, client, retries
        self.sem = asyncio.Semaphore(concurrency)
        self.requests = 0

    def url(self, ref: str) -> str:
        return ref if ref.startswith("http") else f"{self.payer.base_url}/{ref}"

    async def get(self, ref: str, params: dict | None = None) -> dict:
        for attempt in range(self.retries + 1):
            try:
                async with self.sem:
                    self.requests += 1
                    r = await self.client.get(self.url(ref), params=params, headers={"Accept": "application/fhir+json"})
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
                r.raise_for_status()
                return r.json()
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == self.retries:
                    raise
                await asyncio.sleep(0.5 * 2**attempt)
        raise AssertionError("unreachable")

    async def search(self, resource: str, params: dict) -> list[dict]:
        """Every matching resource of the searched type (included resources are dropped)."""
        return (await self.search_with_includes(resource, params))[0]

    async def search_with_includes(self, resource: str, params: dict) -> tuple[list[dict], dict[str, dict]]:
        """Matches of the searched type, plus every other resource in the bundles keyed by id."""
        out: list[dict] = []
        included: dict[str, dict] = {}
        bundle = await self.get(resource, params)
        for _ in range(MAX_PAGES):
            for e in bundle.get("entry", []):
                r = e.get("resource", {})
                if r.get("resourceType") == resource:
                    out.append(r)
                elif r.get("id"):
                    included[r["id"]] = r
            nxt = next((link["url"] for link in bundle.get("link", []) if link.get("relation") == "next"), None)
            if not nxt:
                break
            bundle = await self.get(nxt)
        return out, included


def _npis(practitioner: dict) -> set[str]:
    return {i.get("value") for i in practitioner.get("identifier", []) if i.get("system") == NPI_SYSTEM}


async def find_practitioner(fhir: Fhir, p: Provider) -> dict | None:
    if fhir.payer.lookup == "identifier":
        found = await fhir.search("Practitioner", {"identifier": p.npi})
    else:
        given, _, family = p.name.partition(" ")
        found = await fhir.search("Practitioner", {"family": family, "given": given}) if family else []
    return next((x for x in found if p.npi in _npis(x)), None)


def _ref_id(ref: str) -> str:
    return ref.rstrip("/").rsplit("/", 1)[-1]


def in_state(role: dict, locations: dict[str, dict], state: str) -> bool:
    """False only when every location we could resolve is in another state."""
    states = {locations[i].get("address", {}).get("state") for i in (_ref_id(x.get("reference", "")) for x in role.get("location", [])) if i in locations}
    return not states or state in states


def claims_from_roles(roles: list[dict], codes: set[str], locations: dict[str, dict] | None = None, state: str | None = None) -> list[dict]:
    """One claim per network across the provider's in-state roles in this specialty."""
    claims: dict[str, dict] = {}
    for role in roles:
        if role.get("active") is False:
            continue
        if state and not in_state(role, locations or {}, state):
            continue  # e.g. the same cardiologist's role in a North Carolina clinic
        role_codes = {c.get("code") for s in role.get("specialty", []) for c in s.get("coding", [])}
        if role_codes and not role_codes & codes:
            continue  # a role in another specialty (e.g. internal medicine) says nothing about this one
        accepting = None
        for ext in role.get("extension", []):
            if ext.get("url") == NEWPATIENTS_EXT:
                for sub in ext.get("extension", []):
                    for c in sub.get("valueCodeableConcept", {}).get("coding", []):
                        accepting = accepting or c.get("code")
        updated = (role.get("meta", {}).get("lastUpdated") or "")[:10] or None
        for ext in role.get("extension", []):
            if ext.get("url") != NETWORK_EXT:
                continue
            ref = ext.get("valueReference", {})
            nid = _ref_id(ref.get("reference", ""))
            if not nid:
                continue
            c = claims.setdefault(nid, {"network_id": nid, "network_ref": ref["reference"], "network_name": ref.get("display"),
                                        "accepting_new_patients": accepting, "last_updated": updated})
            c["accepting_new_patients"] = c["accepting_new_patients"] or accepting
            c["last_updated"] = max(filter(None, (c["last_updated"], updated)), default=None)
    return list(claims.values())


@dataclass
class PayerResult:
    payer: Payer
    claims: dict[str, list[dict]] = field(default_factory=dict)  # npi -> claims
    listed: int = 0
    errors: dict[str, str] = field(default_factory=dict)  # npi -> error
    networks: dict[str, str | None] = field(default_factory=dict)  # network id -> name
    requests: int = 0
    seconds: float = 0.0


async def fetch_payer(payer: Payer, providers: list[Provider], specialty: str, client: httpx.AsyncClient,
                      concurrency: int = 6, progress=None, state: str | None = None) -> PayerResult:
    fhir = Fhir(payer, client, concurrency)
    codes = set(TAXONOMIES[specialty])
    res = PayerResult(payer)
    t0 = time.monotonic()

    async def one(p: Provider) -> None:
        try:
            prac = await find_practitioner(fhir, p)
            if prac is None:
                return
            res.listed += 1
            params = {"practitioner": prac["id"], "_include": "PractitionerRole:location"}
            if payer.page_size:
                params["_count"] = str(payer.page_size)
            roles, included = await fhir.search_with_includes("PractitionerRole", params)
            claims = claims_from_roles(roles, codes, included, state)
            if claims:
                res.claims[p.npi] = claims
        except Exception as e:  # one provider must never sink the run
            res.errors[p.npi] = f"{type(e).__name__}: {e}"[:200]
        finally:
            if progress:
                progress(payer.key)

    await asyncio.gather(*(one(p) for p in providers))

    # Name every network once: from the reference's display, a batched search, or one read each.
    refs = {c["network_id"]: c["network_ref"] for cs in res.claims.values() for c in cs}
    res.networks = {c["network_id"]: c["network_name"] for cs in res.claims.values() for c in cs if c["network_name"]}
    todo = [nid for nid in refs if nid not in res.networks]

    async def batch(ids: list[str]) -> None:
        try:
            for org in await fhir.search("Organization", {"_id": ",".join(ids), "_count": str(len(ids))}):
                res.networks[org["id"]] = org.get("name")
        except Exception:
            pass

    async def one_name(nid: str) -> None:
        try:
            res.networks[nid] = (await fhir.get(refs[nid])).get("name")
        except Exception:
            res.networks[nid] = None

    if payer.batch_ids:
        await asyncio.gather(*(batch(todo[i:i + ID_BATCH]) for i in range(0, len(todo), ID_BATCH)))
    await asyncio.gather(*(one_name(nid) for nid in todo if nid not in res.networks))
    for cs in res.claims.values():
        for c in cs:
            c["network_name"] = res.networks.get(c["network_id"])
            del c["network_ref"]
    res.requests, res.seconds = fhir.requests, round(time.monotonic() - t0, 1)
    return res


def snapshot(metro: str, specialty: str, checked: int, results: list[PayerResult]) -> dict:
    return {
        "metro": metro,
        "specialty": specialty,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Directory claims only: what each payer's public directory says, not verified by calls.",
        "payers": {
            r.payer.key: {
                "name": r.payer.name, "base_url": r.payer.base_url, "checked": checked, "listed": r.listed,
                "with_networks": len(r.claims), "errors": len(r.errors), "requests": r.requests, "seconds": r.seconds,
                "networks": dict(sorted(r.networks.items(), key=lambda kv: (kv[1] or "", kv[0]))),
            }
            for r in results
        },
        "claims": {
            npi: {r.payer.key: r.claims[npi] for r in results if npi in r.claims}
            for npi in sorted({n for r in results for n in r.claims})
        },
    }


async def amain(args) -> None:
    from .nppes import METROS
    from .store import load_nppes

    base = Path(args.nppes or f"data/directory/{args.metro}-{args.specialty}.json")
    meta, providers = load_nppes(base)
    payers = [PAYERS[k] for k in args.payers.split(",")]
    done = {p.key: 0 for p in payers}

    def progress(key: str) -> None:
        done[key] += 1
        if done[key] % 100 == 0 or done[key] == len(providers):
            print(f"  {key}: {done[key]}/{len(providers)}", flush=True)

    async with httpx.AsyncClient(timeout=90) as client:
        results = await asyncio.gather(*(fetch_payer(p, providers, args.specialty, client, args.concurrency, progress, METROS[args.metro].state) for p in payers))
    out = Path(args.out or base.with_name(f"{base.stem}-networks.json"))
    out.write_text(json.dumps(snapshot(meta["metro"], args.specialty, len(providers), list(results)), indent=1) + "\n")
    print(f"wrote {out}")
    for r in results:
        print(f"  {r.payer.name:16} listed {r.listed}/{len(providers)}, with {args.specialty} networks {len(r.claims)}, "
              f"{len(r.networks)} networks, {len(r.errors)} errors, {r.requests} requests, {r.seconds}s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metro", default="phoenix")
    ap.add_argument("--specialty", choices=sorted(TAXONOMIES), default="cardiology")
    ap.add_argument("--payers", default=",".join(PAYERS))
    ap.add_argument("--concurrency", type=int, default=6, help="requests in flight per payer")
    ap.add_argument("--nppes", help="NPPES snapshot to start from")
    ap.add_argument("--out")
    asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    main()
