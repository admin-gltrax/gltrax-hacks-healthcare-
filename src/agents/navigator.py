"""Care Navigator: the patient says "I think I need to see a therapist". That's
the whole ask. The navigator does the rest.

It works out, for THIS patient:
  1. Is this urgent? Crisis language always routes to 988 / 911 first.
  2. What kind of care is it? (therapy, dermatology, physical therapy...)
  3. Every realistic route to it, given their coverage and life:
     employer EAP, in-network providers (checked, not just listed),
     PCP-first when the plan needs a referral, telehealth, Medicare- or
     Medicaid-specific routes, community resources (211, community health
     centers, sliding scale), and self-pay.
  4. A ranked recommendation with the reason, the cost, and exactly what PJ's
     crew will do next if the patient says go (call offices with the swarm,
     request a referral, book the EAP intake).

PJ never diagnoses and never decides whether someone needs care: the patient
asked, so PJ helps them get it, and points to their PCP or nurse line for
"should I?" questions.

Hackathon build: rules over the simulated plan, employer and directory.
TODO(meta): Muse Spark normalizes free text into a need (structured output) and
writes the "why" lines; Muse Wonder plans multi-step cases (e.g. referral, then
prior auth, then scheduling).
"""
from __future__ import annotations

import re

from ..patient.models import AgentTask, CareRequest, HealthRecord, Pathway, Program, TaskStatus
from ..sim.payers import eap_for
from ..sim.providers import PROVIDERS

CRISIS = re.compile(
    r"\b(kill myself|suicid\w*|end my life|want to die|hurt(?:ing)? myself|self[- ]harm|overdos\w*|"
    r"(?:no|don'?t see the|not any) point (?:of|in) (?:living|going on|life)|better off without me|don'?t want to (?:live|be here)|"
    r"can'?t breathe|chest pain|heart attack|stroke|unconscious|bleeding a lot)\b",
    re.I,
)

# free text -> (need key, plain label, benefit service, provider specialty). Order matters:
# "physical therapy" must match before plain "therapy".
NEEDS = [
    (r"physical therap|\bpt\b|knee|back pain|shoulder|sprain", "physical_therapy", "physical therapy", "physical_therapy", "physical therapy"),
    (r"therap|counsel|psycholog|anxiety|depress|stress|grief|mental", "therapy", "a therapist", "therapy_outpatient", "therapy"),
    (r"psychiatr|medication for (my )?(anxiety|depression|adhd)", "psychiatry", "a psychiatrist", "psychiatry", "psychiatry"),
    (r"derm|skin|rash|mole|acne", "dermatology", "a dermatologist", "dermatology", "dermatology"),
    (r"checkup|physical|primary care|family doctor|pcp", "primary_care", "a primary care visit", "primary_care", "family medicine"),
]


def classify(text: str) -> tuple[str, str, str, str]:
    for pattern, key, label, service, specialty in NEEDS:
        if re.search(pattern, text, re.I):
            return key, label, service, specialty
    return "specialist", "a specialist", "specialist", "specialist"


def _crisis_pathway() -> Pathway:
    return Pathway(
        kind="crisis", rank=0, title="Get help right now",
        why="What you said sounds urgent. You don't have to wait for an appointment.",
        cost="Free",
        steps=["If you might hurt yourself or someone else, call or text 988 (Suicide & Crisis Lifeline) now.",
               "If it's a medical emergency, call 911 or go to the nearest emergency room."],
        agent_can_do=[],
    )


