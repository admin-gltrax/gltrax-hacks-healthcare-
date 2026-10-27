"""FastAPI app: starts swarms, streams events over SSE, serves the dashboard.

    uvicorn src.api.server:app --host 0.0.0.0 --port 8000

Hosting model (single process, in-memory state, so run exactly ONE instance):
- Anyone can open the dashboard and watch a recorded run (POST /api/replay). Free, safe, no keys used.
- Live runs spend model credits, so they require APP_ACCESS_TOKEN (header X-Access-Token).
  With no token configured, live runs are disabled unless MOCK_LLM=1 (offline demo mode).
"""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import time
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from ..config import mock_enabled
from ..intake import detect_payer, parse_request
from ..schemas import Constraints
from ..sim.scenarios import DEFAULT_PAYER, PAYER_PLANS, make_scenarios, patient_for, swarm_demo_scenarios
from ..swarm.candidates import directory_search
from ..swarm.dispatcher import run_swarm
from ..swarm.events import EventBus
from ..directory.nppes import METROS, TAXONOMIES
from ..directory.store import directory_view
from ..voice import MAX_WAV_BYTES, TranscribeError, transcribe_wav

STATIC = Path(__file__).parent / "static"
ROOT = Path(__file__).resolve().parents[2]

app = FastAPI(title="Swarm Scheduler")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


STATE: dict = {
    "bus": EventBus(),
    "task": None,
    "result": None,
    "constraints": Constraints(),
    "mode": "idle",  # idle | live | replay
    "live_starts": [],  # unix timestamps of live starts (for rate limits)
}


# ---- settings are read per request so they can be changed without a restart in tests ----
def _token() -> str:
    return os.getenv("APP_ACCESS_TOKEN", "")


def _replay_file() -> Path:
    return Path(os.getenv("REPLAY_FILE", str(ROOT / "recordings" / "demo.jsonl")))


def _run_dir() -> Path:
    return Path(os.getenv("RUN_DIR", str(ROOT / "data" / "runs")))


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def live_enabled() -> bool:
    return mock_enabled() or bool(_token())


def require_live(x_access_token: str | None = Header(default=None)) -> None:
    """Live runs and approvals spend credits / act for the patient: gate them."""
    token = _token()
    if not token:
        if mock_enabled():
            return  # offline demo mode: nothing to protect
        raise HTTPException(403, "Live runs are disabled on this server (APP_ACCESS_TOKEN is not set).")
    if not x_access_token or not hmac.compare_digest(x_access_token.encode(), token.encode()):
        raise HTTPException(401, "Invalid or missing access token.")


def _busy() -> bool:
    t = STATE["task"]
    return bool(t and not t.done())


class StartBody(BaseModel):
    demo: bool = True  # the fixed 15-office swarm
    n: int = 15
    seed: int = 1
    k: int = 15
    utterance: str | None = None  # patient's request; parsed into constraints if given


class ApproveBody(BaseModel):
    office_id: str
    slot_start: str


class ReplayBody(BaseModel):
    speed: float = 1.0


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/config")
def config():
    return {
        "live_enabled": live_enabled(),
        "token_required": bool(_token()),
        "mock": mock_enabled(),
        "replay_available": _replay_file().exists(),
    }


@app.get("/api/directory")
def directory(metro: str = "phoenix", specialty: str = "cardiology"):
    """Public and free: real providers from the local directory snapshots. Nothing is fetched live."""
    if metro not in METROS or specialty not in TAXONOMIES:
        return JSONResponse({"error": "unknown metro or specialty"}, status_code=404)
    try:
        return directory_view(metro, specialty)
    except FileNotFoundError:
        return JSONResponse({"error": "no directory snapshot on this server"}, status_code=404)


@app.get("/api/state")
def state():
    return {"running": _busy(), "mode": STATE["mode"], "events": len(STATE["bus"].history)}


