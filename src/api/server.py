"""FastAPI app: starts swarms, streams events over SSE, serves the dashboard.

    uvicorn src.api.server:app --reload
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from ..intake import parse_request
from ..schemas import Constraints
from ..sim.scenarios import DEMO_PATIENT, make_scenarios, swarm_demo_scenarios
from ..swarm.dispatcher import run_swarm
from ..swarm.events import EventBus

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Swarm Scheduler")

STATE: dict = {"bus": EventBus(), "task": None, "result": None, "constraints": Constraints()}


class StartBody(BaseModel):
    demo: bool = True  # the fixed 15-office swarm
    n: int = 15
    seed: int = 1
    k: int = 15
    utterance: str | None = None  # patient's request; parsed into constraints if given


class ApproveBody(BaseModel):
    office_id: str
    slot_start: str


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    t = STATE["task"]
    return {"running": bool(t and not t.done()), "events": len(STATE["bus"].history)}


@app.post("/api/swarm/start")
async def start(body: StartBody | None = None):
    body = body or StartBody()
    t = STATE["task"]
    if t and not t.done():
        return JSONResponse({"error": "a swarm is already running"}, status_code=409)
    constraints = Constraints()
    if body.utterance:
        constraints = await parse_request(body.utterance)
    scenarios = swarm_demo_scenarios() if body.demo else make_scenarios(body.n, seed=body.seed)
    bus = EventBus()
    STATE.update(bus=bus, constraints=constraints, result=None)
    bus.publish("patient_request", utterance=body.utterance, constraints=constraints.model_dump())

    async def job():
        try:
            STATE["result"] = await run_swarm(
                scenarios, DEMO_PATIENT, constraints, bus=bus, k=body.k, shared_blackboard=True
            )
        except Exception as e:  # surface to the dashboard instead of dying silently
            bus.publish("swarm_error", error=f"{type(e).__name__}: {e}")
        finally:
            bus.dump(f"data/runs/{time.strftime('%Y%m%d-%H%M%S')}-events.jsonl")

    STATE["task"] = asyncio.create_task(job())
    return {"total": len(scenarios), "constraints": constraints.model_dump()}


@app.post("/api/approve")
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
        q = bus.subscribe()  # subscribe first, then replay, then dedupe by seq
        try:
            replay = list(bus.history)
            last = -1
            for ev in replay:
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
