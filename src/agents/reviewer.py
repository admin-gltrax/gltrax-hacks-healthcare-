"""The adversary: an insurer-side medical reviewer that tries to deny PJ's appeal
before the real insurer can.

It runs on Muse Spark Open (open weights) on partner credits: Baseten by
default, or Fireworks (REVIEWER_PROVIDER). It never faces the patient and never
writes a word of the letter. The loop:

  1. The reviewer scores the draft against the plan's OWN rules (the denial
     letter's criteria, read by reader.py, or the strategist's map) and lists
     every specific reason it would still deny.
  2. The writer (Muse Spark, on Meta) revises the letter to answer the
     objections it can answer from the facts on file.
  3. Up to 3 rounds. It stops when the reviewer can't find a reason to deny,
     or when every remaining reason needs evidence that isn't on file: then PJ
     turns them into plain to-dos for the family. Rewording can't create evidence.

Code guards (the model is checked, never trusted):
  - an objection must cite a rule that exists (R1..Rn); invented rules are dropped
    and counted, and a "deny" with no real reason left counts as a pass;
  - the reviewer's output has no letter field, and anything letter-like it
    returns is ignored: only short reasons reach the writer, never text to paste;
  - every revision must pass appeals.check_letter against the ORIGINAL facts
    (numbers in an objection don't become allowed), or the previous letter stays.
"""
from __future__ import annotations

import json
import re
from typing import Callable

from . import ai, appeals

MARKER = "PJ REVIEWER"
MAX_ROUNDS = 3

REVIEW = ai.schema("plan_review", {
    "verdict": {"type": "string", "enum": ["approve", "deny"]},
    "objections": {"type": "array", "items": {"type": "object", "properties": {
        "rule_id": {"type": "string", "description": "The id of the plan rule, e.g. R2"},
        "reason": {"type": "string", "description": "One specific sentence: why this rule isn't met by the appeal"},
        "fix": {"type": "string", "enum": ["letter", "evidence"],
                "description": "letter = the evidence on file answers it but the letter doesn't say so; evidence = the evidence isn't on file"},
        "needs": {"type": "string", "description": "Plainly, what would answer it (a document, or a point to make)"}},
        "required": ["rule_id", "reason", "fix", "needs"]}}})

_LETTERISH = ("letter", "body", "revised_letter", "draft", "rewrite", "text")


def numbered(rules: list[str]) -> list[dict]:
    return [{"id": f"R{i + 1}", "rule": r} for i, r in enumerate(rules)]


def _prompt(service: str, plan_reason: str, rules: list[str], evidence: list[str], body: str, round_no: int) -> str:
    return (f"[{MARKER}] You are a utilization-management medical reviewer at a health plan, reviewing a member's appeal "
            "of a denied service. This is a software simulation: every person, plan and number is fictional.\n"
            "Your job is adversarial: find every LEGITIMATE reason to uphold the denial, judged only against the plan's own "
            "coverage rules below. Cite each rule by its id (R1, R2...). Never invent a rule or a requirement that isn't listed.\n"
            "Judge the appeal letter itself: a rule is met only if the letter makes the case for it and names the supporting "
            "evidence. A vague line like \"see the enclosed records\" or \"the criteria are answered in the table\" does not meet a rule.\n"
            "For each rule the appeal doesn't satisfy, give one specific reason. Set fix=\"letter\" when the evidence on file "
            "would answer it but the letter doesn't make the case, or fix=\"evidence\" when the evidence on file doesn't support "
            "it; in `needs`, say plainly what document or point would answer it.\n"
            "Do not object to tone, length or formatting. Do not write, rewrite or suggest letter wording: reasons only.\n"
            "If no listed rule gives a legitimate reason to deny, set verdict=\"approve\" with no objections.\n\n"
            + json.dumps({"review_round": round_no, "service_denied": service, "plan_reason": plan_reason,
                          "coverage_rules": numbered(rules), "evidence_on_file": evidence, "appeal_letter": body}, indent=1))


def clean_review(raw: dict, rules: list[str]) -> dict:
    """Keep only objections that cite a real rule; the reviewer's words stay short reasons."""
    known = {f"R{i + 1}" for i in range(len(rules))}
    seen, objections, invented = set(), [], 0
    for o in (raw.get("objections") or [])[:12]:
        if not isinstance(o, dict):
            continue
        rid = str(o.get("rule_id", "")).strip().upper()
        m = re.fullmatch(r"R?(\d{1,2})", rid)
        rid = f"R{m.group(1)}" if m else rid
        if rid not in known:
            invented += 1
            continue
        if rid in seen:
            continue
        seen.add(rid)
        reason = " ".join(str(o.get("reason", "")).split())[:300]
        if not reason:
            invented += 1
            continue
        objections.append({"rule_id": rid, "rule": rules[int(rid[1:]) - 1], "reason": reason,
                           "fix": o.get("fix") if o.get("fix") in ("letter", "evidence") else "evidence",
                           "needs": " ".join(str(o.get("needs", "")).split())[:300]})
    return {"verdict": "deny" if objections else "approve", "objections": objections,
            "invented_rules_dropped": invented,
            "letter_text_ignored": any(k in raw for k in _LETTERISH)}


