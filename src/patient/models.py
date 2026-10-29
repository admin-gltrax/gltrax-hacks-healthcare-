"""The patient's own health record, in the shapes the dashboard and agents share.

Everything here is owned by the patient and shown to the patient first. Fields
carry a `source` and, where it matters, a `confidence`, so the dashboard can say
where a fact came from ("from your insurer", "you told PJ", "from Dr. Lee's
records") and whether an agent has checked it.

All data in this repo is fictional. See README "Privacy and safety".
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Where a fact came from. Shown to the patient next to the fact.
Source = Literal[
    "you",  # the patient told us
    "insurance_card",  # read from a photo of the card
    "insurer",  # insurer portal / Patient Access API / eligibility check
    "directory",  # provider directory (NPPES, payer directory); often wrong
    "call",  # an agent confirmed it on a call
    "records",  # came back in a medical-records response
    "demo",  # fictional seed data
]
Confidence = Literal["confirmed", "likely", "unverified"]


# ---------------------------------------------------------------- the person

class Patient(BaseModel):
    """Demo sign-in is name only (no password): see README "Sign-in"."""

    id: str = Field(default_factory=lambda: _id("pt"))
    display_name: str
    email: str | None = None
    dob: str | None = None  # YYYY-MM-DD, only once the patient gives it
    zip_code: str | None = None
    employer: str | None = None  # used to look for an Employee Assistance Program
    created_at: str = Field(default_factory=_now)
    onboarding_step: Literal["welcome", "coverage", "pcp", "records", "done"] = "welcome"


# ---------------------------------------------------------------- coverage

class Program(str, Enum):
    """Which world the coverage lives in. Changes every navigation answer."""

    employer = "employer"
    marketplace = "marketplace"
    medicare = "medicare"  # Original Medicare
    medicare_advantage = "medicare_advantage"
    medicaid = "medicaid"
    dual = "dual"  # Medicare + Medicaid
    none = "none"
    unknown = "unknown"


class BenefitLine(BaseModel):
    """One plain-language answer to "is this covered and what will it cost me?"."""

    service: str  # e.g. "therapy_outpatient", "primary_care", "specialist", "labs"
    label: str  # plain words: "Therapy (talk therapy, in network)"
    covered: Literal["yes", "no", "partly", "unknown"] = "unknown"
    you_pay: str | None = None  # "$30 per visit", "20% after deductible"
    needs_referral: bool | None = None
    needs_prior_auth: bool | None = None
    visit_limit: str | None = None  # "20 visits a year"
    notes: str | None = None
    source: Source = "insurer"
    confidence: Confidence = "likely"


class Coverage(BaseModel):
    payer: str
    plan_name: str
    program: Program = Program.unknown
    plan_type: str | None = None  # HMO, PPO, EPO, PFFS...
    member_id: str | None = None
    group_number: str | None = None
    deductible: str | None = None
    deductible_met: str | None = None
    out_of_pocket_max: str | None = None
    out_of_pocket_met: str | None = None
    pcp_required: bool | None = None  # HMOs usually require a PCP and referrals
    eap_available: bool | None = None  # Employee Assistance Program through employer
    eap_sessions: str | None = None
    member_phone: str | None = None
    behavioral_health_phone: str | None = None
    nurse_line: str | None = None
    benefits: list[BenefitLine] = Field(default_factory=list)
    plain_summary: str | None = None  # PJ's two-sentence explanation
    source: Source = "insurer"
    checked_at: str = Field(default_factory=_now)

    def benefit(self, service: str) -> BenefitLine | None:
        return next((b for b in self.benefits if b.service == service), None)


# ---------------------------------------------------------------- care team

class CareTeamMember(BaseModel):
    id: str = Field(default_factory=lambda: _id("ct"))
    role: Literal["pcp", "specialist", "therapist", "pharmacy", "dentist", "other"]
    name: str
    practice: str | None = None
    specialty: str | None = None
    npi: str | None = None  # fictional here
    phone: str | None = None
    fax: str | None = None  # where records requests go
    address: str | None = None
    in_network: Literal["yes", "no", "unknown"] = "unknown"
    source: Source = "directory"
    confidence: Confidence = "unverified"


# ---------------------------------------------------------------- records requests

class RecordsRequestStatus(str, Enum):
    draft = "draft"  # PJ wrote it
    awaiting_signature = "awaiting_signature"  # patient must sign (it is THEIR right)
    sent = "sent"  # faxed
    acknowledged = "acknowledged"  # office confirmed receipt
    received = "received"  # records arrived and were filed into buckets
    overdue = "overdue"  # past the legal response window; PJ follows up
    failed = "failed"  # fax failed / wrong number


class RecordsRequest(BaseModel):
    """A patient's own request for their records (HIPAA right of access).

    The patient is the requester; the agent only prepares and sends it after the
    patient signs. Never send without a signature."""

    id: str = Field(default_factory=lambda: _id("rr"))
    to: CareTeamMember
    what: list[str] = Field(default_factory=lambda: [
        "visit notes", "problem list", "medications", "allergies", "lab results",
        "imaging reports", "immunizations", "family history",
    ])
    date_range: str = "last 3 years"
    delivery: Literal["fax_back", "secure_email", "portal", "mail"] = "secure_email"
    letter: str | None = None
    status: RecordsRequestStatus = RecordsRequestStatus.draft
    signed_at: str | None = None
    sent_at: str | None = None
    due_by: str | None = None  # sent_at + response window
    fax_id: str | None = None
    history: list[dict] = Field(default_factory=list)  # {at, status, note}

    def mark(self, status: RecordsRequestStatus, note: str = "") -> None:
        self.status = status
        self.history.append({"at": _now(), "status": status.value, "note": note})

    def set_due(self, days: int) -> None:
        sent = datetime.fromisoformat(self.sent_at) if self.sent_at else datetime.now(timezone.utc)
        self.due_by = (sent.date() + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------- health items (the buckets)

class Bucket(str, Enum):
    connection = "connection"  # social needs and connection, in plain words
    clinicals = "clinicals"  # labs, conditions, medicines, visits
    routines = "routines"  # food, movement, sleep, stress
    family_genes = "family_genes"  # family history and genetics to watch


class Flag(str, Enum):
    ok = "ok"
    watch = "watch"  # worth a look at the next visit
    act = "act"  # PJ suggests a next step (never a diagnosis)


class HealthItem(BaseModel):
    id: str = Field(default_factory=lambda: _id("hi"))
    bucket: Bucket
    kind: str  # "lab", "condition", "medication", "allergy", "visit", "need", "habit", "family_history", "genetic_result"...
    title: str  # plain words: "A1c (3-month blood sugar)"
    value: str | None = None  # "5.9%"
    when: str | None = None  # YYYY-MM-DD
    plain_meaning: str | None = None  # PJ's one-line, non-diagnostic explanation
    flag: Flag = Flag.ok
    source: Source = "you"
    confidence: Confidence = "likely"


# ---------------------------------------------------------------- what PJ is doing for you

class TaskStatus(str, Enum):
    todo = "todo"
    working = "working"
    waiting_on_you = "waiting_on_you"
    waiting_on_them = "waiting_on_them"
    done = "done"
    blocked = "blocked"


class AgentTask(BaseModel):
    """One line in "What PJ is doing for you". The heart of the pitch: the
    confusing back-and-forth is visible, owned by an agent, and finishes."""

    id: str = Field(default_factory=lambda: _id("task"))
    title: str  # "Ask Dr. Lee's office for your records"
    agent: Literal["coverage", "care_team", "records", "navigator", "swarm", "guide", "outreach", "workflow"]
    status: TaskStatus = TaskStatus.todo
    detail: str | None = None
    needs_you: str | None = None  # the one thing the patient must do, if any
    updated_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------- care navigation

PathwayKind = Literal[
    "crisis",  # emergency: 911 / 988, always first when triggered
    "eap",  # employer Employee Assistance Program
    "in_network",  # covered provider through insurance
    "pcp_first",  # start with the PCP (referral or HMO rules)
    "telehealth",  # covered virtual option
    "medicare",  # Medicare-specific route
    "medicaid",  # Medicaid-specific route
    "community",  # 211, community clinics, sliding-scale, support groups
    "self_pay",  # cash price / sliding scale
]


class Pathway(BaseModel):
    kind: PathwayKind
    title: str
    why: str  # why this option fits THIS patient
    cost: str | None = None
    steps: list[str] = Field(default_factory=list)
    agent_can_do: list[str] = Field(default_factory=list)  # what PJ's crew will do if asked
    rank: int = 99


class CareRequest(BaseModel):
    """"I think I need to see a therapist" -> a ranked set of real options."""

    id: str = Field(default_factory=lambda: _id("care"))
    need_text: str
    need: str  # normalized: "therapy", "dermatology", "physical_therapy"...
    urgent: bool = False
    pathways: list[Pathway] = Field(default_factory=list)
    recommended: str | None = None  # pathway kind
    created_at: str = Field(default_factory=_now)


# ---------------------------------------------------------------- risk factors and the support plan

class RiskFactor(BaseModel):
    """Something about a person's life that changes what support they should get.

    Never a diagnosis: either something the person (or their caregiver) told PJ,
    or something read straight off their record (age, coverage)."""

    key: str  # catalog key in src/agents/outreach.py, e.g. "lives_alone"
    label: str  # plain words: "Lives alone"
    source: Source = "you"
    confidence: Confidence = "likely"


SupportKind = Literal["benefit", "preventive", "check_in", "resource", "coverage", "safety"]
SupportStatus = Literal["suggested", "started", "done", "dismissed"]


class SupportAction(BaseModel):
    """One proactive step PJ suggests from a person's risk factors and coverage.

    The person (or someone they authorized) decides; PJ never starts outreach
    on its own. Every suggestion says why, from which source, and what it costs."""

    key: str  # stable per person: catalog key, so dismissing sticks across refreshes
    kind: SupportKind
    title: str
    why: str  # cites the risk factor and/or the plan benefit
    cost: str | None = None
    agent_can_do: list[str] = Field(default_factory=list)
    because: list[str] = Field(default_factory=list)  # risk factor keys
    source: Source = "insurer"
    confidence: Confidence = "likely"
    status: SupportStatus = "suggested"
    priority: int = 50  # lower first


# ---------------------------------------------------------------- agent workflows (bills, appeals, requests)

StepKind = Literal["agent", "approve", "send", "wait", "outcome"]
StepStatus = Literal["pending", "working", "done", "needs_you", "skipped", "failed"]


class WorkflowStep(BaseModel):
    key: str
    title: str
    agent: str  # which crew member does it: "Billing agent", "Policy agent", "You"...
    kind: StepKind = "agent"
    status: StepStatus = "pending"
    detail: str | None = None
    due: str | None = None  # YYYY-MM-DD, for waits and filing windows
    engine: str | None = None  # the model that did the step ("muse-spark-1.3"), or "rules"


WorkflowStatus = Literal["working", "needs_you", "waiting_on_them", "won", "partly_won", "lost", "closed"]


class Workflow(BaseModel):
    """A multi-step job PJ's crew runs end to end: contest a bill, appeal a
    denial, request rides or equipment. Agents do every step they can; the
    person approves before anything is sent; PJ tracks the clock and escalates."""

    id: str = Field(default_factory=lambda: _id("wf"))
    template: str  # key in src/agents/workflows.py TEMPLATES
    title: str
    inputs: dict = Field(default_factory=dict)
    steps: list[WorkflowStep] = Field(default_factory=list)
    status: WorkflowStatus = "working"
    letter: str | None = None  # what will be sent, shown in full before approval
    findings: list[str] = Field(default_factory=list)  # what the agents found, in plain words
    calls: list[dict] = Field(default_factory=list)  # phone calls the caller agent made (src/agents/office_calls.py)
    documents: list[dict] = Field(default_factory=list)  # what the reader agent read: kind, model, fields (never the image)
    criteria: list[dict] = Field(default_factory=list)  # the plan's criteria mapped to evidence (strategist agent)
    checks: list[dict] = Field(default_factory=list)  # guardrail results on what the models produced
    outcome: str | None = None
    saved: str | None = None  # money or hours recovered, when there is a number
    deadline: str | None = None  # the filing or decision window PJ is watching
    deadline_note: str | None = None  # where the deadline comes from and how sure PJ is
    signed_by: str | None = None
    history: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)

    def log(self, note: str) -> None:
        self.history.append({"at": _now(), "note": note})

    def step(self, key: str) -> WorkflowStep:
        return next(s for s in self.steps if s.key == key)


# ---------------------------------------------------------------- the care circle

Relation = Literal["parent", "child", "spouse", "other"]
# How the account holder is allowed to act for this person. Consent is the
# product: nothing about another adult is done without their say-so.
Authority = Literal[
    "parent_of_minor",  # a parent or guardian of someone under 18 (HIPAA personal representative)
    "consented_helper",  # an adult invited the account holder and chose what they may do
    "legal_representative",  # healthcare power of attorney or guardian, attested by the account holder
    "pending_consent",  # invited but the person hasn't said yes yet: nothing but their name is visible
]
Permission = Literal["view", "act", "approve"]


class CareRecipient(BaseModel):
    """Someone the account holder helps: an older parent, a child, a spouse."""

    id: str = Field(default_factory=lambda: _id("cr"))
    relation: Relation
    authority: Authority
    permissions: list[Permission] = Field(default_factory=list)
    consent_note: str  # plain words, shown on screen: how this access was granted
    consented_at: str | None = None
    record: "HealthRecord"


# ---------------------------------------------------------------- the whole record

class HealthRecord(BaseModel):
    patient: Patient
    coverage: Coverage | None = None
    care_team: list[CareTeamMember] = Field(default_factory=list)
    items: list[HealthItem] = Field(default_factory=list)
    records_requests: list[RecordsRequest] = Field(default_factory=list)
    tasks: list[AgentTask] = Field(default_factory=list)
    care_requests: list[CareRequest] = Field(default_factory=list)
    workflows: list[Workflow] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)  # told to PJ; derived ones are computed
    support_status: dict[str, SupportStatus] = Field(default_factory=dict)  # support action key -> status
    circle: list[CareRecipient] = Field(default_factory=list)  # people this account helps (account holder's record only)
    active_id: str | None = None  # which circle member the dashboard shows; None = the account holder

    def pcp(self) -> CareTeamMember | None:
        return next((m for m in self.care_team if m.role == "pcp"), None)

    def bucket(self, b: Bucket) -> list[HealthItem]:
        return [i for i in self.items if i.bucket == b]

    def task(self, task_id: str) -> AgentTask | None:
        return next((t for t in self.tasks if t.id == task_id), None)


CareRecipient.model_rebuild()


def age_on(dob: str | None, on: date | None = None) -> int | None:
    if not dob:
        return None
    try:
        b = date.fromisoformat(dob)
    except ValueError:
        return None
    on = on or date.today()
    return on.year - b.year - ((on.month, on.day) < (b.month, b.day))


def today() -> str:
    return date.today().isoformat()
