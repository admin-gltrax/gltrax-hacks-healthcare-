"""Care circle: manage care for an older parent, a child, or a spouse.

Most healthcare is managed by someone other than the patient: the adult child
on hold for a parent, the parent juggling a child's vaccines. The circle lets
one account hold several people, with access that matches real life and the
law, and that the person can always see:

  - A child under 18: the parent or guardian is their personal representative
    and can view, act and approve. At 18 that ends automatically, and the now
    adult child decides.
  - Another adult: nothing but their name until THEY say yes, and they choose
    what the helper may do (see, and/or have PJ act). Approving bookings and
    signing records requests stays with them.
  - Healthcare power of attorney or guardian: the account holder attests to it
    and can approve on the person's behalf. PJ shows that it is attested, not
    verified (no document check in this demo).

Fictional data only, like everything else here. Real deployments need real
identity verification and documents: see docs/FAMILY-AND-AGING.md.
"""
from __future__ import annotations

from ..patient.models import CareRecipient, HealthRecord, Patient, Permission, Relation, _now, age_on

ALL: list[Permission] = ["view", "act", "approve"]
HELPER_CHOICES: list[Permission] = ["view", "act"]  # an adult never hands approval to a helper here


class NotAllowed(Exception):
    """The account holder doesn't have that permission for this person."""


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()).lower() == " ".join(b.split()).lower()


def add(account: HealthRecord, name: str, relation: Relation, dob: str | None = None) -> CareRecipient:
    name = " ".join((name or "").split())[:80]
    if not name:
        raise ValueError("name is required")
    if len(account.circle) >= 8:
        raise ValueError("a care circle holds up to 8 people")
    rec = HealthRecord(patient=Patient(display_name=name, dob=dob))
    first = name.split()[0]
    age = age_on(dob)
    if age is not None and age < 18:
        cr = CareRecipient(relation=relation, authority="parent_of_minor", permissions=list(ALL), record=rec,
                           consented_at=_now(),
                           consent_note=f"You're {first}'s parent or guardian, so you can see and manage {first}'s care. "
                                        f"When {first} turns 18, {first} decides who helps.")
    else:
        cr = CareRecipient(relation=relation, authority="pending_consent", permissions=[], record=rec,
                           consent_note=f"Waiting for {first} to say yes. Until then PJ shows only {first}'s name.")
    account.circle.append(cr)
    return cr


def find(account: HealthRecord, person_id: str) -> CareRecipient:
    cr = next((c for c in account.circle if c.id == person_id), None)
    if cr is None:
        raise KeyError(person_id)
    _age_out(cr)
    return cr


def _age_out(cr: CareRecipient) -> None:
    """A parent's automatic access ends at 18."""
    age = age_on(cr.record.patient.dob)
    if cr.authority == "parent_of_minor" and age is not None and age >= 18:
        first = cr.record.patient.display_name.split()[0]
        cr.authority, cr.permissions, cr.consented_at = "pending_consent", [], None
        cr.consent_note = f"{first} is 18 now, so {first} decides who helps. Ask {first} to say yes again."


def consent(account: HealthRecord, person_id: str, typed_name: str, permissions: list[str]) -> CareRecipient:
    """The person themself says yes, by typing their own name (in the demo, on the helper's phone)."""
    cr = find(account, person_id)
    if cr.authority == "parent_of_minor":
        raise ValueError("a parent already manages a minor's care")
    if not _same(typed_name, cr.record.patient.display_name):
        raise NotAllowed(f"Only {cr.record.patient.display_name} can say yes. They type their own name.")
    chosen = [p for p in HELPER_CHOICES if p in permissions]
    if "act" in chosen and "view" not in chosen:
        chosen.insert(0, "view")
    if not chosen:
        raise ValueError("choose at least what the helper may see")
    first = cr.record.patient.display_name.split()[0]
    helper = account.patient.display_name.split()[0]
    cr.authority, cr.permissions, cr.consented_at = "consented_helper", chosen, _now()
    cr.consent_note = (f"{first} said yes on {cr.consented_at[:10]}: {helper} can "
                       + ("see and ask PJ to act" if "act" in chosen else "see")
                       + f". {first} still approves bookings and signs requests, and can take this back any time.")
    return cr


def attest_representative(account: HealthRecord, person_id: str, typed_name: str, document: str) -> CareRecipient:
    """The account holder attests to a healthcare power of attorney or guardianship."""
    cr = find(account, person_id)
    if not _same(typed_name, account.patient.display_name):
        raise NotAllowed("Type your own full name to attest.")
    document = (document or "healthcare power of attorney").strip()[:60]
    first = cr.record.patient.display_name.split()[0]
    cr.authority, cr.permissions, cr.consented_at = "legal_representative", list(ALL), _now()
    cr.consent_note = (f"You attested on {cr.consented_at[:10]} that you hold {document} for {first}. "
                       "PJ hasn't checked the document; a real deployment would.")
    return cr


def revoke(account: HealthRecord, person_id: str) -> None:
    """Either side can end it. The person's record leaves the account holder's view."""
    cr = find(account, person_id)
    account.circle.remove(cr)
    if account.active_id == cr.id:
        account.active_id = None


def resolve(account: HealthRecord) -> tuple[HealthRecord, CareRecipient | None]:
    """The record the dashboard is showing, and the relationship (None = the account holder)."""
    if account.active_id:
        try:
            cr = find(account, account.active_id)
        except KeyError:
            account.active_id = None
        else:
            return cr.record, cr
    return account, None


def can(cr: CareRecipient | None, perm: Permission) -> bool:
    return cr is None or perm in cr.permissions


def require(cr: CareRecipient | None, perm: Permission) -> None:
    if not can(cr, perm):
        first = cr.record.patient.display_name.split()[0]
        why = {
            "view": f"{first} hasn't said yes yet.",
            "act": f"{first} lets you see, but hasn't asked PJ to act for you.",
            "approve": f"Only {first} can approve this (or someone with healthcare power of attorney).",
        }[perm]
        raise NotAllowed(why)


def signer(account: HealthRecord, cr: CareRecipient | None) -> tuple[str, str | None]:
    """Whose typed name signs for this record, and in what capacity."""
    if cr is None:
        return account.patient.display_name, None
    if cr.authority == "parent_of_minor":
        return account.patient.display_name, f"parent or guardian of {cr.record.patient.display_name}"
    if cr.authority == "legal_representative":
        return account.patient.display_name, f"personal representative of {cr.record.patient.display_name}"
    return cr.record.patient.display_name, None  # the person signs for themself


def summary(account: HealthRecord) -> list[dict]:
    people = [{"id": None, "name": account.patient.display_name, "relation": "you", "authority": "self",
               "permissions": list(ALL), "active": account.active_id is None, "age": age_on(account.patient.dob),
               "consent_note": "Your own care."}]
    for cr in account.circle:
        _age_out(cr)
        people.append({"id": cr.id, "name": cr.record.patient.display_name, "relation": cr.relation,
                       "authority": cr.authority, "permissions": cr.permissions, "active": account.active_id == cr.id,
                       "age": age_on(cr.record.patient.dob) if "view" in cr.permissions else None,
                       "consent_note": cr.consent_note})
    return people
