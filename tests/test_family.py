"""Care circle, support plan and agent workflows: the rules that make it safe to
act for someone else, and the jobs PJ's crew runs end to end."""
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.agents import circle, outreach, workflows
from src.api.server import app
from src.patient.models import HealthRecord, Patient
from src.patient.store import reset_store
from src.sim.payers import portal_lookup


@pytest.fixture()
def client():
    reset_store()
    return TestClient(app)


def _years_ago(n: int) -> str:
    t = date.today()
    return t.replace(year=t.year - n).isoformat()


def _start(client, name="Sam Cole"):
    return client.post("/api/p/start", json={"name": name}).json()


# ---------------------------------------------------------------- care circle

def test_parent_manages_a_minor_and_access_ends_at_18():
    acc = HealthRecord(patient=Patient(display_name="Sam Cole"))
    kid = circle.add(acc, "Leo Cole", "child", _years_ago(9))
    assert kid.authority == "parent_of_minor" and set(kid.permissions) == {"view", "act", "approve"}
    assert circle.signer(acc, kid) == ("Sam Cole", "parent or guardian of Leo Cole")
    kid.record.patient.dob = _years_ago(18)
    kid = circle.find(acc, kid.id)
    assert kid.authority == "pending_consent" and kid.permissions == []  # Leo decides now


def test_adult_sees_nothing_until_they_say_yes(client):
    _start(client)
    d = client.post("/api/p/circle", json={"name": "Rosa Cole", "relation": "parent", "dob": _years_ago(78)}).json()
    rosa = d["viewing"]
    assert d["limited"] is True and d["buckets"] == [] and rosa["permissions"] == []
    assert [a["key"] for a in d["actions"]] == ["consent"]
    assert client.post("/api/p/coverage", json={"card": "BWM-1"}).status_code == 403
    assert client.post("/api/p/workflows", json={"template": "bill_dispute"}).status_code == 403
    # Only Rosa can say yes, by typing her own name.
    assert client.post(f"/api/p/circle/{rosa['id']}/consent", json={"typed_name": "Sam Cole"}).status_code == 400
    d = client.post(f"/api/p/circle/{rosa['id']}/consent", json={"typed_name": "rosa cole", "permissions": ["act"]}).json()
    assert d["viewing"]["permissions"] == ["view", "act"] and d["limited"] is False
    assert "still approves" in d["viewing"]["consent_note"]


def test_a_helper_can_start_work_but_never_sign_for_an_adult(client):
    _start(client)
    d = client.post("/api/p/circle", json={"name": "Rosa Cole", "relation": "parent", "dob": _years_ago(78)}).json()
    pid = d["viewing"]["id"]
    client.post(f"/api/p/circle/{pid}/consent", json={"typed_name": "Rosa Cole", "permissions": ["view", "act"]})
    client.post("/api/p/coverage", json={"card": "BWM-77031882"})
    d = client.post("/api/p/workflows", json={"template": "plan_resource", "inputs": {"resource": "rides"}}).json()
    wf = d["workflows"][0]
    assert wf["status"] == "needs_you"
    r = client.post(f"/api/p/workflows/{wf['id']}/approve", json={"typed_name": "Sam Cole"})
    assert r.status_code == 403 and "Only Rosa" in r.json()["detail"]
    # With healthcare power of attorney (attested), the account holder signs as her representative.
    client.post(f"/api/p/circle/{pid}/representative", json={"typed_name": "Sam Cole"})
    d = client.post(f"/api/p/workflows/{wf['id']}/approve", json={"typed_name": "Sam Cole"}).json()
    assert d["workflows"][0]["signed_by"] == "Sam Cole, personal representative of Rosa Cole"


def test_switching_people_and_revoking(client):
    _start(client)
    d = client.post("/api/p/circle", json={"name": "Leo Cole", "relation": "child", "dob": _years_ago(9)}).json()
    assert d["viewing"]["name"] == "Leo Cole" and [p["active"] for p in d["circle"]] == [False, True]
    d = client.post("/api/p/active", json={"person_id": None}).json()
    assert d["viewing"]["relation"] == "you"
    d = client.delete(f"/api/p/circle/{d['circle'][1]['id']}").json()
    assert len(d["circle"]) == 1


