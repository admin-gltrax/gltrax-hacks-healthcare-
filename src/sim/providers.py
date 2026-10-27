"""A fictional provider directory: primary care, therapists, specialists.

Stands in for NPPES (the national provider registry) plus the insurer's
directory. Like real directories, it is sometimes WRONG: `directory_fax` can be
stale while `true_fax` is right, and `directory_networks` can list plans the
office no longer takes. The Care Team agent's job is to notice and fix that
(by calling, via the swarm) before a records request goes to a dead fax line.

IDs use a SIM- prefix so they can never be mistaken for real NPIs.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SimProvider:
    sim_id: str
    name: str
    practice: str
    role: str  # pcp | therapist | specialist
    specialty: str
    zip_code: str
    phone: str
    directory_fax: str
    true_fax: str
    address: str
    directory_networks: list[str] = field(default_factory=list)  # plan prefixes the directory claims
    true_networks: list[str] = field(default_factory=list)  # plan prefixes actually accepted
    accepting_new: bool = True
    telehealth: bool = False
    sliding_scale: bool = False


PROVIDERS: list[SimProvider] = [
    SimProvider("SIM-1001", "Dr. Maya Lee", "Cedar Point Family Medicine", "pcp", "family medicine", "60614",
                "(555) 010-0201", "(555) 010-0202", "(555) 010-0202", "214 Cedar Pt Ave, Suite 3",
                ["EVG", "BWM"], ["EVG", "BWM"]),
    SimProvider("SIM-1002", "Dr. Samuel Okafor", "Harbor Light Internal Medicine", "pcp", "internal medicine", "60614",
                "(555) 010-0211", "(555) 010-0212", "(555) 010-0219", "88 Harbor Light Rd",
                ["EVG", "PSM"], ["PSM"]),  # stale fax AND stale network: the directory problem
    SimProvider("SIM-1003", "Dr. Ana Ruiz", "Juniper Community Health Center", "pcp", "family medicine", "60615",
                "(555) 010-0221", "(555) 010-0222", "(555) 010-0222", "5 Juniper St",
                ["PSM", "BWM"], ["PSM", "BWM", "EVG"], sliding_scale=True),
    SimProvider("SIM-2001", "Jordan Blake, LCSW", "Larkspur Counseling", "therapist", "therapy", "60614",
                "(555) 010-0231", "(555) 010-0232", "(555) 010-0232", "41 Larkspur Ln",
                ["EVG", "BWM"], ["EVG", "BWM"], telehealth=True),
    SimProvider("SIM-2002", "Priya Nair, PhD", "Marlow Psychology Group", "therapist", "therapy", "60614",
                "(555) 010-0241", "(555) 010-0242", "(555) 010-0242", "900 Marlow Ave",
                ["EVG"], ["EVG"], accepting_new=False),  # directory says yes, phones say "not taking new patients"
    SimProvider("SIM-2003", "Kestrel Community Mental Health", "Kestrel CMHC", "therapist", "therapy", "60615",
                "(555) 010-0251", "(555) 010-0252", "(555) 010-0252", "12 Kestrel Way",
                ["PSM"], ["PSM"], sliding_scale=True),
    SimProvider("SIM-3001", "Dr. Elena Park", "Northgate Dermatology", "specialist", "dermatology", "60614",
                "(555) 010-0261", "(555) 010-0262", "(555) 010-0262", "300 Northgate Blvd",
                ["EVG", "BWM"], ["EVG"]),
]


def find(name_or_practice: str) -> list[SimProvider]:
    q = name_or_practice.strip().lower()
    return [p for p in PROVIDERS if q and (q in p.name.lower() or q in p.practice.lower())]


def by_role(role: str, specialty: str | None = None) -> list[SimProvider]:
    return [p for p in PROVIDERS if p.role == role and (specialty is None or p.specialty == specialty)]
