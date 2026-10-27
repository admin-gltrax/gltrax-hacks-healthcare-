"""How a records request physically leaves the building.

Medical-records departments still run on fax, so the Records agent sends
through a `FaxChannel`. The hackathon build only has `SimulatedFax`, which
"delivers" to the fictional directory and fails for numbers that are stale.
A real adapter (a HIPAA-eligible fax API under a BAA) is post-hackathon; see
README "Real-world path".
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from ..sim.providers import PROVIDERS


@dataclass
class FaxResult:
    ok: bool
    fax_id: str
    detail: str


class FaxChannel(Protocol):
    def send(self, to_number: str, pages: list[str]) -> FaxResult: ...


class SimulatedFax:
    """Succeeds for a provider's true fax; fails ("no fax tone") for a stale one."""

    def __init__(self):
        self.outbox: list[dict] = []

    def send(self, to_number: str, pages: list[str]) -> FaxResult:
        fax_id = f"fax_{uuid.uuid4().hex[:8]}"
        live = {p.true_fax for p in PROVIDERS}
        ok = to_number in live
        self.outbox.append({"fax_id": fax_id, "to": to_number, "pages": len(pages), "ok": ok})
        return FaxResult(ok, fax_id, "delivered" if ok else "no fax tone at that number")
