"""The action menu: what PJ can do for this person, one tap each.

The home screen leads with actions, not information and not an empty chat box.
Healthcare is complicated; the person shouldn't have to know what to ask. Each
action is a template of real work PJ's crew does, adjusted to the person being
viewed (self, a parent, a child), what's set up, and what the account holder is
allowed to do for them.

Kinds the dashboard knows how to run:
  ask      open Ask PJ with `prompt` (sent right away, or prefilled when `edit`)
  flow     a built-in flow: coverage, pcp, records, circle, about, export
  support  jump to the support plan (PJ's suggestions from risk factors)
  workflow open the form for one of PJ's crew jobs (`target` = workflow template)

The crew jobs (contest a bill, appeal a denial, request rides or equipment...)
come from src/agents/workflows.py and sit right under this menu; the
scheduling swarm leads the "Get care" group.
"""
from __future__ import annotations

from ..patient.models import CareRecipient, HealthRecord
from . import circle as circle_agent
from . import outreach


def menu(account: HealthRecord, record: HealthRecord, cr: CareRecipient | None) -> list[dict]:
    first = record.patient.display_name.split()[0]
    you = cr is None
    whose = "your" if you else f"{first}'s"
    if not circle_agent.can(cr, "view"):
        return [_a("consent", "flow", "consent", f"Ask {first} to say yes", "people",
                   f"{first} chooses what you can see and what PJ may do. Nothing else shows until then.")]
    acting = circle_agent.can(cr, "act")
    cov, pcp = record.coverage, record.pcp()
    suggested = [a for a in outreach.support_plan(record) if a.status == "suggested"]
    out = [
        _a("find_care", "ask", "", f"Find a doctor who really takes {whose} plan", "steth",
           "Say what kind of care. PJ checks the plan, skips wrong directory listings and finds the soonest real opening.",
           prompt="I need a ", edit=True, needs=None if cov else "coverage"),
        _a("call_office", "workflow", "office_request", f"Have PJ call {whose} doctor's office", "phone",
           "Referral, refill, a letter, a nurse question... PJ works the phone menu, waits on hold and gets the right person.",
           needs=None if pcp else "pcp"),
        _a("benefits", "support", "", f"Find benefits {'you' if you else first} aren't using", "gift",
           f"{len(suggested)} things PJ found from {whose} age, plan and situation." if suggested
           else "Tell PJ a little more and it will look for free benefits and programs.",
           badge=len(suggested) or None),
        _a("coverage", "flow", "coverage" if not cov else "", f"What does {whose} plan cover?", "shield",
           "Plain answers: what's covered, what it costs, referrals, and free extras through work.",
           prompt=None if not cov else "What does my plan cover?"),
        _a("records", "flow", "records" if pcp else "pcp", f"Get {whose} medical records", "doc",
           "PJ writes the legal request, you sign, PJ faxes it and follows up until it arrives."
           if pcp else "Add the regular doctor first; PJ double-checks their phone and fax by calling."),
        _a("checkup", "ask", "", "Book a checkup" if record.patient.dob is None or (outreach.age_on(record.patient.dob) or 30) < 65
           else "Book the yearly Wellness Visit", "list", "Free on almost every plan, and the easiest visit to put off.",
           prompt="I need a checkup with my primary care doctor"),
        _a("about", "flow", "about", f"Tell PJ about {'yourself' if you else first}", "user",
           "Lives alone, a recent fall, many medicines, hard to afford... PJ turns it into covered next steps."),
    ]
    if you:
        out.insert(4, _a("care_for", "flow", "circle", "Manage care for a parent or child", "people",
                         "Add an older parent, a child or a spouse. They choose what you can see and do."))
    for a in out:
        if not acting:
            a["disabled"] = f"{first} lets you see, but hasn't asked PJ to act for you."
    return out


def _a(key, kind, target, title, icon, blurb, prompt=None, edit=False, needs=None, badge=None) -> dict:
    a = {"key": key, "kind": kind, "target": target, "title": title, "icon": icon, "blurb": blurb}
    if prompt is not None:
        a["prompt"], a["edit"] = prompt, edit
    if needs:
        a["needs"] = needs
    if badge:
        a["badge"] = badge
    return a
