"""Coverage agent: "figure out what the hell my insurance actually covers."

Hackathon build (works now, no model needed):
  card or member ID -> simulated insurer portal (src/sim/payers.py) -> Coverage
  with plain-language benefit lines -> employer EAP lookup -> PJ summary.

Meta models (wired in when MOCK_LLM=0, see README "Meta model map"):
  - read_card(): Muse Spark vision reads a photo of the insurance card.
  - summarize(): Muse Spark rewrites the plan into two sentences a patient gets.
  - portal navigation: Muse computer-use drives the (simulated) insurer portal.

Real-world path (post-hackathon): member-authorized Patient Access FHIR API
(Coverage, ExplanationOfBenefit; via an aggregator), eligibility 270/271 for
live deductible/OOP numbers, and the plan's Summary of Benefits and Coverage.
Never store portal passwords; never scrape a portal without the patient
present. See docs/DATA-SOURCES.md.
"""
from __future__ import annotations

from ..patient.models import AgentTask, Coverage, HealthRecord, Program, TaskStatus
from ..sim.payers import DEMO_CARDS, eap_for, portal_lookup


class CoverageNotFound(Exception):
    pass


def read_card(card_text_or_id: str) -> dict:
    """Mock card reader: accepts a demo member ID (or text containing one).
    TODO(meta): Muse Spark vision on an image upload -> {payer, plan, member_id, group}."""
    for mid, card in DEMO_CARDS.items():
        if mid.lower() in (card_text_or_id or "").lower():
            return dict(card)
    return {"member_id": (card_text_or_id or "").strip()}


def plain_summary(cov: Coverage) -> str:
    """Two sentences, no jargon. TODO(meta): let Muse Spark rewrite, keep the numbers."""
    kind = {
        Program.employer: "a plan through work",
        Program.marketplace: "a Marketplace plan",
        Program.medicare: "Original Medicare",
        Program.medicare_advantage: "a Medicare Advantage plan",
        Program.medicaid: "Medicaid",
        Program.dual: "Medicare and Medicaid together",
    }.get(cov.program, "a health plan")
    gate = (
        "You need a primary care doctor, and they send referrals before most specialist visits."
        if cov.pcp_required else
        "You can see specialists without a referral."
    )
    money = ""
    if cov.deductible and cov.deductible != "$0":
        money = f" You've paid {cov.deductible_met or '$0'} of your {cov.deductible} deductible so far this year."
    return f"You have {kind} ({cov.plan_type or 'plan'}) with {cov.payer.replace(' (fictional)', '')}. {gate}{money}"


async def understand_coverage(record: HealthRecord, card: str, employer: str | None = None) -> Coverage:
    task = AgentTask(title="Figure out what your insurance covers", agent="coverage", status=TaskStatus.working)
    record.tasks.insert(0, task)

    info = read_card(card)
    cov = portal_lookup(info.get("member_id", ""))
    if cov is None:
        task.status = TaskStatus.waiting_on_you
        task.needs_you = "Check the member ID on your card (or snap a photo of the front)."
        raise CoverageNotFound(info.get("member_id", ""))

    if employer:
        record.patient.employer = employer
    eap = eap_for(record.patient.employer)
    cov.eap_available = bool(eap)
    cov.eap_sessions = eap["sessions"] if eap else None
    cov.plain_summary = plain_summary(cov)

    record.coverage = cov
    record.patient.onboarding_step = "pcp" if record.patient.onboarding_step in ("welcome", "coverage") else record.patient.onboarding_step
    task.status = TaskStatus.done
    task.detail = cov.plain_summary
    return cov
