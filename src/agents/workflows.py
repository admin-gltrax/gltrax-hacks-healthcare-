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
(src/sim/counterparties.py).

Meta models do the hard parts, each behind code that checks it:
  Caller agent      Muse Spark phones the doctor's office (src/agents/office_caller.py)
  Reader agent      Muse Spark vision reads the denial letter, bill or EOB (reader.py)
  Strategist        Muse Wonder maps the evidence to the plan's own rules (appeals.py)
  Writer agent      Muse Spark drafts the letter; check_letter() must pass
  Reviewer agent    Muse Spark Open (partner credits) plays the insurer's reviewer
                    and tries to deny the appeal; the writer revises (reviewer.py)
A model step returns Pending: it runs in the background while the page shows it
live, and falls back to the rules if the model is off, over budget or fails.
Each step records its engine, so the screen says which model did what.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Awaitable, Callable

from ..config import mock_enabled
from ..patient.models import AgentTask, HealthRecord, TaskStatus, Workflow, WorkflowStep, _now
from ..sim import counterparties as cp
from . import ai, appeals, office_calls, reader, reviewer

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


# ---------------------------------------------------------------- model steps

@dataclass
class Pending:
    """A step a model is doing. `work` runs outside the lock (it's I/O); `done`
    and `fallback` run under it and return the step's detail line."""
    label: str  # what the screen says while it runs
    role: str  # model role, for the engine badge (src/config.py)
    work: Callable[[], Awaitable[Any]]
    done: Callable[[Any], str]
    fallback: Callable[[str], str]
    skip_on_fallback: bool = False  # an optional step: if its model is unavailable, skip it (with a note)


class Skip(str):
    """A step's detail line when the step didn't run (shown as skipped, with the reason)."""


LOCK = threading.RLock()  # one in-memory store, background jobs: mutate records under this
_CTX: dict[str, dict] = {}  # workflow id -> {"account", "save", "live"}
_ENGINE = threading.local()


def _mark(engine: str) -> None:
    _ENGINE.value = engine


def _live(wf: Workflow) -> bool:
    return _CTX.get(wf.id, {}).get("live", False) and ai.enabled()


def _account(wf: Workflow) -> str | None:
    return _CTX.get(wf.id, {}).get("account")


def background() -> bool:
    """Real model calls run in the background; the offline mock runs inline (tests, local demo)."""
    v = os.getenv("PJ_BACKGROUND", "auto")
    return (not mock_enabled()) if v == "auto" else v == "1"


def _call(wf: Workflow, rec: HealthRecord, purpose: str, details: str, then: Callable[[dict], str] | None = None):
    """The caller agent phones the doctor's office; the call log goes on the workflow,
    live as it happens when Muse Spark is on the line."""
    def finish(c: dict, note: str = "") -> str:
        i = next((k for k, x in enumerate(wf.calls) if x is entry), None)
        if i is None:
            wf.calls.append(c)
        else:
            wf.calls[i] = c
        return (then(c) if then else office_calls.summary(c)) + note

    if rec.pcp() is None:
        wf.findings.append("Add the regular doctor first, so PJ knows which office to call.")
        return "Add the regular doctor first, so PJ knows which office to call."
    pcp = rec.pcp()
    entry = {"practice": pcp.practice or pcp.name, "phone": pcp.phone, "purpose": purpose,
             "purpose_label": office_calls.PURPOSES.get(purpose, purpose), "live": True, "transcript": [],
             "engine": ai.engine_label("caller") if ai.enabled() else "rules"}
    if not _live(wf):
        entry.update(office_calls.call_office(rec, purpose, details), live=False)
        wf.calls.append(entry)
        return finish(entry)
    wf.calls.append(entry)
    on_line = lambda who, text: entry["transcript"].append({"speaker": who, "text": text})  # noqa: E731
    return Pending(f"On the phone with {entry['practice']} now", "caller",
                   lambda: office_calls.call_office_live(rec, purpose, details, account=_account(wf), on_line=on_line),
                   lambda c: finish({**c, "live": False}),
                   lambda why: finish({**office_calls.call_office(rec, purpose, details), "live": False,
                                       "fallback": why}, " (scripted call: " + why + ")"))


# --- bill dispute -------------------------------------------------------------