# ---------------------------------------------------------------- support plan

_ADVICE = re.compile(r"\b(you have|diagnos(e|is|ed) you|take \d|increase your|stop taking|start taking)\b", re.I)


def _rec(dob, card=None, told=(), employer=None):
    rec = HealthRecord(patient=Patient(display_name="Pat Doe", dob=dob, employer=employer))
    rec.coverage = portal_lookup(card) if card else None
    outreach.set_told(rec, list(told))
    return rec


def test_support_plan_for_an_older_adult_uses_their_benefits():
    rec = _rec(_years_ago(78), "BWM-1", ["lives_alone", "recent_fall", "many_medicines", "no_ride", "hard_to_afford"])
    keys = [a.key for a in outreach.support_plan(rec)]
    assert keys[0] == "wellness_visit"
    assert {"fall_check", "med_review", "check_in_calls", "rides", "cost_help", "dental"} <= set(keys)
    rides = next(a for a in outreach.support_plan(rec) if a.key == "rides")
    assert rides.kind == "benefit" and rides.cost == "$0"  # the plan covers rides: use it


def test_support_plan_for_a_child_and_a_teen():
    keys = [a.key for a in outreach.support_plan(_rec(_years_ago(9), "PSM-1"))]
    assert "well_child" in keys and "teen_privacy" not in keys and "wellness_visit" not in keys
    assert "teen_privacy" in [a.key for a in outreach.support_plan(_rec(_years_ago(15), "PSM-1"))]


def test_support_plan_never_gives_medical_advice_and_always_cites_why():
    rec = _rec(_years_ago(80), "BWM-1", list(outreach.TOLD))
    for a in outreach.support_plan(rec):
        assert a.why and not _ADVICE.search(a.title + " " + a.why), a.key
        assert set(a.because) <= {f.key for f in outreach.all_factors(rec)}


def test_support_actions_start_and_dismiss_stick():
    rec = _rec(_years_ago(70), "BWM-1", ["recent_fall"])
    task = outreach.start(rec, "fall_check")
    assert task.agent == "outreach" and task.status.value == "working"
    outreach.dismiss(rec, "dental")
    plan = {a.key: a.status for a in outreach.support_plan(rec)}
    assert plan["fall_check"] == "started" and plan["dental"] == "dismissed"


# ---------------------------------------------------------------- agent workflows

@pytest.mark.parametrize("template,inputs", [
    ("bill_dispute", {"biller": "Harbor Light", "issue": "duplicate"}),
    ("pa_appeal", {"service": "MRI of the lower back", "reason": "not_medically_necessary", "urgent": True}),
    ("plan_resource", {"resource": "home_aide"}),
    ("dme", {"equipment": "oxygen", "situation": "renewal_due"}),
    ("caregiving_appeal", {"program": "medicaid_home_care", "hours_before": 20, "hours_after": 12}),
    ("counselor_request", {"focus": "grief"}),
])
def test_every_workflow_stops_for_consent_before_sending(template, inputs):
    rec = _rec(_years_ago(72), "BWM-77031882")
    wf = workflows.start(rec, template, inputs)
    sent = [s for s in wf.steps if s.kind == "send"]
    assert wf.status == "needs_you" and all(s.status == "pending" for s in sent)  # nothing has left
    assert wf.letter and "Signature: ______" in wf.letter and wf.findings
    with pytest.raises(workflows.WorkflowError):
        workflows.approve(rec, wf.id, "Someone Else", "Pat Doe")
    workflows.approve(rec, wf.id, "pat doe", "Pat Doe")
    assert all(s.status == "done" for s in sent) and wf.status == "waiting_on_them" and "/Pat Doe/" in wf.letter
    workflows.respond(rec, wf.id)
    assert wf.status == "won" and wf.outcome
    assert rec.tasks[0].title == wf.title and rec.tasks[0].status.value == "done"


def test_bill_dispute_reports_the_money_saved():
    rec = _rec(_years_ago(40), "EVG-1")
    wf = workflows.start(rec, "bill_dispute", {"issue": "in_network_billed_as_out"})
    workflows.approve(rec, wf.id, "Pat Doe", "Pat Doe")
    assert workflows.respond(rec, wf.id).saved == "$605"


