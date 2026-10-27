"""The four plain-language buckets of the dashboard, plus the two "how care
works for you" panels. Names are what a patient would say, not what a chart
would say. Keep them short; PJ explains the rest."""
from __future__ import annotations

from .models import Bucket

BUCKETS: dict[Bucket, dict] = {
    Bucket.connection: {
        "name": "Life & Connection",
        "tagline": "The people and things around you that shape your health.",
        "covers": [
            "who you can lean on", "loneliness", "caregiving", "housing", "food",
            "getting to appointments", "money stress", "work", "safety at home",
        ],
        "clinical_term": "social determinants of health (SDOH)",
        "pj": "Health isn't only what happens at the doctor. This is the rest of your life, the part that matters most.",
    },
    Bucket.clinicals: {
        "name": "Clinicals",
        "tagline": "Your lab results, conditions, medicines and visits, explained.",
        "covers": ["lab results", "conditions", "medicines", "allergies", "vaccines", "visits", "imaging"],
        "clinical_term": "problem list, results, medication list, encounters",
        "pj": "This is what your doctors have on file, in plain words. If something's flagged, I'll tell you what to ask about.",
    },
    Bucket.routines: {
        "name": "Routines",
        "tagline": "Food, movement, sleep and stress: the everyday stuff.",
        "covers": ["what you eat", "movement", "sleep", "stress", "alcohol and smoking", "screen time"],
        "clinical_term": "lifestyle and behavioral factors",
        "pj": "Small habits add up. We track the few that matter for you, not everything.",
    },
    Bucket.family_genes: {
        "name": "Family & Genes",
        "tagline": "What runs in your family, and what to keep an eye on.",
        "covers": ["family history", "genetic test results", "screenings to start early"],
        "clinical_term": "family history, hereditary risk, genomics",
        "pj": "Your family's story can change when screenings should start. Tell me what you know and I'll show what it means.",
    },
}

PANELS = {
    "coverage": {
        "name": "My Coverage",
        "tagline": "Your insurance in plain English: what's covered, what it costs, what you've used.",
    },
    "care_team": {
        "name": "My Care Team",
        "tagline": "Your doctor, specialists and pharmacy, with the right phone and fax numbers.",
    },
    "tasks": {
        "name": "What PJ is doing for you",
        "tagline": "The calls, forms and follow-ups, handled. You only see what needs you.",
    },
}


def bucket_meta() -> list[dict]:
    return [{"key": b.value, **meta} for b, meta in BUCKETS.items()]