# --- reading documents (Muse Spark vision) ------------------------------------------

def _doc(wf: Workflow, name: str) -> dict | None:
    return _CTX.get(wf.id, {}).get("docs", {}).get(name)


def _read(wf: Workflow, rec: HealthRecord, field_name: str, kind: str, apply: Callable[[dict], str],
          rules: Callable[[], str]):
    """Read the document the person gave for `field_name`, then apply() the fields; rules() if there's none."""
    d = _doc(wf, field_name)
    if not d:
        return rules()
    if not _live(wf):
        wf.findings.append(f"PJ couldn't read the {reader.LABELS[kind]} right now, so it used what you typed.")
        return rules()

    def done(fields: dict) -> str:
        who = fields.get("member_name") or fields.get("patient_name") or ""
        wf.documents.append({"kind": kind, "label": reader.LABELS[kind], "engine": ai.engine_label("reader"),
                             "from": d.get("from", "photo"), "fields": {k: v for k, v in fields.items() if k != "_dropped"},
                             "dropped": fields.get("_dropped", [])})
        if who and rec.patient.display_name.split()[-1].lower() not in who.lower():
            wf.findings.append(f"Heads up: the {reader.LABELS[kind]} is for {who}, not {rec.patient.display_name}. Check it's the right one.")
        return apply(fields)

    def fallback(why: str) -> str:
        wf.findings.append(f"PJ couldn't read the {reader.LABELS[kind]} ({why}), so it used what you typed.")
        return rules()

    return Pending(f"Reading the {reader.LABELS[kind]}", "reader",
                   lambda: reader.read(kind, image=d.get("image"), text=d.get("text"), account=_account(wf)), done, fallback)


def _retitle(rec: HealthRecord, wf: Workflow) -> None:
    """Once a document is read, the title says what it's really about (the task follows it)."""
    t = TEMPLATES.get(wf.template)
    if not t or not t.title_for:
        return
    new = t.title_for(wf.inputs)
    task = _task(rec, wf)
    if task:
        task.title = new
    wf.title = new


def _read_doc(wf: Workflow, kind: str) -> dict | None:
    return next((x["fields"] for x in wf.documents if x["kind"] == kind), None)


def _write(wf: Workflow, kind: str, facts: dict, header: str, rules: Callable[[], str]):
    """The writer agent drafts; check_letter() decides whether its draft reaches the consent gate."""
    if not _live(wf):
        return rules()

    def done(body: str) -> str:
        body = appeals.strip_signoff(body)
        checks = appeals.check_letter(body, facts)
        ok = all(c["ok"] for c in checks)
        wf.checks.append({"what": f"{kind.capitalize()} letter by {ai.engine_label('writer')}", "passed": ok, "items": checks})
        if not ok:
            failed = "; ".join(c["check"].lower() for c in checks if not c["ok"])
            return rules() + f" (Spark's draft failed a check: {failed}; PJ used the standard letter.)"
        wf.letter = f"{header}\n\n{body}\n\nPrepared with my assistant, PJ, at my direction.\n\n{SIGNATURE}\n"
        return f"Drafted by the writer agent from the facts on file only, and checked: {len(checks)} of {len(checks)} checks passed."

    return Pending(f"Writing the {kind} letter", "writer", lambda: appeals.draft_letter(kind, facts, _account(wf)), done,
                   lambda why: rules() + f" (writer unavailable: {why})")


# --- bill dispute -------------------------------------------------------------

def _bill_itemize(wf: Workflow, rec: HealthRecord):
    def rules() -> str:
        case = cp.BILL_CASES.get(wf.inputs.get("issue") or "not_sure", cp.BILL_CASES["not_sure"])
        wf.findings.append("Itemized bill: " + "; ".join(case["lines"]))
        return f"Called {wf.inputs.get('biller') or 'the billing office'} and got an itemized bill with billing codes."

    def apply(b: dict) -> str:
        if b.get("biller") and not wf.inputs.get("biller"):
            wf.inputs["biller"] = b["biller"]
            _retitle(rec, wf)
        wf.findings.append("Itemized bill: " + "; ".join(f"{ln['code']} {ln['description']} ${ln['amount']:,.2f}" for ln in b["lines"]))
        return f"Read the itemized bill: {len(b['lines'])} lines, ${b['amount_due']:,.2f} due."
    return _read(wf, rec, "bill_doc", "bill", apply, rules)


