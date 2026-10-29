"""A fully set-up fictional patient, for judges and the demo video.

"Load the demo patient" skips onboarding and shows every bucket filled in, a
coverage panel, a verified PCP, a records request that came back, and PJ's
task list mid-flight. Built through the same agents a real sign-up uses, so the
demo exercises the real code paths.
"""
from __future__ import annotations

from ..agents import care_team, circle, coverage, outreach, records, workflows
from ..patient.models import Bucket, Flag, HealthItem, HealthRecord
from ..sim.payers import DEMO_CARDS

DEMO_NAME = "Alex Rivera"
MOM, KID = "Rosa Rivera", "Leo Rivera"


async def build_demo(record: HealthRecord) -> HealthRecord:
    record.patient.dob = "1984-05-09"
    record.patient.zip_code = "60614"
    await coverage.understand_coverage(record, list(DEMO_CARDS)[0], employer="Northwind Logistics")
    pcp = care_team.add_from_directory(record, "SIM-1001")
    await care_team.verify_contact(record, pcp)
    req = records.draft(record, pcp)
    records.sign(record, req.id, record.patient.display_name)
    records.send(record, req.id)
    records.receive(record, req.id)
    record.items.extend([
        HealthItem(bucket=Bucket.connection, kind="need", title="Lives alone, sees friends most weekends", source="you"),
        HealthItem(bucket=Bucket.connection, kind="need", title="Caregiver for a parent, a few evenings a week", source="you",
                   flag=Flag.watch, plain_meaning="Caregiving is real work. PJ can find respite and support programs nearby."),
        HealthItem(bucket=Bucket.connection, kind="need", title="Gets to appointments by bus", source="you"),
        HealthItem(bucket=Bucket.routines, kind="habit", title="Sleep: about 6 hours on weeknights", source="you",
                   flag=Flag.watch, plain_meaning="Many adults do better with 7 or more. Worth tracking for a couple of weeks."),
        HealthItem(bucket=Bucket.routines, kind="habit", title="Lunch out most workdays", source="you"),
        HealthItem(bucket=Bucket.routines, kind="habit", title="Stress: high at work lately", source="you", flag=Flag.watch),
        HealthItem(bucket=Bucket.family_genes, kind="genetic_result", title="No genetic testing on file", source="you",
                   plain_meaning="With a parent who had colon cancer young, ask your PCP whether genetic counseling makes sense."),
    ])
    outreach.set_told(record, ["caregiver_strain"])
    record.patient.onboarding_step = "done"
    await _mom(record)
    await _kid(record)
    return record


async def _mom(account: HealthRecord) -> None:
    """Alex's mother: 78, Medicare Advantage HMO, lives alone, fell this spring.
    Alex holds her healthcare power of attorney (attested), so Alex can sign."""
    cr = circle.add(account, MOM, "parent", "1948-02-11")
    circle.attest_representative(account, cr.id, DEMO_NAME, "healthcare power of attorney")
    rec = cr.record
    rec.patient.zip_code = "60614"
    await coverage.understand_coverage(rec, "BWM-77031882")
    pcp = care_team.add_from_directory(rec, "SIM-1002")
    await care_team.verify_contact(rec, pcp)
    outreach.set_told(rec, ["lives_alone", "recent_fall", "many_medicines", "heart_condition", "no_ride", "hard_to_afford"])
    rec.items.extend([
        HealthItem(bucket=Bucket.clinicals, kind="condition", title="Heart rhythm problem (atrial fibrillation)", source="demo",
                   plain_meaning="On her problem list. Her cardiologist follows it."),
        HealthItem(bucket=Bucket.clinicals, kind="visit", title="Emergency visit after a fall at home", when="2026-04-03",
                   source="demo", flag=Flag.watch, plain_meaning="No broken bones. Worth a fall-risk check at the next visit."),
        HealthItem(bucket=Bucket.clinicals, kind="medication", title="6 daily medicines on her list", source="demo",
                   flag=Flag.watch, plain_meaning="A pharmacist review can catch duplicates and side effects."),
        HealthItem(bucket=Bucket.connection, kind="need", title="Lives alone; Alex visits twice a week", source="you"),
        HealthItem(bucket=Bucket.connection, kind="need", title="Stopped driving last year", source="you", flag=Flag.watch,
                   plain_meaning="Her plan includes free rides to appointments."),
    ])
    rec.patient.onboarding_step = "done"
    # A bill PJ already fixed, and an appeal waiting for Alex's signature.
    bill = workflows.start(rec, "bill_dispute", {"biller": "Harbor Light Internal Medicine", "issue": "duplicate",
                                                 "service_date": "2026-08-14"}, live=False)
    workflows.approve(rec, bill.id, DEMO_NAME, *circle.signer(account, cr))
    workflows.respond(rec, bill.id)
    workflows.start(rec, "pa_appeal", {"service": "Physical therapy at home after her fall",
                                       "reason": "not_medically_necessary", "denied_on": "2026-10-20"}, live=False)


async def _kid(account: HealthRecord) -> None:
    """Alex's son: 9, on Medicaid. Alex is his parent, so Alex manages his care."""
    cr = circle.add(account, KID, "child", "2017-06-02")
    rec = cr.record
    await coverage.understand_coverage(rec, "PSM-30018467")
    pcp = care_team.add_from_directory(rec, "SIM-1003")
    await care_team.verify_contact(rec, pcp)
    rec.items.extend([
        HealthItem(bucket=Bucket.clinicals, kind="condition", title="Asthma, mild", source="demo",
                   plain_meaning="On his problem list. His school has a copy of the action plan."),
        HealthItem(bucket=Bucket.clinicals, kind="immunization", title="Flu shot due this fall", source="demo", flag=Flag.act,
                   plain_meaning="Covered at no cost on his plan."),
    ])
    rec.patient.onboarding_step = "done"

