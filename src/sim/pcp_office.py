"""A fictional primary care office on the phone: menu, hold music, transfers.

Stands in for the call PJ's caller agent makes to the patient's own doctor's
office. Deterministic, so the demo and tests always tell the same story. The
staff, extensions and reference numbers are invented.

Live mode (post-hackathon) reuses the scheduling swarm's call worker
(src/agents/worker.py: Muse Spark with press_dtmf and hold handling) against a
real line, with the patient's consent and the same data-minimization rules.
"""
from __future__ import annotations

import hashlib

# The phone menu, in the order the recording reads it.
MENU = [("1", "appointments", "scheduling"), ("2", "prescription refills", "refills"), ("3", "referrals and authorizations", "referrals"),
        ("4", "medical records", "records"), ("5", "billing", "billing"), ("6", "the nurse line", "nurse"), ("0", "the front desk", "front_desk")]

STAFF = {
    "front_desk": ("Tanya", "front desk"),
    "scheduling": ("Jorge", "scheduler"),
    "refills": ("Keisha", "medical assistant (refills)"),
    "referrals": ("Marcus", "referral coordinator"),
    "records": ("Lena", "medical records"),
    "billing": ("Priya", "billing office"),
    "nurse": ("Nurse Dana", "triage nurse"),
    "ma": ("Rob", "the doctor's medical assistant"),
}
HOLD_MINUTES = {"front_desk": 4, "scheduling": 18, "refills": 12, "referrals": 23, "records": 9, "billing": 27, "nurse": 15, "ma": 6}

# What the patient needs -> (menu department to try, who really handles it, what they do, days until done)
PURPOSES: dict[str, dict] = {
    "referral": {"label": "a referral", "try": "referrals", "handler": "referrals", "days": 5,
                 "done": "Referral request entered and sent to the plan for approval."},
    "refill": {"label": "a prescription refill", "try": "refills", "handler": "refills", "days": 2,
               "done": "Refill request sent to the doctor to sign; it goes to the pharmacy on file."},
    "letter": {"label": "a letter or form from the doctor", "try": "front_desk", "handler": "ma", "days": 5,
               "done": "The doctor's medical assistant has the request; the doctor signs and the office faxes it."},
    "order": {"label": "an order for equipment or a service", "try": "referrals", "handler": "ma", "days": 4,
              "done": "Order request routed to the doctor; the signed order goes to the plan and the supplier."},
    "nurse_question": {"label": "a question for the nurse", "try": "nurse", "handler": "nurse", "days": 1,
                       "done": "The nurse took the question and will call back today. PJ passes on exactly what they say."},
    "records": {"label": "medical records", "try": "records", "handler": "records", "days": 10,
                "done": "Records request confirmed in their queue, with the date it's due."},
    "appointment": {"label": "an appointment", "try": "scheduling", "handler": "scheduling", "days": 1,
                    "done": "Soonest opening found and held for the patient to approve."},
    "billing": {"label": "a billing question", "try": "billing", "handler": "billing", "days": 7,
                "done": "Billing put the account on hold and opened a review."},
}


def _ref(*parts: str) -> str:
    return "R-" + str(int(hashlib.sha256("|".join(parts).encode()).hexdigest(), 16) % 90000 + 10000)


def call(practice: str, phone: str | None, purpose: str, who: dict, details: str = "") -> dict:
    """One phone call, start to finish. `who` holds only what may be shared:
    name, dob, member_id, plan (see agents/office_calls.py)."""
    p = PURPOSES.get(purpose, PURPOSES["referral"])
    digit = next(d for d, _, dept in MENU if dept == p["try"])
    first_dept, handler = p["try"], p["handler"]
    menu_read = "; ".join(f"press {d} for {label}" for d, label, _ in MENU)
    t: list[tuple[str, str]] = [
        ("office", f"Thank you for calling {practice}. If this is an emergency, hang up and dial 911. {menu_read.capitalize()}."),
        ("pj", f"[pressed {digit}: {dict((dept, label) for _, label, dept in MENU)[first_dept]}]"),
        ("office", "All of our staff are helping other patients. Please stay on the line; your call will be answered in the order received."),
        ("pj", f"[on hold {HOLD_MINUTES[first_dept]} minutes; PJ keeps the place in line]"),
    ]
    name, role = STAFF[first_dept]
    t.append(("office", f"{practice}, this is {name}. How can I help?"))
    intro = (f"Hi {name}, I'm PJ, an AI assistant calling on behalf of your patient {who['name']}, "
             f"with their permission. I'm calling about {p['label']}.")
    t.append(("pj", intro))
    t.append(("office", "Can I get the patient's date of birth?"))
    t.append(("pj", f"{who['dob'] or 'I can have them call to confirm it'}" + (f", and the member ID is {who['member_id']}." if who.get("member_id") else ".")))
    hold = HOLD_MINUTES[first_dept]
    if handler != first_dept:
        h_name, h_role = STAFF[handler]
        t += [("office", f"Okay, I found them. That's handled by {h_role}. Let me transfer you."),
              ("pj", f"[transferred; on hold {HOLD_MINUTES[handler]} more minutes]"),
              ("office", f"This is {h_name}, {h_role}."),
              ("pj", f"Hi {h_name}, I'm PJ, an AI assistant for {who['name']}. {name} sent me over about {p['label']}.")]
        hold += HOLD_MINUTES[handler]
        name, role = h_name, h_role
    ask = details or p["label"]
    ref = _ref(practice, purpose, who["name"], details)
    t += [("pj", f"The request: {ask}. Can you take care of it, and is there a reference number?"),
          ("office", f"Yes. {p['done']} Your reference is {ref}."),
          ("pj", f"Thank you, {name}. To confirm: {p['done'].lower()} Reference {ref}. When should we expect it?"),
          ("office", f"Give it about {p['days']} business day{'s' if p['days'] != 1 else ''}."),
          ("pj", "Thanks so much. Have a good day.")]
    return {
        "practice": practice, "phone": phone, "purpose": purpose, "purpose_label": p["label"],
        "menu_path": f"pressed {digit}" + (f", then transferred to {role}" if handler != first_dept else ""),
        "hold_minutes": hold, "reached": f"{name}, {role}", "reference": ref,
        "result": p["done"], "days": p["days"], "transcript": [{"speaker": s, "text": x} for s, x in t],
    }