def _bill_eob(wf: Workflow, rec: HealthRecord):
    def rules() -> str:
        case = cp.BILL_CASES.get(wf.inputs.get("issue") or "not_sure", cp.BILL_CASES["not_sure"])
        wf.findings.append(case["finding"])
        return f"Compared every line with {_payer(rec)}'s explanation of benefits. Billed ${case['billed']}; the plan says you owe ${case['owed']}."

    def apply(e: dict) -> str:
        bill = _read_doc(wf, "bill")
        if not bill:
            wf.findings.append(f"The EOB says you owe ${e['total_you_owe']:,.2f}.")
            return f"Read the EOB: you owe ${e['total_you_owe']:,.2f}."
        m = reader.match_bill(bill, e)
        wf.findings.extend(m["problems"] or ["Every line on the bill matches the EOB."])
        wf.inputs.update(billed=m["billed"], owed=m["owed"])
        return (f"Matched every bill line to the EOB (the math is done in code, not by the model): billed ${m['billed']:,.2f}, "
                f"you owe ${m['owed']:,.2f}, overcharge ${m['overcharge']:,.2f}.")
    if _doc(wf, "eob_doc") is None and _read_doc(wf, "bill"):
        return "No EOB yet: PJ will get it from the plan's member portal. Using the bill as read."
    return _read(wf, rec, "eob_doc", "eob", apply, rules)


def _bill_draft(wf: Workflow, rec: HealthRecord):
    bill, eob = _read_doc(wf, "bill"), _read_doc(wf, "eob")
    if not (bill and eob):
        return _bill_draft_rules(wf, rec)
    facts = {"to": f"the billing office at {bill.get('biller') or wf.inputs.get('biller')}", "patient": rec.patient.display_name,
             "member_id": rec.coverage.member_id if rec.coverage else "", "plan": _plan(rec), "subject_of": "the bill",
             "account": bill.get("account"), "date_of_service": bill.get("service_date"), "eob_claim": eob.get("claim"),
             "problems_found": [f for f in wf.findings if "billed" in f or "EOB" in f][-4:],
             "amount_billed": f"${wf.inputs.get('billed', 0):,.2f}", "amount_owed_per_eob": f"${wf.inputs.get('owed', 0):,.2f}",
             "asks": ["correct the bill to match the EOB", "send an updated itemized statement",
                      "hold the account from collections during the review", "reply in writing"]}
    header = f"To: Billing Office, {bill.get('biller') or wf.inputs.get('biller')}\nRe: Account {bill.get('account')}, {_who(rec)}"
    return _write(wf, "billing dispute", facts, header, lambda: _bill_draft_rules(wf, rec))


def _bill_draft_rules(wf: Workflow, rec: HealthRecord) -> str:
    case = cp.BILL_CASES.get(wf.inputs.get("issue") or "not_sure", cp.BILL_CASES["not_sure"])
    if isinstance(wf.inputs.get("billed"), (int, float)):
        case = {**case, "billed": f"{wf.inputs['billed']:,.2f}", "owed": f"{wf.inputs['owed']:,.2f}",
                "finding": " ".join(f for f in wf.findings if "billed" in f or "EOB" in f)}
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


