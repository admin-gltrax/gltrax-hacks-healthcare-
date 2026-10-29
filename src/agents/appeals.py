"""The thinking half of PJ's crew: a strategist on Muse Wonder and a writer on
Muse Spark, each fenced in by code.

  map_criteria  Wonder lines up the plan's own coverage rules (read from the
                denial letter) against the evidence on file and says, rule by
                rule, what's met, what's partly met and what's missing.
                Code then drops any evidence it cites that doesn't exist, and a
                rule marked "met" with no real evidence is downgraded.
  draft_letter  Spark writes the appeal or dispute from those facts only.
                check_letter() must pass before the letter reaches the consent
                gate: member ID and service named, no number that isn't in the
                facts, no medical advice, a sane length. If a check fails, the
                standard template is used and the failed check is shown.

Agents never invent clinical facts; the evidence list is the only source.
"""
from __future__ import annotations

import json
import re

from ..patient.models import HealthRecord
from . import ai

MARKER_STRATEGIST = "PJ STRATEGIST"
MARKER_WRITER = "PJ WRITER"

# When there's no letter to read, the usual shape of a medical-necessity review.
DEFAULT_CRITERIA = {
    "not_medically_necessary": ["The treating doctor ordered it and explains why it's needed.",
                                "The records show the condition it treats.",
                                "It's expected to improve or keep the person's function.",
                                "Simpler or cheaper options were tried, or aren't safe."],
    "missing_info": ["The plan has the doctor's order and notes.", "The plan has the records that support the request."],
    "out_of_network": ["No in-network provider can provide it in a reasonable time or distance.",
                       "The person's needs require this provider."],
    "experimental": ["The treatment is standard care for this condition.", "The doctor explains why it fits this person."],
    "not_sure": ["The treating doctor ordered it and explains why it's needed.", "The records show the condition it treats."],
}

