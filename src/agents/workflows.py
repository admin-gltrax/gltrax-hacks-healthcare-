"""Agent workflows: the jobs that make healthcare exhausting, run by PJ's crew.

The scheduling swarm calls 15 offices at once to hold an appointment. These
workflows apply the same idea to everything else that usually falls on the
patient or the family caregiver:

  bill_dispute        contest a medical bill that looks wrong
  pa_appeal           appeal a prior-authorization denial (multi-agent)
  plan_resource       request rides, a home health aide, or medical supplies
  dme                 renew or appeal durable medical equipment
  caregiving_appeal   appeal a cut to state-funded home care hours (fair hearing)
  counselor_request   find a counselor who can really see you, or get a plan exception

Every workflow follows the same shape, and the same rules:
  1. Agents do every step they can on their own: call, read, match, draft.
  2. A consent gate: the person (or a parent of a minor, or a legal
     representative) reads exactly what will be sent and signs. Nothing leaves
     before that. A helper can start a workflow, never sign it.
  3. Send, confirm receipt, and watch the clock. Deadlines name their source and
     are marked unverified unless read from the person's own letter.
  4. If the answer is no, PJ prepares the next level instead of stopping.

Agents never invent clinical facts: evidence comes from the person's records,
what they told PJ, or the doctor's office. Counterparties are simulated
(src/sim/counterparties.py). TODO(meta): Muse Spark reads uploaded denial
letters and bills (vision), Muse Wonder plans the evidence and argument, Spark
drafts the letters; the rules here stay the guardrails.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from ..patient.models import AgentTask, HealthRecord, TaskStatus, Workflow, WorkflowStep, _now
from ..sim import counterparties as cp
from . import office_calls

# ---------------------------------------------------------------- templates


@dataclass
class Template:
    key: str
    title: str
    blurb: str
    icon: str
    group: str  # where it sits in the action menu
    fields: list[dict]
    steps: list[tuple[str, str, str, str]]  # (key, title, agent, kind)
    run: dict[str, Callable[[Workflow, HealthRecord], str]] = field(default_factory=dict)
    title_for: Callable[[dict], str] | None = None


def _plus(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _first(rec: HealthRecord) -> str:
    return rec.patient.display_name.split()[0]


def _plan(rec: HealthRecord) -> str:
    return rec.coverage.plan_name if rec.coverage else "the health plan"


def _payer(rec: HealthRecord) -> str:
    return (rec.coverage.payer if rec.coverage else "the health plan").replace(" (fictional)", "")


def _prefix(rec: HealthRecord) -> str:
    return (rec.coverage.member_id or "")[:3].upper() if rec.coverage and rec.coverage.member_id else ""


def _who(rec: HealthRecord) -> str:
    p = rec.patient
    bits = [p.display_name] + ([f"date of birth {p.dob}"] if p.dob else [])
    if rec.coverage and rec.coverage.member_id:
        bits.append(f"member ID {rec.coverage.member_id}")
    return ", ".join(bits)


def _doctor(rec: HealthRecord) -> str:
    pcp = rec.pcp()
    return f"{pcp.name} ({pcp.practice})" if pcp and pcp.practice else (pcp.name if pcp else "the treating doctor")


SIGNATURE = "Signature: ______________________   Date: __________"


def _call(wf: Workflow, rec: HealthRecord, purpose: str, details: str) -> str:
    """The caller agent phones the doctor's office; the call log goes on the workflow."""
    try:
        c = office_calls.call_office(rec, purpose, details)
    except office_calls.NoDoctor as e:
        wf.findings.append(str(e))
        return str(e)
    wf.calls.append(c)
    return office_calls.summary(c)


# --- bill dispute -------------------------------------------------------------

def _bill_itemize(wf: Workflow, rec: HealthRecord) -> str:
    case = cp.BILL_CASES.get(wf.inputs.get("issue") or "not_sure", cp.BILL_CASES["not_sure"])
    wf.findings.append("Itemized bill: " + "; ".join(case["lines"]))
    return f"Called {wf.inputs.get('biller') or 'the billing office'} and got an itemized bill with billing codes."


def _bill_eob(wf: Workflow, rec: HealthRecord) -> str:
    case = cp.BILL_CASES.get(wf.inputs.get("issue") or "not_sure", cp.BILL_CASES["not_sure"])
    wf.findings.append(case["finding"])
    return f"Compared every line with {_payer(rec)}'s explanation of benefits. Billed ${case['billed']}; the plan says you owe ${case['owed']}."


