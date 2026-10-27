"""Shared state across concurrent calls.

Privacy by design: workers only ever see *times* of held slots at other offices
(never office names or transcripts), so honest leverage works without leaking
anything between calls.
"""
from __future__ import annotations

from ..schemas import Constraints, Offer


class Blackboard:
    def __init__(self, constraints: Constraints):
        self.constraints = constraints
        self.offers: dict[str, Offer] = {}  # key: office_id|slot
        self.facts: dict[str, dict] = {}

    def add_offer(self, offer: Offer) -> bool:
        """Upsert an offer. Returns True if the best offer changed."""
        before = self.best()
        self.offers[f"{offer.office_id}|{offer.slot_start}"] = offer
        after = self.best()
        return (before.offer_id if before else None) != (after.offer_id if after else None)

    def valid_held(self) -> list[Offer]:
        return [o for o in self.offers.values() if o.held and self.constraints.slot_ok(o.slot_start)]

    def best(self) -> Offer | None:
        held = self.valid_held()
        return min(held, key=lambda o: o.slot_start) if held else None

    def held_slots_excluding(self, office_id: str) -> list[str]:
        return sorted(o.slot_start for o in self.valid_held() if o.office_id != office_id)

    def record_fact(self, office_id: str, field: str, value: str) -> None:
        self.facts.setdefault(office_id, {})[field] = value

    def leaderboard(self) -> list[Offer]:
        return sorted(self.valid_held(), key=lambda o: o.slot_start)
