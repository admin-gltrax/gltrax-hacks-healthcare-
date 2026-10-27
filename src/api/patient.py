"""Patient-facing API: the dashboard's backend.

Sign-in is DEMO ONLY: a name (email optional) creates a record and a random
session cookie. No passwords, because no real health data may ever enter this
build. The real version needs real authentication: see README "Sign-in".

All routes are under /api/p. Every route works offline (MOCK_LLM=1 or not):
the agents run deterministically over the simulated insurers, directory and
records office.
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..agents import care_team, coverage, guide, records
from ..patient.buckets import PANELS, bucket_meta
from ..patient.demo import DEMO_NAME, build_demo
from ..patient.models import AgentTask, Bucket, HealthRecord, TaskStatus
from ..patient.store import export_json, store
from ..sim.payers import DEMO_CARDS

router = APIRouter(prefix="/api/p")
COOKIE = "pj_session"


class StartBody(BaseModel):
    name: str
    email: str | None = None


class CoverageBody(BaseModel):
    card: str  # member ID or text read off the card
    employer: str | None = None


class PcpBody(BaseModel):
    sim_id: str


class SignBody(BaseModel):
    typed_name: str


class AskBody(BaseModel):
    text: str


def _me(session: str | None) -> HealthRecord:
    rec = store().get(session)
    if rec is None:
        raise HTTPException(401, "Start by telling PJ your name.")
    return rec


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7)


def dashboard(rec: HealthRecord) -> dict:
    return {
        "patient": rec.patient.model_dump(mode="json"),
        "pj": guide.next_step(rec),
        "buckets": [
            {**meta, "items": [i.model_dump(mode="json") for i in rec.bucket(Bucket(meta["key"]))]}
            for meta in bucket_meta()
        ],
        "panels": PANELS,
        "coverage": rec.coverage.model_dump(mode="json") if rec.coverage else None,
        "care_team": [m.model_dump(mode="json") for m in rec.care_team],
        "records_requests": [r.model_dump(mode="json") for r in rec.records_requests],
        "tasks": [t.model_dump(mode="json") for t in rec.tasks],
        "care_requests": [c.model_dump(mode="json") for c in rec.care_requests[:3]],
        "demo_cards": list(DEMO_CARDS),
    }


@router.post("/start")
def start(body: StartBody, response: Response):
    try:
        token, rec = store().create(body.name, body.email)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _set_cookie(response, token)
    return dashboard(rec)


@router.post("/demo")
async def demo(response: Response):
    token, rec = store().create(DEMO_NAME)
    await build_demo(rec)
    store().put(token, rec)
    _set_cookie(response, token)
    return dashboard(rec)


@router.post("/signout")
def signout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
def me(pj_session: str | None = Cookie(default=None)):
    return dashboard(_me(pj_session))


@router.get("/me/export", response_class=PlainTextResponse)
def export(pj_session: str | None = Cookie(default=None)):
    """Everything, as JSON. It's the patient's data; they can take it anywhere."""
    return export_json(_me(pj_session))


@router.post("/coverage")
async def set_coverage(body: CoverageBody, pj_session: str | None = Cookie(default=None)):
    rec = _me(pj_session)
    try:
        await coverage.understand_coverage(rec, body.card, body.employer)
    except coverage.CoverageNotFound:
        raise HTTPException(404, "PJ couldn't find that plan. Check the member ID on your card.")
    store().put(pj_session, rec)
    return dashboard(rec)


@router.get("/providers")
def providers(q: str, pj_session: str | None = Cookie(default=None)):
    _me(pj_session)
    return care_team.search(q)


@router.post("/pcp")
async def set_pcp(body: PcpBody, pj_session: str | None = Cookie(default=None)):
    rec = _me(pj_session)
    try:
        member = care_team.add_from_directory(rec, body.sim_id)
    except KeyError:
        raise HTTPException(404, "Unknown provider")
    result = await care_team.verify_contact(rec, member)
    store().put(pj_session, rec)
    return {**dashboard(rec), "corrections": result["corrections"]}


@router.post("/records")
def draft_records(pj_session: str | None = Cookie(default=None)):
    rec = _me(pj_session)
    try:
        req = records.draft(rec)
    except ValueError as e:
        raise HTTPException(400, str(e))
    store().put(pj_session, rec)
    return {**dashboard(rec), "request_id": req.id}


@router.post("/records/{req_id}/sign")
def sign_records(req_id: str, body: SignBody, pj_session: str | None = Cookie(default=None)):
    rec = _me(pj_session)
    try:
        records.sign(rec, req_id, body.typed_name)
        records.send(rec, req_id)
    except records.NotSigned as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, "Unknown request")
    store().put(pj_session, rec)
    return dashboard(rec)


@router.post("/records/{req_id}/simulate-response")
def simulate_response(req_id: str, pj_session: str | None = Cookie(default=None)):
    """Demo control: the doctor's office answers (normally days or weeks later)."""
    rec = _me(pj_session)
    try:
        records.receive(rec, req_id)
    except KeyError:
        raise HTTPException(404, "Unknown request")
    store().put(pj_session, rec)
    return dashboard(rec)


@router.post("/ask")
def ask(body: AskBody, pj_session: str | None = Cookie(default=None)):
    rec = _me(pj_session)
    answer = guide.ask(rec, body.text[:500])
    store().put(pj_session, rec)
    return {**dashboard(rec), "answer": answer}


@router.post("/care/{care_id}/go")
def go(care_id: str, kind: str, pj_session: str | None = Cookie(default=None)):
    """The patient picks a pathway. The hand-off point to the crew; today it
    records the choice as a task. TODO: run the swarm for in_network, request
    a referral for pcp_first, book an EAP intake for eap."""
    rec = _me(pj_session)
    req = next((c for c in rec.care_requests if c.id == care_id), None)
    path = next((p for p in (req.pathways if req else []) if p.kind == kind), None)
    if not path:
        raise HTTPException(404, "Unknown option")
    rec.tasks.insert(0, AgentTask(title=path.title, agent="swarm" if kind == "in_network" else "navigator",
                                  status=TaskStatus.working,
                                  detail="PJ is on it: " + ("; ".join(path.agent_can_do) or "following up")))
    store().put(pj_session, rec)
    return dashboard(rec)