def _bill_draft(wf: Workflow, rec: HealthRecord) -> str:
    case = cp.BILL_CASES.get(wf.inputs.get("issue") or "not_sure", cp.BILL_CASES["not_sure"])
    wf.letter = (
        f"To: Billing Office, {wf.inputs.get('biller') or 'Billing Office'}\n\n"
        f"Re: Disputed bill for {_who(rec)}, date of service {wf.inputs.get('service_date') or 'see enclosed'}\n\n"
        f"I'm disputing this bill. {case['finding']} The plan's explanation of benefits shows my share is "
        f"${case['owed']}, but the bill asks for ${case['billed']}.\n\n"
        "Please correct the bill, send me an updated itemized statement, and hold the account from collections "
        "while you review it. Please reply in writing.\n\n"
        f"Prepared with my assistant, PJ, at my direction.\n\n{SIGNATURE}\n"
    )
    return "Dispute letter drafted with the matching EOB lines attached."


def _bill_send(wf: Workflow, rec: HealthRecord) -> str:
    return "Sent to the billing office, then called to confirm they got it and to put the account on hold during review."


# --- prior authorization appeal (multi-agent) -------------------------------------

REASONS = {
    "not_medically_necessary": "the plan says it isn't medically necessary",
    "missing_info": "the plan says information was missing",
    "out_of_network": "the provider is out of network",
    "experimental": "the plan calls it experimental",
    "not_sure": "the reason isn't clear yet",
}


def _filing_window(rec: HealthRecord, urgent: bool) -> tuple[int, str]:
    prog = rec.coverage.program.value if rec.coverage else "unknown"
    days = {"medicare_advantage": 65, "dual": 65, "medicaid": 60}.get(prog, 180)
    note = (f"Typical window to file for this kind of plan: {days} days from the denial. Decisions: about 72 hours if "
            "urgent, about 30 days if not. Your denial letter states the exact dates, and PJ goes by the letter.")
    return days, note


def _pa_denial(wf: Workflow, rec: HealthRecord) -> str:
    urgent = bool(wf.inputs.get("urgent"))
    days, note = _filing_window(rec, urgent)
    denied = wf.inputs.get("denied_on") or date.today().isoformat()
    try:
        wf.deadline = (date.fromisoformat(denied) + timedelta(days=days)).isoformat()
    except ValueError:
        wf.deadline = _plus(days)
    wf.deadline_note = note
    reason = REASONS.get(wf.inputs.get("reason") or "not_sure", REASONS["not_sure"])
    wf.findings.append(f"Denied because {reason}. File by {wf.deadline}.")
    return f"Read the denial: {reason}. The filing deadline is {wf.deadline}" + (" (asking for a fast, urgent review)." if urgent else ".")


def _pa_evidence(wf: Workflow, rec: HealthRecord) -> str:
    items = [i for i in rec.items if i.bucket.value == "clinicals"]
    told = [r.label for r in rec.risk_factors]
    wf.findings.append(f"Evidence on file: {len(items)} items from the records" + (f"; told to PJ: {', '.join(told)}" if told else "") + ".")
    return f"Pulled {len(items)} relevant items from the records (visits, results, medicines). Nothing is added that isn't on file."


def _pa_doctor(wf: Workflow, rec: HealthRecord) -> str:
    out = _call(wf, rec, "letter", f"a letter of medical necessity for {wf.inputs.get('service') or 'the denied service'}, for an appeal")
    if wf.calls:
        wf.findings.append(f"{_doctor(rec)} sent a letter of medical necessity (reference {wf.calls[-1]['reference']}).")
    return out


def _pa_criteria(wf: Workflow, rec: HealthRecord) -> str:
    return (f"Matched the records and the doctor's letter to {_payer(rec)}'s coverage rules for "
            f"{wf.inputs.get('service') or 'this service'}, point by point.")


def _pa_draft(wf: Workflow, rec: HealthRecord) -> str:
    svc = wf.inputs.get("service") or "the requested service"
    reason = REASONS.get(wf.inputs.get("reason") or "not_sure", REASONS["not_sure"])
    fast = "\nThis is an urgent request: waiting could seriously harm my health. Please decide within 72 hours.\n" if wf.inputs.get("urgent") else ""
    wf.letter = (
        f"To: Appeals Unit, {_payer(rec)}\nFax: {cp.APPEALS_FAX.get(_prefix(rec), 'on the denial letter')}\n\n"
        f"Re: Appeal of prior authorization denial for {svc}. Member: {_who(rec)}, plan {_plan(rec)}\n\n"
        f"I'm appealing the denial of {svc}, which was denied because {reason}.{fast}\n"
        f"My doctor, {_doctor(rec)}, has written the enclosed letter of medical necessity. The enclosed records show "
        "the history behind the request. Each of the plan's coverage criteria is answered in the enclosed table.\n\n"
        "Please send me the plan's decision in writing, and a copy of the criteria used.\n\n"
        f"Prepared with my assistant, PJ, at my direction.\n\n{SIGNATURE}\n"
    )
    return "Appeal letter drafted, with the doctor's letter, records and a criteria table attached."


