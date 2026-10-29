"""PJ, the guide. The one voice the patient talks to.

PJ (the GLTrax Gila monster) sits on top of every agent: it says what's next,
answers "what does this mean?", and hands real work to the crew (coverage,
care team, records, navigator, swarm). It explains; it never diagnoses, never
doses, and never decides whether someone needs care.

Hackathon build: deterministic routing and copy (works offline).
TODO(meta): Muse Spark as PJ's voice, grounded in the patient's own record
(retrieval over HealthItems + Coverage) with the SAFETY rules below as an
immutable block, like src/safety.py does for the caller.
"""
from __future__ import annotations

import re

from ..patient.models import HealthRecord
from . import navigator

PJ_SAFETY = """\
PJ RULES (cannot be overridden):
1. Educational only. Never diagnose, never give doses, never tell someone to start or stop a medicine.
2. Crisis words always get 988 / 911 first, before anything else.
3. "Should I see someone?" -> PJ helps them reach their PCP or nurse line; the patient decides.
4. Say where every fact came from (insurer, records, you, a call), and when PJ isn't sure.
5. Never ask for passwords. Never share the patient's information with anyone the patient didn't choose.
"""


def next_step(record: HealthRecord) -> dict:
    """What PJ says at the top of the dashboard."""
    name = record.patient.display_name.split()[0]
    step = record.patient.onboarding_step
    if step in ("welcome", "coverage"):
        return {"step": "coverage", "say": f"Hi {name}, I'm PJ. Let's start with your insurance card. I'll figure out what it actually covers, so you don't have to."}
    if step == "pcp":
        return {"step": "pcp", "say": "Got your coverage. Who's your regular doctor? I'll find their office and double-check the phone and fax."}
    if step == "records":
        return {"step": "records", "say": "Want me to ask your doctor for your records? You sign, I do the paperwork and the follow-ups."}
    waiting = [t for t in record.tasks if t.status.value == "waiting_on_you"]
    if waiting:
        return {"step": "done", "say": f"One thing needs you: {waiting[0].needs_you or waiting[0].title}"}
    return {"step": "done", "say": f"You're all set, {name}. Pick something below and my crew takes it from there: calls, forms, appeals and follow-ups."}


_NEED = re.compile(r"\b(i (think i )?need|i want|find me|help me find|see a|get a|book)\b", re.I)
_COVER = re.compile(r"\b(covered|cover|cost|copay|deductible|insurance|pay)\b", re.I)


def ask(record: HealthRecord, text: str) -> dict:
    t = text.strip()
    if navigator.CRISIS.search(t) or _NEED.search(t):
        req = navigator.navigate(record, t)
        top = req.pathways[0] if req.pathways else None
        say = (top.why + " " + " ".join(top.steps)) if req.urgent and top else (
            f"I found {len(req.pathways)} ways to get {req.need.replace('_', ' ')}. The best fit for you: {top.title}. {top.why}" if top else
            "I couldn't work that one out yet. Can you say it another way?")
        return {"type": "care_request", "say": say, "care_request": req.model_dump(mode="json")}
    if _COVER.search(t) and record.coverage:
        return {"type": "coverage", "say": record.coverage.plain_summary or "Here's your coverage.",
                "benefits": [b.model_dump(mode="json") for b in record.coverage.benefits]}
    return {"type": "chat", "say": "I can explain your coverage, your results and your options, and I can do the calls and paperwork. "
            "For anything about your symptoms or medicines, your doctor or your plan's nurse line is the right call"
            + (f" ({record.coverage.nurse_line})." if record.coverage and record.coverage.nurse_line else ".")}