def test_a_denied_appeal_escalates_to_outside_review():
    rec = _rec(_years_ago(72), "BWM-1")
    wf = workflows.start(rec, "pa_appeal", {"service": "home physical therapy", "denied_on": "2026-10-20"})
    assert wf.deadline == "2026-12-24" and "letter" in wf.deadline_note  # 65 days on Medicare Advantage, letter wins
    workflows.approve(rec, wf.id, "Pat Doe", "Pat Doe")
    workflows.respond(rec, wf.id, "denied")
    assert wf.status == "lost"
    nxt = rec.workflows[0]
    assert nxt.template == "external_review" and nxt.status == "needs_you" and "outside" in nxt.letter


def test_rides_need_no_doctors_order_but_an_aide_does():
    rec = _rec(_years_ago(72), "BWM-1")
    rides = workflows.start(rec, "plan_resource", {"resource": "rides"})
    aide = workflows.start(rec, "plan_resource", {"resource": "home_aide"})
    assert rides.step("order").status == "skipped" and aide.step("order").status == "done"


def test_counterparty_numbers_are_fictional():
    from src.sim import counterparties as cp
    nums = list(cp.APPEALS_FAX.values()) + [cp.STATE_AGENCY["fax"], cp.STATE_AGENCY["phone"], cp.DME_SUPPLIER["phone"]]
    assert all(re.fullmatch(r"\(555\) 010-01\d\d", n) for n in nums)


# ---------------------------------------------------------------- the home screen

def test_home_leads_with_actions_and_the_demo_family(client):
    d = client.post("/api/p/demo").json()
    keys = [a["key"] for a in d["actions"]]
    assert keys[:3] == ["find_care", "call_office", "benefits"] and "care_for" in keys
    assert {w["key"] for w in d["workflow_catalog"]} >= {"office_request", "bill_dispute", "pa_appeal", "dme", "caregiving_appeal"}
    people = {p["name"]: p for p in d["circle"]}
    assert people["Rosa Rivera"]["authority"] == "legal_representative"
    assert people["Leo Rivera"]["authority"] == "parent_of_minor"
    rosa = client.post("/api/p/active", json={"person_id": people["Rosa Rivera"]["id"]}).json()
    statuses = {w["template"]: w["status"] for w in rosa["workflows"]}
    assert statuses == {"pa_appeal": "needs_you", "bill_dispute": "won"}
    assert rosa["support_plan"][0]["key"] == "wellness_visit"


# ---------------------------------------------------------------- calling the doctor's office

def _with_doctor(card="BWM-77031882"):
    from src.agents import care_team
    rec = _rec("1948-02-11", card)
    care_team.add_from_directory(rec, "SIM-1002")
    return rec


def test_office_call_works_the_menu_holds_and_gets_the_right_person():
    from src.agents import office_calls
    c = office_calls.call_office(_with_doctor(), "letter", "a letter of medical necessity")
    text = " ".join(t["text"] for t in c["transcript"])
    assert "AI assistant calling on behalf of" in text  # always discloses
    assert c["menu_path"].startswith("pressed 0") and "transferred" in c["menu_path"]  # front desk -> the right person
    assert c["hold_minutes"] == 10 and c["reached"] == "Rob, the doctor's medical assistant" and c["reference"].startswith("R-")
    assert c["shared"] == ["name", "dob", "member_id", "plan"]
    assert not re.search(r"social security|address|card number", text, re.I)  # data minimization


def test_office_request_workflow_and_other_workflows_use_the_caller():
    rec = _with_doctor()
    wf = workflows.start(rec, "office_request", {"purpose": "referral", "details": "referral to a cardiologist"})
    assert wf.status == "waiting_on_them" and wf.calls[0]["reached"] == "Marcus, referral coordinator"
    assert workflows.respond(rec, wf.id).status == "won"
    appeal = workflows.start(rec, "pa_appeal", {"service": "home physical therapy"})
    assert appeal.calls and appeal.calls[0]["purpose"] == "letter"
    no_doc = workflows.start(_rec("1948-02-11", "BWM-1"), "office_request", {"purpose": "refill"})
    assert any("Add the regular doctor first" in f for f in no_doc.findings) and not no_doc.calls
