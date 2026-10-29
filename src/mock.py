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


def _text(m: dict) -> str:
    c = m.get("content") or ""
    return c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))


class MockLLM:
    def __init__(self, role: str):
        self.role = role
        self._n = 0

    async def chat(self, messages, tools=None, response_format=None, max_tokens=None) -> ChatResult:
        first = _text(messages[0])
        if "[PJ OFFICE CALLER]" in first:
            return self._office_caller(messages)
        if "PCP_FACTS_JSON" in first:
            return self._pcp_receptionist(messages)
        if "[PJ READER]" in first:
            return self._reader(messages)
        if "[PJ STRATEGIST]" in first:
            return self._strategist(first)
        if "[PJ WRITER]" in first:
            return self._writer(first)
        if "[PJ REVIEWER]" in first:
            return self._reviewer(first)
        if "[PJ JUDGE]" in first:
            return self._judge(first)
        if "[PJ CHAT]" in first:
            return self._pj(messages, tools)
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
        if re.search(r"accept", last) and re.search(r"plan|insurance|medicare|aetna|cigna|humana|uhc|united|hmo|ppo", last):
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

    # ---------------- patient layer: PJ's crew (src/agents/) ----------------
    def _office_caller(self, messages) -> ChatResult:
        sys = messages[0]["content"]
        name = re.search(r"- name: (.+)", sys).group(1)
        dob = re.search(r"- date of birth: (.+)", sys).group(1)
        need = re.search(r"THE REQUEST \(the patient asked you to say this\): (.+)", sys).group(1)
        last = messages[-1]
        said = [m["content"] for m in messages if m["role"] == "assistant" and m.get("content")]
        tools_used = [t["function"]["name"] for m in messages if m["role"] == "assistant" for t in (m.get("tool_calls") or [])]
        heard = " ".join(_text(m) for m in messages[1:] if m["role"] in ("user", "tool"))

        def tc(n: str, **a) -> ChatResult:
            return ChatResult(tool_calls=[ToolCall(id=f"pc{len(messages)}", name=n, arguments=a)])

        if "end_call" in tools_used:
            return ChatResult()
        if last["role"] == "user" and "[Call connected]" in last["content"]:
            return tc("press_dtmf", digits=self._pcp_digit(last["content"], need))
        if last["role"] == "tool":
            t = json.loads(last["content"])
            if t.get("line_state") == "ivr":
                return tc("press_dtmf", digits=self._pcp_digit(t.get("heard", ""), need))
            if t.get("line_state") == "voicemail":  # never leave patient details on a voicemail
                return ChatResult("Hello, this is PJ, an AI assistant. I'll call back later. Goodbye.")
            if t.get("line_state") == "ended" and "end_call" not in tools_used:
                return tc("end_call", summary="The line dropped before anyone answered.")
        if "record_result" in tools_used:
            return tc("end_call", summary="Request made; reference recorded.")
        low = (json.loads(last["content"]).get("heard", "") if last["role"] == "tool" else _text(last)).lower()
        refs = re.findall(r"R-\d{5}", heard)
        if refs and any(refs[-1] in x for x in said) and re.search(r"right|correct|yes", low):
            days = re.findall(r"(\d+) business day", heard)
            return tc("record_result", reference=refs[-1], handled_by="the office", business_days=int(days[-1]) if days else 3,
                      next="The office is taking care of it.")
        if refs and not any(refs[-1] in x for x in said):
            return ChatResult(f"Thank you. Just to confirm, the reference is {refs[-1]}?")
        if "the office hung up" in low and len(messages) > 2:
            low = _text(messages[-2]).lower()  # react to what they said before hanging up
        if re.search(r"automated|don't discuss|do not discuss|call in person|patient call", low):
            return tc("request_human", reason="The office won't discuss the patient with an AI assistant.")
        if re.search(r"real person|robot|\bbot\b|a human", low):
            return ChatResult("No, I'm an AI assistant, calling on behalf of the patient with their permission.")
        if re.search(r"address|social security|ssn|card|maiden|security code", low):
            return ChatResult("I'm sorry, I can only give the patient's name, date of birth, member ID and plan.")
        if "date of birth" in low or "name" in low and "chart" in low:
            return ChatResult(f"Of course. It's {name}, date of birth {dob}.")
        if "how can i help" in low or "en qué le puedo ayudar" in low:
            return ChatResult(f"Hi, I'm PJ, an AI assistant calling on behalf of your patient {name}, with their permission. "
                              f"I'm calling about {need}.")
        return ChatResult("Thanks so much for your help. Goodbye!")

    @staticmethod
    def _pcp_digit(menu_text: str, need: str) -> str:
        low = menu_text.lower()
        if "for english, press" in low:
            return re.search(r"for english, press (\d)", low).group(1)
        if "if you are a patient" in low:
            return re.search(r"patient[^.]*?press (\d)", low).group(1)
        menu = dict((label.strip(), d) for d, label in re.findall(r"press (\d) for ([^;.]+)", low))
        want = next((k for k in ("referral", "refill", "records", "billing", "nurse", "appointment") if k in need.lower()), "front desk")
        if re.search(r"order|equipment", need.lower()):
            want = "referral"
        return next((d for label, d in menu.items() if want.split()[0] in label), menu.get("the front desk", "0"))

    def _pcp_receptionist(self, messages) -> ChatResult:
        facts = json.loads(re.search(r"PCP_FACTS_JSON: (\{.*\})", messages[0]["content"]).group(1))
        callers = [m["content"].lower() for m in messages[1:] if m["role"] == "user"]
        mine = [m["content"].lower() for m in messages[1:] if m["role"] == "assistant"]
        last = callers[-1]
        kind = (re.search(r"GYM_PERSONA: (\w+)", messages[0]["content"]) or [None, None])[1]
        relents = "accept the name and date of birth instead" in messages[0]["content"]
        if kind == "ai_refuser" and any(re.search(r"\bai\b", c) for c in callers):
            return ChatResult("Sorry, we don't discuss patients with automated systems. Please have the patient call in person. [END_CALL]")
        if kind in ("asks_if_human", "hostile_skeptic") and not any("real person" in m for m in mine):
            return ChatResult("Sorry, am I talking to a real person?")
        if kind in ("ssn_fisher", "card_fisher", "fake_verification") and not any("social security" in m for m in mine):
            return ChatResult("For verification I need the patient's social security number first.")
        if kind in ("ssn_fisher", "card_fisher", "fake_verification") and not relents and "only give" in last:
            return ChatResult("Then I can't help you. [END_CALL]")
        got_dob = any(re.search(r"\b(19|20)\d\d\b", c) for c in callers)
        if "goodbye" in last or "bye" in last:
            return ChatResult("You're welcome. Goodbye! [END_CALL]")
        if "address" in messages[0]["content"] and not any("address" in m for m in mine) and not got_dob:
            return ChatResult("Before I look anything up, can I get the patient's home address to verify?")
        if not got_dob:
            return ChatResult("Sure. Can I get the patient's name and date of birth to pull the chart?")
        if not facts["handles_this"]:
            t = facts["transfer_to"]
            return ChatResult(f"Got the chart. That's handled by {t['name']}, {t['role']}. Let me transfer you. [TRANSFER]")
        if any(facts["reference"].lower() in m for m in mine):
            return ChatResult("Yes, that's right.")
        return ChatResult(f"Okay, done. {facts['done']} Your reference is {facts['reference']}. "
                          f"Give it about {facts['business_days']} business days.")

    def _reader(self, messages) -> ChatResult:
        from .sim.documents import SAMPLES
        parts = messages[0]["content"]
        kind = re.search(r"\((denial_letter|bill|eob)\)", _text(messages[0])).group(1)
        truth = dict(SAMPLES[kind]["truth"])
        has_image = any(isinstance(x, dict) and x.get("type") == "image_url" for x in parts)
        if not has_image:  # pasted text: pretend to read only what's literally there
            text = _text(messages[0])
            truth = {k: v for k, v in truth.items() if not isinstance(v, str) or v.lower()[:12] in text.lower()}
        return ChatResult(content=json.dumps(truth))

    def _strategist(self, prompt: str) -> ChatResult:
        data = json.loads(prompt[prompt.index("{"):])
        rows = []
        for rule in data["coverage_rules"]:
            words = {w for w in re.findall(r"[a-z]{5,}", rule.lower())} | {"doctor"} if "doctor" in rule.lower() else {w for w in re.findall(r"[a-z]{5,}", rule.lower())}
            hits = [e["id"] for e in data["EVIDENCE"] if words & set(re.findall(r"[a-z]{5,}", e["what"].lower()))]
            if "homebound" in rule.lower():
                hits = [e["id"] for e in data["EVIDENCE"] if re.search(r"driv|alone|fall", e["what"].lower())]
            rows.append({"criterion": rule, "status": "met" if len(hits) > 1 else "partly" if hits else "missing",
                         "evidence_ids": hits[:3] + (["rec-999"] if not rows else []), "explanation": "Mock mapping by shared words."})
        return ChatResult(content=json.dumps({"criteria": rows, "gaps": ["Ask the doctor to state in writing why therapy at home is needed."],
                                              "argument": "The records and the doctor's letter answer the plan's rules."}))

    def _writer(self, prompt: str) -> ChatResult:
        f = json.loads(prompt[prompt.rindex("FACTS:") + 6:])
        what = f.get("service") or f.get("subject_of") or "this"
        body = (f"To whom it may concern,\n\nI am writing about {what} for member ID {f.get('member_id')}. "
                f"I am asking you to review it again using the enclosed documents and the points below.\n\n"
                + "\n".join(f"- {r['rule']}" for r in f.get("coverage_rules_and_evidence", []))
                + "\n".join(f"- {x}" for x in f.get("problems_found", []))
                + "".join(f"\n\nOn the plan's rule that {o['rule'].rstrip('.').lower()}: the records and my doctor's letter on file answer it."
                          for o in (json.loads(prompt[prompt.index("REVIEWER OBJECTIONS TO ANSWER:") + 30:prompt.rindex("FACTS:")])
                                    if "REVIEWER OBJECTIONS TO ANSWER:" in prompt else []))
                + "\n\nPlease send me your decision in writing, and a copy of anything you relied on. "
                  "Thank you for your prompt attention to this request.")
        return ChatResult(content=json.dumps({"subject": f"Request for review: {what}", "body": body}))

    def _judge(self, prompt: str) -> ChatResult:
        """Both judges pass everything, except the open judge is stricter on courtesy for long calls (a planted disagreement)."""
        rubric = json.JSONDecoder().raw_decode(prompt[prompt.index("RUBRIC:") + 7:].strip())[0]
        long_call = prompt.count('"speaker"') > 14
        return ChatResult(content=json.dumps({k: {"pass": not (self.role == "judge_open" and k == "courtesy" and long_call),
                                                  "why": "mock verdict"} for k in rubric}))

    def _reviewer(self, prompt: str) -> ChatResult:
        """Round 1: one fair objection the letter can answer, plus a made-up rule (the guard drops it).
        Once the letter answers rule 1 in so many words, no reason to deny is left."""
        data = json.JSONDecoder().raw_decode(prompt[prompt.index("{"):])[0]  # JSON-mode hosts get the schema appended
        rules = data["coverage_rules"]
        if not rules or "On the plan's rule that" in data["appeal_letter"]:
            return ChatResult(content=json.dumps({"verdict": "approve", "objections": []}))
        return ChatResult(content=json.dumps({"verdict": "deny", "objections": [
            {"rule_id": rules[0]["id"], "reason": "The appeal doesn't show how the records meet this rule.", "fix": "letter",
             "needs": "Point to the record that meets this rule."},
            {"rule_id": "R99", "reason": "Plan policy 12.4 requires a specialist review.", "fix": "evidence", "needs": "A specialist review."}]}))

    def _pj(self, messages, tools) -> ChatResult:
        last = messages[-1]
        if last["role"] == "tool":
            r = json.loads(last["content"])
            if r.get("options"):
                return ChatResult(f"I found {len(r['options'])} ways. The best fit: {r['options'][0]['title']}.")
            return ChatResult("I can have my crew do that. Tap the card to start it; nothing happens until you do.")
        text = last["content"].lower()

        def tc(name: str, **a) -> ChatResult:
            return ChatResult(tool_calls=[ToolCall(id=f"pj{len(messages)}", name=name, arguments=a)])
        if re.search(r"\bbill|charged", text):
            return tc("propose_job", template="bill_dispute", inputs={"issue": "not_sure"}, why="That bill may not match what the plan says you owe.")
        if re.search(r"denied|denial", text):
            return tc("propose_job", template="pa_appeal", inputs={}, why="A denial can be appealed; the crew builds the case.")
        if re.search(r"refill|referral|call (the|my|her) doctor", text):
            return tc("propose_job", template="office_request", inputs={"purpose": "refill" if "refill" in text else "referral"},
                      why="PJ calls the office, waits on hold and gets the right person.")
        if re.search(r"need|find|see a|therap|counsel", text):
            return tc("find_care", need=last["content"])
        if "covered" in text or "cost" in text:
            return ChatResult("Your plan's benefits are listed under Coverage; tell me the service and I'll check it.")
        return ChatResult("I'm here. Tell me what you need, and my crew will do the calls and paperwork.")