def _pa_denial(wf: Workflow, rec: HealthRecord):
    def apply(f: dict) -> str:
        if f.get("service") and not wf.inputs.get("service"):
            wf.inputs["service"] = f["service"].split(",")[0].strip()[:1].lower() + f["service"].split(",")[0].strip()[1:]
            _retitle(rec, wf)
        if f.get("denied_on"):
            wf.inputs["denied_on"] = f["denied_on"]
        wf.inputs["reason"] = f["reason_category"]
        if f.get("criteria"):
            wf.inputs["criteria"] = f["criteria"]
        if f.get("reason_quote"):
            wf.inputs["reason_quote"] = f["reason_quote"]
        if f.get("case_number"):
            wf.inputs["case_number"] = f["case_number"]
        if f.get("appeals_fax"):
            wf.inputs["appeals_fax"] = f["appeals_fax"]
        if f.get("appeal_by"):
            wf.deadline = f["appeal_by"]
        elif f.get("appeal_days") and f.get("denied_on"):
            wf.deadline = (date.fromisoformat(f["denied_on"]) + timedelta(days=f["appeal_days"])).isoformat()
        else:
            return _pa_denial_rules(wf, rec) + " The letter didn't print a deadline, so PJ used the usual window."
        wf.deadline_note = (f"Read from the denial letter by {ai.engine_label('reader')}: appeal by {wf.deadline}"
                            + (f" ({f['appeal_days']} days)" if f.get("appeal_days") else "") + ". The letter wins over any typical window."
                            + (" A fast (expedited) appeal is available." if f.get("expedited_available") else ""))
        quote = f.get("reason_quote") or REASONS.get(f["reason_category"], "")
        wf.findings.append(f"The plan's reason, word for word: \"{quote}\" File by {wf.deadline}.")
        if f.get("criteria"):
            wf.findings.append(f"The letter lists {len(f['criteria'])} coverage rules; the appeal answers each one.")
        return f"Read the denial letter: {(f.get('service') or 'the service').rstrip('.')}, denied on {f.get('denied_on') or '?'}; appeal by {wf.deadline}."
    return _read(wf, rec, "document", "denial_letter", apply, lambda: _pa_denial_rules(wf, rec))


def _pa_denial_rules(wf: Workflow, rec: HealthRecord) -> str:
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


def _pa_doctor(wf: Workflow, rec: HealthRecord):
    def then(c: dict) -> str:
        if c.get("ok", True):
            wf.findings.append(f"{_doctor(rec)}'s office is sending a letter of medical necessity (reference {c['reference']}).")
        return office_calls.summary(c)
    return _call(wf, rec, "letter", f"a letter of medical necessity for {wf.inputs.get('service') or 'the denied service'}, for an appeal", then)


def _pa_criteria(wf: Workflow, rec: HealthRecord):
    def rules() -> str:
        return (f"Matched the records and the doctor's letter to {_payer(rec)}'s coverage rules for "
                f"{wf.inputs.get('service') or 'this service'}, point by point.")
    if not _live(wf):
        return rules()
    reason = wf.inputs.get("reason") or "not_sure"
    criteria = wf.inputs.get("criteria") or appeals.DEFAULT_CRITERIA.get(reason, appeals.DEFAULT_CRITERIA["not_sure"])
    evidence = appeals.evidence_for(rec, wf.calls)

    def done(m: dict) -> str:
        wf.criteria = m["criteria"]
        wf.inputs["argument"] = m["argument"]
        met = sum(r["status"] == "met" for r in m["criteria"])
        part = sum(r["status"] == "partly" for r in m["criteria"])
        wf.findings.append(f"Coverage rules: {met} met, {part} partly met, {len(m['criteria']) - met - part} missing evidence.")
        for g in m["gaps"][:3]:
            wf.findings.append(f"Gap to close: {g}")
        wf.checks.append({"what": f"Evidence map by {ai.engine_label('strategist')}", "passed": m["invented_citations_dropped"] == 0,
                          "items": [{"check": "Every citation points to real evidence on file", "ok": m["invented_citations_dropped"] == 0,
                                     **({"detail": f"{m['invented_citations_dropped']} made-up citation(s) removed"} if m["invented_citations_dropped"] else {})},
                                    {"check": "A rule counts as met only with evidence", "ok": True}]})
        return f"Mapped {len(evidence)} pieces of evidence to the plan's {len(m['criteria'])} rules: {met} met, {part} partly."
    return Pending("Mapping the evidence to the plan's rules", "strategist",
                   lambda: appeals.map_criteria(wf.inputs.get("service") or "", wf.inputs.get("reason_quote") or REASONS.get(reason, ""),
                                                criteria, evidence, _account(wf)), done,
                   lambda why: rules() + f" (strategist unavailable: {why})")


