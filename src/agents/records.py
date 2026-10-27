"""Records agent: get the patient's records from their doctor, on their behalf.

The request is the PATIENT's own (HIPAA right of access): the agent drafts it,
the patient reads and signs it, and only then does it go out by fax. The agent
tracks the legal response window and follows up when it lapses. When records
come back they are filed into the four buckets (src/sim/records_office.py in
the demo).

Facts below are tagged like docs/DATA-SOURCES.md: verify [from memory] items
before relying on them outside the demo.
- Patients have a right to their records, and can have copies sent to a third
  party they designate, in writing and signed. [from memory]
- Covered entities generally must act within 30 calendar days, with one
  30-day extension if they tell the patient why. [from memory]
- They may charge only a reasonable, cost-based fee. [from memory]

TODO(meta): Muse Spark drafts the letter in the patient's words and later
reads returned PDFs (vision) into HealthItems.
"""
from __future__ import annotations

from ..channels.fax import FaxChannel, SimulatedFax
from ..patient.models import (
    AgentTask, CareTeamMember, HealthRecord, RecordsRequest, RecordsRequestStatus, TaskStatus, _now,
)
from ..sim.records_office import records_from

RIGHT_OF_ACCESS_DAYS = 30  # [from memory] see module docstring


class NotSigned(Exception):
    pass


def letter(record: HealthRecord, to: CareTeamMember, req: RecordsRequest) -> str:
    p = record.patient
    items = ", ".join(req.what)
    return (
        f"To: Medical Records, {to.practice or to.name}\n"
        f"Fax: {to.fax or 'unknown'}\n\n"
        "Request for access to my health information\n\n"
        f"I, {p.display_name}{' (date of birth ' + p.dob + ')' if p.dob else ''}, am requesting a copy of my "
        f"health records under my right of access. Please include: {items}, for the {req.date_range}.\n\n"
        f"Please send them to me by {req.delivery.replace('_', ' ')}. I understand you may charge a "
        "reasonable, cost-based fee; please tell me the amount before sending if there is one.\n\n"
        "This request was prepared with my assistant, PJ, at my direction. Questions about it can go to me.\n\n"
        "Signature: ______________________   Date: __________\n"
    )


def draft(record: HealthRecord, to: CareTeamMember | None = None) -> RecordsRequest:
    to = to or record.pcp()
    if to is None:
        raise ValueError("add a doctor first")
    req = RecordsRequest(to=to)
    req.letter = letter(record, to, req)
    req.mark(RecordsRequestStatus.awaiting_signature, "Drafted. Needs your signature.")
    record.records_requests.insert(0, req)
    record.tasks.insert(0, AgentTask(
        title=f"Get your records from {to.practice or to.name}", agent="records",
        status=TaskStatus.waiting_on_you, needs_you="Read the request and sign it. It's your right; PJ just does the paperwork.",
    ))
    return req


def _req(record: HealthRecord, req_id: str) -> RecordsRequest:
    for r in record.records_requests:
        if r.id == req_id:
            return r
    raise KeyError(req_id)


def _task(record: HealthRecord, req: RecordsRequest) -> AgentTask | None:
    title = f"Get your records from {req.to.practice or req.to.name}"
    return next((t for t in record.tasks if t.title == title), None)


def sign(record: HealthRecord, req_id: str, typed_name: str) -> RecordsRequest:
    req = _req(record, req_id)
    if typed_name.strip().lower() != record.patient.display_name.strip().lower():
        raise NotSigned("Type your name exactly as it appears on your account to sign.")
    req.signed_at = _now()
    req.letter = (req.letter or "").replace("Signature: ______________________   Date: __________",
                                            f"Signature: /{record.patient.display_name}/   Date: {req.signed_at[:10]}")
    req.mark(RecordsRequestStatus.draft, "Signed by you.")
    return req


def send(record: HealthRecord, req_id: str, fax: FaxChannel | None = None) -> RecordsRequest:
    req = _req(record, req_id)
    if not req.signed_at:
        raise NotSigned("The request has to be signed before PJ can send it.")
    fax = fax or SimulatedFax()
    to = record.pcp() if record.pcp() and record.pcp().id == req.to.id else req.to
    result = fax.send(to.fax or "", [req.letter or ""])
    req.fax_id = result.fax_id
    task = _task(record, req)
    if result.ok:
        req.sent_at = _now()
        req.set_due(RIGHT_OF_ACCESS_DAYS)
        req.mark(RecordsRequestStatus.sent, f"Faxed to {to.fax}.")
        if task:
            task.status, task.needs_you = TaskStatus.waiting_on_them, None
            task.detail = f"Sent. They have until {req.due_by} to respond; PJ follows up if they don't."
        if record.patient.onboarding_step == "records":
            record.patient.onboarding_step = "done"
    else:
        req.mark(RecordsRequestStatus.failed, f"Fax failed: {result.detail}.")
        if task:
            task.status = TaskStatus.working
            task.detail = "The fax number didn't work. PJ is checking the right number with the office."
    return req


def receive(record: HealthRecord, req_id: str) -> int:
    """Demo: the office answers. Files the records into the buckets."""
    req = _req(record, req_id)
    new = records_from(req.to.npi or "")
    record.items.extend(new)
    req.mark(RecordsRequestStatus.received, f"{len(new)} items added to your buckets.")
    task = _task(record, req)
    if task:
        task.status, task.detail = TaskStatus.done, f"Records arrived. {len(new)} things added to your dashboard."
    return len(new)
