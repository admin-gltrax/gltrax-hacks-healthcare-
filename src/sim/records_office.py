"""What a (fictional) medical-records department sends back.

When a records request is "answered" in the demo, these items are filed into the
patient's buckets with source="records". Post-hackathon the same filing step
takes real documents (C-CDA, FHIR bundles or scanned PDFs read by a vision
model) and turns them into HealthItems.
"""
from __future__ import annotations

from ..patient.models import Bucket, Flag, HealthItem


def records_from(provider_sim_id: str) -> list[HealthItem]:
    r = "records"
    return [
        HealthItem(bucket=Bucket.clinicals, kind="lab", title="A1c (3-month average blood sugar)", value="5.9%",
                   when="2026-06-12", flag=Flag.watch, source=r,
                   plain_meaning="Slightly above the usual range. Worth asking at your next visit what it means for you."),
        HealthItem(bucket=Bucket.clinicals, kind="lab", title="LDL cholesterol", value="142 mg/dL", when="2026-06-12",
                   flag=Flag.watch, source=r, plain_meaning="Higher than many doctors aim for. Ask whether it changes anything."),
        HealthItem(bucket=Bucket.clinicals, kind="lab", title="Kidney function (eGFR)", value="94", when="2026-06-12",
                   flag=Flag.ok, source=r, plain_meaning="In the usual range."),
        HealthItem(bucket=Bucket.clinicals, kind="vital", title="Blood pressure", value="134/86", when="2026-06-12",
                   flag=Flag.watch, source=r, plain_meaning="A little above target. One reading isn't the whole story."),
        HealthItem(bucket=Bucket.clinicals, kind="medication", title="Lisinopril 10 mg, once a day", source=r,
                   plain_meaning="A blood pressure medicine."),
        HealthItem(bucket=Bucket.clinicals, kind="allergy", title="Penicillin (rash)", source=r, flag=Flag.watch,
                   plain_meaning="Make sure every new doctor and pharmacy knows."),
        HealthItem(bucket=Bucket.clinicals, kind="vaccine", title="Flu shot", when="2025-10-04", source=r,
                   plain_meaning="Due again this fall.", flag=Flag.act),
        HealthItem(bucket=Bucket.clinicals, kind="visit", title="Annual physical with your PCP", when="2026-06-12", source=r),
        HealthItem(bucket=Bucket.family_genes, kind="family_history", title="Mother: type 2 diabetes", source=r,
                   flag=Flag.watch, plain_meaning="Family history is one reason doctors check blood sugar more often."),
        HealthItem(bucket=Bucket.family_genes, kind="family_history", title="Father: colon cancer at 52", source=r,
                   flag=Flag.act,
                   plain_meaning="A parent diagnosed before 60 can mean colon screening should start earlier. Ask your PCP when you should start."),
        HealthItem(bucket=Bucket.routines, kind="habit", title="Doctor's note: 'walks 2-3 times a week'", source=r),
    ]