def _pa_facts(wf: Workflow, rec: HealthRecord) -> tuple[dict, str]:
    """What the writer may use (and check_letter enforces), and the To/Re header code adds."""
    call = next((c for c in reversed(wf.calls) if c.get("purpose") == "letter" and c.get("ok", True)), None)
    fax = wf.inputs.get("appeals_fax") or cp.APPEALS_FAX.get(_prefix(rec), "")
    facts = {"to": f"the Appeals Unit at {_payer(rec)}", "member_name": rec.patient.display_name, "date_of_birth": rec.patient.dob,
             "member_id": rec.coverage.member_id if rec.coverage else "", "plan": _plan(rec),
             "service": wf.inputs.get("service"), "subject_of": wf.inputs.get("service") or "", "denied_on": wf.inputs.get("denied_on"),
             "case_number": wf.inputs.get("case_number", ""), "plan_reason": wf.inputs.get("reason_quote") or REASONS.get(wf.inputs.get("reason") or "not_sure"),
             "treating_doctor": _doctor(rec),
             "doctor_letter": f"letter of medical necessity requested, reference {call['reference']}" if call else "",
             "coverage_rules_and_evidence": [{"rule": r["criterion"], "evidence": r["evidence"]} for r in wf.criteria],
             "core_argument": wf.inputs.get("argument", ""),
             "urgent": bool(wf.inputs.get("urgent")), **({"fast_decision_hours": 72} if wf.inputs.get("urgent") else {}),
             "enclosures": ["doctor's letter of medical necessity", "medical records", "the denial notice"]}
    header = (f"To: Appeals Unit, {_payer(rec)}\nFax: {fax or 'on the denial letter'}\n"
              f"Re: Appeal of prior authorization denial{' (case ' + wf.inputs['case_number'] + ')' if wf.inputs.get('case_number') else ''}. "
              f"Member: {_who(rec)}, plan {_plan(rec)}")
    return facts, header


def _pa_draft(wf: Workflow, rec: HealthRecord):
    if not _live(wf):
        return _pa_draft_rules(wf, rec)
    facts, header = _pa_facts(wf, rec)
    return _write(wf, "appeal", facts, header, lambda: _pa_draft_rules(wf, rec))


FOOTER = "Prepared with my assistant, PJ, at my direction."


def _letter_body(letter: str) -> str:
    """The part of a drafted letter between the To/Re header and the footer."""
    head, _, rest = letter.partition("\n\n")
    if rest.startswith("Re:"):  # the standard letter puts Re: in its own paragraph
        rest = rest.partition("\n\n")[2]
    return rest.split(FOOTER)[0].replace(SIGNATURE, "").strip()


def _pa_review(wf: Workflow, rec: HealthRecord):
    """The insurer-side reviewer (Muse Spark Open) tries to deny the draft; the writer revises."""
    if not wf.letter:
        return Skip("Nothing to stress-test yet.")
    if not _live(wf) or not ai.role_ready("reviewer"):
        return Skip("Skipped: the insurer-side reviewer (Muse Spark Open on partner credits) isn't switched on here. "
                    "The appeal is unchanged.")
    facts, header = _pa_facts(wf, rec)
    rules = [r["criterion"] for r in wf.criteria] or wf.inputs.get("criteria") or \
        appeals.DEFAULT_CRITERIA.get(wf.inputs.get("reason") or "not_sure", appeals.DEFAULT_CRITERIA["not_sure"])
    evidence = [e["what"] for e in appeals.evidence_for(rec, wf.calls)]
    body = _letter_body(wf.letter)
    wf.review = {"engine": ai.engine_label("reviewer"), "writer": ai.engine_label("writer"), "rules": reviewer.numbered(rules),
                 "original": body, "rounds": [], "live": True}

    def on_round(entry: dict) -> None:
        with LOCK:
            wf.review["rounds"].append(entry)

    def done(r: dict) -> str:
        wf.review.update(rounds=r["rounds"], passed=r["passed"], todos=r["todos"], note=r["note"], live=False, final=r["body"])
        if r["revised"]:
            wf.letter = f"{header}\n\n{r['body']}\n\n{FOOTER}\n\n{SIGNATURE}\n"
        revisions = [x["revision"] for x in r["rounds"] if x.get("revision")]
        wf.checks.append({"what": f"Stress test by {ai.engine_label('reviewer')}", "passed": r["invented_rules_dropped"] == 0 and all(v["accepted"] for v in revisions),
                          "items": [{"check": "Every objection cites a rule the plan really has", "ok": r["invented_rules_dropped"] == 0,
                                     **({"detail": f"{r['invented_rules_dropped']} made-up rule(s) removed"} if r["invented_rules_dropped"] else {})},
                                    {"check": "The reviewer wrote none of the letter", "ok": True,
                                     **({"detail": "letter text it offered was ignored"} if r["letter_text_ignored"] else {})},
                                    {"check": "Every revision passed the letter checks", "ok": all(v["accepted"] for v in revisions),
                                     **({"detail": f"{len(revisions)} revision(s)"} if revisions else {})}]})
        n = len(r["rounds"])
        if r["passed"]:
            wf.findings.append(f"The insurer-side reviewer couldn't find a reason to deny after {n} round{'s' if n != 1 else ''}"
                               + (f" and {len(revisions)} revision{'s' if len(revisions) != 1 else ''}." if revisions else "."))
            return (f"Stress-tested: the insurer-side reviewer went over it {n} time{'s' if n != 1 else ''}"
                    + (f"; the writer answered its objections in {len(revisions)} revision{'s' if len(revisions) != 1 else ''}" if revisions else "")
                    + ", and the last review found no reason to deny.")
        for t in r["todos"]:
            wf.findings.append(f"To do before sending: {t}")
        return (f"Stress-tested over {n} round{'s' if n != 1 else ''}: {len(r['todos'])} reason{'s' if len(r['todos']) != 1 else ''} to deny "
                + ("still stands" if len(r["todos"]) == 1 else "still stand") + (f". {r['note']}" if r["note"] else ".") + " PJ listed exactly what's missing; you can still sign and send.")

    def fallback(why: str) -> str:
        wf.review = {}
        return f"Skipped: the insurer-side reviewer isn't available right now ({why}). The appeal is unchanged."

    return Pending("The insurer's reviewer is trying to deny the appeal", "reviewer",
                   lambda: reviewer.stress_test("appeal", facts, body, rules, evidence, _account(wf), on_round=on_round),
                   done, fallback, skip_on_fallback=True)


