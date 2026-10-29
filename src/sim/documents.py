"""Fictional sample documents for the demo: a prior-authorization denial letter,
an itemized bill and the plan's explanation of benefits (EOB), all for Rosa.

Each sample has its printed text (rendered to a PNG by scripts/make_sample_docs.py
and served at /samples/<file>) and the ground truth the reader agent should
extract. The truth makes Spark's reading measurable (scripts/eval_reader.py) and
lets the offline mock answer like a perfect reader.

Every name, number and amount here is invented. Each page says so in print.
"""
from __future__ import annotations

FOOTER = "SAMPLE - FICTIONAL DOCUMENT FOR A SOFTWARE DEMO. Not a real notice, bill or person."

SAMPLES: dict[str, dict] = {
    "denial_letter": {
        "file": "denial-letter.png",
        "title": "Denial letter: home physical therapy",
        "lines": [
            ("h1", "Bluewater Health (fictional)"),
            ("small", "Medicare Advantage Plans  |  PO Box 0153, Lakeview, IL 60601  |  Member Services (555) 010-0150"),
            ("rule", ""),
            ("b", "NOTICE OF DENIAL OF MEDICAL COVERAGE"),
            ("", "Date of this notice: October 20, 2026          Case number: SIM-PA-20431"),
            ("", ""),
            ("", "Member: Rosa Rivera          Member ID: BWM-77031882          Date of birth: 02/11/1948"),
            ("", "Plan: Bluewater Medicare Advantage HMO"),
            ("", "Requested by: Dr. Samuel Okafor, Harbor Light Internal Medicine"),
            ("", ""),
            ("b", "What we denied"),
            ("", "Home health physical therapy, 12 visits over 6 weeks."),
            ("", ""),
            ("b", "Why we denied it"),
            ("", "\"The information we received does not show that you are homebound or that skilled"),
            ("", "therapy in your home is medically necessary. Outpatient physical therapy is available.\""),
            ("", ""),
            ("b", "Coverage rules we used"),
            ("", "1. The member is homebound: leaving home takes a considerable and taxing effort."),
            ("", "2. A doctor has certified a plan of care for the therapy."),
            ("", "3. Skilled therapy is needed to restore or keep the member's function."),
            ("", "4. The services are reasonable and necessary for the member's condition."),
            ("", ""),
            ("b", "Your right to appeal"),
            ("", "You have 65 days from the date of this notice to ask for an appeal: by December 24, 2026."),
            ("", "Send your appeal and any supporting records to the Appeals Unit, fax (555) 010-0153."),
            ("", "If waiting could seriously harm your health, ask for a fast (expedited) appeal."),
            ("", "We decide fast appeals within 72 hours."),
        ],
        "truth": {
            "plan": "Bluewater Medicare Advantage HMO", "member_name": "Rosa Rivera", "member_id": "BWM-77031882",
            "service": "Home health physical therapy, 12 visits over 6 weeks", "denied_on": "2026-10-20",
            "reason_category": "not_medically_necessary",
            "reason_quote": "The information we received does not show that you are homebound or that skilled therapy in "
                            "your home is medically necessary. Outpatient physical therapy is available.",
            "criteria": ["The member is homebound: leaving home takes a considerable and taxing effort.",
                         "A doctor has certified a plan of care for the therapy.",
                         "Skilled therapy is needed to restore or keep the member's function.",
                         "The services are reasonable and necessary for the member's condition."],
            "appeal_by": "2026-12-24", "appeal_days": 65, "appeals_fax": "(555) 010-0153", "expedited_available": True,
            "case_number": "SIM-PA-20431",
        },
    },
    "bill": {
        "file": "itemized-bill.png",
        "title": "Itemized bill: Harbor Light Internal Medicine",
        "lines": [
            ("h1", "Harbor Light Internal Medicine (fictional)"),
            ("small", "88 Harbor Light Rd  |  Billing (555) 010-0215"),
            ("rule", ""),
            ("b", "ITEMIZED STATEMENT"),
            ("", "Statement date: October 15, 2026          Account: SIM-HL-55120"),
            ("", "Patient: Rosa Rivera          Date of service: September 22, 2026"),
            ("", "Insurance: Bluewater Medicare Advantage HMO"),
            ("", ""),
            ("mono", "CODE    DESCRIPTION                               CHARGE"),
            ("mono", "99214   Office visit, established patient        $210.00"),
            ("mono", "99214   Office visit, established patient        $210.00"),
            ("mono", "80048   Basic metabolic panel                     $48.00"),
            ("mono", "36415   Blood draw (venipuncture)                 $25.00"),
            ("mono", ""),
            ("mono", "        Total charges                            $493.00"),
            ("mono", "        Insurance payments                         $0.00"),
            ("mono", "        AMOUNT DUE                               $493.00"),
            ("", ""),
            ("", "Please pay by November 14, 2026."),
        ],
        "truth": {
            "biller": "Harbor Light Internal Medicine", "patient_name": "Rosa Rivera", "service_date": "2026-09-22",
            "account": "SIM-HL-55120",
            "lines": [{"code": "99214", "description": "Office visit, established patient", "amount": 210.0},
                      {"code": "99214", "description": "Office visit, established patient", "amount": 210.0},
                      {"code": "80048", "description": "Basic metabolic panel", "amount": 48.0},
                      {"code": "36415", "description": "Blood draw (venipuncture)", "amount": 25.0}],
            "amount_due": 493.0,
        },
    },
    "eob": {
        "file": "eob.png",
        "title": "Explanation of benefits from Bluewater Health",
        "lines": [
            ("h1", "Bluewater Health (fictional)"),
            ("small", "Explanation of Benefits  |  THIS IS NOT A BILL"),
            ("rule", ""),
            ("", "Member: Rosa Rivera          Member ID: BWM-77031882"),
            ("", "Provider: Harbor Light Internal Medicine          Date of service: September 22, 2026"),
            ("", "Claim number: SIM-CL-88412"),
            ("", ""),
            ("mono", "CODE    SERVICE                        BILLED   PLAN PAID   YOU OWE"),
            ("mono", "99214   Office visit                  $210.00     $142.00     $0.00"),
            ("mono", "80048   Basic metabolic panel          $48.00      $12.00     $0.00"),
            ("mono", "36415   Blood draw                     $25.00       $3.00     $0.00"),
            ("mono", ""),
            ("mono", "        TOTAL                         $283.00     $157.00     $0.00"),
            ("", ""),
            ("", "Your plan covers primary care visits and lab work at $0. The provider may not bill you"),
            ("", "more than the \"You owe\" amount for covered services."),
        ],
        "truth": {
            "payer": "Bluewater Health", "member_name": "Rosa Rivera", "service_date": "2026-09-22",
            "claim": "SIM-CL-88412",
            "lines": [{"code": "99214", "description": "Office visit", "billed": 210.0, "plan_paid": 142.0, "you_owe": 0.0},
                      {"code": "80048", "description": "Basic metabolic panel", "billed": 48.0, "plan_paid": 12.0, "you_owe": 0.0},
                      {"code": "36415", "description": "Blood draw", "billed": 25.0, "plan_paid": 3.0, "you_owe": 0.0}],
            "total_you_owe": 0.0,
        },
    },
}


def text_of(kind: str) -> str:
    return "\n".join(t for _, t in SAMPLES[kind]["lines"]) + "\n" + FOOTER


def catalog() -> list[dict]:
    return [{"kind": k, "title": v["title"], "url": f"/samples/{v['file']}"} for k, v in SAMPLES.items()]
