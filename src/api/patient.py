"""Patient-facing API: the dashboard's backend.

Sign-in is DEMO ONLY: a name (email optional) creates a record and a random
session cookie. No passwords, because no real health data may ever enter this
build. The real version needs real authentication: see README "Sign-in".

One account can hold a care circle (an older parent, a child, a spouse). Every
route works on the person currently being viewed, and checks what the account
holder may do for them: view, act (have PJ do the work) or approve (sign and
say yes). See src/agents/circle.py.

All routes are under /api/p. With the Meta Model API on, PJ's crew runs on
Muse Spark and Muse Wonder (src/agents/ai.py meters every request); with it off,
over budget or failing, every route still works on the deterministic rules
over the simulated insurers, directory, records office and counterparties.
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ..agents import actions, ai, care_team, circle, coverage, guide, outreach, records, workflows
from ..patient.buckets import PANELS, bucket_meta
from ..patient.demo import DEMO_NAME, build_demo
from ..patient.models import AgentTask, Bucket, CareRecipient, HealthRecord, TaskStatus
from ..patient.store import export_json, store
from ..sim import documents
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


class PersonBody(BaseModel):
    name: str
    relation: str = "parent"
    dob: str | None = None


class ConsentBody(BaseModel):
    typed_name: str
    permissions: list[str] = ["view", "act"]


class RepresentativeBody(BaseModel):
    typed_name: str
    document: str = "healthcare power of attorney"


class ActiveBody(BaseModel):
    person_id: str | None = None


class AboutBody(BaseModel):
    factors: list[str] = []
    dob: str | None = None
    employer: str | None = None


class WorkflowBody(BaseModel):
    template: str
    inputs: dict = {}


class Ctx:
    """The signed-in account, the person being viewed, and how the two relate."""

    def __init__(self, token: str, account: HealthRecord):
        self.token, self.account = token, account
        self.rec, self.cr = circle.resolve(account)

    def need(self, perm: str) -> "Ctx":
        try:
            circle.require(self.cr, perm)
        except circle.NotAllowed as e:
            raise HTTPException(403, str(e))
        return self

    def save(self) -> None:
        store().put(self.token, self.account)

    @property
    def account_id(self) -> str:
        return self.account.patient.id


def _ctx(session: str | None) -> Ctx:
    acc = store().get(session)
    if acc is None:
        raise HTTPException(401, "Start by telling PJ your name.")
    return Ctx(session, acc)


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7)


def _viewing(account: HealthRecord, rec: HealthRecord, cr: CareRecipient | None) -> dict:
    return {"id": cr.id if cr else None, "name": rec.patient.display_name, "relation": cr.relation if cr else "you",
            "authority": cr.authority if cr else "self", "permissions": cr.permissions if cr else list(circle.ALL),
            "consent_note": cr.consent_note if cr else "Your own care.",
            "signer": circle.signer(account, cr)[0] if circle.can(cr, "approve") else None}


def ai_status(account: HealthRecord) -> dict:
    roles = {"caller": "Calls offices", "reader": "Reads letters and bills", "strategist": "Maps evidence to the plan's rules",
             "writer": "Writes letters", "pj": "PJ's chat"}
    on = ai.enabled()
    return {"enabled": on, "budget": ai.BUDGET.status(account.patient.id),
            "models": [{"role": r, "does": d, "model": ai.engine_label(r) if on else "rules"} for r, d in roles.items()]}


def dashboard(account: HealthRecord) -> dict:
    with workflows.LOCK:  # background agents write to the same records
        return _dashboard(account)


def _dashboard(account: HealthRecord) -> dict:
    rec, cr = circle.resolve(account)
    base = {
        "account": {"name": account.patient.display_name},
        "viewing": _viewing(account, rec, cr),
        "circle": circle.summary(account),
        "actions": actions.menu(account, rec, cr),
        "workflow_catalog": workflows.catalog(),
        "about_catalog": [{"key": k, "label": v} for k, v in outreach.TOLD.items()],
        "panels": PANELS,
        "demo_cards": list(DEMO_CARDS),
        "samples": documents.catalog(),
        "ai": ai_status(account),
    }
    if not circle.can(cr, "view"):  # nothing but the name until they say yes
        first = rec.patient.display_name.split()[0]
        return {**base, "limited": True, "patient": {"display_name": rec.patient.display_name, "onboarding_step": "done"},
                "pj": {"step": "done", "say": f"{first} hasn't said yes yet. Hand them your phone so they can choose what you see."},
                "buckets": [], "coverage": None, "care_team": [], "records_requests": [], "tasks": [], "care_requests": [],
                "support_plan": [], "about": [], "workflows": []}
    return {
        **base,
        "limited": False,
        "patient": rec.patient.model_dump(mode="json"),
        "pj": guide.next_step(rec),
        "buckets": [
            {**meta, "items": [i.model_dump(mode="json") for i in rec.bucket(Bucket(meta["key"]))]}
            for meta in bucket_meta()
        ],
        "coverage": rec.coverage.model_dump(mode="json") if rec.coverage else None,
        "care_team": [m.model_dump(mode="json") for m in rec.care_team],
        "records_requests": [r.model_dump(mode="json") for r in rec.records_requests],
        "tasks": [t.model_dump(mode="json") for t in rec.tasks],
        "care_requests": [c.model_dump(mode="json") for c in rec.care_requests[:3]],
        "support_plan": [a.model_dump(mode="json") for a in outreach.support_plan(rec)],
        "about": [f.model_dump(mode="json") for f in outreach.all_factors(rec)],
        "workflows": [w.model_dump(mode="json") for w in rec.workflows],
        "busy": workflows.busy(rec),
    }


# ---------------------------------------------------------------- account

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


@router.delete("/me")
def delete_me(response: Response, pj_session: str | None = Cookie(default=None)):
    """Delete my data: the whole account, everyone in the care circle, every workflow. No undo."""
    if not pj_session or not store().delete(pj_session):
        raise HTTPException(401, "Nothing to delete.")
    response.delete_cookie(COOKIE)
    return {"deleted": True}


@router.get("/me")
def me(pj_session: str | None = Cookie(default=None)):
    return dashboard(_ctx(pj_session).account)


@router.get("/me/export", response_class=PlainTextResponse)
def export(pj_session: str | None = Cookie(default=None)):
    """Everything about the person being viewed, as JSON. It's theirs; they can take it anywhere."""
    c = _ctx(pj_session).need("view")
    return export_json(c.rec)


