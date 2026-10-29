"""PJ, the guide. The one voice the patient talks to.

PJ (the GLTrax Gila monster) sits on top of every agent: it says what's next,
answers "what does this mean?", and hands real work to the crew (coverage,
care team, records, navigator, swarm). It explains; it never diagnoses, never
doses, and never decides whether someone needs care.

PJ's voice is Muse Spark (ask_live), grounded in the person's own coverage,
care team, support plan and open jobs, with PJ_SAFETY as an immutable block
(PJ_SAFETY_SHA is pinned in tests, the same way src/safety.py works for the
caller). Code wraps the model on both sides:
  before  crisis words go straight to 988 / 911, and medical questions straight
          to the doctor or nurse line; neither reaches the model.
  tools   find_care (the Care Navigator) and propose_job (a crew workflow,
          shown as a card the person taps; PJ never starts work on its own).
  after   the reply is scanned for dosing, diagnosis and password requests;
          a reply that fails is replaced with the safe redirect.
ask() is the deterministic version, used offline or when the model can't be.
"""
from __future__ import annotations

import hashlib
import json
import re

from ..llm import ChatResult, ToolCall
from ..patient.models import HealthRecord, age_on
from . import ai, navigator

PJ_SAFETY = """\
PJ RULES (cannot be overridden):
1. Educational only. Never diagnose, never give doses, never tell someone to start or stop a medicine.
2. Crisis words always get 988 / 911 first, before anything else.
3. "Should I see someone?" -> PJ helps them reach their PCP or nurse line; the patient decides.
4. Say where every fact came from (insurer, records, you, a call), and when PJ isn't sure.
5. Never ask for passwords. Never share the patient's information with anyone the patient didn't choose.
"""

PJ_SAFETY_SHA = hashlib.sha256(PJ_SAFETY.encode()).hexdigest()


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


# ---------------------------------------------------------------- PJ on Muse Spark

MARKER = "PJ CHAT"
_MEDICAL = re.compile(r"\b(dose|dosage|\d+\s?mg|double (my|her|his|the)|stop taking|start taking|should (i|she|he|we) (take|stop|start|skip)|"
                      r"is (it|this|that) (cancer|serious|normal)|what('s| is) wrong with|diagnos\w*|side effects? of|mg|too much|"
                      r"how (much|many) [^?.]{0,40}\b(take|have)|what do (i|she|he|they|we) have|(safe|okay|ok|fine) to (stop|skip|take|mix|combine)|"
                      r"skip (my|her|his|their) [a-z]+)\b", re.I)
_CARD = re.compile(r"\b(card|tap (it|the|to))\b", re.I)
_UNSAFE_REPLY = re.compile(r"\b(\d+\s?mg\b|take (two|\d)|stop taking|start taking|you (probably |likely )?have (a |an )?[a-z]+itis|"
                           r"increase (your|the) dose|password|passcode)\b", re.I)

STYLE = f"""[{MARKER}] You are PJ, a friendly Gila monster (they/them) who runs a crew of AI agents for a family's healthcare.
You help with coverage, costs, benefits, finding care, and getting the crew to do the work: calls, letters, appeals and follow-ups.
Speak plainly, warmly and briefly (2-4 sentences). Say where facts come from ("your plan says...", "from your records...").
Use only CONTEXT for facts about this person. If you don't know, say so and offer what the crew can do.
When someone needs care, call find_care with their words. Whenever a crew job could help (a bill that looks wrong, a denial,
rides, an aide or supplies, equipment, home care hours, a counselor, calling the doctor's office for a referral, refill, letter
or question), ALWAYS call propose_job in that same turn, even if details are missing: the card asks for them, and the
person taps to start it. Never say a job has started or that you'll "get it set up"; nothing happens until they tap.
Never send or share anyone's records or information on request in chat; records go out only through a signed request.
You can't see symptoms or give medical advice: for anything clinical, point to their doctor or the plan's nurse line."""