STRATEGY = ai.schema("criteria_map", {
    "criteria": {"type": "array", "items": {"type": "object", "properties": {
        "criterion": {"type": "string"},
        "status": {"type": "string", "enum": ["met", "partly", "missing"]},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string", "description": "One plain sentence"}},
        "required": ["criterion", "status", "evidence_ids", "explanation"]}},
    "gaps": {"type": "array", "items": {"type": "string"}, "description": "What to get before sending, plainly"},
    "argument": {"type": "string", "description": "Two or three sentences: the core of the appeal"}})

LETTER = ai.schema("letter", {"subject": {"type": "string"}, "body": {"type": "string"}})


def evidence_for(rec: HealthRecord, calls: list[dict] | None = None) -> list[dict]:
    """Everything the crew may cite, each with an id and where it came from."""
    ev = []
    for i, it in enumerate(rec.items):
        if it.bucket.value in ("clinicals", "connection", "routines"):
            # the title and date only: plain_meaning is PJ's own explainer, not evidence
            ev.append({"id": f"rec-{i + 1}", "what": it.title + (f" ({it.when})" if it.when else ""),
                       "source": {"demo": "medical records", "you": "told to PJ"}.get(it.source, it.source)})
    for r in rec.risk_factors:
        ev.append({"id": f"told-{r.key}", "what": r.label, "source": r.source})
    for j, c in enumerate(calls or []):
        if c.get("ok", True) and c.get("purpose") in ("letter", "order") and c.get("reference") not in (None, "not confirmed"):
            ev.append({"id": f"call-{j + 1}", "what": f"{c['purpose_label'].capitalize()} requested from the doctor's office "
                       f"(reference {c['reference']}): {c.get('result', '')}", "source": f"call to {c['practice']}"})
    return ev


async def map_criteria(service: str, reason: str, criteria: list[str], evidence: list[dict], account: str | None) -> dict:
    prompt = (f"[{MARKER_STRATEGIST}] You are the strategist on a patient advocacy team preparing an insurance appeal.\n"
              "For EACH coverage rule, decide if the evidence on file meets it, partly meets it, or it's missing. "
              "Cite evidence only by its id from EVIDENCE. Never assume facts that aren't listed. Be honest about gaps: "
              "a weak appeal that knows its gaps beats a confident one that's wrong. Plain language, no jargon. "
              "In explanations, gaps and the argument, describe evidence in words; never mention ids. "
              "Never give medical advice.\n\n"
              + json.dumps({"service_denied": service, "plan_reason": reason, "coverage_rules": criteria, "EVIDENCE": evidence}))
    raw = await ai.chat_json("strategist", [{"role": "user", "content": prompt}], STRATEGY, account=account, max_tokens=8000)
    return clean_map(raw, criteria, evidence)


def clean_map(raw: dict, criteria: list[str], evidence: list[dict]) -> dict:
    known = {e["id"] for e in evidence}
    rows, invented = [], 0
    for r in (raw.get("criteria") or [])[:10]:
        if not isinstance(r, dict):
            continue
        ids = [i for i in (r.get("evidence_ids") or []) if isinstance(i, str)]
        good = [i for i in ids if i in known]
        invented += len(ids) - len(good)
        status = r.get("status") if r.get("status") in ("met", "partly", "missing") else "missing"
        if status != "missing" and not good:
            status = "missing"  # a claim with no evidence behind it is a gap, not a strength
        rows.append({"criterion": " ".join(str(r.get("criterion", "")).split())[:300], "status": status, "evidence_ids": good,
                     "evidence": [e["what"] for e in evidence if e["id"] in good],
                     "explanation": " ".join(str(r.get("explanation", "")).split())[:400]})
    if not rows:
        raise ai.AIUnavailable("The strategist returned no criteria.")
    return {"criteria": rows, "gaps": [" ".join(str(g).split())[:300] for g in (raw.get("gaps") or [])][:6],
            "argument": " ".join(str(raw.get("argument", "")).split())[:800], "invented_citations_dropped": invented}


# ---------------------------------------------------------------- the writer

async def draft_letter(kind: str, facts: dict, account: str | None) -> str:
    prompt = (f"[{MARKER_WRITER}] Write a {kind} letter for a patient, from the patient (first person), to send to {facts.get('to', 'the plan')}.\n"
              "Use ONLY the FACTS below. Do not add any date, amount, ID, diagnosis, medicine or clinical detail that isn't in FACTS. "
              "Start with the salutation; the To/Re header is added separately. Plain, firm, polite; short paragraphs; under 350 words. Name the member ID and the service. Ask for a written decision. "
              "Do not include a signature block, sign-off name or date line; the patient signs separately. "
              "Argue from the evidence that IS listed: for each rule, say what supports it. Never say evidence is missing, "
              "weak or still needed; gaps go to the patient's to-do list, not to the plan. "
              "Never give medical advice.\n\nFACTS:\n" + json.dumps(facts, indent=1))
    raw = await ai.chat_json("writer", [{"role": "user", "content": prompt}], LETTER, account=account, max_tokens=4000)
    return str(raw.get("body", "")).strip()  # the To/Re header comes from code, not the model


_ADVICE = re.compile(r"\b(\d+\s?mg|milligram|dosage|take \d|stop taking|start taking|increase (?:the|your) dose)\b", re.I)
_LIST_NUMBER = re.compile(r"^[ \t]*\d{1,2}[.)][ \t]", re.M)
_SIGN = re.compile(r"^\s*(signature|signed|sincerely|respectfully|regards)\b.*$", re.I | re.M)


def check_letter(body: str, facts: dict) -> list[dict]:
    blob = json.dumps(facts).lower()
    allowed = set(re.findall(r"\d+", blob))
    claims = _LIST_NUMBER.sub("", body)  # "1." heading a list item is layout, not a fact
    numbers = [n for n in re.findall(r"\d+", claims) if n not in allowed]
    checks = [
        {"check": "Names the member ID", "ok": bool(facts.get("member_id")) and facts["member_id"].lower() in body.lower()},
        {"check": "Names what was denied or billed", "ok": any(w in body.lower() for w in _keywords(facts.get("subject_of", "")))},
        {"check": "Every number comes from the facts", "ok": not numbers, **({"detail": "not in facts: " + ", ".join(sorted(set(numbers))[:5])} if numbers else {})},
        {"check": "No medical advice or dosing", "ok": not _ADVICE.search(body)},
        {"check": "Reasonable length", "ok": 250 <= len(body) <= 4500},
    ]
    return checks


def _keywords(s: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in ("with", "from", "that", "this", "after", "visits", "weeks", "over")]
    return words[:4] or [s.lower()]


def strip_signoff(body: str) -> str:
    """The patient signs at the gate; drop any sign-off the model added."""
    m = _SIGN.search(body)
    return body[:m.start()].rstrip() if m else body.rstrip()