@app.post("/api/swarm/start", dependencies=[Depends(require_live)])
async def start(body: StartBody | None = None):
    body = body or StartBody()
    if _busy():
        return JSONResponse({"error": "a swarm is already running"}, status_code=409)

    # Cost guards: a cooldown between runs and a rolling 24h cap.
    now = time.time()
    recent = [t for t in STATE["live_starts"] if now - t < 86400]
    if recent and now - recent[-1] < _int_env("MIN_SECONDS_BETWEEN_RUNS", 10):
        return JSONResponse({"error": "please wait a few seconds between live runs"}, status_code=429)
    if len(recent) >= _int_env("MAX_LIVE_RUNS_PER_DAY", 30):
        return JSONResponse({"error": "daily live-run limit reached"}, status_code=429)
    STATE["live_starts"] = recent + [now]

    constraints = Constraints()
    if body.utterance:
        constraints = await parse_request(body.utterance[:500])
    # The insurer the patient names picks whose real directory is searched; others fall back to the default.
    named = detect_payer(body.utterance)
    payer = named if named in PAYER_PLANS else DEFAULT_PAYER
    patient = patient_for(payer)
    directory = directory_search(payer, specialty=constraints.specialty)
    if named and named != payer:  # e.g. Aetna: say why, then run on the default payer's directory
        directory["requested"] = directory_search(named, specialty=constraints.specialty)
    scenarios = swarm_demo_scenarios(plan=patient.plan) if body.demo else make_scenarios(min(body.n, 40), seed=body.seed, plan=patient.plan)
    bus = EventBus()
    STATE.update(bus=bus, constraints=constraints, result=None, mode="live")
    bus.publish("patient_request", utterance=body.utterance, constraints=constraints.model_dump(), payer=patient.payer, plan=patient.plan)
    run_dir = _run_dir()

    async def job():
        try:
            STATE["result"] = await run_swarm(
                scenarios, patient, constraints, bus=bus, k=min(body.k, 20), shared_blackboard=True, directory=directory
            )
        except Exception as e:  # surface to the dashboard instead of dying silently
            bus.publish("swarm_error", error=f"{type(e).__name__}: {e}")
        finally:
            try:
                bus.dump(run_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-events.jsonl")
            except OSError:
                pass  # read-only or full disk must not break the run

    STATE["task"] = asyncio.create_task(job())
    return {"total": len(scenarios), "constraints": constraints.model_dump()}


def load_recording(path: Path) -> tuple[dict, list[dict]]:
    meta: dict = {}
    events: list[dict] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("type") == "recording_meta":
            meta = e
        else:
            events.append(e)
    return meta, events


@app.post("/api/replay")
async def replay(body: ReplayBody | None = None):
    """Public and free: re-streams a recorded run with its original pacing. Uses no model credits."""
    body = body or ReplayBody()
    if _busy():
        return JSONResponse({"error": "a run is already in progress"}, status_code=409)
    path = _replay_file()
    if not path.exists():
        return JSONResponse({"error": "no recording is available on this server"}, status_code=404)
    meta, events = load_recording(path)
    speed = max(0.25, min(body.speed, 1000.0))
    bus = EventBus()
    STATE.update(bus=bus, result=None, mode="replay")
    bus.publish("replay_started", source=meta.get("source"), models=meta.get("models"), recorded_at=meta.get("recorded_at"))

    async def job():
        prev = events[0]["ts"] if events else 0.0
        for e in events:
            gap = max(min(e["ts"] - prev, 2.0), 0.03) / speed  # keep natural pacing, but never a dead pause
            prev = e["ts"]
            await asyncio.sleep(gap)
            bus.publish(e["type"], **{k: v for k, v in e.items() if k not in ("seq", "ts", "type")})

    STATE["task"] = asyncio.create_task(job())
    return {"events": len(events), "source": meta.get("source")}


@app.post("/api/intake/transcribe", dependencies=[Depends(require_live)])
async def intake_transcribe(request: Request):
    """Patient speaks the request: body is a 16 kHz mono WAV recorded in the browser."""
    wav = await request.body()
    if not wav.startswith(b"RIFF") or wav[8:12] != b"WAVE":
        return JSONResponse({"error": "send audio/wav"}, status_code=415)
    if len(wav) > MAX_WAV_BYTES:
        return JSONResponse({"error": "recording is too long; keep it under a minute"}, status_code=413)
    try:
        text = await transcribe_wav(wav)
    except (TranscribeError, httpx.HTTPError) as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    return {"text": text[:500]}


@app.post("/api/approve", dependencies=[Depends(require_live)])
async def approve(body: ApproveBody):
    """The patient approves the held slot. The agent can hold; only the patient confirms."""
    res = STATE["result"]
    if not res or not res.best or (res.best.office_id, res.best.slot_start) != (body.office_id, body.slot_start):
        return JSONResponse({"error": "that offer is not the current best held offer"}, status_code=409)
    STATE["bus"].publish("patient_approved", office_id=body.office_id, slot_start=body.slot_start)
    return {"ok": True}


@app.get("/api/events")
async def events(request: Request):
    bus: EventBus = STATE["bus"]

    async def gen():
        q = bus.subscribe()  # subscribe first, then replay history, then dedupe by seq
        try:
            history = list(bus.history)
            last = -1
            yield "retry: 3000\n\n"
            for ev in history:
                last = ev["seq"]
                yield f"data: {json.dumps(ev)}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield ": keepalive\n\n"
                    continue
                if ev["seq"] <= last:
                    continue
                last = ev["seq"]
                yield f"data: {json.dumps(ev)}\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
