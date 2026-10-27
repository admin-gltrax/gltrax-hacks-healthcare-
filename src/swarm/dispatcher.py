"""Runs many calls at once.

Swarm mode: one shared Blackboard, so offices that answer early create honest
leverage for the ones still on hold. Eval mode: each call gets its own board.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..agents.worker import CallRunner
from ..eval.judge import score_call
from ..llm import LLM, get_llm
from ..schemas import CallResult, CallScore, Constraints, Offer, OfficeScenario, PatientProfile
from .blackboard import Blackboard
from .events import EventBus


@dataclass
class SwarmResult:
    results: list[CallResult] = field(default_factory=list)
    scores: list[CallScore] = field(default_factory=list)
    best: Offer | None = None
    truth: dict = field(default_factory=dict)


def truth_delta(scenarios: list[OfficeScenario], results: list[CallResult], plan: str) -> dict:
    """How wrong was the directory? Compares 'directory says in network' with what the call found."""
    by_id = {r.office_id: r for r in results}
    claimed = confirmed_yes = confirmed_no = unknown = 0
    for sc in scenarios:
        if plan not in sc.directory_claims_plans:
            continue
        claimed += 1
        r = by_id.get(sc.office_id)
        got = r.outcome.accepts_plan if r else None
        if got == "yes":
            confirmed_yes += 1
        elif got == "no":
            confirmed_no += 1
        else:
            unknown += 1
    return {"claimed_in_network": claimed, "confirmed_yes": confirmed_yes, "confirmed_no": confirmed_no, "unverified": unknown}


async def run_swarm(
    scenarios: list[OfficeScenario],
    patient: PatientProfile,
    constraints: Constraints,
    *,
    bus: EventBus | None = None,
    k: int = 15,
    stagger_s: float = 0.15,
    shared_blackboard: bool = True,
    prompt_text: str | None = None,
    worker_llm: LLM | None = None,
    office_llm: LLM | None = None,
    scale: float | None = None,
    directory: dict | None = None,
) -> SwarmResult:
    bus = bus or EventBus()
    worker_llm = worker_llm or get_llm("worker")
    office_llm = office_llm or get_llm("office")
    board = Blackboard(constraints)
    sem = asyncio.Semaphore(k)
    out = SwarmResult()

    stand_ins = (directory or {}).get("stand_ins", [])
    if directory is not None:
        bus.publish("directory_search", **directory)  # step 1: real directory data, shown as such
    bus.publish(
        "swarm_started",
        total=len(scenarios),
        patient={"name": patient.name, "payer": patient.payer, "plan": patient.plan},
        constraints=constraints.model_dump(),
        offices=[
            {"office_id": s.office_id, "name": s.practice_name, "persona": s.persona, "distance": s.distance_miles,
             **({"city": stand_ins[i]["city"]} if i < len(stand_ins) else {})}
            for i, s in enumerate(scenarios)
        ],
    )

    async def one(i: int, sc: OfficeScenario) -> tuple[CallResult, CallScore]:
        await asyncio.sleep(i * stagger_s)
        async with sem:
            runner = CallRunner(
                sc, patient, constraints, worker_llm, office_llm,
                board if shared_blackboard else Blackboard(constraints),
                bus=bus, prompt_text=prompt_text, scale=scale,
            )
            res = await runner.run()
        score = score_call(res, sc, patient, constraints)
        bus.publish(
            "scored", office_id=sc.office_id, success=score.success, safety=score.safety, safety_ok=score.safety_ok,
            notes=score.notes, escalated=score.escalated,
        )
        bus.publish("truth_update", **truth_delta(scenarios, [r for r in out.results] + [res], patient.plan))
        out.results.append(res)
        return res, score

    pairs = await asyncio.gather(*(one(i, s) for i, s in enumerate(scenarios)))
    out.results = [p[0] for p in pairs]
    out.scores = [p[1] for p in pairs]
    out.best = board.best()
    out.truth = truth_delta(scenarios, out.results, patient.plan)
    name = {s.office_id: s.practice_name for s in scenarios}
    bus.publish(
        "swarm_finished",
        best=(
            {"office_id": out.best.office_id, "name": name[out.best.office_id], "slot_start": out.best.slot_start, "held": out.best.held}
            if out.best else None
        ),
        truth=out.truth,
        success_rate=round(sum(s.success for s in out.scores) / max(1, len(out.scores)), 3),
        safety_pass_rate=round(sum(s.safety_ok for s in out.scores) / max(1, len(out.scores)), 3),
        leaderboard=[{"office_id": o.office_id, "name": name[o.office_id], "slot_start": o.slot_start} for o in board.leaderboard()],
    )
    return out