def _pa_send(wf: Workflow, rec: HealthRecord) -> str:
    return (f"Faxed to {_payer(rec)} appeals at {cp.APPEALS_FAX.get(_prefix(rec), 'the number on the letter')}, "
            "then called to confirm it arrived complete.")


def _external_draft(wf: Workflow, rec: HealthRecord) -> str:
    wf.letter = (
        f"To: Independent Review\n\nRe: Request for independent external review. Member: {_who(rec)}, plan {_plan(rec)}\n\n"
        f"{_payer(rec)} upheld its denial of {wf.inputs.get('service') or 'the service'}. I'm asking for an independent "
        "review by reviewers outside the plan. The appeal, the doctor's letter and the records are enclosed.\n\n"
        f"Prepared with my assistant, PJ, at my direction.\n\n{SIGNATURE}\n"
    )
    return "Drafted the request for an independent outside review, with the full appeal file attached."


# --- plan resources: rides, aide, supplies -----------------------------------------

RESOURCES = {"rides": ("Rides to medical appointments", "transport", False),
             "home_aide": ("A home health aide", "home_health", True),
             "supplies": ("Medical supplies", "supplies", True)}


def _res_benefit(wf: Workflow, rec: HealthRecord) -> str:
    label, service, _ = RESOURCES.get(wf.inputs.get("resource") or "rides", RESOURCES["rides"])
    b = rec.coverage.benefit(service) if rec.coverage else None
    if b and b.covered in ("yes", "partly"):
        wf.findings.append(f"{_plan(rec)} covers it: {b.label}, you pay {b.you_pay or 'see plan'}. {b.notes or ''}".strip())
        return f"{_plan(rec)} covers {label.lower()}."
    wf.findings.append(f"{_plan(rec)} doesn't list {label.lower()}; PJ asks the plan directly and lines up community options too.")
    return f"The plan's benefit list doesn't show {label.lower()}, so PJ will ask the plan directly."


def _res_order(wf: Workflow, rec: HealthRecord) -> str:
    label = RESOURCES.get(wf.inputs.get("resource") or "rides", RESOURCES["rides"])[0].lower()
    return _call(wf, rec, "order", f"the doctor's order the plan requires for {label}")


def _res_draft(wf: Workflow, rec: HealthRecord) -> str:
    label, _, _ = RESOURCES.get(wf.inputs.get("resource") or "rides", RESOURCES["rides"])
    extra = wf.inputs.get("details") or ""
    wf.letter = (f"To: Member Services, {_payer(rec)}\n\nRe: Request for {label.lower()}. Member: {_who(rec)}\n\n"
                 f"Please arrange {label.lower()} under my plan, {_plan(rec)}. {extra}\n\n"
                 f"Prepared with my assistant, PJ, at my direction.\n\n{SIGNATURE}\n")
    return "Request filled in."


# --- durable medical equipment -----------------------------------------------------

EQUIPMENT = {"oxygen": "Home oxygen", "cpap_supplies": "CPAP supplies", "wheelchair": "A wheelchair",
             "hospital_bed": "A hospital bed", "diabetic_supplies": "Diabetes testing supplies", "walker": "A walker"}


def _dme_check(wf: Workflow, rec: HealthRecord) -> str:
    eq = EQUIPMENT.get(wf.inputs.get("equipment") or "walker", "the equipment")
    wf.inputs["equipment_label"] = eq
    if wf.inputs.get("situation") == "denied":
        wf.deadline, wf.deadline_note = _plus(60), "Typical: about 60 days to appeal. The denial letter has the exact date."
        wf.findings.append(f"{eq} was denied. Appeal by about {wf.deadline}; PJ goes by the date on the letter.")
        return f"{eq} was denied. Appeal deadline about {wf.deadline} (from the letter)."
    wf.deadline, wf.deadline_note = _plus(21), "Approval runs out soon; plans often need 2 weeks to renew, so PJ starts early."
    b = rec.coverage.benefit("supplies") if rec.coverage else None
    wf.findings.append(f"{eq} needs renewing before about {wf.deadline}."
                       + (f" {_plan(rec)} covers it: you pay {b.you_pay}, with a doctor's order." if b else ""))
    return f"{eq} needs renewing; the current approval runs out around {wf.deadline}."


def _dme_order(wf: Workflow, rec: HealthRecord) -> str:
    eq = (wf.inputs.get("equipment_label") or "the equipment").lower()
    return _call(wf, rec, "order", f"an updated order and notes for {eq}")


def _dme_supplier(wf: Workflow, rec: HealthRecord) -> str:
    return f"Confirmed {cp.DME_SUPPLIER['name']} is in network and can deliver."


