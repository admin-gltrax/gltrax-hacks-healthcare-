"""Partner credits (Muse Spark Open on Baseten and Fireworks) push the frontier:
an adversarial insurer-side reviewer, a call gym of simulated receptionists,
cross-family judges and the bigger reader eval. THE RULE: the patient-facing
crew stays on Meta's Model API. Offline, these tests prove the code guards."""
import asyncio
import json

import pytest

from src import config
from src.agents import ai, appeals, reviewer, workflows
from src.llm import ChatResult
from tests.conftest import ScriptedLLM
from tests.test_spark_crew import _rosa

RULES = ["The member is homebound.", "A doctor has certified a plan of care."]
FACTS = {"member_id": "BWM-77031882", "service": "home physical therapy", "subject_of": "home physical therapy",
         "plan_reason": "not medically necessary", "to": "the plan"}
BODY = ("To whom it may concern, I am appealing the denial of home physical therapy for member ID BWM-77031882. "
        "My doctor ordered it and the records show why I need it. Please send me your decision in writing. " * 2)


@pytest.fixture(autouse=True)
def _fresh_budget(monkeypatch):
    monkeypatch.setattr(ai, "BUDGET", ai.Budget())


def _by_role(monkeypatch, **scripts):
    fakes = {r: ScriptedLLM(s) for r, s in scripts.items()}

    def llm(role, account=None):
        if role not in fakes:
            raise AssertionError(f"unexpected model call: {role}")
        return fakes[role]
    monkeypatch.setattr(ai, "llm", llm)
    return fakes


def _j(d) -> ChatResult:
    return ChatResult(content=json.dumps(d))


# ---------------------------------------------------------------- THE RULE: providers by role

def test_patient_facing_crew_stays_on_meta_and_partner_roles_use_their_own_keys(monkeypatch):
    rv = config.role_cfg("reviewer")
    assert rv.base_url == "https://inference.baseten.co/v1" and rv.api_key_env == "BASETEN_API_KEY"
    assert rv.model == "meta-models/muse-spark-open"
    monkeypatch.setenv("REVIEWER_PROVIDER", "fireworks")
    rv = config.role_cfg("reviewer")
    assert rv.base_url.startswith("https://api.fireworks.ai") and rv.model == "accounts/fireworks/models/muse-spark-open"
    assert config.role_cfg("judge_open").api_key_env == "FIREWORKS_API_KEY"
    monkeypatch.setenv("OFFICE_PROVIDER", "fireworks")  # the simulated receptionists may move to partner credits
    assert ai.model_for("office").endswith("muse-spark-open")
    for role in config.PATIENT_FACING:  # ...the patient-facing crew may not
        monkeypatch.setenv(f"{role.upper()}_PROVIDER", "fireworks")
        with pytest.raises(ai.AIUnavailable):
            ai.model_for(role)
    monkeypatch.setenv("REVIEWER_MODEL", "meta-models/muse-spark-open-contributor")
    with pytest.raises(ai.AIUnavailable):
        ai.model_for("reviewer")


def test_json_mode_hosts_get_the_schema_in_the_prompt(monkeypatch):
    fakes = _by_role(monkeypatch, reviewer=[_j({"verdict": "approve", "objections": []})])
    seen = {}
    orig = fakes["reviewer"].chat

    async def spy(messages, tools=None, response_format=None, max_tokens=None):
        seen.update(rf=response_format, text=messages[-1]["content"])
        return await orig(messages, tools, response_format, max_tokens)
    fakes["reviewer"].chat = spy
    asyncio.run(reviewer.review("x", "y", RULES, [], BODY, 1, None))
    assert seen["rf"] == {"type": "json_object"} and '"verdict"' in seen["text"] and "JSON Schema" in seen["text"]


# ---------------------------------------------------------------- the adversarial plan reviewer

def test_the_reviewer_tries_to_deny_the_appeal_and_the_writer_revises():
    rec = _rosa()
    wf = workflows.start(rec, "pa_appeal", {"document": {"sample": "denial_letter"}}, account="t")
    keys = [s.key for s in wf.steps]
    assert keys.index("draft") < keys.index("review") < keys.index("approve")
    st = wf.step("review")
    assert st.status == "done" and "muse-spark-open" in st.engine and wf.status == "needs_you"
    r1, r2 = wf.review["rounds"]
    assert r1["verdict"] == "deny" and [o["rule_id"] for o in r1["objections"]] == ["R1"]
    assert r1["invented_rules_dropped"] == 1  # the mock cites "R99", which the plan doesn't have
    assert r1["revision"]["accepted"] and all(c["ok"] for c in r1["revision"]["checks"])
    assert r2["verdict"] == "approve" and wf.review["passed"] and wf.review["todos"] == []
    assert wf.review["original"] != wf.review["final"] and wf.review["final"] in wf.letter
    assert "Signature: ____" in wf.letter and "BWM-77031882" in wf.letter
    check = next(c for c in wf.checks if c["what"].startswith("Stress test"))
    assert "made-up rule" in check["items"][0]["detail"]
    assert "Plan policy 12.4" not in wf.letter  # an invented rule never reaches the letter