async def review(service: str, plan_reason: str, rules: list[str], evidence: list[str], body: str, round_no: int,
                 account: str | None) -> dict:
    raw = await ai.chat_json("reviewer", [{"role": "user", "content": _prompt(service, plan_reason, rules, evidence, body, round_no)}],
                             REVIEW, account=account, max_tokens=8000)
    return clean_review(raw, rules)


async def revise(kind: str, facts: dict, body: str, objections: list[dict], account: str | None) -> str:
    """The writer (Muse Spark on Meta) answers the objections it can, from the facts only."""
    asks = [{"rule": o["rule"], "objection": o["reason"]} for o in objections if o["fix"] == "letter"]
    prompt = (f"[{appeals.MARKER_WRITER}] Revise this {kind} letter, written from the patient (first person) to {facts.get('to', 'the plan')}.\n"
              "The plan's reviewer raised the objections below. Answer each one by pointing to the evidence in FACTS that meets "
              "that rule, rule by rule. Use ONLY the FACTS: do not add any date, amount, ID, diagnosis, medicine or clinical "
              "detail that isn't in FACTS, even if an objection mentions it. Keep everything that already works. "
              "Start with the salutation; no signature block, sign-off name or date line. Plain, firm, polite; under 400 words. "
              "Name the member ID and the service. Ask for a written decision. Never give medical advice. Never say evidence "
              "is missing or weak.\n\n"
              f"CURRENT LETTER:\n{body}\n\nREVIEWER OBJECTIONS TO ANSWER:\n{json.dumps(asks, indent=1)}\n\n"
              "FACTS:\n" + json.dumps(facts, indent=1))
    raw = await ai.chat_json("writer", [{"role": "user", "content": prompt}], appeals.LETTER, account=account, max_tokens=5000)
    return str(raw.get("body", "")).strip()


async def stress_test(kind: str, facts: dict, body: str, rules: list[str], evidence: list[str], account: str | None,
                      on_round: Callable[[dict], None] | None = None, max_rounds: int = MAX_ROUNDS) -> dict:
    """Review, revise, repeat. Raises ai.AIUnavailable only if the first review can't run."""
    service, reason = str(facts.get("service") or ""), str(facts.get("plan_reason") or "")
    rounds: list[dict] = []
    current, note = body, ""
    for n in range(1, max_rounds + 1):
        try:
            r = await review(service, reason, rules, evidence, current, n, account)
        except ai.AIUnavailable as e:
            if n == 1:
                raise
            note = f"The reviewer dropped out in round {n} ({e}); PJ kept the last checked letter."
            break
        entry = {"round": n, **r}
        rounds.append(entry)
        if on_round:
            on_round(entry)
        if r["verdict"] == "approve":
            break
        if not any(o["fix"] == "letter" for o in r["objections"]):
            note = "Every reason left needs evidence that isn't on file yet; rewording can't fix that."
            break
        if n == max_rounds:
            break
        try:
            new = appeals.strip_signoff(await revise(kind, facts, current, r["objections"], account))
        except ai.AIUnavailable as e:
            note = f"The writer couldn't revise ({e}); PJ kept the last checked letter."
            break
        checks = appeals.check_letter(new, facts)  # the original facts: an objection's numbers aren't facts
        ok = all(c["ok"] for c in checks)
        entry["revision"] = {"body": new, "checks": checks, "accepted": ok}
        if not ok:
            note = "A revision failed the letter checks, so PJ kept the previous letter."
            break
        current = new
    last = rounds[-1] if rounds else {"verdict": "deny", "objections": []}
    passed = last["verdict"] == "approve"
    todos = [] if passed else [_todo(o) for o in last["objections"]]
    return {"rounds": rounds, "passed": passed, "body": current, "revised": current != body, "todos": todos, "note": note,
            "invented_rules_dropped": sum(x["invented_rules_dropped"] for x in rounds),
            "letter_text_ignored": any(x["letter_text_ignored"] for x in rounds)}


def _todo(o: dict) -> str:
    what = o["needs"] or o["reason"]
    return f"{what.rstrip('.')} (for the plan's rule: \"{o['rule'].rstrip('.')}\")."
