"""Run the call gym: N fictional offices (src/sim/gym.py) against PJ's real caller.

The caller stays on Meta's Muse Spark (role "caller"); the receptionists run on
whatever the "office" role points at (OFFICE_PROVIDER=fireworks for partner
credits). Calls run in parallel under a concurrency cap and a requests-per-minute
limiter per provider, so a big run stays under Meta's 3,000 RPM per team and the
partner's limits. Every call is scored by gym.score(); the report aggregates.
"""
from __future__ import annotations

import asyncio
import statistics
import time
from collections import defaultdict

from ..agents import ai
from ..agents.office_caller import OfficeCall
from ..sim import gym

SAFETY_KEYS = ["disclosed_ai_to_each_person", "no_extra_data_shared", "no_human_claim", "confirmed_ai_when_asked",
               "no_voicemail_data", "no_fabricated_reference"]


class Limiter:
    """At most `rpm` request starts per minute (evenly spaced), shared by every call on one provider."""

    def __init__(self, rpm: int):
        self.gap = 60.0 / max(1, rpm)
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.gap
        if delay > 0:
            await asyncio.sleep(delay)


class Limited:
    def __init__(self, llm, limiter: Limiter):
        self.llm, self.limiter = llm, limiter

    def __getattr__(self, k):
        return getattr(self.llm, k)

    async def chat(self, *a, **k):
        await self.limiter.wait()
        return await self.llm.chat(*a, **k)


async def run_one(persona: dict, limiters: dict[str, Limiter], timeout: float = 240.0) -> dict:
    caller, office = ai.llm("caller", "gym"), ai.llm("office", "gym")
    c, o = Limited(caller, limiters["caller"]), Limited(office, limiters["office"])
    line = gym.GymLine(persona, o)
    call = OfficeCall(persona["practice"], persona["phone"], persona["purpose"], persona["details"], persona["who"], c, o,
                      max_turns=34, line=line)
    t0 = time.monotonic()
    row = {"id": persona["id"], "kind": persona["kind"], "purpose": persona["purpose"], "relents": persona["relents"]}
    try:
        result = await asyncio.wait_for(call.run(), timeout)
    except (ai.AIUnavailable, asyncio.TimeoutError) as e:
        row.update(error=f"{type(e).__name__}: {str(e)[:200]}", seconds=round(time.monotonic() - t0, 2),
                   transcript=call.transcript, requests={"caller": caller.requests, "office": office.requests},
                   cost=round(caller.cost() + office.cost(), 6))
        return row
    row.update(gym.score(persona, result, call), seconds=round(time.monotonic() - t0, 2),
               requests={"caller": caller.requests, "office": office.requests},
               tokens={"caller": [caller.prompt_tokens, caller.completion_tokens], "office": [office.prompt_tokens, office.completion_tokens]},
               cost={"caller": caller.cost(), "office": office.cost()}, models={"caller": caller.model, "office": office.model},
               reference=result["reference"], reached=result["reached"], menu_path=result["menu_path"], hold_minutes=result["hold_minutes"],
               escalated=call.escalated, voicemail=line.voicemail_messages, transcript=result["transcript"])
    return row


async def run(personas: list[dict], concurrency: int = 16, caller_rpm: int = 1500, office_rpm: int = 600,
              on_done=None) -> list[dict]:
    limiters = {"caller": Limiter(caller_rpm), "office": Limiter(office_rpm)}
    sem = asyncio.Semaphore(concurrency)

    async def one(p):
        async with sem:
            row = await run_one(p, limiters)
        if on_done:
            on_done(row)
        return row
    return await asyncio.gather(*(one(p) for p in personas))


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))], 2)


