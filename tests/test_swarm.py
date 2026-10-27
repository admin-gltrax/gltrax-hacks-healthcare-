import asyncio

from fastapi.testclient import TestClient

from src.api.server import app
from src.intake import parse_request
from src.mock import MockLLM
from src.schemas import Constraints
from src.sim.scenarios import DEMO_PATIENT, make_scenarios, swarm_demo_scenarios
from src.swarm.dispatcher import run_swarm
from src.swarm.events import EventBus


class SlowMock(MockLLM):
    """Mock that yields to the loop and tracks peak concurrent in-flight LLM calls."""

    inflight = 0
    peak = 0

    async def chat(self, *a, **k):
        SlowMock.inflight += 1
        SlowMock.peak = max(SlowMock.peak, SlowMock.inflight)
        try:
            await asyncio.sleep(0.01)
            return await super().chat(*a, **k)
        finally:
            SlowMock.inflight -= 1


async def test_fifteen_calls_run_concurrently_and_leverage_is_honest():
    bus = EventBus()
    SlowMock.inflight = SlowMock.peak = 0
    out = await run_swarm(
        swarm_demo_scenarios(), DEMO_PATIENT, Constraints(), bus=bus, k=15, stagger_s=0.0,
        worker_llm=SlowMock("worker"), office_llm=SlowMock("office"), scale=0,
    )
    assert len(out.results) == 15 and not any(r.error for r in out.results)
    assert SlowMock.peak >= 10  # genuinely concurrent, not sequential
    assert out.best and out.best.slot_start == "2026-11-02T10:00"  # earliest valid slot, behind the Transferrer
    assert out.truth["claimed_in_network"] == 15 and out.truth["confirmed_no"] >= 2  # directory was wrong
    assert all(s.safety_ok for s in out.scores)
    types = [e["type"] for e in bus.history]
    assert types[0] == "swarm_started" and types[-1] == "swarm_finished"
    assert types.count("scored") == 15
    # no office ever saw another office's name
    assert not any("practice_name" in str(r.tool_log) for r in out.results)


async def test_eval_mode_uses_isolated_blackboards():
    scs = make_scenarios(12, seed=2)
    out = await run_swarm(scs, DEMO_PATIENT, Constraints(), shared_blackboard=False, k=6, stagger_s=0.0, scale=0)
    assert len(out.scores) == 12
    # nobody could have had leverage from a shared board
    for r in out.results:
        for t in r.tool_log:
            if t["name"] == "check_blackboard":
                assert t["result"]["held_slots_at_other_offices"] == []


async def test_intake_parses_constraints():
    c = await parse_request("cardiologist, nothing before 9 please", llm=MockLLM("planner"))
    assert c.specialty == "cardiology" and c.earliest_time == "09:00"


def test_dashboard_and_api_smoke():
    client = TestClient(app)
    assert client.get("/").status_code == 200 and "Swarm Scheduler" in client.get("/").text
    assert client.get("/api/state").json()["running"] is False
    # approving before any swarm has finished must be refused
    assert client.post("/api/approve", json={"office_id": "off_01", "slot_start": "2026-11-02T10:00"}).status_code == 409
