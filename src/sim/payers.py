"""Fictional insurers, plans and employers.

Stands in for the real sources the Coverage agent will use after the hackathon
(insurer Patient Access FHIR APIs, eligibility 270/271, the plan's Summary of
Benefits). Every name, number and price here is invented. The "portal" lookup
is keyed by member ID prefix so a demo card always resolves to the same plan.

Phone numbers use the 555-01xx fictional range.
"""
from __future__ import annotations

from ..patient.models import BenefitLine, Coverage, Program


def _b(service, label, covered="yes", you_pay=None, referral=False, prior_auth=False, limit=None, notes=None):
    return BenefitLine(
        service=service, label=label, covered=covered, you_pay=you_pay,
        needs_referral=referral, needs_prior_auth=prior_auth, visit_limit=limit, notes=notes,
    )


PLANS: dict[str, Coverage] = {
    # Employer PPO: no referrals, therapy covered, EAP through the employer.
    "EVG": Coverage(
        payer="Evergreen Health (fictional)",
        plan_name="Evergreen Choice PPO 2500",
        program=Program.employer,
        plan_type="PPO",
        group_number="NW-40021",
        deductible="$2,500",
        deductible_met="$640",
        out_of_pocket_max="$6,000",
        out_of_pocket_met="$910",
        pcp_required=False,
        member_phone="(555) 010-0140",
        behavioral_health_phone="(555) 010-0141",
        nurse_line="(555) 010-0142",
        benefits=[
            _b("primary_care", "Primary care visit (in network)", you_pay="$25 per visit"),
            _b("preventive", "Yearly checkup and preventive screenings", you_pay="$0"),
            _b("specialist", "Specialist visit (in network)", you_pay="$60 per visit", notes="No referral needed on a PPO."),
            _b("therapy_outpatient", "Therapy (talk therapy, in network)", you_pay="$25 per visit",
               notes="Same cost as a primary care visit (mental health parity)."),
            _b("psychiatry", "Psychiatrist (medication management)", you_pay="$60 per visit"),
            _b("telehealth", "Virtual visits through the plan's telehealth partner", you_pay="$0"),
            _b("labs", "Lab work (in network)", you_pay="20% after deductible"),
            _b("physical_therapy", "Physical therapy", you_pay="$40 per visit", limit="30 visits a year"),
            _b("dermatology", "Dermatologist", you_pay="$60 per visit"),
            _b("genetic_testing", "Genetic testing", covered="partly", prior_auth=True,
               notes="Covered when a doctor orders it and your family history meets the plan's criteria."),
            _b("out_of_network", "Out-of-network care", covered="partly", you_pay="40% after a separate $5,000 deductible"),
        ],
    ),
    # Medicare Advantage HMO: PCP required, referrals needed for specialists.
    "BWM": Coverage(
        payer="Bluewater Health (fictional)",
        plan_name="Bluewater Medicare Advantage HMO",
        program=Program.medicare_advantage,
        plan_type="HMO",
        deductible="$0",
        deductible_met="$0",
        out_of_pocket_max="$4,900",
        out_of_pocket_met="$350",
        pcp_required=True,
        member_phone="(555) 010-0150",
        behavioral_health_phone="(555) 010-0151",
        nurse_line="(555) 010-0152",
        benefits=[
            _b("primary_care", "Primary care visit", you_pay="$0"),
            _b("preventive", "Annual Wellness Visit and preventive screenings", you_pay="$0"),
            _b("specialist", "Specialist visit", you_pay="$35 per visit", referral=True,
               notes="Your PCP has to send a referral first (HMO)."),
            _b("therapy_outpatient", "Therapy (talk therapy)", you_pay="$20 per visit",
               notes="No referral needed for mental health on this plan."),
            _b("psychiatry", "Psychiatrist", you_pay="$35 per visit"),
            _b("telehealth", "Virtual visits", you_pay="$0"),
            _b("labs", "Lab work", you_pay="$0"),
            _b("physical_therapy", "Physical therapy", you_pay="$30 per visit", prior_auth=True),
            _b("dermatology", "Dermatologist", you_pay="$35 per visit", referral=True),
            _b("dental", "Dental cleanings", you_pay="$0", limit="2 a year", notes="Extra benefit many Medicare Advantage plans add."),
            _b("out_of_network", "Out-of-network care", covered="no", notes="HMO: only emergencies are covered out of network."),
        ],
    ),
    # Medicaid managed care.
    "PSM": Coverage(
        payer="Prairie State Medicaid (fictional)",
        plan_name="Prairie Care Medicaid Managed Care",
        program=Program.medicaid,
        plan_type="HMO",
        deductible="$0",
        out_of_pocket_max="$0",
        pcp_required=True,
        member_phone="(555) 010-0160",
        behavioral_health_phone="(555) 010-0161",
        nurse_line="(555) 010-0162",
        benefits=[
            _b("primary_care", "Primary care visit", you_pay="$0"),
            _b("preventive", "Checkups and screenings", you_pay="$0"),
            _b("specialist", "Specialist visit", you_pay="$0", referral=True),
            _b("therapy_outpatient", "Therapy (talk therapy)", you_pay="$0",
               notes="Medicaid also covers community mental health centers."),
            _b("psychiatry", "Psychiatrist", you_pay="$0"),
            _b("telehealth", "Virtual visits", you_pay="$0"),
            _b("labs", "Lab work", you_pay="$0"),
            _b("transport", "Rides to medical appointments", you_pay="$0",
               notes="Non-emergency medical transportation: book at least 2 days ahead."),
            _b("physical_therapy", "Physical therapy", you_pay="$0", prior_auth=True),
            _b("dermatology", "Dermatologist", you_pay="$0", referral=True),
        ],
    ),
}

# Employer -> Employee Assistance Program. EAPs are run by the employer, not the
# insurer, so a patient usually has no idea theirs exists.
EMPLOYER_EAP: dict[str, dict] = {
    "northwind logistics": {"sessions": "6 free counseling sessions a year", "phone": "(555) 010-0170",
                            "how": "Call the EAP line; they match you with a counselor, usually within a week."},
    "acme schools": {"sessions": "5 free counseling sessions per issue", "phone": "(555) 010-0171",
                     "how": "Call the EAP line or use the app your HR department shared."},
}

DEMO_CARDS = {
    # What a photographed card would yield (member ID prefix picks the plan).
    "EVG-55120943": {"payer": "Evergreen Health", "plan": "Evergreen Choice PPO 2500", "member_id": "EVG-55120943"},
    "BWM-77031882": {"payer": "Bluewater Health", "plan": "Bluewater Medicare Advantage HMO", "member_id": "BWM-77031882"},
    "PSM-30018467": {"payer": "Prairie State Medicaid", "plan": "Prairie Care Medicaid Managed Care", "member_id": "PSM-30018467"},
}


def portal_lookup(member_id: str) -> Coverage | None:
    """The simulated insurer portal / Patient Access API. Returns a fresh copy."""
    plan = PLANS.get((member_id or "")[:3].upper())
    if not plan:
        return None
    cov = plan.model_copy(deep=True)
    cov.member_id = member_id
    return cov


def eap_for(employer: str | None) -> dict | None:
    return EMPLOYER_EAP.get((employer or "").strip().lower())