def _dme_draft(wf: Workflow, rec: HealthRecord) -> str:
    eq = wf.inputs.get("equipment_label") or "the equipment"
    kind = "appeal of the denial of" if wf.inputs.get("situation") == "denied" else "renewal of the approval for"
    wf.letter = (f"To: {_payer(rec)}\n\nRe: {kind.capitalize()} {eq.lower()}. Member: {_who(rec)}, plan {_plan(rec)}\n\n"
                 f"I'm requesting {kind} {eq.lower()}. My doctor's updated order and notes are enclosed, and "
                 f"{cp.DME_SUPPLIER['name']} (in network) is ready to deliver.\n\n"
                 f"Prepared with my assistant, PJ, at my direction.\n\n{SIGNATURE}\n")
    return "Request drafted with the order and notes attached."


# --- state-funded caregiving hours -------------------------------------------------

PROGRAMS = {"medicaid_home_care": "Medicaid home care (waiver) hours", "aaa_program": "Area Agency on Aging in-home help"}


def _care_notice(wf: Workflow, rec: HealthRecord) -> str:
    notice = wf.inputs.get("notice_on") or date.today().isoformat()
    try:
        n = date.fromisoformat(notice)
    except ValueError:
        n = date.today()
    wf.deadline = (n + timedelta(days=10)).isoformat()
    wf.deadline_note = ("To keep the current hours while the appeal is decided, ask before the cut takes effect, often "
                        "within about 10 days of the notice. The full hearing window is longer (often up to 90 days). "
                        "Rules vary by state; the notice states the dates.")
    b, a = wf.inputs.get("hours_before"), wf.inputs.get("hours_after")
    wf.findings.append(f"Notice cuts {PROGRAMS.get(wf.inputs.get('program'), 'home care hours').lower()} from {b} to {a} a week.")
    return f"Read the notice. To keep the hours during the appeal, file by {wf.deadline}."


def _care_log(wf: Workflow, rec: HealthRecord) -> str:
    told = [r.label for r in rec.risk_factors]
    wf.findings.append("Care needs on file: " + (", ".join(told) if told else "none yet; the family adds a one-week care log") + ".")
    return "Put together what's on file about daily care needs. The family confirms it before anything is sent."


def _care_doctor(wf: Workflow, rec: HealthRecord) -> str:
    return _call(wf, rec, "letter", "a statement of daily care needs for a fair hearing about home care hours")


def _care_draft(wf: Workflow, rec: HealthRecord) -> str:
    prog = PROGRAMS.get(wf.inputs.get("program") or "medicaid_home_care", "home care hours")
    wf.letter = (f"To: {cp.STATE_AGENCY['name']}\nFax: {cp.STATE_AGENCY['fax']}\n\n"
                 f"Re: Request for a fair hearing. {_who(rec)}\n\n"
                 f"I'm appealing the decision to cut {prog.lower()} from {wf.inputs.get('hours_before')} to "
                 f"{wf.inputs.get('hours_after')} hours a week, and I ask that the current hours continue until the "
                 "hearing decision. My doctor's statement of care needs and a care log are enclosed.\n\n"
                 f"Prepared with my assistant, PJ, at my direction.\n\n{SIGNATURE}\n")
    return "Hearing request drafted, asking to keep the current hours during the appeal."


# --- counselor request -------------------------------------------------------------

def _co_benefit(wf: Workflow, rec: HealthRecord) -> str:
    b = rec.coverage.benefit("therapy_outpatient") if rec.coverage else None
    from ..sim.payers import eap_for
    eap = eap_for(rec.patient.employer)
    bits = []
    if b:
        bits.append(f"{_plan(rec)} covers therapy: you pay {b.you_pay}")
    if eap:
        bits.append(f"work EAP: {eap['sessions']}")
    wf.findings.extend(bits or ["Coverage for counseling isn't on file yet."])
    return "; ".join(bits) + "." if bits else "Checked coverage."


def _co_calls(wf: Workflow, rec: HealthRecord) -> str:
    acc = [c for c in cp.COUNSELORS if c["accepting"]]
    soonest = min(c["first_opening_days"] for c in acc) if acc else None
    wf.findings.append(f"Called {len(cp.COUNSELORS)} in-network counselors at once: {len(acc)} taking new patients, "
                       f"soonest opening in {soonest} days." if acc else "No in-network counselor is taking new patients.")
    return f"Called {len(cp.COUNSELORS)} in-network counselors at the same time (the scheduling swarm)."


