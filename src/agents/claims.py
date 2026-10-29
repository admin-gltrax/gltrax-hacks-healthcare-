"""The claim checker: every factual claim in a letter must be backed by the facts.

check_letter() catches invented numbers, IDs and dosing. It can't see an
invented *claim*: the judges caught the writer asserting "leaving home takes a
considerable and taxing effort" when nothing on file said so. This closes that gap.

A verifier model from a different family than the writer (Qwen3.6-35B-A3B on a
Modal dedicated endpoint; VERIFIER_PROVIDER to switch) lists every factual claim
the letter makes and, for each, the words in FACTS that back it. It's a guard,
not patient-facing. Code then checks the checker:

  - a claim must really be in the letter (word for word, or nearly); claims the
    verifier made up are dropped and counted;
  - "supported" needs a quote that really is in FACTS; a claim whose quote isn't
    there is unsupported, whatever the verifier said;
  - a long letter with no claims at all means the verifier didn't do the job, so
    the letter counts as not checked rather than passed.

Any unsupported claim keeps the letter from the signature: the writer gets one
repair try, then PJ uses the standard letter (workflows._write).
"""
from __future__ import annotations

import json
import re

from . import ai

MARKER = "PJ CLAIMS"

CLAIMS = ai.schema("claims", {"claims": {"type": "array", "items": {"type": "object", "properties": {
    "claim": {"type": "string", "description": "The claim, copied word for word from the letter"},
    "status": {"type": "string", "enum": ["supported", "unsupported"]},
    "fact": {"type": "string", "description": "The exact words in FACTS that back it; empty if none"}},
    "required": ["claim", "status", "fact"]}}})


def _norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 3}


def _in_letter(claim: str, letter: str) -> bool:
    c, text = _norm(claim), _norm(letter)
    if c and c in text:
        return True
    words = _words(claim)
    return bool(words) and len(words & _words(letter)) / len(words) >= 0.85


def _in_facts(quote: str, facts_blob: str) -> bool:
    q = _norm(quote)
    if not q:
        return False
    if q in _norm(facts_blob):
        return True
    words = _words(quote)
    return bool(words) and words <= _words(facts_blob)


def prompt(body: str, facts: dict) -> str:
    return (f"[{MARKER}] You check an insurance appeal letter for claims that aren't backed by the record. Everything is fictional.\n"
            "List EVERY factual claim the letter makes about the patient, their condition, abilities, care, history, the doctor, "
            "dates, documents or what the evidence shows. Copy each claim word for word from the letter. Skip requests, "
            "legal arguments, politeness and the patient's own wishes.\n"
            "For each claim, find the words in FACTS that back it and copy them exactly into `fact`. If nothing in FACTS says it, "
            "status is unsupported and `fact` is empty. Being on a list of the plan's coverage rules is NOT evidence that the "
            "rule is met. A doctor's letter that was only requested is not a letter that was written.\n\n"
            f"FACTS:\n{json.dumps(facts, indent=1)}\n\nLETTER:\n{body}")


def clean(raw: dict, body: str, facts: dict) -> dict:
    blob = json.dumps(facts)
    out, invented, overruled = [], 0, 0
    for c in (raw.get("claims") or [])[:40]:
        if not isinstance(c, dict):
            continue
        claim = " ".join(str(c.get("claim", "")).split())[:400]
        if not claim or not _in_letter(claim, body):
            invented += 1
            continue
        fact = " ".join(str(c.get("fact", "")).split())[:400]
        supported = c.get("status") == "supported" and _in_facts(fact, blob)
        if c.get("status") == "supported" and not supported:
            overruled += 1  # "supported" without real backing in FACTS
        out.append({"claim": claim, "supported": supported, "fact": fact if supported else ""})
    return {"claims": out, "unsupported": [c["claim"] for c in out if not c["supported"]],
            "invented_claims_dropped": invented, "support_overruled": overruled}


async def check(body: str, facts: dict, account: str | None = None) -> dict:
    """Raises ai.AIUnavailable if the verifier can't run or didn't really check."""
    raw = await ai.chat_json("verifier", [{"role": "user", "content": prompt(body, facts)}], CLAIMS, account=account, max_tokens=8000)
    res = clean(raw, body, facts)
    if not res["claims"] and len(body) > 400:
        raise ai.AIUnavailable("the claim checker found no claims in a full letter, so it didn't really check")
    return res


def as_check(res: dict) -> dict:
    """One line for the workflow's guardrails panel."""
    bad = res["unsupported"]
    detail = (f"not backed by the facts: \"{bad[0][:120]}\"" + (f" and {len(bad) - 1} more" if len(bad) > 1 else "")) if bad else \
        f"{len(res['claims'])} claims, each backed by the facts"
    return {"check": "Every claim is backed by the facts", "ok": not bad, "detail": detail}
