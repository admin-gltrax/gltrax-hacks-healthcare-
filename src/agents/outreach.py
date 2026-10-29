"""Outreach agent: turns a person's risk factors and coverage into a support plan.

Healthcare leaves the work of finding benefits to the person least equipped to
do it. Most people never use the free Wellness Visit, the medication review,
the rides, the dental cleanings or the cost-help programs they already qualify
for. PJ looks at what it knows about one person (age, plan, what they or their
caregiver said) and proposes the specific, covered next steps, each with the
reason, the source and the cost. The person decides; PJ does the legwork.

Rules, not a model, so it is deterministic and testable:
  - Never a diagnosis and never medical advice. Suggestions are "use this
    benefit", "ask about this at the visit", "here's a program", never "you
    have" or "take/stop".
  - Every suggestion names the risk factor or plan benefit it comes from.
  - Nothing is started without a yes from someone allowed to say yes
    (src/agents/circle.py).

TODO(meta): Muse Spark rewrites `why` in the person's own words and language,
grounded in these rules' output; Wonder plans multi-step outreach (screener,
then application, then follow-up).
"""
from __future__ import annotations

from ..patient.models import (
    AgentTask, HealthRecord, Program, RiskFactor, SupportAction, TaskStatus, age_on,
)
from ..sim.payers import eap_for

# What a person (or their caregiver) can tell PJ. Plain words; never a diagnosis
# PJ makes, only what someone reports.
TOLD: dict[str, str] = {
    "lives_alone": "Lives alone",
    "recent_fall": "Fell in the past year",
    "heart_condition": "Has a heart condition",
    "diabetes": "Has diabetes",
    "many_medicines": "Takes 5 or more medicines",
    "memory_concerns": "Memory changes someone has noticed",
    "hard_to_afford": "Hard to afford medicines, food or bills",
    "no_ride": "No easy way to get to appointments",
    "caregiver_strain": "Caring for someone else and stretched thin",
}

MEDICARE = (Program.medicare, Program.medicare_advantage, Program.dual)


def derived(record: HealthRecord) -> list[RiskFactor]:
    """Facts read straight off the record, so nobody has to type them."""
    out: list[RiskFactor] = []
    age = age_on(record.patient.dob)
    if age is not None:
        if age >= 65:
            out.append(RiskFactor(key="age_65_plus", label=f"Age {age}", source="you", confidence="confirmed"))
        elif age < 18:
            out.append(RiskFactor(key="under_18", label=f"Age {age}", source="you", confidence="confirmed"))
            if age >= 13:
                out.append(RiskFactor(key="teen", label="Teenager", source="you", confidence="confirmed"))
    cov = record.coverage
    if cov and cov.program in MEDICARE:
        out.append(RiskFactor(key="on_medicare", label="Has Medicare", source="insurer", confidence="confirmed"))
    if cov and cov.program in (Program.medicaid, Program.dual):
        out.append(RiskFactor(key="on_medicaid", label="Has Medicaid", source="insurer", confidence="confirmed"))
    if eap_for(record.patient.employer):
        out.append(RiskFactor(key="has_eap", label="Free help through work (EAP)", source="insurer", confidence="likely"))
    return out


def all_factors(record: HealthRecord) -> list[RiskFactor]:
    return derived(record) + [f for f in record.risk_factors if f.key in TOLD]


def set_told(record: HealthRecord, keys: list[str]) -> list[RiskFactor]:
    """Replace what the person told PJ. Unknown keys are ignored."""
    record.risk_factors = [RiskFactor(key=k, label=TOLD[k], source="you") for k in dict.fromkeys(keys) if k in TOLD]
    return record.risk_factors


def _cost(record: HealthRecord, service: str, default: str | None = None) -> str | None:
    b = record.coverage.benefit(service) if record.coverage else None
    return (b.you_pay if b and b.covered in ("yes", "partly") else None) or default