def test_objections_must_cite_real_rules_and_the_reviewer_never_writes_the_letter():
    raw = {"verdict": "deny", "letter": "Dear plan, here is a better letter...",
           "objections": [{"rule_id": "R7", "reason": "Policy 9.1 says no.", "fix": "letter", "needs": "x"},
                          {"rule_id": "2", "reason": "No certified plan of care is on file.", "fix": "evidence", "needs": "The signed plan of care"},
                          {"rule_id": "R2", "reason": "duplicate", "fix": "letter", "needs": ""},
                          "not an object"]}
    out = reviewer.clean_review(raw, RULES)
    assert [o["rule_id"] for o in out["objections"]] == ["R2"] and out["objections"][0]["rule"] == RULES[1]
    assert out["invented_rules_dropped"] == 1 and out["letter_text_ignored"] and "letter" not in json.dumps(out["objections"])
    only_invented = reviewer.clean_review({"verdict": "deny", "objections": [{"rule_id": "R9", "reason": "nope", "fix": "letter"}]}, RULES)
    assert only_invented["verdict"] == "approve"  # no real reason to deny left is a pass


def test_missing_evidence_becomes_plain_todos_and_no_rewording_is_attempted(monkeypatch):
    deny = _j({"verdict": "deny", "objections": [{"rule_id": "R1", "reason": "Nothing shows she's homebound.", "fix": "evidence",
                                                   "needs": "A note from the doctor saying leaving home takes a taxing effort"}]})
    fakes = _by_role(monkeypatch, reviewer=[deny], writer=[])
    r = asyncio.run(reviewer.stress_test("appeal", FACTS, BODY, RULES, [], None))
    assert not r["passed"] and len(r["rounds"]) == 1 and fakes["writer"].calls == 0 and not r["revised"]
    assert r["todos"] == ['A note from the doctor saying leaving home takes a taxing effort (for the plan\'s rule: "The member is homebound").']


def test_a_revision_that_fails_the_letter_checks_is_never_used(monkeypatch):
    deny = _j({"verdict": "deny", "objections": [{"rule_id": "R2", "reason": "The letter never mentions the plan of care.",
                                                   "fix": "letter", "needs": "Say the doctor certified it"}]})
    bad = _j({"subject": "x", "body": "Member BWM-77031882. The plan owes me $4,000 for 30 visits of home physical therapy. " * 5})
    _by_role(monkeypatch, reviewer=[deny], writer=[bad])
    r = asyncio.run(reviewer.stress_test("appeal", FACTS, BODY, RULES, [], None))
    rev = r["rounds"][0]["revision"]
    assert rev["accepted"] is False and r["body"] == BODY and not r["revised"] and "letter checks" in r["note"]


def test_the_loop_stops_after_three_rounds_with_what_is_still_missing(monkeypatch):
    deny = _j({"verdict": "deny", "objections": [{"rule_id": "R1", "reason": "Homebound status isn't argued.", "fix": "letter", "needs": "Explain it"}]})
    ok = _j({"subject": "x", "body": BODY + " I can't leave home without great effort, as the records on file show."})
    fakes = _by_role(monkeypatch, reviewer=[deny, deny, deny], writer=[ok, ok])
    r = asyncio.run(reviewer.stress_test("appeal", FACTS, BODY, RULES, [], None))
    assert len(r["rounds"]) == 3 and fakes["writer"].calls == 2 and not r["passed"] and r["todos"] and r["revised"]


def test_reviewer_unavailable_skips_the_step_and_leaves_the_appeal_alone(monkeypatch):
    async def down(*a, **k):
        raise ai.AIUnavailable("403 from Baseten")
    monkeypatch.setattr(reviewer, "stress_test", down)
    wf = workflows.start(_rosa(), "pa_appeal", {"document": {"sample": "denial_letter"}}, account="t")
    st = wf.step("review")
    assert st.status == "skipped" and st.engine is None and "403 from Baseten" in st.detail and wf.status == "needs_you"
    assert wf.review == {} and "Signature: ____" in wf.letter
    monkeypatch.setenv("REVIEWER_API_KEY_ENV", "NO_SUCH_KEY_FOR_TESTS")
    monkeypatch.setenv("MOCK_LLM", "0")  # no key for the reviewer: the step says so instead of failing
    assert ai.role_ready("reviewer") is False


def test_the_prebuilt_demo_skips_the_stress_test_and_spends_nothing():
    wf = workflows.start(_rosa(), "pa_appeal", {"service": "MRI"}, live=False)
    assert wf.step("review").status == "skipped" and ai.BUDGET.status()["used_today"] == 0
