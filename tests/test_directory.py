import httpx
import pytest

from src.directory import nppes
from src.directory.nppes import METROS, TAXONOMIES, NppesError, fetch_metro, search, to_provider

PHX = METROS["phoenix"]
CARDIO = TAXONOMIES["cardiology"]


def row(npi, *, city="PHOENIX", zip_="850164425", codes=("207RC0000X",), status="A", practice=()):
    loc = {"address_1": "1 MAIN ST", "address_purpose": "LOCATION", "city": city, "state": "AZ", "postal_code": zip_, "telephone_number": "602-555-0100"}
    return {
        "number": npi,
        "basic": {"first_name": "ANA", "last_name": "DIAZ", "credential": "MD", "status": status, "last_updated": "2026-10-01"},
        "addresses": [{**loc, "address_purpose": "MAILING"}, loc],
        "practiceLocations": list(practice),
        "taxonomies": [{"code": c, "desc": "x", "primary": i == 0} for i, c in enumerate(codes)],
    }


def registry(results_by_desc: dict[str, list[dict]], calls: list | None = None):
    """Fake NPPES: pages results 200 at a time, like the real API."""

    def handler(req: httpx.Request) -> httpx.Response:
        q = dict(req.url.params)
        if calls is not None:
            calls.append(q)
        rows = results_by_desc.get(q["taxonomy_description"], [])
        if "postal_code" in q:
            rows = [r for r in rows if r["addresses"][1]["postal_code"].startswith(q["postal_code"].rstrip("*"))]
        skip, limit = int(q["skip"]), int(q["limit"])
        page = rows[skip:skip + limit]
        return httpx.Response(200, json={"result_count": len(page), "results": page})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_normalizes_and_filters_to_the_metro():
    p = to_provider(row("1", practice=[{"address_1": "9 ELM", "city": "YUMA", "state": "AZ", "postal_code": "85364"}]), PHX, CARDIO)
    assert p.npi == "1" and p.name == "Ana Diaz" and p.specialty == "Cardiovascular Disease"
    assert p.address.city == "Phoenix" and p.address.zip == "85016" and p.phone == "602-555-0100"
    assert len(p.locations) == 1  # the Yuma practice location is outside the metro
    assert p.network == []  # NPPES knows nothing about networks

    assert to_provider(row("2", city="YUMA", zip_="85364"), PHX, CARDIO) is None  # 853 prefix, but Yuma County
    assert to_provider(row("3", status="D"), PHX, CARDIO) is None  # deactivated
    assert to_provider(row("4", codes=("2080P0202X",)), PHX, CARDIO) is None  # pediatric cardiology: not in scope
    # out-of-metro main address but a practice location in Mesa: kept, Mesa is primary
    p = to_provider(row("5", city="TUCSON", zip_="85711", practice=[{"address_1": "2 OAK", "city": "MESA", "state": "AZ", "postal_code": "852011111"}]), PHX, CARDIO)
    assert p and p.address.city == "Mesa" and p.address.zip == "85201"


async def test_pages_through_results_and_dedupes_across_specialties():
    many = [row(f"{i:010d}") for i in range(450)]  # 3 pages
    both = row("9999999999", codes=("207RI0011X", "207RC0000X"))
    calls: list = []
    async with registry({"Cardiovascular Disease": many + [both], "Interventional Cardiology": [both]}, calls) as c:
        providers = await fetch_metro(PHX, "cardiology", client=c)
    assert len(providers) == 451  # the dual-specialty provider is counted once
    assert [q["skip"] for q in calls if q["taxonomy_description"] == "Cardiovascular Disease"] == ["0", "200", "400"]
    assert next(p for p in providers if p.npi == "9999999999").specialty == "Interventional Cardiology"  # its primary


async def test_splits_by_zip3_when_a_query_hits_the_cap(monkeypatch):
    monkeypatch.setattr(nppes, "MAX_SKIP", 200)  # cap at 400 rows to keep the fixture small
    rows = [row(f"{i:010d}", zip_=f"85{2 + i % 2}011111") for i in range(500)]
    calls: list = []
    async with registry({"Cardiovascular Disease": rows}, calls) as c:
        providers = await fetch_metro(PHX, "cardiology", client=c)
    assert len(providers) == 500
    assert {q.get("postal_code") for q in calls} >= {"850*", "851*", "852*", "853*"}


async def test_api_errors_are_raised():
    def handler(req):
        return httpx.Response(200, json={"Errors": [{"description": "bad"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(NppesError):
            await search(c, taxonomy_description="x", state="AZ")


def test_detect_payer():
    from src.intake import detect_payer

    assert detect_payer("I have an AARP plan through United") == "uhc"
    assert detect_payer("Cigna open access") == "cigna"
    assert detect_payer("my Humana card") == "humana"
    assert detect_payer("I need a cardiologist") is None and detect_payer(None) is None


def test_directory_search_gives_counts_and_anonymous_stand_ins():
    from src.swarm.candidates import directory_search

    d = directory_search("uhc")
    assert d["available"] and d["in_network"] > 0 and len(d["stand_ins"]) == 15
    for s in d["stand_ins"]:
        assert set(s) == {"city", "accepting"}  # never a real name, NPI or phone
    assert len({s["city"] for s in d["stand_ins"]}) > 5  # spread across the metro
    assert not directory_search("aetna")["available"]
    assert not directory_search("uhc", specialty="../../etc")["available"]  # parsed text never reaches a path