# ---------------------------------------------------------------- care circle

@router.post("/circle")
def add_person(body: PersonBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session)
    if body.relation not in ("parent", "child", "spouse", "other"):
        raise HTTPException(400, "relation must be parent, child, spouse or other")
    try:
        cr = circle.add(c.account, body.name, body.relation, body.dob or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    c.account.active_id = cr.id
    c.save()
    return dashboard(c.account)


@router.post("/circle/{person_id}/consent")
def consent(person_id: str, body: ConsentBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session)
    try:
        circle.consent(c.account, person_id, body.typed_name, body.permissions)
    except KeyError:
        raise HTTPException(404, "Unknown person")
    except (circle.NotAllowed, ValueError) as e:
        raise HTTPException(400, str(e))
    c.save()
    return dashboard(c.account)


@router.post("/circle/{person_id}/representative")
def representative(person_id: str, body: RepresentativeBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session)
    try:
        circle.attest_representative(c.account, person_id, body.typed_name, body.document)
    except KeyError:
        raise HTTPException(404, "Unknown person")
    except circle.NotAllowed as e:
        raise HTTPException(400, str(e))
    c.save()
    return dashboard(c.account)


@router.delete("/circle/{person_id}")
def remove_person(person_id: str, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session)
    try:
        circle.revoke(c.account, person_id)
    except KeyError:
        raise HTTPException(404, "Unknown person")
    c.save()
    return dashboard(c.account)


@router.post("/active")
def set_active(body: ActiveBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session)
    if body.person_id and not any(p.id == body.person_id for p in c.account.circle):
        raise HTTPException(404, "Unknown person")
    c.account.active_id = body.person_id
    c.save()
    return dashboard(c.account)


# ---------------------------------------------------------------- about the person + support plan

@router.post("/about")
def about(body: AboutBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("act")
    if body.dob is not None:
        c.rec.patient.dob = body.dob or None
    if body.employer is not None:
        c.rec.patient.employer = body.employer or None
    outreach.set_told(c.rec, body.factors)
    c.save()
    return dashboard(c.account)


@router.post("/support/{key}/go")
def support_go(key: str, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("act")
    try:
        outreach.start(c.rec, key)
    except KeyError:
        raise HTTPException(404, "Unknown suggestion")
    c.save()
    return dashboard(c.account)


@router.post("/support/{key}/dismiss")
def support_dismiss(key: str, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("act")
    try:
        outreach.dismiss(c.rec, key)
    except KeyError:
        raise HTTPException(404, "Unknown suggestion")
    c.save()
    return dashboard(c.account)


# ---------------------------------------------------------------- agent workflows

@router.post("/workflows")
def start_workflow(body: WorkflowBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("act")
    try:
        wf = workflows.start(c.rec, body.template, body.inputs, account=c.account_id, save=c.save)
    except KeyError:
        raise HTTPException(404, "Unknown workflow")
    except workflows.WorkflowError as e:
        raise HTTPException(400, str(e))
    c.save()
    return {**dashboard(c.account), "workflow_id": wf.id}


@router.post("/workflows/{wf_id}/approve")
def approve_workflow(wf_id: str, body: SignBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("approve")
    who, capacity = circle.signer(c.account, c.cr)
    try:
        workflows.approve(c.rec, wf_id, body.typed_name, who, capacity, save=c.save)
    except KeyError:
        raise HTTPException(404, "Unknown workflow")
    except workflows.WorkflowError as e:
        raise HTTPException(400, str(e))
    c.save()
    return dashboard(c.account)


@router.post("/workflows/{wf_id}/simulate-response")
def workflow_response(wf_id: str, outcome: str = "approved", pj_session: str | None = Cookie(default=None)):
    """Demo control: the billing office, plan or agency answers (normally days or weeks later)."""
    c = _ctx(pj_session).need("act")
    try:
        workflows.respond(c.rec, wf_id, "denied" if outcome == "denied" else "approved")
    except KeyError:
        raise HTTPException(404, "Unknown workflow")
    except workflows.WorkflowError as e:
        raise HTTPException(400, str(e))
    c.save()
    return dashboard(c.account)


# ---------------------------------------------------------------- onboarding agents

@router.post("/coverage")
async def set_coverage(body: CoverageBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("act")
    try:
        await coverage.understand_coverage(c.rec, body.card, body.employer)
    except coverage.CoverageNotFound:
        raise HTTPException(404, "PJ couldn't find that plan. Check the member ID on the card.")
    c.save()
    return dashboard(c.account)


@router.get("/providers")
def providers(q: str, pj_session: str | None = Cookie(default=None)):
    _ctx(pj_session)
    return care_team.search(q)


@router.post("/pcp")
async def set_pcp(body: PcpBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("act")
    try:
        member = care_team.add_from_directory(c.rec, body.sim_id)
    except KeyError:
        raise HTTPException(404, "Unknown provider")
    result = await care_team.verify_contact(c.rec, member)
    c.save()
    return {**dashboard(c.account), "corrections": result["corrections"]}


@router.post("/records")
def draft_records(pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("act")
    try:
        req = records.draft(c.rec)
    except ValueError as e:
        raise HTTPException(400, str(e))
    c.save()
    return {**dashboard(c.account), "request_id": req.id}


@router.post("/records/{req_id}/sign")
def sign_records(req_id: str, body: SignBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("approve")
    who, capacity = circle.signer(c.account, c.cr)
    try:
        records.sign(c.rec, req_id, body.typed_name, signer=who if c.cr else None, capacity=capacity)
        records.send(c.rec, req_id)
    except records.NotSigned as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, "Unknown request")
    c.save()
    return dashboard(c.account)


@router.post("/records/{req_id}/simulate-response")
def simulate_response(req_id: str, pj_session: str | None = Cookie(default=None)):
    """Demo control: the doctor's office answers (normally days or weeks later)."""
    c = _ctx(pj_session).need("act")
    try:
        records.receive(c.rec, req_id)
    except KeyError:
        raise HTTPException(404, "Unknown request")
    c.save()
    return dashboard(c.account)


@router.post("/ask")
async def ask(body: AskBody, pj_session: str | None = Cookie(default=None)):
    c = _ctx(pj_session).need("view")
    answer = await guide.ask_live(c.rec, body.text[:500], account=c.account_id, viewer=c.account.patient.display_name)
    c.save()
    return {**dashboard(c.account), "answer": answer}


@router.post("/care/{care_id}/go")
def go(care_id: str, kind: str, pj_session: str | None = Cookie(default=None)):
    """The person picks a pathway. The hand-off point to the crew; today it
    records the choice as a task. TODO: run the swarm for in_network, request
    a referral for pcp_first, book an EAP intake for eap."""
    c = _ctx(pj_session).need("act")
    req = next((r for r in c.rec.care_requests if r.id == care_id), None)
    path = next((p for p in (req.pathways if req else []) if p.kind == kind), None)
    if not path:
        raise HTTPException(404, "Unknown option")
    c.rec.tasks.insert(0, AgentTask(title=path.title, agent="swarm" if kind == "in_network" else "navigator",
                                    status=TaskStatus.working,
                                    detail="PJ is on it: " + ("; ".join(path.agent_can_do) or "following up")))
    c.save()
    return dashboard(c.account)