def report(rows: list[dict], meta: dict | None = None) -> dict:
    done = [r for r in rows if "error" not in r]
    errors = [r for r in rows if "error" in r]
    safety = {k: sum(r["safety"][k] for r in done) for k in SAFETY_KEYS}
    by_kind: dict[str, dict] = defaultdict(lambda: {"calls": 0, "success": 0, "safe": 0, "errors": 0})
    for r in rows:
        k = by_kind[r["kind"]]
        k["calls"] += 1
        if "error" in r:
            k["errors"] += 1
            continue
        k["success"] += r["success"]
        k["safe"] += r["safe"]
    secs = [r["seconds"] for r in done]
    reqs = [r["requests"]["caller"] + r["requests"]["office"] for r in done]
    cost_caller = sum(r["cost"]["caller"] for r in done)
    cost_office = sum(r["cost"]["office"] for r in done)
    err_cost = sum(r.get("cost", 0) for r in errors if isinstance(r.get("cost"), (int, float)))
    n = len(done) or 1
    failures = [{"id": r["id"], "kind": r["kind"], "failed": [k for k, v in r["safety"].items() if not v]} for r in done if not r["safe"]]
    return {
        **(meta or {}), "calls": len(rows), "completed": len(done), "errors": len(errors),
        "error_samples": [{"id": r["id"], "kind": r["kind"], "error": r["error"]} for r in errors[:5]],
        "safety_pass_rate": round(sum(r["safe"] for r in done) / n, 4), "safety_checks": {k: f"{v}/{len(done)}" for k, v in safety.items()},
        "safety_failures": failures,
        "ai_disclosed_to_each_person": f"{safety['disclosed_ai_to_each_person']}/{len(done)}",
        "data_leaks": len(done) - safety["no_extra_data_shared"] + (len(done) - safety["no_voicemail_data"]),
        "human_claims": len(done) - safety["no_human_claim"],
        "reference_really_heard": f"{sum(r['outcome'] == 'reference' for r in done)} calls got a reference; "
                                  f"{len(done) - safety['no_fabricated_reference']} recorded one the office never said",
        "success_rate": round(sum(r["success"] for r in done) / n, 4),
        "success_by_persona": {k: {**v, "rate": round(v["success"] / max(1, v["calls"] - v["errors"]), 3)} for k, v in sorted(by_kind.items())},
        "outcomes": {o: sum(r["outcome"] == o for r in done) for o in ("reference", "handed_back", "voicemail", "dropped", "no_result")},
        "latency_s": {"p50": _pct(secs, 0.5), "p95": _pct(secs, 0.95), "max": max(secs) if secs else 0},
        "requests_per_call": {"mean": round(statistics.mean(reqs), 1) if reqs else 0, "p95": _pct(reqs, 0.95)},
        "cost_usd": {"caller_meta": round(cost_caller, 4), "office_partner": round(cost_office, 4), "errored_calls": round(err_cost, 4),
                     "total": round(cost_caller + cost_office + err_cost, 4),
                     "per_call": round((cost_caller + cost_office) / n, 5)},
    }


def markdown(rep: dict) -> str:
    lines = [f"**{rep['completed']} of {rep['calls']} calls completed** ({rep['errors']} errored) · "
             f"safety **{rep['safety_pass_rate'] * 100:.1f}%** · success {rep['success_rate'] * 100:.1f}% · "
             f"p50 {rep['latency_s']['p50']} s, p95 {rep['latency_s']['p95']} s · "
             f"{rep['requests_per_call']['mean']} requests and ${rep['cost_usd']['per_call']:.4f} per call", "",
             "| Safety check | Passed |", "|---|---|"]
    lines += [f"| {k.replace('_', ' ')} | {v} |" for k, v in rep["safety_checks"].items()]
    lines += ["", "| Persona | Calls | Success | Safe |", "|---|---|---|---|"]
    lines += [f"| {k.replace('_', ' ')} | {v['calls']} | {v['success']} ({v['rate'] * 100:.0f}%) | {v['safe']} |"
              for k, v in rep["success_by_persona"].items()]
    return "\n".join(lines)
