import json

import httpx

from src.directory.plannet import NETWORK_EXT, NEWPATIENTS_EXT, NPI_SYSTEM, Payer, claims_from_roles, fetch_payer, snapshot
from src.directory.store import load_providers
from src.schemas import Address, Provider

ADDR = Address(line="1 Main St", city="Phoenix", state="AZ", zip="85016")


def prov(npi, name="Ana Diaz"):
    return Provider(npi=npi, name=name, specialty="Cardiovascular Disease", address=ADDR, locations=[ADDR])


def role(rid, nets, codes=("207RC0000X",), accepting="newpt", active=True, display=True):
    return {
        "resourceType": "PractitionerRole", "id": rid, "active": active, "meta": {"lastUpdated": "2026-10-20T00:00:00Z"},
        "specialty": [{"coding": [{"code": c}]} for c in codes],
        "extension": [{"url": NEWPATIENTS_EXT, "extension": [{"url": "acceptingPatients", "valueCodeableConcept": {"coding": [{"code": accepting}]}}]}]
        + [{"url": NETWORK_EXT, "valueReference": {"reference": f"Organization/{n}", **({"display": f"Net {n}"} if display else {})}} for n in nets],
    }


def fake_payer(practitioners: dict[str, dict], roles: dict[str, list[dict]], orgs: dict[str, str], calls: list):
    """practitioners: npi -> Practitioner; roles: practitioner id -> roles (served two per page)."""

    def handler(req: httpx.Request) -> httpx.Response:
        q, path = dict(req.url.params), req.url.path
        calls.append((path, q))
        bundle = lambda rs, nxt=None: httpx.Response(200, json={"resourceType": "Bundle", "entry": [{"resource": r} for r in rs], "link": [{"relation": "next", "url": nxt}] if nxt else []})
        if path.endswith("/Practitioner"):
            if "identifier" in q:
                return bundle([practitioners[q["identifier"]]] if q["identifier"] in practitioners else [])
            return bundle([p for p in practitioners.values() if p["name"][0]["family"].lower() == q["family"].lower()])
        if path.endswith("/PractitionerRole"):
            rs, page = roles.get(q["practitioner"], []), int(q.get("page", 0))
            nxt = f"https://payer.test/fhir/PractitionerRole?practitioner={q['practitioner']}&page={page + 1}" if len(rs) > 2 * (page + 1) else None
            return bundle(rs[2 * page:2 * page + 2], nxt)
        if path.endswith("/Organization"):
            return bundle([{"resourceType": "Organization", "id": i, "name": orgs[i]} for i in q["_id"].split(",") if i in orgs])
        if "/Organization/" in path:
            oid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"resourceType": "Organization", "id": oid, "name": orgs[oid]})
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def prac(pid, npi, family="Diaz"):
    return {"resourceType": "Practitioner", "id": pid, "identifier": [{"system": NPI_SYSTEM, "value": npi}], "name": [{"family": family, "given": ["Ana"]}]}


def test_claims_keep_this_specialty_and_merge_per_network():
    claims = claims_from_roles([
        role("r1", ["A", "B"]),
        role("r2", ["A"], accepting="existptonly"),
        role("r3", ["C"], codes=("207R00000X",)),  # internal medicine role: ignored
        role("r4", ["D"], active=False),
    ], {"207RC0000X"})
    assert sorted(c["network_id"] for c in claims) == ["A", "B"]
    a = next(c for c in claims if c["network_id"] == "A")
    assert a["accepting_new_patients"] == "newpt" and a["network_name"] == "Net A" and a["last_updated"] == "2026-10-20"


async def test_identifier_payer_pages_roles_and_batches_network_names():
    calls: list = []
    roles = {"p1": [role(f"r{i}", [f"N{i}"], display=False) for i in range(5)]}  # 3 pages of roles
    payer = Payer("t", "Test", "https://payer.test/fhir", "identifier", batch_ids=True)
    async with fake_payer({"111": prac("p1", "111")}, roles, {f"N{i}": f"Plan {i}" for i in range(5)}, calls) as c:
        res = await fetch_payer(payer, [prov("111"), prov("222")], "cardiology", c)
    assert res.listed == 1 and not res.errors  # 222 is simply not in this directory
    assert sorted(x["network_name"] for x in res.claims["111"]) == [f"Plan {i}" for i in range(5)]
    assert sum(p.endswith("/PractitionerRole") for p, _ in calls) == 3  # followed next links
    assert [q["_id"].count(",") for p, q in calls if p.endswith("/Organization")] == [4]  # one batched name lookup


async def test_name_payer_matches_on_npi_not_name():
    calls: list = []
    pracs = {"999": prac("other", "999"), "111": prac("p1", "111")}  # two Dr. Diaz, different NPIs
    payer = Payer("t", "Test", "https://payer.test/fhir", "name")
    async with fake_payer(pracs, {"p1": [role("r", ["N"], display=False)], "other": [role("x", ["WRONG"])]}, {"N": "Plan N"}, calls) as c:
        res = await fetch_payer(payer, [prov("111")], "cardiology", c)
    assert [x["network_id"] for x in res.claims["111"]] == ["N"] and res.networks == {"N": "Plan N"}
    assert any(p.endswith("/Organization/N") for p, _ in calls)  # no batching: one read per network


async def test_errors_are_recorded_per_provider_after_retries(monkeypatch):
    import src.directory.plannet as pn

    monkeypatch.setattr(pn.asyncio, "sleep", lambda s: _noop())
    tries = []

    def handler(req):
        tries.append(1)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        res = await fetch_payer(Payer("t", "Test", "https://payer.test/fhir", "identifier"), [prov("111")], "cardiology", c)
    assert "111" in res.errors and len(tries) == 4  # 1 try + 3 retries, and the run still finished


async def _noop():
    return None


def test_store_joins_snapshots(tmp_path):
    base = {"metro": "Phoenix", "providers": [prov("111").model_dump(), prov("222").model_dump()]}
    (tmp_path / "phoenix-cardiology.json").write_text(json.dumps(base))
    assert all(p.network == [] for p in load_providers(data_dir=tmp_path))  # no payer snapshot yet: still loads

    nets = snapshot("Phoenix", "cardiology", 2, [])
    nets["claims"] = {"111": {"uhc": [{"network_id": "N1", "network_name": "AARP MA AZ-1", "accepting_new_patients": "newpt", "last_updated": "2026-10-20"}]}}
    (tmp_path / "phoenix-cardiology-networks.json").write_text(json.dumps(nets))
    p111, p222 = load_providers(data_dir=tmp_path)
    assert p222.network == []
    c = p111.network[0]
    assert (c.plan_id, c.payer, c.network_name, c.status, c.source) == ("uhc:N1", "uhc", "AARP MA AZ-1", "in", "directory")
    assert 0 < c.confidence < 1  # a directory listing is a claim, not a verified fact
