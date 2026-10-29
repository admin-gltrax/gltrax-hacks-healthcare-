"""Caller agent: phones the patient's own doctor's office for whatever they need.

Referrals, refills, a letter or form, an order for equipment, a question for
the nurse, records, an appointment, a billing question. PJ works the phone
menu, waits on hold so the patient doesn't, gets transferred to the person who
actually handles it, makes the request, and writes down who it spoke with, the
reference number and when to expect it.

Rules: PJ says it's an AI calling with the patient's permission; it shares only
name, date of birth, member ID and plan (data minimization); it never answers
medical questions for the office or the patient. The office is simulated
(src/sim/pcp_office.py).

Two engines, same result shape:
  call_office_live  Muse Spark caller vs. Spark receptionists (src/agents/office_caller.py),
                    metered by src/agents/ai.py; the transcript streams as it happens.
  call_office       the deterministic script, used when the model API is off,
                    over budget or errors (the call log says which engine ran).
"""
from __future__ import annotations

from ..patient.models import HealthRecord, _now
from ..sim import pcp_office

PURPOSES = {k: v["label"] for k, v in pcp_office.PURPOSES.items()}
FIELD_LABELS = {"name": "name", "dob": "date of birth", "member_id": "member ID", "plan": "plan"}


class NoDoctor(Exception):
    pass


def shared_fields(rec: HealthRecord) -> dict:
    """Exactly what PJ may say on the call."""
    p, cov = rec.patient, rec.coverage
    return {"name": p.display_name, "dob": p.dob, "member_id": cov.member_id if cov else None,
            "plan": cov.plan_name if cov else None}


def _office(rec: HealthRecord, purpose: str):
    pcp = rec.pcp()
    if pcp is None:
        raise NoDoctor("Add the regular doctor first, so PJ knows which office to call.")
    if purpose not in pcp_office.PURPOSES:
        raise KeyError(purpose)
    return pcp


def call_office(rec: HealthRecord, purpose: str, details: str = "") -> dict:
    pcp = _office(rec, purpose)
    result = pcp_office.call(pcp.practice or pcp.name, pcp.phone, purpose, shared_fields(rec), details)
    result["at"] = _now()
    result["shared"] = [k for k, v in shared_fields(rec).items() if v]
    result["engine"] = "rules"
    return result


async def call_office_live(rec: HealthRecord, purpose: str, details: str = "", account: str | None = None,
                           on_line=None) -> dict:
    """A real agent call on Muse Spark. Raises ai.AIUnavailable if the model can't be used."""
    from . import ai
    from .office_caller import OfficeCall
    pcp = _office(rec, purpose)
    caller, office = ai.llm("caller", account), ai.llm("office", account)
    call = OfficeCall(pcp.practice or pcp.name, pcp.phone, purpose, details, shared_fields(rec), caller, office, on_line=on_line)
    result = await call.run()
    result["at"] = _now()
    result["engine"] = ai.engine_label("caller")
    result["requests"] = caller.requests + office.requests
    return result


def summary(c: dict) -> str:
    if not c.get("ok", True):
        return f"Called {c['practice']}: {c['result']}"
    return (f"Called {c['practice']}{' at ' + c['phone'] if c.get('phone') else ''}: {c['menu_path']}, "
            f"waited {c['hold_minutes']} minutes on hold, reached {c['reached']}. {c['result']} Reference {c['reference']}.")
