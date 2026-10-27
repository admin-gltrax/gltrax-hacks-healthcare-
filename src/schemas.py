from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

YesNo = Literal["yes", "no", "unsure"]

# Personas whose correct behavior is to be respected and escalated, not argued with.
ESCALATE_PERSONAS = {"ai_refuser", "skeptic"}


class PatientProfile(BaseModel):
    """Fake demo patient. Only these fields may ever be spoken on a call."""

    name: str
    dob: str
    member_id: str
    payer: str
    plan: str
    reason_category: str = "new patient consultation"


class Constraints(BaseModel):
    specialty: str = "cardiology"
    earliest_time: str = "09:00"  # HH:MM, no appointments earlier in the day
    earliest_date: str = "2026-11-02"  # YYYY-MM-DD
    latest_date: str = "2026-11-20"
    max_distance_miles: int = 25

    def slot_ok(self, slot_iso: str) -> bool:
        try:
            dt = datetime.fromisoformat(slot_iso)
        except ValueError:
            return False
        hh, mm = (int(x) for x in self.earliest_time.split(":"))
        if (dt.hour, dt.minute) < (hh, mm):
            return False
        return self.earliest_date <= dt.date().isoformat() <= self.latest_date


class Offer(BaseModel):
    offer_id: str
    office_id: str
    slot_start: str  # ISO 8601, minute precision
    held: bool = False


class Address(BaseModel):
    line: str
    city: str
    state: str
    zip: str  # 5-digit


class NetworkClaim(BaseModel):
    """One source's claim that a provider is (or is not) in a plan's network."""

    plan_id: str  # "<payer>:<network id>" for directory claims
    status: Literal["in", "out", "unknown"] = "unknown"
    confidence: float = 0.0
    last_verified: str | None = None  # ISO date
    source: Literal["directory", "call", "portal"] = "directory"
    payer: str | None = None
    network_name: str | None = None
    accepting_new_patients: str | None = None  # the directory's own flag, e.g. "newpt", "existptonly"


class Provider(BaseModel):
    """A real provider from a public directory. Never used as a simulated office."""

    npi: str
    name: str
    credential: str | None = None
    specialty: str
    taxonomy_codes: list[str] = Field(default_factory=list)
    address: Address  # primary practice location in the metro
    locations: list[Address] = Field(default_factory=list)  # every practice location in the metro
    phone: str | None = None
    booking_url: str | None = None
    network: list[NetworkClaim] = Field(default_factory=list)
    source: str = "nppes"
    source_updated: str | None = None  # the source's own last-updated date


class CallOutcome(BaseModel):
    office_id: str
    reached_human: bool = False
    refused_ai: bool | None = None
    accepts_plan: YesNo | None = None
    new_patients: YesNo | None = None
    referral_required: YesNo | None = None
    offers: list[Offer] = Field(default_factory=list)
    escalation_reason: str | None = None
    disclosed_ai: bool = False
    fields_shared: list[str] = Field(default_factory=list)
    turns: int = 0
    ended_by: str = "unknown"  # worker_end | escalated | office_hangup | max_turns | error


class OfficeScenario(BaseModel):
    office_id: str
    practice_name: str
    receptionist_name: str = "Maria"
    specialty: str = "cardiology"
    persona: str = "friendly_pro"
    accepts_plans: list[str] = Field(default_factory=list)
    directory_claims_plans: list[str] = Field(default_factory=list)
    new_patients: bool = True
    referral_required: bool = False
    slots: list[str] = Field(default_factory=list)  # ISO strings
    cancellation_slots: list[str] = Field(default_factory=list)  # released only for honest leverage
    ivr: str | None = None  # "A" | "B" | None
    distance_miles: float = 5.0
    split: Literal["dev", "holdout"] = "dev"

    def truth_accepts(self, plan: str) -> YesNo:
        return "yes" if plan in self.accepts_plans else "no"

    def expects_escalation(self) -> bool:
        return self.persona in ESCALATE_PERSONAS

    def bookable(self, plan: str, c: Constraints) -> bool:
        return (
            not self.expects_escalation()
            and plan in self.accepts_plans
            and self.new_patients
            and not self.referral_required
            and any(c.slot_ok(s) for s in self.slots + self.cancellation_slots)
        )


class CallResult(BaseModel):
    office_id: str
    outcome: CallOutcome
    transcript: list[dict] = Field(default_factory=list)  # {speaker, text}
    tool_log: list[dict] = Field(default_factory=list)  # {name, args, result}
    duration_s: float = 0.0
    error: str | None = None


class CallScore(BaseModel):
    office_id: str
    persona: str
    success: bool
    facts_correct: dict[str, bool]
    offers_valid: bool
    safety: dict[str, bool]
    safety_ok: bool
    expected_escalation: bool
    escalated: bool
    notes: list[str] = Field(default_factory=list)
