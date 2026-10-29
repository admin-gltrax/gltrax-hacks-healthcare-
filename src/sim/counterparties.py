"""Fictional billing offices, plan appeal units, suppliers and state agencies.

They stand in for the people PJ's workflow agents call, fax and file with. Every
name, number and dollar amount is invented. Responses are deterministic so the
demo and the tests always tell the same story; `outcome="denied"` lets the demo
show what PJ does when the answer is no (it escalates).

Phone and fax numbers use the 555-01xx fictional range.
"""
from __future__ import annotations

# ---------------------------------------------------------------- bills

# What an itemized bill looks like for each kind of problem, and what the
# plan's explanation of benefits (EOB) says the patient really owes.
BILL_CASES: dict[str, dict] = {
    "duplicate": {
        "lines": ["Office visit, established patient (99214): $210", "Office visit, established patient (99214): $210",
                  "Basic metabolic panel (80048): $48"],
        "finding": "The same office visit (code 99214) is billed twice on the same day. The plan's EOB shows one visit.",
        "owed": 35, "billed": 468,
    },
    "in_network_billed_as_out": {
        "lines": ["Specialist visit (99204): $640, billed as out of network"],
        "finding": "The office is in the plan's network, but the bill uses out-of-network prices. In network, the plan's "
                   "EOB says you owe your $35 specialist copay.",
        "owed": 35, "billed": 640,
    },
    "preventive_billed": {
        "lines": ["Annual Wellness Visit (G0439) coded with a problem visit (99213): $165"],
        "finding": "A preventive visit was coded as a problem visit. Preventive visits are $0 on the plan; the EOB "
                   "would cover it if the office fixes the code.",
        "owed": 0, "billed": 165,
    },
    "already_paid": {
        "lines": ["Physical therapy, 4 visits: $120"],
        "finding": "You already paid $120 on the day of service (your receipt matches), but the bill doesn't show it.",
        "owed": 0, "billed": 120,
    },
    "not_sure": {
        "lines": ["Office visit (99213): $180", "Venipuncture (36415): $25", "Lipid panel (80061): $65"],
        "finding": "Lab work was billed before the plan processed it. The EOB shows the plan paid most of it; you owe the "
                   "$35 copay, not the full $270.",
        "owed": 35, "billed": 270,
    },
}

# ---------------------------------------------------------------- plan appeal units, suppliers, agencies

APPEALS_FAX = {"BWM": "(555) 010-0153", "EVG": "(555) 010-0143", "PSM": "(555) 010-0163"}
STATE_AGENCY = {"name": "State Department of Aging and Disability Services (fictional)", "fax": "(555) 010-0180",
                "phone": "(555) 010-0181"}
DME_SUPPLIER = {"name": "Summit Home Medical Supply (fictional)", "phone": "(555) 010-0190"}
COUNSELORS = [  # in-network counselors the scheduling swarm "calls"
    {"name": "Larkspur Counseling", "accepting": True, "first_opening_days": 44},
    {"name": "Cedar Hollow Therapy", "accepting": False, "first_opening_days": None},
    {"name": "Marlow Behavioral Health", "accepting": True, "first_opening_days": 51},
    {"name": "Brightwater Counseling Group", "accepting": False, "first_opening_days": None},
]
OUT_OF_NETWORK_COUNSELOR = {"name": "Juniper Grief & Life Transitions", "first_opening_days": 6}


def respond(template: str, inputs: dict, outcome: str = "approved") -> tuple[str, str, str | None]:
    """The other side answers. Returns (status, plain outcome, saved)."""
    won = outcome != "denied"
    if template == "office_request":
        from .pcp_office import PURPOSES
        p = PURPOSES.get(inputs.get("purpose") or "referral", PURPOSES["referral"])
        if not won:
            return "lost", "The office couldn't finish it yet (the doctor is out). PJ will call back on their return date.", None
        return "won", {
            "referral": "The referral is approved by the plan. PJ can now find the soonest specialist opening.",
            "refill": "The refill was signed and sent to the pharmacy. Ready for pickup tomorrow.",
            "letter": "The doctor signed the letter, and the office faxed it.",
            "order": "The doctor signed the order; it went to the plan and the supplier.",
            "nurse_question": "The nurse called back. PJ wrote down exactly what they said, word for word.",
            "records": "The office confirmed the records are on the way.",
            "appointment": "An opening is held for the patient to approve.",
            "billing": "Billing finished the review and sent a corrected statement.",
        }.get(inputs.get("purpose"), p["done"]), None
    if template == "bill_dispute":
        case = BILL_CASES.get(inputs.get("issue") or "not_sure", BILL_CASES["not_sure"])
        if not won:
            return "lost", "The billing office says the bill is correct. PJ can take it to the plan's member services next.", None
        saved = case["billed"] - case["owed"]
        return "won", f"Corrected bill received: you owe ${case['owed']}, not ${case['billed']}.", f"${saved}"
    if template in ("pa_appeal", "external_review"):
        svc = inputs.get("service") or "the service"
        if won:
            return "won", f"The plan reversed its decision: {svc} is approved.", None
        return "lost", f"The plan kept its denial of {svc}. PJ prepared the next level: an independent outside review.", None
    if template == "dme":
        eq = inputs.get("equipment_label") or "the equipment"
        if won:
            return "won", f"Approved: {eq} for the next 12 months. {DME_SUPPLIER['name']} confirmed delivery.", None
        return "lost", f"The plan denied {eq}. PJ prepared an appeal with the doctor's updated notes.", None
    if template == "plan_resource":
        res = inputs.get("resource")
        if not won:
            return "lost", "The plan said no. PJ found community programs that can help instead.", None
        return "won", {
            "rides": "Ride booked: pickup 45 minutes before the appointment, return ride on call.",
            "home_aide": "Home health aide approved: an in-home assessment is set for next week.",
            "supplies": "Supplies approved and shipping in 3 to 5 days, with automatic refills.",
        }.get(res, "Approved."), None
    if template == "caregiving_appeal":
        before, after = int(inputs.get("hours_before") or 0), int(inputs.get("hours_after") or 0)
        if won:
            return "won", (f"Hearing decision: home care hours restored to {before} a week. Hours stayed at {before} "
                           "during the appeal because PJ asked in time."), (f"{before - after} hours a week" if before > after else None)
        return "lost", "The hearing kept the cut. PJ found caregiver respite programs and can request a re-assessment in 90 days.", None
    if template == "counselor_request":
        if won:
            c = OUT_OF_NETWORK_COUNSELOR
            return "won", (f"The plan approved {c['name']} at your in-network price (a single case agreement). "
                           f"PJ is holding an intake in {c['first_opening_days']} days for your yes."), None
        return "lost", "The plan said no exception. PJ is holding the soonest in-network opening and a waitlist spot.", None
    return ("won" if won else "lost"), "Answered.", None
