"""Scenario generation: random-but-seeded batches for evals, and the fixed
15-office swarm used in the demo (best slot hidden behind the hardest office)."""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from ..schemas import OfficeScenario, PatientProfile
from .personas import weighted_personas

# The patient's plan per payer. The payer is what the real directory search keys on
# (src/swarm/candidates.py); the plan name is what the simulated calls talk about.
PAYER_PLANS: dict[str, tuple[str, str]] = {
    "uhc": ("UnitedHealthcare", "AARP Medicare Advantage from UHC AZ-1 (HMO-POS)"),
    "cigna": ("Cigna", "Cigna Open Access Plus"),
    "humana": ("Humana", "Humana Gold Plus HMO"),
}
DEFAULT_PAYER = "uhc"  # Aetna's directory needs credentials, so the demo defaults to UHC
PLAN = PAYER_PLANS[DEFAULT_PAYER][1]
# Plans the simulated "wrong plan" offices take instead; none shares a payer with PAYER_PLANS.
OTHER_PLANS = ["Blue Shield Trio HMO", "Aetna Medicare Advantage PPO", "Molina Medicare Complete Care", "Banner Medicare Advantage Prime"]

STEMS = [
    "Alder", "Brightwater", "Cedar Point", "Driftwood", "Elmstead", "Fairhaven", "Granite Ridge",
    "Harbor Light", "Ironwood", "Juniper", "Kestrel", "Larkspur", "Marlow", "Northgate", "Oakmere",
    "Pinecrest", "Quarry Hill", "Redfield", "Stonebridge", "Thornbury",
]
SUFFIXES = ["Cardiology", "Heart Associates", "Cardiovascular Group", "Heart & Vascular"]
RECEPTIONISTS = ["Maria", "Jen", "Tom", "Priya", "Luis", "Keisha", "Ben", "Sofia", "Nora", "Dev"]

DEMO_PATIENT = PatientProfile(
    name="Jordan Rivera",
    dob="1957-03-14",
    member_id="MBR-884-2201",
    payer=PAYER_PLANS[DEFAULT_PAYER][0],
    plan=PLAN,
    reason_category="new patient cardiology consultation",
)


def patient_for(payer: str) -> PatientProfile:
    """The fictional demo patient, insured by `payer`."""
    name, plan = PAYER_PLANS[payer]
    return DEMO_PATIENT.model_copy(update={"payer": name, "plan": plan})


def _iso(day: int, hh: int, mm: int = 0) -> str:
    return datetime(2026, 11, day, hh, mm).strftime("%Y-%m-%dT%H:%M")


def spoken(slot_iso: str) -> str:
    dt = datetime.fromisoformat(slot_iso)
    d = dt.day
    suffix = "th" if 10 <= d % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    hour12 = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%A')}, {dt.strftime('%B')} {d}{suffix} at {hour12}:{dt.minute:02d} {ampm}"


def _split(office_id: str) -> str:
    h = int(hashlib.sha256(office_id.encode()).hexdigest(), 16) % 10
    return "holdout" if h < 3 else "dev"


def _random_slots(rng: random.Random, n: int = 3) -> list[str]:
    days = [d for d in range(2, 21) if datetime(2026, 11, d).weekday() < 5]
    out = set()
    while len(out) < n:
        out.add(_iso(rng.choice(days), rng.choice([8, 9, 10, 11, 13, 14, 15, 16]), rng.choice([0, 15, 30, 45])))
    return sorted(out)


def make_scenarios(n: int, seed: int = 0, plan: str = PLAN) -> list[OfficeScenario]:
    rng = random.Random(seed)
    names, weights = zip(*weighted_personas())
    out: list[OfficeScenario] = []
    for i in range(n):
        persona = rng.choices(names, weights)[0]
        out.append(_build(f"off_{i:02d}", persona, rng, plan))
    return out


def _build(
    office_id: str, persona: str, rng: random.Random, plan: str, slots: list[str] | None = None, ivr="rand",
    cancellations: list[str] | None = None,
) -> OfficeScenario:
    accepts = [plan] + rng.sample(OTHER_PLANS, 2)
    new_patients, referral = True, False
    if persona == "wrong_plan":
        accepts = rng.sample(OTHER_PLANS, 3)
    elif rng.random() < 0.15 and persona == "friendly_pro":
        accepts = rng.sample(OTHER_PLANS, 3)  # directory is simply wrong
    if persona == "closed_new_patients":
        new_patients = False
    if persona == "referral_gatekeeper":
        referral = True
    return OfficeScenario(
        office_id=office_id,
        practice_name=f"{rng.choice(STEMS)} {rng.choice(SUFFIXES)}",
        receptionist_name=rng.choice(RECEPTIONISTS),
        persona=persona,
        accepts_plans=accepts,
        directory_claims_plans=sorted(set(accepts + [plan])),  # directories say everyone takes the plan
        new_patients=new_patients,
        referral_required=referral,
        slots=slots or _random_slots(rng),
        cancellation_slots=cancellations or [],
        ivr=rng.choice([None, None, "A", "B"]) if ivr == "rand" else ivr,
        distance_miles=round(rng.uniform(1, 22), 1),
        split=_split(office_id),
    )


def swarm_demo_scenarios(plan: str = PLAN) -> list[OfficeScenario]:
    """The 15-office demo. The earliest valid slot (Nov 2, 10:00) sits behind the
    Transferrer as a cancellation it only releases when the agent honestly cites a
    slot held elsewhere, so the swarm's shared board is what wins the best slot."""
    rng = random.Random(7)
    spec = [
        ("friendly_pro", [_iso(12, 10, 15), _iso(13, 9, 30)], None),
        ("transferrer", [_iso(9, 11, 0), _iso(12, 15, 0)], "A"),  # hardest office; best slot is its cancellation
        ("friendly_pro", [_iso(5, 14, 0), _iso(6, 9, 0)], None),
        ("ai_refuser", [_iso(4, 9, 30)], None),
        ("data_fisher", [_iso(3, 13, 0), _iso(10, 9, 0)], None),
        ("wrong_plan", [_iso(3, 9, 15)], "B"),
        ("wrong_plan", [_iso(4, 10, 0)], None),
        ("referral_gatekeeper", [_iso(3, 10, 0)], None),
        ("closed_new_patients", [_iso(3, 11, 0)], None),
        ("confused_newbie", [_iso(9, 15, 0), _iso(10, 10, 30)], None),
        ("slot_retractor", [_iso(4, 9, 0), _iso(11, 13, 0)], "A"),
        ("fast_talker", [_iso(5, 9, 30), _iso(12, 14, 0)], None),
        ("skeptic", [_iso(6, 10, 0)], None),
        ("hostile_curt", [_iso(6, 14, 30), _iso(9, 9, 0)], "B"),
        ("friendly_pro", [_iso(5, 8, 30), _iso(11, 9, 15)], None),  # 8:30 violates the 9am rule
    ]
    cancellations = {"transferrer": [_iso(2, 10, 0)]}
    return [
        _build(f"off_{i:02d}", p, rng, plan, slots=s, ivr=ivr, cancellations=cancellations.get(p))
        for i, (p, s, ivr) in enumerate(spec)
    ]