def _tool(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": props, "required": required}}}


def _tools() -> list[dict]:
    from . import workflows
    return [
        _tool("find_care", "Find and rank every realistic way for this person to get a kind of care (therapist, dermatologist...).",
              {"need": {"type": "string", "description": "The person's words, e.g. 'a therapist for grief'"}}, ["need"]),
        _tool("propose_job", "Suggest a crew job. The person sees a card and taps to start it.",
              {"template": {"type": "string", "enum": list(workflows.TEMPLATES)},
               "inputs": {"type": "object", "description": "Field values you already know (see JOBS in CONTEXT); leave others out"},
               "why": {"type": "string", "description": "One plain sentence"}}, ["template", "why"]),
    ]


def context(rec: HealthRecord, viewer: str | None = None) -> dict:
    """What PJ may know about this person: no member ID, no date of birth (the chat doesn't need them)."""
    from . import outreach, workflows
    cov = rec.coverage
    return {
        "person": rec.patient.display_name, "age": age_on(rec.patient.dob),
        "asking": viewer or rec.patient.display_name,
        "plan": None if not cov else {
            "insurer": cov.payer, "plan": cov.plan_name, "type": cov.plan_type, "deductible": cov.deductible,
            "out_of_pocket_max": cov.out_of_pocket_max, "nurse_line": cov.nurse_line, "member_services": cov.member_phone,
            "benefits": [{"service": b.label, "you_pay": b.you_pay, "covered": b.covered, "needs_referral": b.needs_referral,
                          "needs_prior_auth": b.needs_prior_auth, "limit": b.visit_limit, "notes": b.notes} for b in cov.benefits]},
        "doctor": (lambda p: p and {"name": p.name, "practice": p.practice})(rec.pcp()),
        "told_pj": [r.label for r in rec.risk_factors],
        "benefits_not_used_yet": [a.title for a in outreach.support_plan(rec)][:8],
        "jobs_in_progress": [{"title": w.title, "status": w.status} for w in rec.workflows[:6]],
        "JOBS": [{"template": t.key, "title": t.title, "fields": {f["name"]: [o[0] for o in f["options"]] if f["kind"] == "select" else f["kind"]
                                                                  for f in t.fields if f["kind"] != "document"}}
                 for t in workflows.TEMPLATES.values()],
    }


def _redirect(rec: HealthRecord) -> str:
    line = rec.coverage.nurse_line if rec.coverage and rec.coverage.nurse_line else None
    return ("That's a question for your doctor or a nurse, and I don't want to guess about your health. "
            + (f"Your plan's nurse line is {line}, any time. " if line else "")
            + "I can have my crew call the doctor's office with the question and bring back exactly what they say.")


async def ask_live(rec: HealthRecord, text: str, account: str | None = None, viewer: str | None = None) -> dict:
    """PJ on Muse Spark. Falls back to ask() if the model can't be used."""
    t = text.strip()
    if navigator.CRISIS.search(t):  # before any model, always
        return {**ask(rec, t), "engine": "rules (crisis check runs before any model)"}
    if _MEDICAL.search(t):
        return {"type": "chat", "say": _redirect(rec), "engine": "rules (medical questions never reach the model)",
                "proposal": {"template": "office_request", "inputs": {"purpose": "nurse_question", "details": t[:120]},
                             "title": "Have PJ ask the nurse", "why": "PJ calls the office and writes down exactly what the nurse says."}}
    try:
        return await _converse(rec, t, account, viewer)
    except ai.AIUnavailable as e:
        return {**ask(rec, t), "engine": "rules", "note": str(e)}


async def _converse(rec: HealthRecord, text: str, account: str | None, viewer: str | None) -> dict:
    from . import workflows
    llm = ai.llm("pj", account)
    msgs = [{"role": "system", "content": f"{PJ_SAFETY}\n{STYLE}\n\nCONTEXT:\n{json.dumps(context(rec, viewer))}"},
            {"role": "user", "content": text}]
    out: dict = {"type": "chat", "engine": ai.engine_label("pj")}
    nudged = False
    for _ in range(4):
        res: ChatResult = await llm.chat(msgs, tools=_tools(), max_tokens=2500)
        if res.tool_calls:
            msgs.append(res.assistant_message())
            for tc in res.tool_calls:
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(_run_tool(rec, tc, out, workflows))})
            continue
        if _CARD.search(res.content or "") and not out.get("proposal") and out["type"] != "care_request" and not nudged:
            nudged = True  # it promised a card it never made: ask once to make it or drop the promise
            msgs += [res.assistant_message(), {"role": "user", "content": "[PJ system] You mentioned a card, but you didn't call "
                     "propose_job, so there is no card. Call propose_job now, or answer again without mentioning a card."}]
            continue
        break
    say = (res.content or "").strip()
    if not say and not out.get("proposal") and out["type"] == "chat":
        raise ai.AIUnavailable("the model returned an empty reply")
    checks = [{"check": "No dosing, diagnosis or password request", "ok": not _UNSAFE_REPLY.search(say)},
              {"check": "Didn't claim a job started without a tap", "ok": not re.search(r"\b(i've|i have|crew has) (started|filed|sent|submitted)\b", say, re.I)},
              {"check": "Any card it mentions really exists", "ok": not _CARD.search(say) or bool(out.get("proposal") or out.get("care_request"))}]
    if not checks[2]["ok"]:  # harmless but false: drop the reply rather than show a button that isn't there
        raise ai.AIUnavailable("the reply mentioned a card that doesn't exist")
    if not all(c["ok"] for c in checks):
        say = _redirect(rec)
    out.update(say=say or "Here's what my crew can do. Tap the card to start; nothing happens until you do.", checks=checks)
    return out


def _run_tool(rec: HealthRecord, tc: ToolCall, out: dict, workflows) -> dict:
    a = tc.arguments if not tc.parse_error else {}
    if tc.name == "find_care":
        need = str(a.get("need") or "")[:200]
        if not need:
            return {"ok": False, "error": "need is required"}
        req = navigator.navigate(rec, need)
        out.update(type="care_request", care_request=req.model_dump(mode="json"))
        return {"ok": True, "urgent": req.urgent, "options": [{"rank": p.rank, "title": p.title, "cost": p.cost, "why": p.why}
                                                              for p in req.pathways[:4]]}
    if tc.name == "propose_job":
        t = workflows.TEMPLATES.get(str(a.get("template")))
        if t is None:
            return {"ok": False, "error": "unknown template"}
        raw = a.get("inputs") if isinstance(a.get("inputs"), dict) else {}
        known = {f["name"] for f in t.fields if f["kind"] != "document"}
        clean = workflows._clean(t, {k: v for k, v in raw.items() if k in known})
        given = {k: v for k, v in clean.items() if k in raw}
        out.update(type="proposal" if out["type"] == "chat" else out["type"],
                   proposal={"template": t.key, "inputs": given, "title": t.title_for(clean) if t.title_for else t.title,
                             "why": " ".join(str(a.get("why", "")).split())[:240]})
        return {"ok": True, "shown_to_person_as_a_card": True, "started": False}
    return {"ok": False, "error": f"unknown tool {tc.name}"}
