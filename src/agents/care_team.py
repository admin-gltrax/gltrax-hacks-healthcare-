"""Care Team agent: find the patient's doctor and get the details RIGHT.

Hackathon build: searches the fictional directory (src/sim/providers.py), adds
the PCP with the directory's numbers marked "unverified", then verifies them the
way a person would: by calling the office. The verification call is where the
swarm comes in (src/swarm): one call per office, many offices at once. In mock
mode `verify_contact` resolves instantly against the simulation's ground truth.

Directories are often wrong (stale fax numbers, plans the office dropped);
the dashboard's "directory vs reality" counter shows every correction.

Real-world path: NPPES NPI Registry API + the insurer's Provider Directory API
(Plan-Net FHIR) for candidates; a real call (telephony adapter, AI disclosure,
consent) for verification. See docs/DATA-SOURCES.md.
"""
from __future__ import annotations

from ..patient.models import AgentTask, CareTeamMember, HealthRecord, TaskStatus
from ..sim.providers import PROVIDERS, SimProvider, find


def search(query: str) -> list[dict]:
    return [
        {"sim_id": p.sim_id, "name": p.name, "practice": p.practice, "specialty": p.specialty,
         "address": p.address, "phone": p.phone}
        for p in find(query)
    ]


def _plan_prefix(record: HealthRecord) -> str | None:
    if record.coverage and record.coverage.member_id:
        return record.coverage.member_id[:3].upper()
    return None


def _sim(sim_id: str) -> SimProvider:
    for p in PROVIDERS:
        if p.sim_id == sim_id:
            return p
    raise KeyError(sim_id)


def add_from_directory(record: HealthRecord, sim_id: str, role: str = "pcp") -> CareTeamMember:
    p = _sim(sim_id)
    prefix = _plan_prefix(record)
    member = CareTeamMember(
        role=role, name=p.name, practice=p.practice, specialty=p.specialty, npi=p.sim_id,
        phone=p.phone, fax=p.directory_fax, address=p.address,
        in_network=("yes" if prefix in p.directory_networks else "no") if prefix else "unknown",
        source="directory", confidence="unverified",
    )
    record.care_team = [m for m in record.care_team if not (role == "pcp" and m.role == "pcp")]
    record.care_team.insert(0, member)
    return member


async def verify_contact(record: HealthRecord, member: CareTeamMember) -> dict:
    """Call the office to confirm fax, network and new-patient status.
    TODO(meta): run a real verification call through src/agents/worker.py
    against the simulated office (and later a real one), not the oracle below."""
    task = AgentTask(title=f"Double-check {member.practice or member.name}'s phone, fax and insurance",
                     agent="care_team", status=TaskStatus.working)
    record.tasks.insert(0, task)
    p = _sim(member.npi or "")
    prefix = _plan_prefix(record)
    corrections = []
    if member.fax != p.true_fax:
        corrections.append(f"fax was {member.fax}, it's really {p.true_fax}")
        member.fax = p.true_fax
    if prefix:
        truly_in = prefix in p.true_networks
        if (member.in_network == "yes") != truly_in:
            corrections.append("the directory was wrong about your insurance" +
                               (": they DO take it" if truly_in else ": they don't take it anymore"))
        member.in_network = "yes" if truly_in else "no"
    member.source, member.confidence = "call", "confirmed"
    task.status = TaskStatus.done
    task.detail = "Confirmed. " + ("Fixed: " + "; ".join(corrections) if corrections else "Everything in the directory was right.")
    if record.patient.onboarding_step == "pcp":
        record.patient.onboarding_step = "records"
    return {"corrections": corrections, "member": member}
