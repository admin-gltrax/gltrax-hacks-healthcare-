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


# ---------------------------------------------------------------- the reader eval set (30+ documents)
#
# Generated deterministically from the tables below, each with ground truth, so
# scripts/eval_reader.py can measure field accuracy across plans, denial reasons,
# deadlines printed or not, duplicate lines, out-of-network pricing and bills
# already partly paid. All invented; every page carries FOOTER.

_PAYERS = [  # (payer, plan, member-ID prefix, appeal days, appeals fax)
    ("Bluewater Health", "Bluewater Medicare Advantage HMO", "BWM", 65, "(555) 010-0153"),
    ("Sagebrush Community Health", "Sagebrush Medicaid Managed Care", "SGM", 60, "(555) 010-0163"),
    ("Northstar Insurance", "Northstar Gold PPO", "NSP", 180, "(555) 010-0173"),
    ("Keystone Benefits", "Keystone Employer HMO", "KEH", 180, "(555) 010-0183"),
    ("Redwood Health Exchange", "Redwood Marketplace Silver EPO", "RMS", 180, "(555) 010-0193"),
]
_PEOPLE = [("Marisol Vega", "1951-03-14"), ("Theo Lindqvist", "1979-08-02"), ("Priya Natarajan", "1990-11-23"),
           ("Walter Okonkwo", "1946-06-30"), ("Hana Sato", "2012-01-09"), ("Dmitri Kowal", "1966-12-17"),
           ("Grace Abara", "1958-05-05"), ("Luis Ibarra", "1983-09-27"), ("June Whitlock", "1940-02-19"),
           ("Omar Haddad", "1972-07-11"), ("Iris Moreau", "2005-04-03")]