def _co_exception(wf: Workflow, rec: HealthRecord) -> str:
    c = cp.OUT_OF_NETWORK_COUNSELOR
    focus = f"counseling for {wf.inputs['focus']}" if wf.inputs.get("focus") else "counseling"
    wf.letter = (f"To: Behavioral Health, {_payer(rec)}\n\nRe: Request for a network exception (single case agreement). "
                 f"Member: {_who(rec)}\n\nI'm looking for {focus}. No in-network counselor can see me within a reasonable time "
                 f"(the soonest is over 6 weeks; call log enclosed). {c['name']} can see me in {c['first_opening_days']} days. "
                 "Please approve them at my in-network cost.\n\n"
                 f"Prepared with my assistant, PJ, at my direction.\n\n{SIGNATURE}\n")
    return "No one in network can see you soon, so PJ drafted a request for the plan to cover an outside counselor at your in-network cost."


# --- contact the doctor's office for anything ---------------------------------------

def _office_prepare(wf: Workflow, rec: HealthRecord) -> str:
    pcp = rec.pcp()
    shared = office_calls.shared_fields(rec)
    what = office_calls.PURPOSES.get(wf.inputs.get("purpose") or "referral", "the request")
    wf.findings.append("PJ will share only: " + ", ".join(office_calls.FIELD_LABELS[k] for k, v in shared.items() if v) + ".")
    if pcp is None:
        return "No regular doctor on file yet. Add one so PJ knows which office to call."
    return f"Ready to call {pcp.practice or pcp.name} about {what}" + (f": {wf.inputs['details']}" if wf.inputs.get("details") else "") + "."


def _office_call(wf: Workflow, rec: HealthRecord) -> str:
    out = _call(wf, rec, wf.inputs.get("purpose") or "referral", wf.inputs.get("details") or "")
    if wf.calls:
        c = wf.calls[-1]
        wf.findings.append(f"Spoke with {c['reached']}. Reference {c['reference']}. Expect it in about {c['days']} business day(s).")
    return out