def support_plan(record: HealthRecord) -> list[SupportAction]:
    """The ranked support plan for this person. Statuses persist by key."""
    f = {r.key for r in all_factors(record)}
    name = record.patient.display_name.split()[0]
    cov = record.coverage
    plan = cov.plan_name if cov else "your plan"
    pcp = record.pcp()
    acts: list[SupportAction] = []

    def add(**kw) -> None:
        acts.append(SupportAction(**kw))

    # --- Checkups the plan already pays for (the most-skipped free benefit) ---
    if {"age_65_plus", "on_medicare"} <= f:
        add(key="wellness_visit", kind="preventive", priority=10, because=["age_65_plus", "on_medicare"],
            title="Book the yearly Medicare Wellness Visit",
            why="Medicare covers a yearly Wellness Visit at no cost. It's where to review every medicine, "
                "check memory and fall risk, and plan screenings.",
            cost=_cost(record, "preventive", "$0"),
            agent_can_do=[f"Find a time with {pcp.name}" if pcp else "Find a primary care doctor first",
                          "Write down the questions to bring"])
    elif "under_18" in f:
        add(key="well_child", kind="preventive", priority=10, because=["under_18"],
            title=f"Well-child checkup and vaccines for {name}",
            why="Checkups and recommended vaccines for children are covered at no cost on most plans.",
            cost=_cost(record, "preventive", "$0 on most plans"),
            agent_can_do=[f"Find a time with {pcp.name}" if pcp else "Find a pediatrician who takes the plan",
                          "Check which vaccines are due on the immunization record"])
    elif cov and cov.benefit("preventive"):
        add(key="checkup", kind="preventive", priority=40, because=[],
            title="Use your free yearly checkup",
            why=f"{plan} covers a yearly checkup and preventive screenings.",
            cost=_cost(record, "preventive", "$0"),
            agent_can_do=["Find a time with your doctor"])

    if "teen" in f:
        add(key="teen_privacy", kind="resource", priority=80, because=["teen"], source="you", confidence="likely",
            title=f"Some of {name}'s visits can be private",
            why="Teens can talk with their doctor alone, and some services stay between them. "
                "PJ shows a parent what's shared and respects what isn't.")

    # --- Safety at home ---
    if "recent_fall" in f or {"age_65_plus", "lives_alone"} <= f:
        add(key="fall_check", kind="safety", priority=15, because=[k for k in ("recent_fall", "age_65_plus", "lives_alone") if k in f],
            title="Ask for a fall-risk check",
            why="A fall in the past year is the strongest sign of another one. The Wellness Visit includes a fall-risk "
                "check, and plans usually cover physical therapy for strength and balance.",
            cost=_cost(record, "physical_therapy"),
            agent_can_do=["Add it to the questions for the next visit", "Find a covered balance or strength program"])

    if "many_medicines" in f:
        add(key="med_review", kind="benefit", priority=20, because=["many_medicines"],
            title="A free review of every medicine",
            why="Medicare drug plans offer a free medication review (Medication Therapy Management) to people who take "
                "many medicines; any pharmacist can also do a brown-bag review. Never stop a medicine on your own.",
            cost="$0" if "on_medicare" in f else "Often free at the pharmacy",
            agent_can_do=["Ask the plan whether you qualify for a medication review", "Make one list of every medicine"])

    if "memory_concerns" in f and "age_65_plus" in f:
        add(key="memory_check", kind="preventive", priority=20, because=["memory_concerns", "age_65_plus"],
            title="Ask for a memory check at the Wellness Visit",
            why="Medicare's Wellness Visit includes a check for memory changes. Bring the person who noticed them.",
            cost=_cost(record, "preventive", "$0"),
            agent_can_do=["Add it to the questions for the next visit"])
        add(key="dementia_program", kind="benefit", priority=45, because=["memory_concerns"], confidence="unverified",
            title="If a doctor diagnoses dementia: Medicare's GUIDE program",
            why="GUIDE adds care coordination, a 24/7 support line and respite for family caregivers. "
                "Only some practices take part, so PJ checks what's near you.",
            agent_can_do=["Check for a GUIDE program near you"])

    # --- Staying on top of a condition (never managing it) ---
    if "heart_condition" in f or "diabetes" in f:
        which = "cardiologist" if "heart_condition" in f else "diabetes specialist"
        b = cov.benefit("specialist") if cov else None
        add(key="specialist_followup", kind="coverage", priority=25, because=[k for k in ("heart_condition", "diabetes") if k in f],
            title=f"Keep {which} visits on track",
            why=f"PJ finds a {which} who really takes {plan}, not just one the directory lists, and holds the soonest time."
                + (" Your plan needs a referral from your primary care doctor first." if b and b.needs_referral else ""),
            cost=_cost(record, "specialist"),
            agent_can_do=(["Ask your primary care doctor for the referral"] if b and b.needs_referral else [])
            + ["Call offices at the same time to find the soonest opening (PJ's swarm)"])

    # --- Not being alone with it ---
    if {"lives_alone", "age_65_plus"} <= f:
        add(key="check_in_calls", kind="check_in", priority=30, because=["lives_alone", "age_65_plus"], confidence="likely",
            title="A friendly daily check-in call",
            why="Many Area Agencies on Aging and senior centers run free daily check-in calls for people who live alone.",
            cost="Free in many areas",
            agent_can_do=["Find programs near you (Eldercare Locator, 211)"])

    if "no_ride" in f:
        ride = cov.benefit("transport") if cov else None
        if ride and ride.covered == "yes":
            add(key="rides", kind="benefit", priority=30, because=["no_ride"],
                title="Free rides to appointments", why=f"{plan} covers rides to medical appointments. {ride.notes or ''}".strip(),
                cost=ride.you_pay, agent_can_do=["Book the ride when PJ books the visit"])
        else:
            add(key="rides", kind="resource", priority=35, because=["no_ride"], confidence="unverified",
                title="Find a ride to appointments",
                why="The plan doesn't list a ride benefit, but local aging and community programs often offer rides.",
                cost="Often free", agent_can_do=["Look up ride programs near you (211)"])

    # --- Paying for it ---
    if "hard_to_afford" in f:
        if "on_medicare" in f and "on_medicaid" not in f:
            add(key="cost_help", kind="benefit", priority=12, because=["hard_to_afford", "on_medicare"], confidence="unverified",
                title="See if Medicare can cost less",
                why="Extra Help and the Medicare Savings Programs can lower or remove premiums and drug costs for people "
                    "with limited income, and many who qualify never apply.",
                cost="Free to apply",
                agent_can_do=["Run the official screener (BenefitsCheckUp) with you", "Fill in the application for you to sign"])
        elif "under_18" in f and "on_medicaid" not in f:
            add(key="cost_help", kind="benefit", priority=12, because=["hard_to_afford", "under_18"], confidence="unverified",
                title=f"Check free or low-cost coverage for {name} (Medicaid, CHIP)",
                why="Children often qualify for Medicaid or CHIP at higher incomes than adults do.",
                cost="Free to apply", agent_can_do=["Check eligibility with you", "Fill in the application for you to sign"])
        elif "on_medicaid" not in f:
            add(key="cost_help", kind="benefit", priority=12, because=["hard_to_afford"], confidence="unverified",
                title="Find help paying for care and the basics",
                why="Depending on income: Medicaid, lower Marketplace premiums, drug-maker assistance, community clinics, and food help.",
                cost="Free to apply", agent_can_do=["Run a benefits screener with you"])

    # --- The caregiver is a patient too ---
    if "caregiver_strain" in f:
        eap = eap_for(record.patient.employer)
        add(key="caregiver_support", kind="benefit" if eap else "resource", priority=30, because=["caregiver_strain"],
            confidence="likely" if eap else "unverified",
            title="Support for you, the caregiver",
            why=(f"Your job's EAP ({eap['sessions']}) also helps caregivers: counseling and help finding elder care."
                 if eap else "Area Agencies on Aging run caregiver programs, including respite so you get a break."),
            cost="$0" if eap else "Often free",
            agent_can_do=["Call the EAP line with you" if eap else "Find caregiver programs near you"])

    # --- Benefits people pay for and never use ---
    if cov:
        dental = cov.benefit("dental")
        if dental and dental.covered == "yes" and dental.you_pay == "$0":
            add(key="dental", kind="benefit", priority=45, because=[],
                title="Use the free dental cleanings", why=f"{plan} includes them ({dental.visit_limit or 'see plan'}).",
                cost="$0", agent_can_do=["Find a dentist who takes the plan"])
        tele = cov.benefit("telehealth")
        if tele and tele.you_pay == "$0":
            add(key="telehealth", kind="benefit", priority=70, because=[],
                title="Video visits from home", why=f"{plan} covers them. Good for quick questions and follow-ups from home.",
                cost="$0", agent_can_do=["Set up the plan's video visits"])
    if "has_eap" in f and "caregiver_strain" not in f and "under_18" not in f:
        eap = eap_for(record.patient.employer)
        add(key="eap", kind="benefit", priority=60, because=["has_eap"],
            title="Free counseling through work", why=f"Your employer's EAP covers {eap['sessions']}, confidential and $0.",
            cost="$0", agent_can_do=["Call the EAP line with you"])

    for a in acts:
        a.status = record.support_status.get(a.key, "suggested")
    return sorted(acts, key=lambda a: (a.status in ("done", "dismissed"), a.priority))


def start(record: HealthRecord, key: str) -> AgentTask:
    """The person (or someone allowed to) said yes. PJ takes the legwork."""
    act = next((a for a in support_plan(record) if a.key == key), None)
    if act is None:
        raise KeyError(key)
    record.support_status[key] = "started"
    task = AgentTask(title=act.title, agent="outreach", status=TaskStatus.working,
                     detail="PJ is on it: " + ("; ".join(act.agent_can_do) or "following up"))
    record.tasks.insert(0, task)
    return task


def dismiss(record: HealthRecord, key: str) -> None:
    if not any(a.key == key for a in support_plan(record)):
        raise KeyError(key)
    record.support_status[key] = "dismissed"