_DENIALS = [  # (service, reason category, plan's reason, criteria)
    ("MRI of the lower back without contrast", "not_medically_necessary",
     "Records do not show six weeks of conservative treatment such as physical therapy before imaging.",
     ["Low back pain has lasted at least six weeks.", "Conservative treatment was tried for at least six weeks.",
      "No red-flag symptoms require earlier imaging, or they are documented."]),
    ("Continuous glucose monitor and sensors", "missing_info",
     "We did not receive the prescriber's notes or recent blood sugar logs.",
     ["The member has diabetes treated with insulin.", "The prescriber submitted notes from the last six months.",
      "The member checks blood sugar at least four times a day, or has problem lows."]),
    ("Overnight sleep study in a lab", "not_medically_necessary",
     "A home sleep test is the first step under our policy unless a lab study is needed.",
     ["Symptoms suggest a sleep breathing disorder.", "A home test was tried or is not appropriate.",
      "A specialist ordered the in-lab study."]),
    ("Knee replacement surgery by Dr. Ruth Calder (out of network)", "out_of_network",
     "This surgeon is not in your network, and in-network surgeons are available within 30 miles.",
     ["No in-network surgeon can perform the surgery within a reasonable time or distance.",
      "The member's needs require this specific surgeon."]),
    ("Home health physical therapy, 8 visits", "not_medically_necessary",
     "You do not appear to be homebound. Outpatient therapy is available.",
     ["The member is homebound.", "A doctor certified a plan of care.", "Skilled therapy is needed."]),
    ("Gene panel test for inherited heart conditions", "experimental",
     "This test is considered investigational for your diagnosis.",
     ["The test is standard care for the member's condition.", "A genetic counselor or specialist ordered it.",
      "The results will change the member's treatment."]),
    ("Power wheelchair", "not_medically_necessary",
     "A manual wheelchair or scooter would meet your mobility needs.",
     ["The member cannot do daily activities at home with a cane, walker or manual wheelchair.",
      "The member can safely operate a power wheelchair.", "A face-to-face exam was done within 45 days of the order."]),
    ("Brand-name inhaler (step therapy exception)", "not_medically_necessary",
     "Our step therapy rules require trying two preferred inhalers first.",
     ["The member tried the preferred drugs and they did not work or caused side effects.",
      "The preferred drugs are not appropriate for the member."]),
    ("Outpatient infusion therapy, 6 sessions", "missing_info",
     "The request did not include the treatment plan or recent lab results.",
     ["The prescriber submitted the treatment plan.", "Recent lab results support the treatment."]),
    ("Inpatient rehabilitation stay", "not_medically_necessary",
     "You could receive the care you need at a skilled nursing facility.",
     ["The member needs intensive therapy at least three hours a day.", "The member is expected to improve significantly.",
      "Close physician supervision is needed."]),
    ("Specialist visit with a dermatologist", "not_sure",
     "Coverage could not be approved for this request.",
     ["A referral from the primary care doctor is on file."]),
]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _spoken(d: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    return f"{_MONTHS[m - 1]} {dd}, {y}"


def _mdy(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{m}/{dd}/{y}"


def _plus_days(d: str, n: int) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


def _denial(i: int) -> dict:
    payer, plan, prefix, days, fax = _PAYERS[i % len(_PAYERS)]
    name, dob = _PEOPLE[i]
    service, cat, why, crit = _DENIALS[i]
    notice = f"2026-{(i % 9) + 1:02d}-{(i * 3) % 27 + 1:02d}"
    mid = f"{prefix}-{70000000 + i * 1234567}"
    case = f"SIM-PA-{30100 + i * 37}"
    printed = i % 3  # 0: deadline date and days, 1: days only, 2: neither (call member services)
    expedited = i % 2 == 0
    by = _plus_days(notice, days)
    appeal = {0: [f"You have {days} days from the date of this notice to ask for an appeal: by {_spoken(by)}."],
              1: [f"You have {days} days from the date of this notice to ask for an appeal."],
              2: ["To learn how long you have to appeal, call Member Services."]}[printed]
    lines = [("h1", f"{payer} (fictional)"), ("small", f"{plan}  |  Member Services (555) 010-01{40 + i}"), ("rule", ""),
             ("b", "NOTICE OF DENIAL OF COVERAGE"), ("", f"Date of this notice: {_spoken(notice)}          Case number: {case}"), ("", ""),
             ("", f"Member: {name}          Member ID: {mid}          Date of birth: {_mdy(dob)}"), ("", f"Plan: {plan}"), ("", ""),
             ("b", "What we denied"), ("", service + "."), ("", ""), ("b", "Why we denied it"), ("", f"\"{why}\""), ("", ""),
             ("b", "Coverage rules we used")] + [("", f"{k + 1}. {c}") for k, c in enumerate(crit)] + [
             ("", ""), ("b", "Your right to appeal")] + [("", a) for a in appeal] + [
             ("", f"Send your appeal and records to the Appeals Unit, fax {fax}.")] + (
             [("", "If waiting could seriously harm your health, ask for a fast (expedited) appeal. We decide within 72 hours.")] if expedited else [])
    truth = {"plan": plan, "member_name": name, "member_id": mid, "service": service, "denied_on": notice,
             "reason_category": cat, "reason_quote": why, "criteria": crit, "appeal_by": by if printed == 0 else "",
             "appeal_days": days if printed < 2 else 0, "appeals_fax": fax, "expedited_available": expedited, "case_number": case}
    return {"kind": "denial_letter", "file": f"denial-{i + 1:02d}.png", "lines": lines, "truth": truth,
            "tags": [cat, ["deadline printed", "days only", "no deadline"][printed]]}


_SERVICES = [("99213", "Office visit, established patient", 145.0, 92.0), ("99214", "Office visit, established patient", 210.0, 142.0),
             ("99203", "Office visit, new patient", 230.0, 151.0), ("80053", "Comprehensive metabolic panel", 62.0, 14.0),
             ("85025", "Complete blood count", 38.0, 9.0), ("36415", "Blood draw (venipuncture)", 25.0, 3.0),
             ("93000", "Electrocardiogram (EKG)", 95.0, 21.0), ("71046", "Chest X-ray, 2 views", 180.0, 41.0),
             ("97110", "Therapeutic exercise, 15 min", 85.0, 29.0), ("90471", "Vaccine administration", 40.0, 17.0),
             ("G0438", "Annual wellness visit, first", 260.0, 168.0)]
_BILLERS = ["Harbor Light Internal Medicine", "Cedar Grove Family Practice", "Sunrise Imaging Center", "Riverbend Physical Therapy",
            "Maple Street Medical Group", "Desert Bloom Urgent Care", "North Hill Cardiology", "Juniper Lab Services",
            "Bayview Primary Care", "Granite Peak Orthopedics", "Willow Pediatrics"]


def _claim(i: int) -> dict:
    """One visit: the bill and the plan's EOB for it, with this case's twist."""
    payer, plan, prefix, _, _ = _PAYERS[(i + 2) % len(_PAYERS)]
    name, _ = _PEOPLE[(i + 4) % len(_PEOPLE)]
    twist = ["duplicate", "out_of_network", "already_paid", "clean", "duplicate", "preventive_billed", "out_of_network",
             "already_paid", "clean", "duplicate", "out_of_network"][i]
    picks = [_SERVICES[(i + k * 3) % len(_SERVICES)] for k in range(2 + i % 3)]
    oon = twist == "out_of_network"
    bill_lines = [{"code": c, "description": d, "amount": round(amt * (1.6 if oon else 1), 2)} for c, d, amt, _ in picks]
    if twist == "duplicate":
        bill_lines.insert(1, dict(bill_lines[0]))
    eob_lines = []
    for c, d, amt, paid in picks:
        billed = round(amt * (1.6 if oon else 1), 2)
        you = round(billed - paid * (0.6 if oon else 1), 2) if oon else (0.0 if twist == "preventive_billed" else round(min(20.0, billed - paid), 2))
        eob_lines.append({"code": c, "description": d, "billed": billed, "plan_paid": round(paid * (0.6 if oon else 1), 2), "you_owe": you})
    total = round(sum(x["amount"] for x in bill_lines), 2)
    paid_already = round(sum(x["you_owe"] for x in eob_lines) / 2, 2) if twist == "already_paid" else 0.0
    amount_due = round(total - paid_already, 2)
    svc = f"2026-{(i % 8) + 2:02d}-{(i * 5) % 26 + 1:02d}"
    acct, claim = f"SIM-AC-{51000 + i * 41}", f"SIM-CL-{80100 + i * 53}"
    bl = [("h1", f"{_BILLERS[i]} (fictional)"), ("small", f"Billing (555) 010-01{20 + i}"), ("rule", ""), ("b", "ITEMIZED STATEMENT"),
          ("", f"Account: {acct}          Patient: {name}"), ("", f"Date of service: {_spoken(svc)}          Insurance: {plan}"), ("", ""),
          ("mono", "CODE    DESCRIPTION                               CHARGE")]
    bl += [("mono", f"{x['code']:<8}{x['description'][:40]:<41}${x['amount']:>9,.2f}") for x in bill_lines]
    bl += [("mono", ""), ("mono", f"        {'Total charges':<41}${total:>9,.2f}")]
    if paid_already:
        bl += [("mono", f"        {'Patient payment received':<41}-${paid_already:>8,.2f}")]
    bl += [("mono", f"        {'AMOUNT DUE':<41}${amount_due:>9,.2f}")]
    el = [("h1", f"{payer} (fictional)"), ("small", "Explanation of Benefits  |  THIS IS NOT A BILL"), ("rule", ""),
          ("", f"Member: {name}          Member ID: {prefix}-{61000000 + i * 7654321}"),
          ("", f"Provider: {_BILLERS[i]}" + ("  (out of network)" if oon else "") + f"          Date of service: {_spoken(svc)}"),
          ("", f"Claim number: {claim}"), ("", ""), ("mono", "CODE    SERVICE                            BILLED   PLAN PAID   YOU OWE")]
    el += [("mono", f"{x['code']:<8}{x['description']:<33}${x['billed']:>8,.2f}  ${x['plan_paid']:>8,.2f}  ${x['you_owe']:>7,.2f}") for x in eob_lines]
    tot_owe = round(sum(x["you_owe"] for x in eob_lines), 2)
    el += [("mono", ""), ("mono", f"        {'TOTAL':<33}${sum(x['billed'] for x in eob_lines):>8,.2f}  ${sum(x['plan_paid'] for x in eob_lines):>8,.2f}  ${tot_owe:>7,.2f}")]
    el += [("", ""), ("", "Out-of-network providers may bill you more; see your plan for balance billing rules." if oon else
                     "The provider may not bill you more than the \"You owe\" amount for covered services.")]
    bill = {"kind": "bill", "file": f"bill-{i + 1:02d}.png", "lines": bl, "tags": [twist],
            "truth": {"biller": _BILLERS[i], "patient_name": name, "service_date": svc, "account": acct, "lines": bill_lines, "amount_due": amount_due}}
    eob = {"kind": "eob", "file": f"eob-{i + 1:02d}.png", "lines": el, "tags": [twist],
           "truth": {"payer": payer, "member_name": name, "service_date": svc, "claim": claim, "lines": eob_lines, "total_you_owe": tot_owe}}
    return {"bill": bill, "eob": eob}


def eval_documents() -> list[dict]:
    """33 fictional documents with ground truth: 11 denial letters, 11 bills, 11 EOBs."""
    docs = [_denial(i) for i in range(len(_DENIALS))]
    for i in range(11):
        c = _claim(i)
        docs += [c["bill"], c["eob"]]
    return docs


def text_lines(doc: dict) -> str:
    return "\n".join(t for _, t in doc["lines"]) + "\n" + FOOTER
