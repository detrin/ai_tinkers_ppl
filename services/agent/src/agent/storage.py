"""Trip persistence for the hackathon vertical slice.

Swap `InMemoryTripStore` for a database-backed store once `services/api` owns
the `trips` / `candidate_places` / `itinerary_options` schema — the
`TripStore` protocol is the seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pydantic_ai.messages import ModelMessage


@dataclass
class TripRecord:
    trip_id: str
    candidates: list[dict] = field(default_factory=list)
    itineraries: list[dict] = field(default_factory=list)
    # Conversation history for `TripAgent.ask`, so a follow-up question sees
    # prior answers instead of starting a fresh conversation every call.
    messages: list[ModelMessage] = field(default_factory=list)


class TripStore(Protocol):
    def save_candidates(self, trip_id: str, candidates: list[dict]) -> int: ...
    def save_itineraries(self, trip_id: str, itineraries: list[dict]) -> None: ...
    def get(self, trip_id: str) -> TripRecord | None: ...
    def get_messages(self, trip_id: str) -> list[ModelMessage]: ...
    def save_messages(self, trip_id: str, messages: list[ModelMessage]) -> None: ...


class InMemoryTripStore:
    def __init__(self) -> None:
        self._trips: dict[str, TripRecord] = {}

    def _get_or_create(self, trip_id: str) -> TripRecord:
        return self._trips.setdefault(trip_id, TripRecord(trip_id=trip_id))

    def save_candidates(self, trip_id: str, candidates: list[dict]) -> int:
        record = self._get_or_create(trip_id)
        record.candidates.extend(candidates)
        return len(record.candidates)

    def save_itineraries(self, trip_id: str, itineraries: list[dict]) -> None:
        self._get_or_create(trip_id).itineraries = itineraries

    def get(self, trip_id: str) -> TripRecord | None:
        return self._trips.get(trip_id)

    def get_messages(self, trip_id: str) -> list[ModelMessage]:
        record = self._trips.get(trip_id)
        return record.messages if record else []

    def save_messages(self, trip_id: str, messages: list[ModelMessage]) -> None:
        self._get_or_create(trip_id).messages = messages

    def __len__(self) -> int:
        return len(self._trips)
