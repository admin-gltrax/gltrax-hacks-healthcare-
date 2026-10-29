"""The caller agent on Muse Spark: phones the patient's own doctor's office and
gets one thing done (a referral, a refill, a letter, an order...).

It is the scheduling swarm's worker pattern (src/agents/worker.py) pointed at a
different job: the same immutable SAFETY_BLOCK (its SHA is asserted in tests),
tool calls for the phone keypad, and deterministic checks on everything it said.
The office end is OfficeLine (src/sim/pcp_office.py): a phone menu, hold, and
Spark receptionists who transfer it to whoever really handles the request.

Guardrails beyond the prompt:
  - It only ever receives name, date of birth, member ID and plan, plus the
    request the patient typed. It can't leak what it doesn't have.
  - The reference number it records must appear in what the office actually
    said; otherwise the result is marked unconfirmed.
  - Every human it reaches must hear "AI" in its first sentence to them.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Callable

from ..llm import ChatResult, ToolCall
from ..safety import SAFETY_BLOCK, disclosed_ai, scan_utterances
from ..sim import pcp_office

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "office_caller_v0.txt"
MARKER = "PJ OFFICE CALLER"  # lets the offline mock recognize this agent


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": properties, "required": required}}}


TOOLS = [
    _fn("press_dtmf", "Press a key on the phone menu.", {"digits": {"type": "string"}}, ["digits"]),
    _fn("record_result", "Record what the office did, exactly as they said it.", {
        "reference": {"type": "string", "description": "The reference number exactly as the office said it"},
        "handled_by": {"type": "string", "description": "Name and role of who handled it"},
        "business_days": {"type": "integer"},
        "next": {"type": "string", "description": "One plain sentence: what happens next"}},
        ["reference", "handled_by", "business_days", "next"]),
    _fn("request_human", "Hand back to the patient (e.g. the office won't talk to an AI). Ends the call.",
        {"reason": {"type": "string"}}, ["reason"]),
    _fn("end_call", "Hang up after saying goodbye.", {"summary": {"type": "string"}}, ["summary"]),
]

_REF = re.compile(r"R-\d{5}")
_SPELLED_REF = re.compile(r"\bR[\s.-]*((?:\d[\s.-]?){4}\d)\b", re.I)


def refs_said(text: str) -> list[str]:
    """Reference numbers in what the office said, however they were spelled out ("R-9-3-1-2-0" counts as R-93120)."""
    return [f"R-{re.sub(r'[^0-9]', '', m)}" for m in _SPELLED_REF.findall(text)]


def system_prompt(who: dict, purpose_label: str, details: str) -> str:
    ctx = ("PATIENT FIELDS YOU MAY SHARE (this is all you know about the patient):\n"
           f"- name: {who['name']}\n- date of birth: {who.get('dob') or 'unknown'}\n"
           f"- member ID: {who.get('member_id') or 'unknown'}\n- plan: {who.get('plan') or 'unknown'}\n\n"
           f"THE REQUEST (the patient asked you to say this): {purpose_label}" + (f": {details}" if details else "") + "\n")
    return f"{SAFETY_BLOCK}\n[{MARKER}]\n{PROMPT.read_text().strip()}\n\n{ctx}"


class OfficeCall:
    def __init__(self, practice: str, phone: str | None, purpose: str, details: str, who: dict,
                 caller_llm, office_llm, on_line: Callable[[str, str], None] | None = None, max_turns: int = 26,
                 line: pcp_office.OfficeLine | None = None):
        self.practice, self.phone, self.who, self.details = practice, phone, who, details
        self.line = line or pcp_office.OfficeLine(practice, purpose, details, who, office_llm)  # the call gym passes its own
        self.purpose = self.line.purpose
        self.llm = caller_llm
        self.on_line = on_line or (lambda s, t: None)
        self.max_turns = max_turns
        self.msgs = [{"role": "system", "content": system_prompt(who, self.line.p["label"], details)}]
        self.transcript: list[dict] = []
        self.result: dict | None = None
        self.escalated: str | None = None
        self.finished = False
        self._new_person = False
        self._first_to_each: list[str] = []

    def _log(self, speaker: str, text: str) -> None:
        if text:
            self.transcript.append({"speaker": speaker, "text": text})
            self.on_line(speaker, text)

    async def run(self) -> dict:
        hear = getattr(self.line, "hear_opening", None)  # a voice line speaks the menu and transcribes it
        opening = await hear() if hear else self.line.opening()
        self._log("office", opening)
        self.msgs.append({"role": "user", "content": f"[Call connected] {opening}"})
        silences = 0
        for _ in range(self.max_turns):
            res: ChatResult = await self.llm.chat(self.msgs, tools=TOOLS, max_tokens=1500)
            if res.tool_calls and res.content:  # tool turns are silent (see worker.py)
                res = ChatResult(content="", tool_calls=res.tool_calls)
            self.msgs.append(res.assistant_message())
            said = (res.content or "").strip()
            if said:
                if self._new_person:
                    self._first_to_each.append(said)
                    self._new_person = False
                self._log("pj", said)
            for tc in res.tool_calls:
                self.msgs.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(await self._tool(tc))})
            if self.finished or self.line.state == "ended" and not res.tool_calls:
                break
            if res.tool_calls:
                continue
            if not said:
                silences += 1
                if silences >= 3:
                    break
                self.msgs.append({"role": "user", "content": "[silence on the line]"})
                continue
            reply, hold, ended = await self.line.say(said)
            self._heard(reply, hold)
            if ended:
                self.msgs.append({"role": "user", "content": "[The office hung up. Record the result if you have it, then end_call.]"})
        return self._summary()

    def _heard(self, text: str, hold: int, as_tool: bool = False) -> str:
        """Log what the line said. Returns it for a tool result, or appends it as the office's turn."""
        if not text:
            return ""
        if "[on hold" in text:
            before, _, after = text.partition("[on hold")
            minutes, _, greet = after.partition("]")
            self._log("office", before.replace("[transferring]", "").strip())
            self._log("hold", f"On hold{minutes}. PJ keeps the place in line.")
            self._log("office", greet.strip())
            self._new_person = True
        else:
            self._log("office", text)
        content = text + (f"\n[You were on hold {hold} minutes. A person picks up.]" if hold else "")
        if not as_tool:
            self.msgs.append({"role": "user", "content": content})
        return content

    async def _tool(self, tc: ToolCall) -> dict:
        a = tc.arguments
        if tc.parse_error:
            return {"ok": False, "error": f"Could not parse arguments: {tc.parse_error}"}
        if tc.name == "press_dtmf":
            if self.line.state != "ivr":
                return {"ok": False, "error": "No phone menu is active. Speak instead."}
            self._log("pj", f"[pressed {str(a.get('digits', ''))[:1]}]")
            pressed = self.line.press(str(a.get("digits", "")))
            text, hold = (await pressed) if inspect.isawaitable(pressed) else pressed  # a voice line transcribes the menu
            return {"ok": True, "heard": self._heard(text, hold, as_tool=True), "line_state": self.line.state}
        if tc.name == "record_result":
            ref = str(a.get("reference", "")).strip().upper()
            try:
                days = max(0, min(60, int(a.get("business_days") or 0)))
            except (TypeError, ValueError):
                days = 0
            self.result = {"reference": ref, "handled_by": str(a.get("handled_by", ""))[:80], "days": days,
                           "next": str(a.get("next", ""))[:300]}
            return {"ok": True}
        if tc.name == "request_human":
            self.escalated = str(a.get("reason", ""))[:300]
            self.finished = True
            return {"ok": True}
        if tc.name == "end_call":
            self.finished = True
            return {"ok": True}
        return {"ok": False, "error": f"unknown tool {tc.name}"}

    def _summary(self) -> dict:
        office_said = " ".join(t["text"] for t in self.transcript if t["speaker"] == "office")
        pj_said = [t["text"] for t in self.transcript if t["speaker"] == "pj" and not t["text"].startswith("[")]
        r = self.result or {}
        heard_refs = refs_said(office_said)
        ref = r.get("reference") if r.get("reference") in heard_refs else None
        checks = scan_utterances(pj_said, leverage_available=False)
        checks["disclosed_ai_to_each_person"] = bool(self._first_to_each) and all(disclosed_ai(u) for u in self._first_to_each)
        checks["reference_heard_on_call"] = ref is not None
        reached = self.line.reached[-1] if self.line.reached else None
        done = bool(ref) and not self.escalated
        p = self.line.p
        return {
            "practice": self.practice, "phone": self.phone, "purpose": self.purpose, "purpose_label": p["label"],
            "menu_path": ", then transferred to ".join(self.line.menu_path + [x.split(", ", 1)[1] for x in self.line.reached[1:]]) or "no menu",
            "hold_minutes": self.line.hold_minutes, "reached": reached,
            "reference": ref or "not confirmed",
            "result": (r.get("next") or p["done"]) if done else (f"Handed back to you: {self.escalated}" if self.escalated else
                                                                 "PJ couldn't confirm it on this call and will call back."),
            "days": r.get("days") or p["days"], "transcript": self.transcript, "ok": done,
            "checks": checks, "shared": _shared(self.who, pj_said),
        }


def _shared(who: dict, said: list[str]) -> list[str]:
    """Which of the four allowed fields PJ actually said (dates count however they were spoken)."""
    text = " ".join(said).lower()
    out = []
    for k in ("name", "dob", "member_id", "plan"):
        v = str(who.get(k) or "").lower()
        if not v:
            continue
        hit = v in text
        if k == "dob" and not hit and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            from datetime import date
            d = date.fromisoformat(v)
            hit = d.strftime("%B").lower() in text and str(d.year) in text
        if hit:
            out.append(k)
    return out