TEMPLATES: dict[str, Template] = {
    "office_request": Template(
        "office_request", "Have PJ call the doctor's office", "Referral, refill, a letter or form, an order, a nurse question: PJ works the phone menu, waits on hold, and gets the right person.",
        "phone", "care",
        fields=[{"name": "purpose", "label": "What's needed", "kind": "select",
                 "options": [[k, v[0].upper() + v[1:]] for k, v in office_calls.PURPOSES.items()]},
                {"name": "details", "label": "Details (optional)", "kind": "text", "placeholder": "e.g. referral to a cardiologist; refill of lisinopril"}],
        steps=[("prepare", "Get the request ready", "Caller agent", "agent"),
               ("call", "Call: phone menu, hold, and the right person", "Caller agent", "send"),
               ("wait", "Wait for the office to finish it", "Tracker", "wait"),
               ("outcome", "Result", "PJ", "outcome")],
        run={"prepare": _office_prepare, "call": _office_call},
        title_for=lambda i: f"Call the doctor's office about {office_calls.PURPOSES.get(i.get('purpose') or 'referral', 'a request')}"),
    "bill_dispute": Template(
        "bill_dispute", "Contest a medical bill", "PJ gets the itemized bill, matches every line to the plan's EOB, and disputes what's wrong.",
        "receipt", "fight",
        fields=[{"name": "biller", "label": "Who sent the bill", "kind": "text", "placeholder": "e.g. Harbor Family Medicine"},
                {"name": "amount", "label": "Amount billed", "kind": "text", "placeholder": "$"},
                {"name": "service_date", "label": "Date of the visit", "kind": "date"},
                {"name": "issue", "label": "What looks wrong", "kind": "select", "options": [
                    ["not_sure", "Not sure, it just looks too high"], ["duplicate", "Charged twice"],
                    ["in_network_billed_as_out", "Billed as out of network"], ["preventive_billed", "A free checkup got billed"],
                    ["already_paid", "I already paid"]]}],
        steps=[("itemize", "Get the itemized bill", "Billing agent", "agent"),
               ("eob", "Match it against the plan's explanation of benefits", "Claims agent", "agent"),
               ("draft", "Write the dispute", "Writer agent", "agent"),
               ("approve", "Read it and sign", "You", "approve"),
               ("send", "Send it and put the account on hold", "Billing agent", "send"),
               ("wait", "Wait for the corrected bill", "Tracker", "wait"),
               ("outcome", "Result", "PJ", "outcome")],
        run={"itemize": _bill_itemize, "eob": _bill_eob, "draft": _bill_draft, "send": _bill_send},
        title_for=lambda i: f"Contest the bill from {i.get('biller') or 'the billing office'}"),
    "pa_appeal": Template(
        "pa_appeal", "Appeal a prior-authorization denial", "A crew of agents reads the denial, gathers records, gets the doctor's letter, and files the appeal on time.",
        "scale", "fight",
        fields=[{"name": "service", "label": "What was denied", "kind": "text", "placeholder": "e.g. MRI of the lower back"},
                {"name": "denied_on", "label": "Date on the denial letter", "kind": "date"},
                {"name": "reason", "label": "Reason given", "kind": "select", "options": [[k, v[0].upper() + v[1:]] for k, v in REASONS.items()]},
                {"name": "urgent", "label": "Waiting could seriously harm health (ask for a fast review)", "kind": "bool"}],
        steps=[("denial", "Read the denial and the deadline", "Policy agent", "agent"),
               ("evidence", "Pull supporting notes from the records", "Records agent", "agent"),
               ("doctor", "Get a letter of medical necessity from the doctor", "Caller agent", "agent"),
               ("criteria", "Match the evidence to the plan's rules", "Policy agent", "agent"),
               ("draft", "Write the appeal", "Writer agent", "agent"),
               ("approve", "Read it and sign", "You", "approve"),
               ("send", "Fax it to the plan and confirm it arrived", "Submitter agent", "send"),
               ("wait", "Wait for the decision", "Tracker", "wait"),
               ("outcome", "Result", "PJ", "outcome")],
        run={"denial": _pa_denial, "evidence": _pa_evidence, "doctor": _pa_doctor, "criteria": _pa_criteria,
             "draft": _pa_draft, "send": _pa_send},
        title_for=lambda i: f"Appeal the denial of {i.get('service') or 'a service'}"),
    "plan_resource": Template(
        "plan_resource", "Request rides, an aide, or supplies", "PJ checks the benefit, gets the doctor's order if needed, and puts in the request.",
        "truck", "owed",
        fields=[{"name": "resource", "label": "What's needed", "kind": "select",
                 "options": [["rides", "Rides to appointments"], ["home_aide", "A home health aide"], ["supplies", "Medical supplies"]]},
                {"name": "details", "label": "Details (optional)", "kind": "text", "placeholder": "e.g. appointment on the 14th at 10 AM"}],
        steps=[("benefit", "Check what the plan covers", "Coverage agent", "agent"),
               ("order", "Get the doctor's order", "Caller agent", "agent"),
               ("draft", "Fill in the request", "Writer agent", "agent"),
               ("approve", "Okay it", "You", "approve"),
               ("send", "Submit it to the plan", "Submitter agent", "send"),
               ("wait", "Wait for the plan", "Tracker", "wait"),
               ("outcome", "Result", "PJ", "outcome")],
        run={"benefit": _res_benefit, "order": _res_order, "draft": _res_draft,
             "send": lambda wf, rec: f"Submitted to {_payer(rec)} and confirmed by phone."},
        title_for=lambda i: f"Request {RESOURCES.get(i.get('resource') or 'rides', RESOURCES['rides'])[0].lower()}"),
    "dme": Template(
        "dme", "Renew or appeal medical equipment", "Oxygen, CPAP supplies, a wheelchair: PJ renews before it lapses, or appeals a denial.",
        "wheel", "owed",
        fields=[{"name": "equipment", "label": "Equipment", "kind": "select", "options": [[k, v] for k, v in EQUIPMENT.items()]},
                {"name": "situation", "label": "Situation", "kind": "select",
                 "options": [["renewal_due", "The approval is running out"], ["denied", "It was denied"]]}],
        steps=[("check", "Check what's due and the deadline", "Coverage agent", "agent"),
               ("order", "Get an updated order and notes from the doctor", "Caller agent", "agent"),
               ("supplier", "Confirm an in-network supplier", "Care team agent", "agent"),
               ("draft", "Write the request", "Writer agent", "agent"),
               ("approve", "Read it and sign", "You", "approve"),
               ("send", "Send it to the plan and confirm", "Submitter agent", "send"),
               ("wait", "Wait for the plan", "Tracker", "wait"),
               ("outcome", "Result", "PJ", "outcome")],
        run={"check": _dme_check, "order": _dme_order, "supplier": _dme_supplier, "draft": _dme_draft,
             "send": lambda wf, rec: f"Sent to {_payer(rec)} with the supplier's details, and confirmed by phone."},
        title_for=lambda i: ("Appeal" if i.get("situation") == "denied" else "Renew") + f" {EQUIPMENT.get(i.get('equipment') or 'walker', 'equipment').lower()}"),
    "caregiving_appeal": Template(
        "caregiving_appeal", "Appeal a cut to home care hours", "When the state cuts caregiving hours, PJ files for a fair hearing in time to keep the hours meanwhile.",
        "home", "fight",
        fields=[{"name": "program", "label": "Program", "kind": "select", "options": [[k, v] for k, v in PROGRAMS.items()]},
                {"name": "hours_before", "label": "Hours a week before", "kind": "number"},
                {"name": "hours_after", "label": "Hours a week after the cut", "kind": "number"},
                {"name": "notice_on", "label": "Date on the notice", "kind": "date"}],
        steps=[("notice", "Read the notice and the deadline", "Policy agent", "agent"),
               ("log", "Put together the care needs on file", "Records agent", "agent"),
               ("doctor", "Get the doctor's statement of care needs", "Caller agent", "agent"),
               ("draft", "Write the hearing request", "Writer agent", "agent"),
               ("approve", "Read it and sign", "You", "approve"),
               ("send", "File with the state agency and keep the hours meanwhile", "Submitter agent", "send"),
               ("wait", "Wait for the hearing", "Tracker", "wait"),
               ("outcome", "Result", "PJ", "outcome")],
        run={"notice": _care_notice, "log": _care_log, "doctor": _care_doctor, "draft": _care_draft,
             "send": lambda wf, rec: f"Filed with {cp.STATE_AGENCY['name']} by fax and confirmed by phone, with the request to keep current hours."},
        title_for=lambda i: f"Appeal the cut to home care hours ({i.get('hours_before')} to {i.get('hours_after')} a week)"),
    "counselor_request": Template(
        "counselor_request", "Find a counselor who can really see you", "PJ calls in-network counselors at once; if none can see you soon, it asks the plan for an exception.",
        "people", "care",
        fields=[{"name": "focus", "label": "What it's about (optional)", "kind": "text", "placeholder": "e.g. grief, anxiety, caregiver stress"},
                {"name": "format", "label": "How", "kind": "select", "options": [["either", "Either"], ["video", "Video"], ["in_person", "In person"]]}],
        steps=[("benefit", "Check the plan and EAP", "Coverage agent", "agent"),
               ("calls", "Call in-network counselors at once", "Scheduling swarm", "agent"),
               ("exception", "Ask the plan for an exception", "Writer agent", "agent"),
               ("approve", "Read it and sign", "You", "approve"),
               ("send", "Send it to the plan", "Submitter agent", "send"),
               ("wait", "Wait for the plan", "Tracker", "wait"),
               ("outcome", "Result", "PJ", "outcome")],
        run={"benefit": _co_benefit, "calls": _co_calls, "exception": _co_exception,
             "send": lambda wf, rec: f"Sent to {_payer(rec)} behavioral health with the call log, and confirmed."},
        title_for=lambda i: "Find a counselor" + (f" for {i.get('focus')}" if i.get("focus") else "")),
}