def _pa_draft_rules(wf: Workflow, rec: HealthRecord) -> str:
    svc = wf.inputs.get("service") or "the requested service"
    reason = REASONS.get(wf.inputs.get("reason") or "not_sure", REASONS["not_sure"])
    fast = "\nThis is an urgent request: waiting could seriously harm my health. Please decide within 72 hours.\n" if wf.inputs.get("urgent") else ""
    wf.letter = (
        f"To: Appeals Unit, {_payer(rec)}\nFax: {wf.inputs.get('appeals_fax') or cp.APPEALS_FAX.get(_prefix(rec), 'on the denial letter')}\n\n"
        f"Re: Appeal of prior authorization denial for {svc}. Member: {_who(rec)}, plan {_plan(rec)}\n\n"
        f"I'm appealing the denial of {svc}, which was denied because {reason}.{fast}\n"
        f"{_doctor_letter(wf, rec)} The enclosed records show "
        "the history behind the request. Each of the plan's coverage criteria is answered in the enclosed table.\n\n"
        "Please send me the plan's decision in writing, and a copy of the criteria used.\n\n"
        f"Prepared with my assistant, PJ, at my direction.\n\n{SIGNATURE}\n"
    )
    return "Appeal letter drafted, with the doctor's letter, records and a criteria table attached."


def _doctor_letter(wf: Workflow, rec: HealthRecord) -> str:
    """Say only what's true about the doctor's letter: requested (with the call's reference), not 'enclosed'."""
    call = next((c for c in reversed(wf.calls) if c.get("purpose") == "letter" and c.get("ok", True)), None)
    if call:
        return (f"I have asked my doctor, {_doctor(rec)}, for a letter of medical necessity (office reference {call['reference']}); "
                "the office will send it to you directly.")
    return f"My doctor, {_doctor(rec)}, ordered this service."


