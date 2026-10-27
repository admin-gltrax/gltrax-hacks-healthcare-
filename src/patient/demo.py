"""A fully set-up fictional patient, for judges and the demo video.

"Load the demo patient" skips onboarding and shows every bucket filled in, a
coverage panel, a verified PCP, a records request that came back, and PJ's
task list mid-flight. Built through the same agents a real sign-up uses, so the
demo exercises the real code paths.
"""
from __future__ import annotations

from ..agents import care_team, coverage, records
from ..patient.models import Bucket, Flag, HealthItem, HealthRecord
from ..sim.payers import DEMO_CARDS

DEMO_NAME = "Alex Rivera"


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
    record.patient.onboarding_step = "done"
    return record
