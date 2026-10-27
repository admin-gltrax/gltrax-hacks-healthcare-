"""The patient-first flow, end to end, offline: name-only start -> coverage ->
PCP (verified by "calling") -> records request (signed, faxed, answered) ->
"I think I need to see a therapist" -> ranked options."""
import pytest
from fastapi.testclient import TestClient

from src.agents import navigator
from src.api.server import app
from src.patient.models import HealthRecord, Patient
from src.patient.store import reset_store
from src.sim.payers import portal_lookup


@pytest.fixture()
def client():
    reset_store()
    return TestClient(app)


def _start(client, name="Sam Cole"):
    r = client.post("/api/p/start", json={"name": name})
    assert r.status_code == 200
    return r.json()


def test_home_serves_patient_dashboard_and_swarm_moved(client):
    assert "PJ" in client.get("/").text
    assert "Swarm Scheduler" in client.get("/swarm").text


def test_name_only_start_no_password(client):
    d = _start(client)
    assert d["patient"]["display_name"] == "Sam Cole"
    assert d["pj"]["step"] == "coverage"
    assert [b["key"] for b in d["buckets"]] == ["connection", "clinicals", "routines", "family_genes"]
    assert client.cookies.get("pj_session")


def test_requires_session(client):
    assert client.get("/api/p/me").status_code == 401
    assert client.post("/api/p/start", json={"name": "   "}).status_code == 400


def test_full_onboarding_flow(client):
    _start(client)
    d = client.post("/api/p/coverage", json={"card": "EVG-55120943", "employer": "Northwind Logistics"}).json()
    cov = d["coverage"]
    assert cov["plan_type"] == "PPO" and cov["eap_available"] is True
    assert "plan through work" in cov["plain_summary"]
    assert d["pj"]["step"] == "pcp"

    found = client.get("/api/p/providers", params={"q": "harbor"}).json()
    assert found and found[0]["sim_id"] == "SIM-1002"
    d = client.post("/api/p/pcp", json={"sim_id": "SIM-1002"}).json()
    pcp = d["care_team"][0]
    # The directory had a stale fax and a stale network; the verification call fixed both.
    assert pcp["fax"] == "(555) 010-0219" and pcp["confidence"] == "confirmed"
    assert pcp["in_network"] == "no"
    assert len(d["corrections"]) == 2
    assert d["pj"]["step"] == "records"

    d = client.post("/api/p/records").json()
    req_id = d["request_id"]
    assert d["records_requests"][0]["status"] == "awaiting_signature"
    assert client.post(f"/api/p/records/{req_id}/sign", json={"typed_name": "Someone Else"}).status_code == 400
    d = client.post(f"/api/p/records/{req_id}/sign", json={"typed_name": "sam cole"}).json()
    rr = d["records_requests"][0]
    assert rr["status"] == "sent" and rr["due_by"] and "/Sam Cole/" in rr["letter"]
    assert d["pj"]["step"] == "done"

    before = sum(len(b["items"]) for b in d["buckets"])
    d = client.post(f"/api/p/records/{req_id}/simulate-response").json()
    after = sum(len(b["items"]) for b in d["buckets"])
    assert after > before and d["records_requests"][0]["status"] == "received"


def test_unknown_card(client):
    _start(client)
    assert client.post("/api/p/coverage", json={"card": "ZZZ-1"}).status_code == 404


def test_records_never_sent_unsigned():
    from src.agents import records
    rec = HealthRecord(patient=Patient(display_name="Pat"))
    from src.agents import care_team
    m = care_team.add_from_directory(rec, "SIM-1001")
    req = records.draft(rec, m)
    with pytest.raises(records.NotSigned):
        records.send(rec, req.id)


def test_stale_fax_fails_until_verified():
    from src.agents import care_team, records
    rec = HealthRecord(patient=Patient(display_name="Pat"))
    m = care_team.add_from_directory(rec, "SIM-1002")  # directory fax is stale
    req = records.draft(rec, m)
    records.sign(rec, req.id, "Pat")
    assert records.send(rec, req.id).status.value == "failed"


def _rec_with(card, employer=None):
    rec = HealthRecord(patient=Patient(display_name="Pat", employer=employer))
    rec.coverage = portal_lookup(card)
    return rec


def test_therapist_ppo_with_eap():
    rec = _rec_with("EVG-1", employer="Northwind Logistics")
    req = navigator.navigate(rec, "I think I need to see a therapist")
    kinds = [p.kind for p in req.pathways]
    assert req.need == "therapy" and req.recommended == "eap"
    assert "in_network" in kinds and "community" in kinds
    in_net = next(p for p in req.pathways if p.kind == "in_network")
    assert "Larkspur Counseling" in in_net.why
    # Directory lists Marlow, but it isn't taking new patients: PJ says skip it.
    assert any("Marlow" in s for s in in_net.steps)


def test_therapist_medicaid_routes():
    rec = _rec_with("PSM-1")
    req = navigator.navigate(rec, "I need counseling for anxiety")
    kinds = [p.kind for p in req.pathways]
    assert "medicaid" in kinds and "in_network" in kinds and "eap" not in kinds


def test_hmo_specialist_needs_pcp_referral_first():
    rec = _rec_with("BWM-1")
    from src.agents import care_team
    care_team.add_from_directory(rec, "SIM-1001")
    req = navigator.navigate(rec, "I need a dermatologist for a mole")
    assert req.need == "dermatology" and req.recommended == "pcp_first"
    assert "medicare" in [p.kind for p in req.pathways]


def test_physical_therapy_is_not_talk_therapy():
    assert navigator.classify("I need physical therapy for my knee")[0] == "physical_therapy"


def test_crisis_always_first(client):
    _start(client)
    d = client.post("/api/p/ask", json={"text": "I want to end my life"}).json()
    assert d["answer"]["care_request"]["urgent"] is True
    assert "988" in d["answer"]["say"]
    assert d["answer"]["care_request"]["pathways"][0]["kind"] == "crisis"


def test_pj_never_answers_medical_questions(client):
    _start(client)
    d = client.post("/api/p/ask", json={"text": "should I double my lisinopril?"}).json()
    assert d["answer"]["type"] == "chat" and "doctor" in d["answer"]["say"]


def test_demo_patient_fills_every_bucket(client):
    d = client.post("/api/p/demo").json()
    assert all(b["items"] for b in d["buckets"])
    assert d["coverage"] and d["care_team"] and d["records_requests"][0]["status"] == "received"
    assert d["pj"]["step"] == "done"


def test_export_is_the_patients(client):
    _start(client)
    r = client.get("/api/p/me/export")
    assert r.status_code == 200 and '"display_name": "Sam Cole"' in r.text


def test_choose_pathway_creates_task(client):
    _start(client)
    client.post("/api/p/coverage", json={"card": "EVG-55120943", "employer": "Northwind Logistics"})
    d = client.post("/api/p/ask", json={"text": "I think I need to see a therapist"}).json()
    care = d["answer"]["care_request"]
    d = client.post(f"/api/p/care/{care['id']}/go", params={"kind": "in_network"}).json()
    assert d["tasks"][0]["agent"] == "swarm" and d["tasks"][0]["status"] == "working"