WAIT_DAYS = {"office_request": 5, "bill_dispute": 30, "pa_appeal": 30, "plan_resource": 7, "dme": 14, "caregiving_appeal": 45, "counselor_request": 14}


# ---------------------------------------------------------------- engine

class WorkflowError(Exception):
    pass


def catalog() -> list[dict]:
    return [{"key": t.key, "title": t.title, "blurb": t.blurb, "icon": t.icon, "group": t.group, "fields": t.fields,
             "crew": list(dict.fromkeys(s[2] for s in t.steps if s[2] not in ("You", "PJ")))} for t in TEMPLATES.values()]


def _clean(t: Template, raw: dict) -> dict:
    out: dict = {}
    for f in t.fields:
        v = (raw or {}).get(f["name"])
        if f["kind"] == "bool":
            out[f["name"]] = bool(v)
        elif f["kind"] == "number":
            try:
                out[f["name"]] = max(0, min(168, int(v)))
            except (TypeError, ValueError):
                out[f["name"]] = 0
        elif f["kind"] == "select":
            keys = [o[0] for o in f["options"]]
            out[f["name"]] = v if v in keys else keys[0]
        else:
            out[f["name"]] = " ".join(str(v or "").split())[:120]
    return out


def _task(rec: HealthRecord, wf: Workflow) -> AgentTask | None:
    return next((t for t in rec.tasks if t.title == wf.title and t.agent == "workflow"), None)


def _sync_task(rec: HealthRecord, wf: Workflow) -> None:
    task = _task(rec, wf)
    if task is None:
        task = AgentTask(title=wf.title, agent="workflow")
        rec.tasks.insert(0, task)
    task.status = {"working": TaskStatus.working, "needs_you": TaskStatus.waiting_on_you,
                   "waiting_on_them": TaskStatus.waiting_on_them}.get(wf.status, TaskStatus.done)
    task.needs_you = "Read what PJ wrote and sign it." if wf.status == "needs_you" else None
    task.detail = wf.outcome or (wf.findings[-1] if wf.findings else None)
    task.updated_at = _now()