def navigate(record: HealthRecord, need_text: str) -> CareRequest:
    text = need_text.strip()
    req = CareRequest(need_text=text, need="unknown")
    if CRISIS.search(text):
        req.urgent = True
        req.need = "crisis"
        req.pathways = [_crisis_pathway()]
        req.recommended = "crisis"
        record.care_requests.insert(0, req)
        return req

    need, label, service, specialty = classify(text)
    req.need = need
    cov = record.coverage
    benefit = cov.benefit(service) if cov else None
    prefix = cov.member_id[:3].upper() if cov and cov.member_id else None
    paths: list[Pathway] = []

    # 1. Employer EAP: free, fast, and almost nobody knows they have one.
    eap = eap_for(record.patient.employer)
    if need == "therapy" and eap:
        paths.append(Pathway(
            kind="eap", rank=1, title="Free counseling through your job (EAP)",
            why=f"Your employer's Employee Assistance Program covers {eap['sessions']}. No insurance and no deductible, and EAPs are confidential.",
            cost="$0", steps=[eap["how"], f"EAP line: {eap['phone']}"],
            agent_can_do=["Call the EAP line with you and set up the first session"],
        ))

    # 2. In-network providers, checked against what the office REALLY takes.
    if cov and benefit and benefit.covered in ("yes", "partly"):
        real = [p for p in PROVIDERS if p.specialty == specialty and prefix in p.true_networks and p.accepting_new]
        listed_only = [p for p in PROVIDERS if p.specialty == specialty and prefix in p.directory_networks
                       and (prefix not in p.true_networks or not p.accepting_new)]
        names = ", ".join(p.practice for p in real[:3]) or "none found yet"
        steps = [f"Covered: {benefit.label}, you pay {benefit.you_pay or 'see plan'}."]
        if benefit.needs_referral:
            steps.append("Your plan needs a referral from your primary care doctor first.")
        if benefit.needs_prior_auth:
            steps.append("Your plan needs approval first (prior authorization); the office usually files it.")
        if listed_only:
            steps.append(f"Skip {', '.join(p.practice for p in listed_only)}: the directory lists them, but they aren't actually taking your plan or new patients.")
        paths.append(Pathway(
            kind="in_network", rank=2 if benefit.needs_referral else (2 if eap else 1),
            title=f"See {label} covered by {cov.plan_name}",
            why=f"Uses your insurance. Offices that really take your plan right now: {names}.",
            cost=benefit.you_pay, steps=steps,
            agent_can_do=["Call these offices at the same time to find the soonest opening (PJ's swarm)",
                          "Hold the best time for you to approve"],
        ))
        if benefit.needs_referral and record.pcp():
            paths.append(Pathway(
                kind="pcp_first", rank=1, title=f"Ask {record.pcp().name} for a referral",
                why="Your plan won't pay for this specialist without a referral from your primary care doctor.",
                cost=(cov.benefit("primary_care").you_pay if cov.benefit("primary_care") else None),
                steps=["PJ asks your doctor's office for the referral.", "Once it's in, PJ finds the soonest in-network opening."],
                agent_can_do=["Request the referral from your PCP's office", "Then run the scheduling swarm"],
            ))

    # 3. Telehealth through the plan.
    tele = cov.benefit("telehealth") if cov else None
    if tele and tele.covered == "yes" and need in ("therapy", "psychiatry", "dermatology", "primary_care"):
        paths.append(Pathway(
            kind="telehealth", rank=3, title="A video visit through your plan",
            why="Often the fastest way in, from home.", cost=tele.you_pay,
            steps=[f"Your plan's virtual visits cost {tele.you_pay}."],
            agent_can_do=["Find the plan's telehealth option and the soonest slot"],
        ))

    # 4. Program-specific routes.
    if cov and cov.program in (Program.medicare, Program.medicare_advantage, Program.dual):
        paths.append(Pathway(
            kind="medicare", rank=4, title="Medicare's covered options",
            why="Medicare covers outpatient mental health care, including therapy, and a yearly depression screening at your Annual Wellness Visit.",
            steps=["Ask at your Annual Wellness Visit, or call your plan's member line: " + (cov.member_phone or "on your card")],
            agent_can_do=["Check which nearby providers take Medicare"],
        ))
    if cov and cov.program in (Program.medicaid, Program.dual):
        paths.append(Pathway(
            kind="medicaid", rank=2, title="Medicaid routes, including free rides",
            why="Medicaid covers this with no cost to you, and can book a free ride to the appointment.",
            cost="$0", steps=["Community mental health centers take Medicaid and often see people faster.",
                               "Rides: book at least 2 days ahead through the plan."],
            agent_can_do=["Book a ride to the appointment", "Call community mental health centers for the soonest intake"],
        ))

    # 5. Community and low-cost options: always shown, never the only answer for someone with coverage.
    sliding = [p.practice for p in PROVIDERS if p.specialty == specialty and p.sliding_scale]
    paths.append(Pathway(
        kind="community", rank=6 if cov else 2, title="Community and low-cost options",
        why="Good to know about, and the main route if you're between plans.",
        steps=["Dial 211 for local programs near you."] + ([f"Sliding-scale options: {', '.join(sliding)}."] if sliding else []),
        agent_can_do=["Look up local programs for your ZIP code"],
    ))
    if not cov or cov.program == Program.none:
        paths.append(Pathway(
            kind="self_pay", rank=3, title="Paying yourself, at a fair price",
            why="Without insurance, cash prices vary a lot. PJ can ask offices for their self-pay rate.",
            agent_can_do=["Call offices and compare self-pay prices"],
        ))

    paths.sort(key=lambda p: p.rank)
    req.pathways = paths
    req.recommended = paths[0].kind if paths else None
    record.care_requests.insert(0, req)
    record.tasks.insert(0, AgentTask(
        title=f"Find you {label}", agent="navigator", status=TaskStatus.waiting_on_you,
        detail=f"{len(paths)} ways in. Best fit: {paths[0].title}." if paths else None,
        needs_you="Pick an option and PJ will start.",
    ))
    return req
