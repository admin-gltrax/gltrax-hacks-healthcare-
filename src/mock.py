"""Scripted offline models so the whole system (and the dashboard) runs with no
API key: MOCK_LLM=1. Not a quality benchmark: it exists to exercise the plumbing.

MockLLM routes by call shape: tools present -> the worker; response_format -> a JSON
stub; otherwise -> the simulated receptionist (which reads FACTS_JSON from its prompt).
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from .llm import ChatResult, ToolCall

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
_SLOT_RE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2})(?:st|nd|rd|th)? at (\d{1,2}):(\d{2}) (AM|PM)")


def _slots_in(text: str) -> list[str]:
    out = []
    for mo, d, h, m, ap in _SLOT_RE.findall(text):
        hh = int(h) % 12 + (12 if ap == "PM" else 0)
        out.append(datetime(2026, _MONTHS[mo], int(d), hh, int(m)).strftime("%Y-%m-%dT%H:%M"))
    return out


class MockLLM:
    def __init__(self, role: str):
        self.role = role
        self._n = 0

    async def chat(self, messages, tools=None, response_format=None, max_tokens=None) -> ChatResult:
        if tools:
            return self._worker(messages)
        if response_format and response_format.get("json_schema", {}).get("name") == "constraints":
            text = messages[-1]["content"].lower()
            m = re.search(r"before (\d{1,2})", text)
            return ChatResult(content=json.dumps({
                "specialty": "cardiology" if "cardio" in text else "primary care",
                "earliest_time": f"{int(m.group(1)):02d}:00" if m else "08:00",
                "earliest_date": "2026-11-02", "latest_date": "2026-11-20", "max_distance_miles": 25,
            }))
        if response_format:
            return ChatResult(content=json.dumps({"politeness": 4, "efficiency": 4, "interruptions": 4, "readback": 4, "escalation": 4, "failure_tags": [], "notes": "mock"}))
        return self._office(messages)

    # ---------------- simulated receptionist ----------------
    def _office(self, messages) -> ChatResult:
        facts = json.loads(re.search(r"FACTS_JSON: (\{.*\})", messages[0]["content"]).group(1))
        convo = messages[1:]
        callers = [m["content"].lower() for m in convo if m["role"] == "user"]
        last = callers[-1]
        persona = facts["persona"]
        n = len(callers)
        spoken = [s["spoken"] for s in facts["open_slots"]]

        if persona == "ai_refuser" and re.search(r"\bai\b|assistant", last):
            return ChatResult("I'm sorry, we only speak with patients or family. Can I take a callback number? [END_CALL]")
        if persona == "skeptic":
            return ChatResult("The patient needs to call us back personally. What's their callback number? [END_CALL]")
        if persona == "transferrer" and n == 2:
            return ChatResult("Let me transfer you to scheduling. [HOLD 90]")
        gave_info = any("member" in c and "birth" in c for c in callers) or any("mbr-" in c for c in callers)
        if not gave_info and not re.search(r"accept|new patient|referral", last):
            return ChatResult("Sure. May I have the patient's name, date of birth and member ID?")
        if persona == "data_fisher" and not any("social security" in m["content"].lower() for m in convo if m["role"] == "assistant"):
            return ChatResult("To hold a slot I also need their social security number and home address.")
        if re.search(r"social security|credit card|address", last) and persona == "data_fisher":
            return ChatResult("Okay, name, date of birth and member ID will do then.")
        if re.search(r"accept", last) and re.search(r"plan|aetna|medicare|insurance", last):
            ok = any(p.lower() in last for p in facts["accepts_plans"]) or any(p.split()[0].lower() in last and p in facts["accepts_plans"] for p in facts["accepts_plans"])
            if persona == "confused_newbie":
                return ChatResult("Let me check... I think so?")
            return ChatResult("Yes, we accept that plan." if ok else "No, we don't accept that plan, sorry.")
        if re.search(r"new patient", last):
            return ChatResult("Yes, we're accepting new patients." if facts["accepting_new_patients"] else "We're not accepting new patients right now. I can add you to a waitlist.")
        if re.search(r"referral", last):
            return ChatResult("Yes, a referral from a primary care doctor is required." if facts["referral_required"] else "No referral is required.")
        if re.search(r"pencil|hold (?:that|the)|tentative", last):
            return ChatResult("I can pencil that in for 24 hours. The patient will need to confirm.")
        if re.search(r"elsewhere|another office|other office", last) and "earlier" in last:
            if facts.get("cancellation_slots"):
                return ChatResult("Actually, we just had a cancellation: " + facts["cancellation_slots"][0]["spoken"] + ".")
            return ChatResult("Sorry, nothing earlier than what I mentioned.")
        if re.search(r"opening|available|earliest|slot|appointment", last):
            if facts["referral_required"]:
                return ChatResult("I can't discuss availability without a referral.")
            if not facts["accepting_new_patients"]:
                return ChatResult("We're not accepting new patients, sorry.")
            return ChatResult("I have " + " or ".join(spoken[:2]) + "." if spoken else "Nothing open for a while, sorry.")
        if re.search(r"bye|thank", last):
            return ChatResult("You're welcome, goodbye! [END_CALL]")
        return ChatResult("Okay.")

    # ---------------- caller ----------------
    def _worker(self, messages) -> ChatResult:
        self._n += 1
        sys = messages[0]["content"]
        name = re.search(r"- name: (.+)", sys).group(1)
        dob = re.search(r"- date of birth: (.+)", sys).group(1)
        mid = re.search(r"- member ID: (.+)", sys).group(1)
        plan = re.search(r"- plan: (.+)", sys).group(1)

        def tc(n: str, **a) -> ToolCall:
            return ToolCall(id=f"c{len(messages)}_{n}", name=n, arguments=a)

        last = messages[-1]
        calls_so_far = [t for m in messages if m["role"] == "assistant" for t in (m.get("tool_calls") or [])]
        names = [t["function"]["name"] for t in calls_so_far]
        recorded = {}
        for t in calls_so_far:
            if t["function"]["name"] == "record_outcome":
                a = json.loads(t["function"]["arguments"])
                recorded[a["field"]] = a["value"]
        utts = [m["content"] for m in messages if m["role"] == "assistant" and m["content"]]
        text = last["content"] if last["role"] == "user" else ""
        low = text.lower()

        # 1) phone menu
        if last["role"] == "user" and "press" in low and "connected" in low or (last["role"] == "user" and "didn't get that" in low):
            return ChatResult(tool_calls=[tc("press_dtmf", digits=self._ivr_digit(low))])
        if last["role"] == "tool" and '"line_state": "ivr"' in last["content"]:
            heard = json.loads(last["content"]).get("heard", "")
            return ChatResult(tool_calls=[tc("press_dtmf", digits=self._ivr_digit(heard.lower()))])

        # 2) handle refusals / escalation
        if re.search(r"callback|only speak with patients|patient needs to call", low):
            if "request_human" not in names:
                return ChatResult(content="Understood, thank you for your time.", tool_calls=[tc("request_human", reason="Office will not speak with an AI assistant; patient should call back.")])
        if last["role"] == "user" and re.search(r"social security|credit card|home address", low):
            return ChatResult(content="I'm not able to share that. I can only provide the patient's name, date of birth, member ID and plan.")

        # 3) extract facts from what the office just said -> record them
        if last["role"] == "user":
            calls: list[ToolCall] = []
            def rec(f, v):
                if f not in recorded:
                    recorded[f] = v
                    calls.append(tc("record_outcome", field=f, value=v))
            if re.search(r"no, we don't accept|do not accept|don't accept", low): rec("accepts_plan", "no")
            elif re.search(r"yes, we accept", low): rec("accepts_plan", "yes")
            elif "i think so" in low: rec("accepts_plan", "unsure")
            if re.search(r"not accepting new", low): rec("new_patients", "no")
            elif re.search(r"accepting new patients", low): rec("new_patients", "yes")
            if re.search(r"referral .*required|referral from", low) and "no referral" not in low: rec("referral_required", "yes")
            elif "no referral" in low: rec("referral_required", "no")
            for s in _slots_in(text):
                if not any(t["function"]["name"] == "record_offer" and json.loads(t["function"]["arguments"])["slot_start"] == s for t in calls_so_far):
                    calls.append(tc("record_offer", slot_start=s, held=False))
                    break  # record the first only; keep it simple
            if re.search(r"pencil that in", low):
                held = [json.loads(t["function"]["arguments"]) for t in calls_so_far if t["function"]["name"] == "record_offer"]
                if held:
                    calls.append(tc("record_offer", slot_start=held[-1]["slot_start"], held=True))
            if calls:
                return ChatResult(tool_calls=calls)

        # 4) speak next line of the ladder
        deal_breaker = recorded.get("accepts_plan") == "no" or recorded.get("new_patients") == "no" or recorded.get("referral_required") == "yes"
        if deal_breaker or any(re.search(r"can't discuss availability|waitlist", m["content"].lower()) for m in messages if m["role"] == "user"):
            if "end_call" not in names:
                return ChatResult(content="Thank you, I'll let the patient know. Goodbye.", tool_calls=[tc("end_call", summary="Not a fit; recorded reason.")])
        if "pencil_done" in "".join(utts) or any("pencil" in u.lower() for u in utts) and any(re.search(r"pencil that in", m["content"].lower()) for m in messages if m["role"] == "user"):
            if "end_call" not in names:
                return ChatResult(content="Great, so that's a tentative hold; the patient will confirm. Thank you, goodbye.", tool_calls=[tc("end_call", summary="Slot penciled in; awaiting patient approval.")])
        stage = sum(1 for u in utts if "not able to share" not in u)
        ladder = [
            "Hi, I'm an AI assistant calling on behalf of a patient. Is this a good time for a quick scheduling question?",
            f"The patient is {name}, date of birth {dob}, member ID {mid}. Do you accept {plan}?",
            "Are you accepting new patients for cardiology?",
            "Is a referral required?",
            "What are your earliest openings after 9 AM?",
            "Could you pencil in the earliest one while the patient confirms?",
        ]
        if "check_blackboard" not in names and stage == 5:
            return ChatResult(tool_calls=[tc("check_blackboard")])
        if last["role"] == "tool" and "held_slots_at_other_offices" in last["content"]:
            held_elsewhere = json.loads(last["content"])["held_slots_at_other_offices"]
            if held_elsewhere:
                return ChatResult(content=f"I have an opening held elsewhere at {held_elsewhere[0]}. Do you have anything earlier?")
        return ChatResult(content=ladder[min(stage, len(ladder) - 1)])

    @staticmethod
    def _ivr_digit(low: str) -> str:
        pairs = re.findall(r"(\d)\s+(?:for|to)\s+([^,.?]+)", low)
        for key in ("new patient appointment", "new patient", "appointment", "english", "front desk"):
            for d, label in pairs:
                if key in label:
                    return d
        return pairs[0][0] if pairs else "0"
