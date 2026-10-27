"""The call worker: one tool-calling agent per phone call.

There is deliberately NO tool that confirms or books an appointment. The agent can
only record facts, record/hold offers, navigate an IVR, read the blackboard, hand
off to a human, and end the call. Final confirmation belongs to the patient.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from ..config import hold_scale
from ..llm import LLM, ChatResult, ToolCall
from ..safety import disclosed_ai, fields_shared, system_prompt
from ..schemas import CallOutcome, CallResult, Constraints, Offer, OfficeScenario, PatientProfile
from ..sim.office import Office
from ..swarm.blackboard import Blackboard
from ..swarm.events import EventBus

DEFAULT_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "worker_v0.txt"

FACT_FIELDS = ["accepts_plan", "new_patients", "referral_required", "reached_human", "refused_ai"]


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


TOOLS = [
    _fn(
        "record_outcome",
        "Record a fact learned on the call, as soon as you learn it.",
        {
            "field": {"type": "string", "enum": FACT_FIELDS},
            "value": {"type": "string", "enum": ["yes", "no", "unsure"]},
        },
        ["field", "value"],
    ),
    _fn(
        "record_offer",
        "Record an appointment slot the office offered. Set held=true only after they agree to pencil it in. You cannot finalize a booking.",
        {
            "slot_start": {"type": "string", "description": "ISO 8601 local time, e.g. 2026-11-03T08:30"},
            "held": {"type": "boolean"},
        },
        ["slot_start", "held"],
    ),
    _fn("check_blackboard", "See which appointment times are currently held at OTHER offices (times only). Use before negotiating.", {}, []),
    _fn("press_dtmf", "Press phone keys on an automated menu, e.g. '1' or '21'.", {"digits": {"type": "string"}}, ["digits"]),
    _fn("request_human", "Hand off to the patient/a human, e.g. if the office will not speak to an AI. Ends the call.", {"reason": {"type": "string"}}, ["reason"]),
    _fn("end_call", "End the call after reading back key details.", {"summary": {"type": "string"}}, ["summary"]),
]


class CallRunner:
    def __init__(
        self,
        scenario: OfficeScenario,
        patient: PatientProfile,
        constraints: Constraints,
        worker_llm: LLM,
        office_llm: LLM,
        board: Blackboard,
        bus: EventBus | None = None,
        prompt_text: str | None = None,
        max_turns: int = 24,
        scale: float | None = None,
    ):
        self.sc, self.patient, self.c = scenario, patient, constraints
        self.worker, self.board = worker_llm, board
        self.bus = bus or EventBus()
        self.office = Office(scenario, office_llm)
        self.max_turns = max_turns
        self.scale = hold_scale() if scale is None else scale
        tunable = prompt_text if prompt_text is not None else DEFAULT_PROMPT.read_text()
        self.msgs: list[dict] = [{"role": "system", "content": system_prompt(tunable, patient, constraints)}]
        self.outcome = CallOutcome(office_id=scenario.office_id)
        self.transcript: list[dict] = []
        self.tool_log: list[dict] = []
        self.finished = False
        self.hungup = False
        self.blackboard_nonempty = False
        self._first_human_utt: str | None = None
        self.error: str | None = None

    # ---- events ----
    def emit(self, type: str, **data) -> None:
        self.bus.publish(type, office_id=self.sc.office_id, **data)

    def status(self, s: str) -> None:
        self.emit("status", status=s)

    def _log(self, speaker: str, text: str) -> None:
        if not text:
            return
        self.transcript.append({"speaker": speaker, "text": text})
        self.emit("utterance", speaker=speaker, text=text)

    def _say(self, text: str) -> None:
        if self.office.state == "human" and self._first_human_utt is None:
            self._first_human_utt = text
        self._log("agent", text)

    async def _hold(self, seconds: int) -> None:
        self.status("hold")
        self.emit("hold", seconds=seconds)
        if self.scale > 0:
            await asyncio.sleep(seconds * self.scale)
        self.status("talking" if self.office.state == "human" else "ivr")

    # ---- main ----
    async def run(self) -> CallResult:
        t0 = time.monotonic()
        try:
            await self._run()
        except Exception as e:  # one bad call must never take down the swarm
            self.error = f"{type(e).__name__}: {e}"
            self.outcome.ended_by = "error"
            self.status("error")
        o = self.outcome
        o.reached_human = self.office.reached_human
        o.disclosed_ai = disclosed_ai(self._first_human_utt)
        o.fields_shared = fields_shared([t["text"] for t in self.transcript if t["speaker"] == "agent"], self.patient)
        o.turns = sum(1 for t in self.transcript if t["speaker"] == "agent")
        return CallResult(
            office_id=self.sc.office_id,
            outcome=o,
            transcript=self.transcript,
            tool_log=self.tool_log,
            duration_s=round(time.monotonic() - t0, 2),
            error=self.error,
        )

    async def _run(self) -> None:
        self.emit("call_started", name=self.sc.practice_name)
        self.status("dialing")
        opening = self.office.opening()
        self.status("ivr" if self.office.state == "ivr" else "talking")
        self._log("office", opening)
        self.msgs.append({"role": "user", "content": f"[Call connected] {opening}"})

        silences = 0
        for _ in range(self.max_turns):
            res: ChatResult = await self.worker.chat(self.msgs, tools=TOOLS)
            if res.tool_calls and res.content:
                # Tool turns are silent. Models narrate them ("I'll record that"), which
                # would be spoken to the office; drop the text from the call and the history.
                res = ChatResult(content="", tool_calls=res.tool_calls)
            self.msgs.append(res.assistant_message())
            said = (res.content or "").strip()

            if self.hungup:  # after a hangup the agent may only record facts
                for tc in res.tool_calls:
                    self.msgs.append(self._tool_msg(tc, await self._exec(tc)))
                if not res.tool_calls or self.finished:
                    break
                continue

            if said:
                self._say(said)

            if res.tool_calls:
                for tc in res.tool_calls:
                    self.msgs.append(self._tool_msg(tc, await self._exec(tc)))
                if self.finished:
                    return
                if said:
                    await self._hear(said)
                continue

            if not said:
                silences += 1
                if silences >= 3:
                    self.outcome.ended_by = "max_turns"
                    return
                self.msgs.append({"role": "user", "content": "[silence on the line]"})
                continue

            await self._hear(said)
        if not self.finished and self.outcome.ended_by == "unknown":
            self.outcome.ended_by = "max_turns"

    async def _hear(self, said: str) -> None:
        """Deliver the agent's words to the office and append what comes back."""
        if self.office.state == "ivr":
            text, hold, ended = self.office.repeat_menu(), 0, False
        else:
            r = await self.office.reply(said)
            text, hold, ended = r.text, r.hold_s, r.ended
        self._log("office", text)
        content = text
        if hold:
            await self._hold(hold)
            content += f"\n[You were on hold for {hold} seconds. Someone picks up.]"
        if ended:
            self.hungup = True
            self.outcome.ended_by = "office_hangup"
            self.status("done")
            content += "\n[The other party hung up. You may still record facts with tools.]"
        self.msgs.append({"role": "user", "content": content})

    @staticmethod
    def _tool_msg(tc: ToolCall, result: dict) -> dict:
        return {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)}

    # ---- tools ----
    async def _exec(self, tc: ToolCall) -> dict:
        args = tc.arguments
        if tc.parse_error:
            result: dict = {"ok": False, "error": f"Could not parse arguments: {tc.parse_error}"}
        else:
            try:
                result = await self._dispatch(tc.name, args)
            except Exception as e:  # validation errors go back to the model
                result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        self.tool_log.append({"name": tc.name, "args": args, "result": result})
        self.emit("tool", name=tc.name, args=args, result=result)
        return result

    async def _dispatch(self, name: str, a: dict) -> dict:
        o = self.outcome
        if name == "record_outcome":
            field, value = a["field"], a["value"]
            if field not in FACT_FIELDS or value not in ("yes", "no", "unsure"):
                return {"ok": False, "error": "invalid field or value"}
            if field == "refused_ai":
                o.refused_ai = value == "yes"
            elif field == "reached_human":
                pass  # computed from the office state, not self-reported
            else:
                setattr(o, field, value)
            self.board.record_fact(self.sc.office_id, field, value)
            self.emit("outcome_recorded", field=field, value=value)
            return {"ok": True}
        if name == "record_offer":
            slot = a["slot_start"]
            datetime.fromisoformat(slot)  # raises on garbage
            slot = datetime.fromisoformat(slot).strftime("%Y-%m-%dT%H:%M")
            offer = Offer(offer_id=uuid.uuid4().hex[:8], office_id=self.sc.office_id, slot_start=slot, held=bool(a["held"]))
            o.offers = [x for x in o.offers if x.slot_start != slot] + [offer]
            changed = self.board.add_offer(offer)
            self.emit("offer_received", slot_start=slot, held=offer.held, fits=self.c.slot_ok(slot))
            if changed and (best := self.board.best()):
                self.emit("best_offer_changed", slot_start=best.slot_start, best_office_id=best.office_id)
            warn = None if self.c.slot_ok(slot) else "this slot violates the patient's constraints and will not be ranked"
            return {"ok": True, **({"warning": warn} if warn else {})}
        if name == "check_blackboard":
            slots = self.board.held_slots_excluding(self.sc.office_id)
            self.blackboard_nonempty = self.blackboard_nonempty or bool(slots)
            return {
                "held_slots_at_other_offices": slots,
                "note": "Only mention these if relevant, exactly as given. Never name other offices. If empty, do not claim other options.",
            }
        if name == "press_dtmf":
            if self.office.state != "ivr":
                return {"ok": False, "error": "No phone menu is active. Speak instead."}
            r = await self.office.press(str(a["digits"]))
            self._log("office", r.text)
            if r.hold_s:
                await self._hold(r.hold_s)
            if self.office.state == "human":
                self.status("talking")
            if self.office.state == "ended":
                self.hungup = True
                self.outcome.ended_by = "office_hangup"
            return {"ok": True, "heard": r.text, "line_state": self.office.state}
        if name == "request_human":
            o.escalation_reason = str(a.get("reason", ""))[:300]
            o.ended_by = "escalated"
            self.finished = True
            self.status("escalated")
            self.emit("escalated", reason=o.escalation_reason)
            return {"ok": True}
        if name == "end_call":
            o.ended_by = o.ended_by if o.ended_by not in ("unknown",) else "worker_end"
            self.finished = True
            self.status("done")
            return {"ok": True}
        return {"ok": False, "error": f"unknown tool {name}"}