def _pa_send(wf: Workflow, rec: HealthRecord) -> str:
    return (f"Faxed to {_payer(rec)} appeals at {wf.inputs.get('appeals_fax') or cp.APPEALS_FAX.get(_prefix(rec), 'the number on the letter')}, "
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


def _office_call(wf: Workflow, rec: HealthRecord):
    def then(c: dict) -> str:
        if c.get("ok", True):
            wf.findings.append(f"Spoke with {c['reached']}. Reference {c['reference']}. Expect it in about {c['days']} business day(s).")
        else:
            wf.findings.append(c["result"])
        return office_calls.summary(c)
    return _call(wf, rec, wf.inputs.get("purpose") or "referral", wf.inputs.get("details") or "", then)


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
        fields=[{"name": "bill_doc", "label": "Photo of the itemized bill", "kind": "document", "doc": "bill"},
                {"name": "eob_doc", "label": "Photo of the plan's explanation of benefits (EOB)", "kind": "document", "doc": "eob"},
                {"name": "biller", "label": "Who sent the bill", "kind": "text", "placeholder": "e.g. Harbor Family Medicine"},
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
        fields=[{"name": "document", "label": "Photo of the denial letter (or paste its text)", "kind": "document", "doc": "denial_letter"},
                {"name": "service", "label": "What was denied", "kind": "text", "placeholder": "e.g. MRI of the lower back"},
                {"name": "denied_on", "label": "Date on the denial letter", "kind": "date"},
                {"name": "reason", "label": "Reason given", "kind": "select", "options": [[k, v[0].upper() + v[1:]] for k, v in REASONS.items()]},
                {"name": "urgent", "label": "Waiting could seriously harm health (ask for a fast review)", "kind": "bool"}],
        steps=[("denial", "Read the denial and the deadline", "Policy agent", "agent"),
               ("evidence", "Pull supporting notes from the records", "Records agent", "agent"),
               ("doctor", "Get a letter of medical necessity from the doctor", "Caller agent", "agent"),
               ("criteria", "Match the evidence to the plan's rules", "Policy agent", "agent"),
               ("draft", "Write the appeal", "Writer agent", "agent"),
               ("review", "Stress-test the appeal", "Reviewer agent", "agent"),
               ("approve", "Read it and sign", "You", "approve"),
               ("send", "Fax it to the plan and confirm it arrived", "Submitter agent", "send"),
               ("wait", "Wait for the decision", "Tracker", "wait"),
               ("outcome", "Result", "PJ", "outcome")],
        run={"denial": _pa_denial, "evidence": _pa_evidence, "doctor": _pa_doctor, "criteria": _pa_criteria,
             "draft": _pa_draft, "review": _pa_review, "send": _pa_send},
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


def catalog() -> list[dict]:
    return [{"key": t.key, "title": t.title, "blurb": t.blurb, "icon": t.icon, "group": t.group, "fields": t.fields,
             "crew": list(dict.fromkeys(s[2] for s in t.steps if s[2] not in ("You", "PJ")))} for t in TEMPLATES.values()]


class WorkflowError(Exception):
    pass


def _document(f: dict, v) -> dict | None:
    """A photo (data URL), pasted text, or one of the fictional samples. Validated; kept only until it's read."""
    if not isinstance(v, dict):
        return None
    if v.get("sample"):
        from ..sim.documents import SAMPLES
        import base64
        from pathlib import Path
        s = SAMPLES.get(f["doc"])
        if not s or v["sample"] != f["doc"]:
            raise WorkflowError("Unknown sample document.")
        png = Path(__file__).resolve().parents[1] / "api" / "static" / "samples" / s["file"]
        return {"image": "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode(), "from": "sample photo"}
    if v.get("image"):
        try:
            return {"image": reader.check_image(str(v["image"])), "from": "photo"}
        except reader.ReadError as e:
            raise WorkflowError(str(e)) from e
    text = str(v.get("text") or "").strip()
    return {"text": text[:reader.MAX_TEXT], "from": "pasted text"} if text else None


def _documents(t: Template, raw: dict) -> dict:
    return {f["name"]: d for f in t.fields if f["kind"] == "document" and (d := _document(f, (raw or {}).get(f["name"])))}


def _clean(t: Template, raw: dict) -> dict:
    out: dict = {}
    for f in t.fields:
        v = (raw or {}).get(f["name"])
        if f["kind"] == "document":
            continue
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
            if s.status == "working":
                break  # a model is on it; _finish() resumes from here
            fn = run.get(s.key)
            if s.key == "order" and wf.template == "plan_resource" and not RESOURCES.get(wf.inputs.get("resource") or "rides", RESOURCES["rides"])[2]:
                s.status, s.detail = "skipped", "Rides don't need a doctor's order."
                continue
            out = fn(wf, rec) if fn else s.detail
            if isinstance(out, Pending):
                s.status, s.detail, s.engine = "working", out.label + "…", ai.engine_label(out.role)
                wf.status = "working"
                _sync_task(rec, wf)
                _run_pending(rec, wf, s, out)
                return
            s.detail = out
            s.status = "skipped" if isinstance(out, Skip) else "done"
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


def _run_pending(rec: HealthRecord, wf: Workflow, s: WorkflowStep, p: Pending) -> None:
    if not background():
        _finish(rec, wf, s, p)
        return
    threading.Thread(target=_finish, args=(rec, wf, s, p), daemon=True, name=f"pj-{wf.id}-{s.key}").start()


def _finish(rec: HealthRecord, wf: Workflow, s: WorkflowStep, p: Pending) -> None:
    """Do the model work, then apply it (or the rules) under the lock and keep going."""
    try:
        result, err = ai.run(p.work()), None
    except ai.AIUnavailable as e:
        result, err = None, str(e)
    except Exception as e:  # a bad step must not wedge the workflow
        result, err = None, f"{type(e).__name__}: {str(e)[:160]}"
    with LOCK:
        try:
            s.status = "done"
            if err is None:
                s.detail = p.done(result)
            else:
                s.detail, s.engine = p.fallback(err), "rules"
                if p.skip_on_fallback:
                    s.status, s.engine = "skipped", None
        except Exception as e:
            s.detail, s.engine = f"PJ hit a problem on this step ({type(e).__name__}); a person will review it.", "rules"
            s.status = "skipped" if p.skip_on_fallback else "done"
        wf.status = "working"
        wf.log(f"{s.agent}: {s.detail}")
        _advance(rec, wf)
        save = _CTX.get(wf.id, {}).get("save")
    if save:
        try:
            save()
        except Exception:
            pass


def busy(rec: HealthRecord) -> bool:
    return any(st.status == "working" and st.kind in ("agent", "send") for w in rec.workflows for st in w.steps)


def start(rec: HealthRecord, template: str, inputs: dict, account: str | None = None,
          save: Callable[[], None] | None = None, live: bool | None = None) -> Workflow:
    """Start a workflow. live=None uses the Meta models when they're on (src/agents/ai.py);
    live=False keeps it on the rules (the prebuilt demo family, so a page load spends nothing)."""
    t = TEMPLATES.get(template)
    if t is None:
        raise KeyError(template)
    docs = _documents(t, inputs)
    clean = _clean(t, inputs)
    with LOCK:
        wf = Workflow(template=template, title=t.title_for(clean) if t.title_for else t.title, inputs=clean,
                      steps=[WorkflowStep(key=k, title=title, agent=agent, kind=kind) for k, title, agent, kind in t.steps])
        _CTX[wf.id] = {"account": account, "save": save, "live": ai.enabled() if live is None else live, "docs": docs}
        wf.log("Started." + (" Reading: " + ", ".join(d["from"] for d in docs.values()) + "." if docs else ""))
        rec.workflows.insert(0, wf)
        _advance(rec, wf)
    return wf


def get(rec: HealthRecord, wf_id: str) -> Workflow:
    wf = next((w for w in rec.workflows if w.id == wf_id), None)
    if wf is None:
        raise KeyError(wf_id)
    return wf


def approve(rec: HealthRecord, wf_id: str, typed_name: str, signer: str, capacity: str | None = None,
            save: Callable[[], None] | None = None) -> Workflow:
    """The consent gate. `signer` is who may sign for this person (see circle.signer)."""
    with LOCK:
        return _approve(rec, wf_id, typed_name, signer, capacity, save)


def _approve(rec: HealthRecord, wf_id: str, typed_name: str, signer: str, capacity: str | None, save) -> Workflow:
    wf = get(rec, wf_id)
    if save:
        _CTX.setdefault(wf.id, {"live": False})["save"] = save
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
    with LOCK:
        return _respond(rec, wf_id, outcome)


def _respond(rec: HealthRecord, wf_id: str, outcome: str) -> Workflow:
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
    _CTX[follow.id] = {**_CTX.get(wf.id, {"live": False}), "docs": {}}
    follow.criteria = list(wf.criteria)
    rec.workflows.insert(0, follow)
    _advance(rec, follow)
