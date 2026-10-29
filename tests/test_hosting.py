import asyncio
import json

import httpx
import pytest

from src.api import server
from src.swarm.events import EventBus


@pytest.fixture(autouse=True)
def reset(monkeypatch, tmp_path):
    server.STATE.update(bus=EventBus(), task=None, result=None, mode="idle", live_starts=[])
    monkeypatch.setenv("RUN_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setenv("MIN_SECONDS_BETWEEN_RUNS", "0")
    monkeypatch.delenv("APP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("MAX_LIVE_RUNS_PER_DAY", raising=False)
    monkeypatch.setenv("REPLAY_FILE", str(tmp_path / "missing.jsonl"))
    yield
    t = server.STATE["task"]
    if t and not t.done():
        t.cancel()
    server.STATE.update(bus=EventBus(), task=None, result=None, mode="idle", live_starts=[])  # don't leak into other modules


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")


async def wait_done(c, timeout=30):
    for _ in range(int(timeout / 0.1)):
        if not (await c.get("/api/state")).json()["running"]:
            return
        await asyncio.sleep(0.1)
    raise AssertionError("run did not finish")


def types():
    return [e["type"] for e in server.STATE["bus"].history]


async def test_health_config_and_security_headers():
    async with client() as c:
        r = await c.get("/healthz")
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
        cfg = (await c.get("/api/config")).json()
        assert cfg["mock"] is True and cfg["live_enabled"] is True and cfg["replay_available"] is False


async def test_open_demo_runs_live_without_a_token_but_keeps_the_caps(monkeypatch):
    monkeypatch.setenv("APP_ACCESS_TOKEN", "s3cret")  # ignored while the judging window is open
    monkeypatch.setenv("MIN_SECONDS_BETWEEN_RUNS", "3600")
    async with client() as c:
        cfg = (await c.get("/api/config")).json()
        assert cfg["live_enabled"] is True and cfg["token_required"] is False
        assert (await c.post("/api/swarm/start", json={})).status_code == 200
        await wait_done(c)
        assert (await c.post("/api/swarm/start", json={})).status_code == 429  # the caps still hold


async def test_open_demo_needs_a_model_key(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    async with client() as c:
        assert (await c.get("/api/config")).json()["live_enabled"] is False
        assert (await c.post("/api/swarm/start", json={})).status_code == 403
        assert server.STATE["task"] is None


async def test_live_runs_disabled_without_token_when_not_mock(monkeypatch):
    monkeypatch.setenv("OPEN_LIVE_DEMO", "0")
    monkeypatch.setenv("MOCK_LLM", "0")  # real models would be used, so there MUST be a token
    async with client() as c:
        assert (await c.get("/api/config")).json()["live_enabled"] is False
        r = await c.post("/api/swarm/start", json={})
        assert r.status_code == 403
        assert server.STATE["task"] is None  # nothing was started, nothing was spent


async def test_token_gates_live_runs(monkeypatch):
    monkeypatch.setenv("OPEN_LIVE_DEMO", "0")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "s3cret")
    async with client() as c:
        assert (await c.get("/api/config")).json()["token_required"] is True
        assert (await c.post("/api/swarm/start", json={})).status_code == 401
        assert (await c.post("/api/swarm/start", json={}, headers={"x-access-token": "wrong"})).status_code == 401
        assert server.STATE["task"] is None
        r = await c.post("/api/swarm/start", json={}, headers={"x-access-token": "s3cret"})
        assert r.status_code == 200 and r.json()["total"] == 15
        assert (await c.post("/api/swarm/start", json={}, headers={"x-access-token": "s3cret"})).status_code == 409  # busy
        await wait_done(c)
    assert types()[0] == "patient_request" and "swarm_finished" in types()
    assert list((server.Path(server._run_dir())).glob("*-events.jsonl"))  # audit log written


async def test_approve_requires_token(monkeypatch):
    monkeypatch.setenv("OPEN_LIVE_DEMO", "0")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "s3cret")
    async with client() as c:
        r = await c.post("/api/approve", json={"office_id": "off_01", "slot_start": "2026-11-02T10:00"})
        assert r.status_code == 401


async def test_cooldown_and_daily_cap(monkeypatch):
    monkeypatch.setenv("MIN_SECONDS_BETWEEN_RUNS", "60")
    async with client() as c:
        assert (await c.post("/api/swarm/start", json={})).status_code == 200
        await wait_done(c)
        assert (await c.post("/api/swarm/start", json={})).status_code == 429  # cooldown
    monkeypatch.setenv("MIN_SECONDS_BETWEEN_RUNS", "0")
    monkeypatch.setenv("MAX_LIVE_RUNS_PER_DAY", "1")
    async with client() as c:
        r = await c.post("/api/swarm/start", json={})
        assert r.status_code == 429 and "limit" in r.json()["error"]


async def test_replay_is_public_and_replays_in_order(monkeypatch, tmp_path):
    rec = tmp_path / "rec.jsonl"
    lines = [
        {"type": "recording_meta", "source": "mock", "models": None, "recorded_at": "2026-10-27"},
        {"seq": 0, "ts": 100.0, "type": "swarm_started", "total": 1, "offices": []},
        {"seq": 1, "ts": 100.5, "type": "status", "office_id": "off_00", "status": "talking"},
        {"seq": 2, "ts": 101.0, "type": "swarm_finished", "best": None, "truth": {}, "success_rate": 1.0, "safety_pass_rate": 1.0, "leaderboard": []},
    ]
    rec.write_text("\n".join(json.dumps(x) for x in lines))
    monkeypatch.setenv("REPLAY_FILE", str(rec))
    monkeypatch.setenv("APP_ACCESS_TOKEN", "s3cret")  # live is locked, replay must still work
    async with client() as c:
        assert (await c.get("/api/config")).json()["replay_available"] is True
        r = await c.post("/api/replay", json={"speed": 1000})  # no token header
        assert r.status_code == 200 and r.json()["events"] == 3 and r.json()["source"] == "mock"
        await wait_done(c)
        assert (await c.get("/api/state")).json()["mode"] == "replay"
    assert types() == ["replay_started", "swarm_started", "status", "swarm_finished"]
    assert [e["seq"] for e in server.STATE["bus"].history] == [0, 1, 2, 3]  # fresh, monotonic seq


async def test_replay_404_when_no_recording():
    async with client() as c:
        assert (await c.post("/api/replay", json={})).status_code == 404


def _wav(n_samples: int = 1600) -> bytes:
    import struct
    data = b"\x00\x00" * n_samples
    return b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16) + b"data" + struct.pack("<I", len(data)) + data


