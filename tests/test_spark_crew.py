"""PJ's crew on the Meta models: the caller, reader, strategist, writer and PJ's
chat. Offline (MOCK_LLM=1), these tests run the same code paths as live and
prove the guards: what the code enforces no matter what a model says."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from src.agents import ai, appeals, care_team, guide, office_calls, reader, reviewer, workflows
from src.agents.office_caller import OfficeCall
from src.api.server import app
from src.eval.pj_redteam import CASES, check
from src.llm import ChatResult, ToolCall
from src.patient.demo import build_demo
from src.patient.models import HealthRecord, Patient
from src.patient.store import reset_store
from src.safety import SAFETY_BLOCK
from src.sim.documents import SAMPLES
from tests.conftest import ScriptedLLM

PJ_SAFETY_SHA = "3d69fb785b195079cbbf266f75cea43e5dc5bcf39497a452c6b3d91fb46eeb29"


@pytest.fixture()
def client():
    reset_store()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_budget(monkeypatch):
    monkeypatch.setattr(ai, "BUDGET", ai.Budget())


def _rosa() -> HealthRecord:
    acct = asyncio.run(build_demo(HealthRecord(patient=Patient(display_name="Alex Rivera"))))
    return acct.circle[0].record


# ---------------------------------------------------------------- the gateway

def test_budget_caps_and_contributor_models_are_refused(monkeypatch):
    monkeypatch.setenv("PJ_AI_ACCOUNT_REQUESTS", "2")
    b = ai.Budget()
    b.spend("a"), b.spend("a")
    with pytest.raises(ai.AIUnavailable):
        b.spend("a")
    b.spend("b")  # another account still has its own allowance
    monkeypatch.setenv("CALLER_MODEL", "muse-spark-1.3-contributor")
    with pytest.raises(ai.AIUnavailable):
        ai.llm("caller")
    monkeypatch.setenv("PJ_AI", "off")
    assert ai.enabled() is False


def test_the_prebuilt_demo_family_spends_nothing():
    _rosa()
    assert ai.BUDGET.status()["used_today"] == 0


# ---------------------------------------------------------------- the caller (Muse Spark)

def test_live_caller_works_the_menu_gets_transferred_and_proves_what_it_heard():
    rec = _rosa()
    lines = []
    c = asyncio.run(office_calls.call_office_live(rec, "letter", "a letter of medical necessity", on_line=lambda s, t: lines.append(s)))
    assert c["ok"] and c["engine"].endswith("muse-spark-1.3") and c["requests"] > 4
    assert c["reached"] == "Rob, the doctor's medical assistant" and "transferred" in c["menu_path"] and c["hold_minutes"] == 10
    assert all(c["checks"].values()), c["checks"]  # disclosed AI to each person, no extra data, reference heard on the call
    assert set(c["shared"]) <= {"name", "dob", "member_id", "plan"}
    assert c["reference"] in " ".join(t["text"] for t in c["transcript"] if t["speaker"] == "office")
    assert "hold" in lines and lines == [t["speaker"] for t in c["transcript"]]  # streamed live, in order
    said = " ".join(t["text"] for t in c["transcript"] if t["speaker"] == "pj")
    assert "address" in " ".join(t["text"] for t in c["transcript"] if t["speaker"] == "office").lower()  # the front desk fished
    assert "can only give" in said  # and PJ refused


def test_caller_uses_the_same_immutable_safety_block_and_keeps_tool_order():
    rec = _rosa()
    call = OfficeCall("Harbor Light Internal Medicine", None, "refill", "", office_calls.shared_fields(rec),
                      ai.llm("caller"), ai.llm("office"))
    asyncio.run(call.run())
    assert call.msgs[0]["content"].startswith(SAFETY_BLOCK)
    for i, m in enumerate(call.msgs):  # every tool_call is answered by tool messages right after it (Meta returns 400 otherwise)
        if m["role"] == "assistant" and m.get("tool_calls"):
            ids = [t["id"] for t in m["tool_calls"]]
            assert [x.get("tool_call_id") for x in call.msgs[i + 1:i + 1 + len(ids)]] == ids


def test_a_reference_number_the_office_never_said_is_not_trusted():
    rec = _rosa()
    caller = ScriptedLLM([
        ChatResult(tool_calls=[ToolCall("t1", "press_dtmf", {"digits": "2"})]),
        ChatResult("Hi, I'm an AI assistant calling on behalf of Rosa Rivera, with her permission, about a refill."),
        ChatResult("It's Rosa Rivera, date of birth 1948-02-11."),
        ChatResult(tool_calls=[ToolCall("t2", "record_result", {"reference": "R-99999", "handled_by": "x", "business_days": 1, "next": "done"}),
                               ToolCall("t3", "end_call", {"summary": "done"})]),
    ])
    c = OfficeCall("Harbor Light Internal Medicine", None, "refill", "", office_calls.shared_fields(rec), caller, ai.llm("office"))
    out = asyncio.run(c.run())
    assert out["reference"] == "not confirmed" and out["ok"] is False and out["checks"]["reference_heard_on_call"] is False


def test_caller_that_skips_the_ai_disclosure_fails_the_check():
    rec = _rosa()
    caller = ScriptedLLM([ChatResult(tool_calls=[ToolCall("t1", "press_dtmf", {"digits": "2"})]),
                          ChatResult("Hi, this is Rosa's daughter calling about a refill."),
                          ChatResult(tool_calls=[ToolCall("t2", "end_call", {"summary": "x"})])])
    out = asyncio.run(OfficeCall("Harbor Light Internal Medicine", None, "refill", "", office_calls.shared_fields(rec),
                                 caller, ai.llm("office")).run())
    assert out["checks"]["disclosed_ai_to_each_person"] is False


# ---------------------------------------------------------------- the reader (Spark vision) and the money math

def test_reader_validates_what_the_model_returns():
    raw = {"service": "MRI", "denied_on": "October 20", "reason_category": "made_up", "reason_quote": "words not in the letter",
           "criteria": ["a", ""], "appeal_by": "2026-12-24", "appeal_days": "65"}
    out = reader.clean("denial_letter", raw, source_text="The MRI was denied because it isn't needed.")
    assert out["denied_on"] == "" and "denied_on" in out["_dropped"]
    assert out["reason_category"] == "not_sure" and out["reason_quote"] == "" and "reason_quote" in out["_dropped"]
    assert out["criteria"] == ["a"] and out["appeal_by"] == "2026-12-24" and out["appeal_days"] == 65
    bill = reader.clean("bill", {"lines": [{"code": "99214", "description": "x", "amount": "$1,210.50"},
                                           {"code": "1", "description": "y", "amount": "lots"}], "amount_due": None})
    assert bill["lines"][0]["amount"] == 1210.5 and len(bill["lines"]) == 1 and bill["amount_due"] == 1210.5
    with pytest.raises(reader.ReadError):
        reader.check_image("data:text/html;base64,PGgxPg==")


def test_the_money_math_is_code_not_the_model():
    m = reader.match_bill(SAMPLES["bill"]["truth"], SAMPLES["eob"]["truth"])
    assert m["billed"] == 493 and m["owed"] == 0 and m["overcharge"] == 493
    assert any("billed 2 times" in p for p in m["problems"])


# ---------------------------------------------------------------- the appeal crew end to end

def test_appeal_from_a_photo_of_the_denial_letter():
    rec = _rosa()
    wf = workflows.start(rec, "pa_appeal", {"document": {"sample": "denial_letter"}}, account="t")
    assert wf.status == "needs_you" and wf.title == "Appeal the denial of home health physical therapy"
    assert wf.deadline == "2026-12-24" and "Read from the denial letter" in wf.deadline_note  # the letter wins
    assert wf.inputs["case_number"] == "SIM-PA-20431" and wf.inputs["appeals_fax"] == "(555) 010-0153"
    engines = {s.key: s.engine for s in wf.steps}
    assert "muse-spark" in engines["denial"] and "muse-wonder" in engines["criteria"] and "muse-spark" in engines["draft"]
    assert wf.calls[0]["ok"] and "muse-spark" in wf.calls[0]["engine"]
    # the strategist's made-up citation (the mock cites rec-999) was removed and flagged
    assert all("rec-999" not in r["evidence_ids"] for r in wf.criteria)
    assert wf.checks[0]["passed"] is False and "made-up" in wf.checks[0]["items"][0]["detail"]
    assert all(r["status"] == "missing" or r["evidence_ids"] for r in wf.criteria)
    letter_check = next(c for c in wf.checks if c["what"].startswith("Appeal letter"))
    assert letter_check["passed"] and "BWM-77031882" in wf.letter and "Signature: ____" in wf.letter
    assert "base64" not in wf.model_dump_json()  # the image is read, never stored


def test_a_letter_that_invents_a_number_never_reaches_the_signature(monkeypatch):
    async def bad(kind, facts, account):
        return f"I am member {facts['member_id']}. The plan owes me $9,999 and I need 400 visits. " * 6
    monkeypatch.setattr(appeals, "draft_letter", bad)
    wf = workflows.start(_rosa(), "pa_appeal", {"document": {"sample": "denial_letter"}})
    check_ = next(c for c in wf.checks if c["what"].startswith("Appeal letter"))
    assert check_["passed"] is False and "9999" not in wf.letter and "$9,999" not in wf.letter
    assert next(s for s in wf.steps if s.key == "draft").detail.endswith("PJ used the standard letter.)")


def test_bill_dispute_from_photos_saves_what_the_math_says():
    rec = _rosa()
    wf = workflows.start(rec, "bill_dispute", {"bill_doc": {"sample": "bill"}, "eob_doc": {"sample": "eob"}})
    assert wf.title == "Contest the bill from Harbor Light Internal Medicine" and wf.inputs["billed"] == 493
    assert [d["kind"] for d in wf.documents] == ["bill", "eob"] and wf.checks[-1]["passed"]
    workflows.approve(rec, wf.id, "Rosa Rivera", "Rosa Rivera")
    assert workflows.respond(rec, wf.id).saved == "$493"


def test_every_model_step_falls_back_to_the_rules(monkeypatch):
    async def down(*a, **k):
        raise ai.AIUnavailable("API down")
    monkeypatch.setattr(office_calls, "call_office_live", down)
    monkeypatch.setattr(reader, "read", down)
    monkeypatch.setattr(appeals, "map_criteria", down)
    monkeypatch.setattr(appeals, "draft_letter", down)
    monkeypatch.setattr(reviewer, "stress_test", down)
    wf = workflows.start(_rosa(), "pa_appeal", {"document": {"sample": "denial_letter"}, "service": "MRI"})
    assert wf.step("review").status == "skipped" and "unchanged" in wf.step("review").detail
    assert wf.status == "needs_you" and wf.letter and wf.calls[0]["engine"] == "rules" and wf.calls[0]["fallback"] == "API down"
    assert {s.engine for s in wf.steps if s.kind == "agent"} <= {None, "rules"}
    monkeypatch.setenv("PJ_AI", "off")
    off = workflows.start(_rosa(), "office_request", {"purpose": "refill"})
    assert off.calls[0]["engine"] == "rules" and off.status == "waiting_on_them"


def test_background_mode_streams_then_finishes_and_saves(monkeypatch):
    monkeypatch.setenv("PJ_BACKGROUND", "1")
    saved = []
    orig = office_calls.call_office_live

    async def slow(*a, **k):
        await asyncio.sleep(0.3)
        return await orig(*a, **k)
    monkeypatch.setattr(office_calls, "call_office_live", slow)
    rec = _rosa()
    wf = workflows.start(rec, "office_request", {"purpose": "referral"}, save=lambda: saved.append(1))
    assert workflows.busy(rec) and wf.steps[1].status == "working" and wf.calls[0]["live"] is True
    for _ in range(100):
        if not workflows.busy(rec):
            break
        time.sleep(0.05)
    assert wf.status == "waiting_on_them" and wf.calls[0]["ok"] and saved


# ---------------------------------------------------------------- PJ's chat on Muse Spark

def test_pj_safety_block_is_pinned():
    assert guide.PJ_SAFETY_SHA == PJ_SAFETY_SHA


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:40] for c in CASES])
def test_pj_red_team(case):
    rec = _rosa()
    before = len(rec.workflows)
    ans = asyncio.run(guide.ask_live(rec, case["text"], account="t"))
    assert check(case, ans) == []
    assert len(rec.workflows) == before  # PJ proposes; it never starts work from chat


def test_crisis_and_medical_questions_never_reach_the_model(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a model was called")
    monkeypatch.setattr(ai, "llm", boom)
    rec = _rosa()
    assert "988" in asyncio.run(guide.ask_live(rec, "I want to end my life"))["say"]
    assert "nurse" in asyncio.run(guide.ask_live(rec, "how many mg of aspirin should she take"))["say"]


def test_a_reply_that_promises_a_card_it_never_made_is_dropped(monkeypatch):
    fake = ScriptedLLM([ChatResult("Tap the card above to start."), ChatResult("Tap the card above to start.")])
    monkeypatch.setattr(ai, "llm", lambda role, account=None: fake)
    ans = asyncio.run(guide.ask_live(_rosa(), "what can you do for me?"))
    assert ans["engine"] == "rules" and "card" in ans["note"] and fake.calls == 2  # one nudge, then the rules answer


# ---------------------------------------------------------------- the API

def test_api_reads_a_sample_and_reports_the_models(client):
    d = client.post("/api/p/demo").json()
    assert d["ai"]["enabled"] and {m["role"] for m in d["ai"]["models"]} >= {"caller", "reader", "strategist", "writer", "pj"}
    assert [s["kind"] for s in d["samples"]] == ["denial_letter", "bill", "eob"] and d["busy"] is False
    assert client.get(d["samples"][0]["url"]).status_code == 200 and client.get("/samples/nope.png").status_code == 404
    rosa = next(p for p in d["circle"] if p["name"] == "Rosa Rivera")
    client.post("/api/p/active", json={"person_id": rosa["id"]})
    d = client.post("/api/p/workflows", json={"template": "pa_appeal", "inputs": {"document": {"sample": "denial_letter"}}}).json()
    wf = next(w for w in d["workflows"] if w["id"] == d["workflow_id"])
    assert wf["deadline"] == "2026-12-24" and wf["documents"][0]["kind"] == "denial_letter" and wf["criteria"]
    assert client.post("/api/p/workflows", json={"template": "pa_appeal", "inputs": {"document": {"image": "data:text/html;base64,AA=="}}}).status_code == 400
    a = client.post("/api/p/ask", json={"text": "my mom's bill looks too high"}).json()["answer"]
    assert a["proposal"]["template"] == "bill_dispute" and "muse-spark" in a["engine"]
    assert json.dumps(d).count("data:image") == 0


# ---------------------------------------------------------------- storage

def test_sqlite_store_survives_a_restart_and_delete_means_delete(tmp_path, monkeypatch):
    from src.patient import store as st
    monkeypatch.setenv("PATIENT_DB", str(tmp_path / "p.db"))
    st.reset_store()
    c = TestClient(app)
    d = c.post("/api/p/demo").json()
    token = c.cookies.get("pj_session")
    raw = (tmp_path / "p.db").read_bytes()
    assert token.encode() not in raw  # only a hash of the session token is stored
    st.reset_store()  # "restart": a fresh process reads the database
    again = c.get("/api/p/me").json()
    assert again["patient"]["display_name"] == d["patient"]["display_name"] and len(again["circle"]) == len(d["circle"])
    assert c.delete("/api/p/me").json() == {"deleted": True}
    assert c.get("/api/p/me").status_code == 401
    st.store().put(token, HealthRecord(patient=Patient(display_name="ghost")))  # an agent finishing late can't revive it
    st.reset_store()
    c.cookies.set("pj_session", token)
    assert c.get("/api/p/me").status_code == 401


def test_oversized_uploads_are_refused(client):
    r = client.post("/api/p/workflows", content=b"x" * 12_000_001, headers={"content-type": "application/json"})
    assert r.status_code == 413
