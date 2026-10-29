"""Where patient records live.

In memory, keyed by a random session token held in an httpOnly cookie, and
written through to SQLite when PATIENT_DB is set (the Docker image sets it), so
records survive a restart. Single process, like the rest of the app (run
exactly one instance).

Security posture for this build (fictional data only; see docs/COMPLIANCE.md):
  - the database stores a SHA-256 of the session token, never the token, so a
    copy of the file can't be used to sign in;
  - sessions expire after 7 days, matching the cookie;
  - delete() removes the record from memory and disk, and a background agent
    finishing later can't bring it back.
Real data needs real authentication, encryption at rest and an audit log first.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from .models import HealthRecord, Patient

SESSION_DAYS = 7


def _key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PatientStore:
    def __init__(self, db_path: str | None = None):
        self._by_session: dict[str, HealthRecord] = {}
        self._deleted: set[str] = set()
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("CREATE TABLE IF NOT EXISTS records (session_hash TEXT PRIMARY KEY, patient_id TEXT NOT NULL, "
                             "record TEXT NOT NULL, updated_at REAL NOT NULL)")
            self.purge_expired()

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
        if not token or token in self._deleted:
            return None
        rec = self._by_session.get(token)
        if rec is None and self._db is not None:
            with self._lock:
                row = self._db.execute("SELECT record, updated_at FROM records WHERE session_hash = ?", (_key(token),)).fetchone()
            if row and time.time() - row[1] < SESSION_DAYS * 86400:
                rec = self._by_session[token] = HealthRecord.model_validate_json(row[0])
        return rec

    def put(self, token: str, record: HealthRecord) -> None:
        if token in self._deleted:
            return  # deleted means deleted, even if an agent finishes afterwards
        self._by_session[token] = record
        self.save(token)

    def save(self, token: str) -> None:
        if self._db is None or token in self._deleted or token not in self._by_session:
            return
        rec = self._by_session[token]
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)",
                             (_key(token), rec.patient.id, rec.model_dump_json(), time.time()))

    def delete(self, token: str) -> bool:
        """Delete my data: everything for this session, in memory and on disk."""
        existed = self.get(token) is not None
        self._deleted.add(token)
        self._by_session.pop(token, None)
        if self._db is not None:
            with self._lock:
                self._db.execute("DELETE FROM records WHERE session_hash = ?", (_key(token),))
        return existed

    def purge_expired(self) -> int:
        if self._db is None:
            return 0
        with self._lock:
            return self._db.execute("DELETE FROM records WHERE updated_at < ?", (time.time() - SESSION_DAYS * 86400,)).rowcount

    def __len__(self) -> int:
        return len(self._by_session)


_STORE: PatientStore | None = None


def store() -> PatientStore:
    global _STORE
    if _STORE is None:
        _STORE = PatientStore(os.getenv("PATIENT_DB") or None)
    return _STORE


def reset_store() -> None:
    """Tests only."""
    global _STORE
    _STORE = None


def export_json(record: HealthRecord) -> str:
    """The patient can take everything with them, any time (it is theirs)."""
    return json.dumps(record.model_dump(mode="json"), indent=2)
