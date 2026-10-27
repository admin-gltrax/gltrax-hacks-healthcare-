"""Where patient records live during the demo.

In memory, keyed by a random session token held in a cookie. Single process,
like the rest of the app (run exactly one instance). Nothing is written to disk
unless PATIENT_STORE_DIR is set, and even then only fictional demo data should
ever pass through it.

Post-hackathon this becomes a real database with encryption at rest, real
authentication and an audit log: see README "Real-world path".
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from .models import HealthRecord, Patient


class PatientStore:
    def __init__(self, directory: str | None = None):
        self._by_session: dict[str, HealthRecord] = {}
        self._dir = Path(directory) if directory else None
        if self._dir:
            self._dir.mkdir(parents=True, exist_ok=True)

    def create(self, display_name: str, email: str | None = None) -> tuple[str, HealthRecord]:
        name = " ".join(display_name.split())[:80]
        if not name:
            raise ValueError("name is required")
        token = secrets.token_urlsafe(24)
        record = HealthRecord(patient=Patient(display_name=name, email=(email or None)))
        self._by_session[token] = record
        self.save(token)
        return token, record

    def get(self, token: str | None) -> HealthRecord | None:
        return self._by_session.get(token or "")

    def put(self, token: str, record: HealthRecord) -> None:
        self._by_session[token] = record
        self.save(token)

    def save(self, token: str) -> None:
        if not self._dir:
            return
        rec = self._by_session[token]
        (self._dir / f"{rec.patient.id}.json").write_text(rec.model_dump_json(indent=2))

    def __len__(self) -> int:
        return len(self._by_session)


_STORE: PatientStore | None = None


def store() -> PatientStore:
    global _STORE
    if _STORE is None:
        _STORE = PatientStore(os.getenv("PATIENT_STORE_DIR") or None)
    return _STORE


def reset_store() -> None:
    """Tests only."""
    global _STORE
    _STORE = None


def export_json(record: HealthRecord) -> str:
    """The patient can take everything with them, any time (it is theirs)."""
    return json.dumps(record.model_dump(mode="json"), indent=2)