async def test_voice_intake_is_token_gated_and_validates_audio(monkeypatch):
    monkeypatch.setenv("OPEN_LIVE_DEMO", "0")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "s3cret")
    async with client() as c:
        assert (await c.post("/api/intake/transcribe", content=_wav())).status_code == 401  # spends credits: token required
        h = {"x-access-token": "s3cret", "content-type": "audio/wav"}
        assert (await c.post("/api/intake/transcribe", content=b"not audio", headers=h)).status_code == 415
        assert (await c.post("/api/intake/transcribe", content=_wav(1_100_000), headers=h)).status_code == 413
        r = await c.post("/api/intake/transcribe", content=_wav(), headers=h)
        assert r.status_code == 200 and "cardiologist" in r.json()["text"]  # mock transcript


async def test_voice_intake_reports_api_errors(monkeypatch):
    from src import voice

    monkeypatch.setenv("MOCK_LLM", "0")
    monkeypatch.setenv("APP_ACCESS_TOKEN", "s3cret")

    def fake(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/asr/transcribe" and b'"audioEncoding": "WAV"' in request.content
        return httpx.Response(400, json={"error": {"message": "Malformed request"}})

    real = httpx.AsyncClient
    async with client() as c:  # created before the patch below, which is module-wide
        monkeypatch.setattr(voice.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(fake), **kw))
        r = await c.post("/api/intake/transcribe", content=_wav(), headers={"x-access-token": "s3cret"})
    assert r.status_code == 502 and "Malformed request" in r.json()["error"]


async def test_directory_endpoint_serves_the_local_snapshot():
    async with client() as c:
        r = await c.get("/api/directory")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == len(d["providers"]) > 0 and d["metro"].startswith("Phoenix")
        assert {"npi", "name", "city", "payers"} <= set(d["providers"][0])
        assert (await c.get("/api/directory", params={"metro": "../../etc"})).status_code == 404


async def test_swarm_starts_with_a_real_directory_search_for_the_named_payer():
    async with client() as c:
        r = await c.post("/api/swarm/start", json={"utterance": "I have Cigna and need a cardiologist, nothing before 9"})
        assert r.status_code == 200
        await wait_done(c)
    hist = server.STATE["bus"].history
    req = next(e for e in hist if e["type"] == "patient_request")
    d = next(e for e in hist if e["type"] == "directory_search")
    started = next(e for e in hist if e["type"] == "swarm_started")
    assert req["payer"] == "Cigna" and started["patient"]["payer"] == "Cigna"
    assert d["available"] and d["payer"] == "cigna" and 0 < d["accepting_new_patients"] <= d["in_network"] <= d["providers_total"]
    assert [o.get("city") for o in started["offices"]] == [s["city"] for s in d["stand_ins"]]
    assert types().index("directory_search") < types().index("swarm_started")


async def test_unavailable_payer_says_why_and_falls_back():
    async with client() as c:
        assert (await c.post("/api/swarm/start", json={"utterance": "cardiologist, I'm on Aetna"})).status_code == 200
        await wait_done(c)
    d = next(e for e in server.STATE["bus"].history if e["type"] == "directory_search")
    assert d["payer"] == "uhc" and d["available"]
    assert d["requested"]["payer"] == "aetna" and not d["requested"]["available"] and "credentials" in d["requested"]["reason"]