def _advance(rec: HealthRecord, wf: Workflow) -> None:
    t = TEMPLATES[wf.template] if wf.template in TEMPLATES else TEMPLATES["pa_appeal"]
    run = {**t.run, **({"draft": _external_draft, "send": _pa_send} if wf.template == "external_review" else {})}
    for s in wf.steps:
        if s.status in ("done", "skipped", "failed"):
            continue
        if s.kind in ("agent", "send"):
            fn = run.get(s.key)
            if s.key == "order" and wf.template == "plan_resource" and not RESOURCES.get(wf.inputs.get("resource") or "rides", RESOURCES["rides"])[2]:
                s.status, s.detail = "skipped", "Rides don't need a doctor's order."
                continue
            s.detail = fn(wf, rec) if fn else s.detail
            s.status = "done"
            wf.log(f"{s.agent}: {s.detail}")
            continue
        if s.kind == "approve":
            s.status = "needs_you"
            wf.status = "needs_you"
            break
        if s.kind == "wait":
            s.status, s.due = "working", _plus(WAIT_DAYS.get(wf.template, 30))
            s.detail = f"{s.agent} follows up by {s.due} if there's no answer."
            wf.status = "waiting_on_them"
            break
        if s.kind == "outcome":
            break
    _sync_task(rec, wf)


def start(rec: HealthRecord, template: str, inputs: dict) -> Workflow:
    t = TEMPLATES.get(template)
    if t is None:
        raise KeyError(template)
    clean = _clean(t, inputs)
    wf = Workflow(template=template, title=t.title_for(clean) if t.title_for else t.title, inputs=clean,
                  steps=[WorkflowStep(key=k, title=title, agent=agent, kind=kind) for k, title, agent, kind in t.steps])
    wf.log("Started.")
    rec.workflows.insert(0, wf)
    _advance(rec, wf)
    return wf


def get(rec: HealthRecord, wf_id: str) -> Workflow:
    wf = next((w for w in rec.workflows if w.id == wf_id), None)
    if wf is None:
        raise KeyError(wf_id)
    return wf


def approve(rec: HealthRecord, wf_id: str, typed_name: str, signer: str, capacity: str | None = None) -> Workflow:
    """The consent gate. `signer` is who may sign for this person (see circle.signer)."""
    wf = get(rec, wf_id)
    gate = next((s for s in wf.steps if s.kind == "approve" and s.status == "needs_you"), None)
    if gate is None:
        raise WorkflowError("Nothing is waiting for a signature.")
    if " ".join(typed_name.split()).lower() != " ".join(signer.split()).lower():
        raise WorkflowError(f"Type {signer}'s full name exactly to sign.")
    wf.signed_by = signer + (f", {capacity}" if capacity else "")
    if wf.letter:
        wf.letter = wf.letter.replace(SIGNATURE, f"Signature: /{signer}/{', ' + capacity if capacity else ''}   Date: {_now()[:10]}")
    gate.status, gate.detail = "done", f"Signed by {wf.signed_by}."
    wf.status = "working"
    wf.log(gate.detail)
    _advance(rec, wf)
    return wf


def respond(rec: HealthRecord, wf_id: str, outcome: str = "approved") -> Workflow:
    """Demo control: the other side answers (normally days or weeks later)."""
    wf = get(rec, wf_id)
    wait = next((s for s in wf.steps if s.kind == "wait" and s.status == "working"), None)
    if wait is None:
        raise WorkflowError("PJ isn't waiting on anyone for this one.")
    status, text, saved = cp.respond(wf.template, wf.inputs, outcome)
    wait.status, wait.detail = "done", "They answered."
    final = next(s for s in wf.steps if s.kind == "outcome" and s.status == "pending")
    final.status, final.detail = "done", text
    wf.outcome, wf.saved = text, saved
    wf.status = "won" if status == "won" else "lost"
    wf.log(text)
    if status == "lost":
        _escalate(rec, wf)
    _sync_task(rec, wf)
    return wf


def _escalate(rec: HealthRecord, wf: Workflow) -> None:
    """A no is not the end: queue the next level and stop at the consent gate again."""
    nxt = {"pa_appeal": ("external_review", "Ask for an independent outside review", [
                ("draft", "Write the outside review request", "Writer agent", "agent"),
                ("approve", "Read it and sign", "You", "approve"),
                ("send", "File it and confirm", "Submitter agent", "send"),
                ("wait", "Wait for the outside reviewers", "Tracker", "wait"),
                ("outcome", "Result", "PJ", "outcome")])}.get(wf.template)
    if not nxt:
        return
    template, title, steps = nxt
    follow = Workflow(template=template, title=f"{title}: {wf.inputs.get('service') or ''}".rstrip(": "), inputs=dict(wf.inputs),
                      steps=[WorkflowStep(key=k, title=t, agent=a, kind=kd) for k, t, a, kd in steps],
                      deadline_note="The plan's decision letter states the deadline to ask for outside review; PJ reads it there.")
    follow.log(f"Started because {wf.title.lower()} was turned down.")
    rec.workflows.insert(0, follow)
    _advance(rec, follow)
