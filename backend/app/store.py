"""In-process group store with an optional JSON snapshot on disk.

Swap this for Postgres/Supabase later: every caller goes through `store`, and
the method surface is small on purpose.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from pathlib import Path

from .config import settings
from .models import (
    City,
    Group,
    Member,
    MemberPosition,
    Plan,
    Point,
    Proposal,
    SlackThread,
    Transport,
    TripMessage,
)

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike characters

# A Slack thread can run for days, and every message is stored and then
# rewritten on each save. Keep the recent tail, which is all the agent reads.
MAX_MESSAGES_PER_TRIP = 500


def _merge(current: list[str], incoming: list[str]) -> list[str]:
    """Union, case-insensitive, keeping the order things were first said in."""
    seen = {value.casefold() for value in current}
    merged = list(current)
    for value in incoming:
        cleaned = value.strip()
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            merged.append(cleaned)
    return merged


def _join_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


class GroupStore:
    def __init__(self, state_file: Path | None = None) -> None:
        self._groups: dict[str, Group] = {}
        self._by_code: dict[str, str] = {}
        self._by_slack: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._state_file = state_file
        self._load()

    # -- persistence ------------------------------------------------------
    def _load(self) -> None:
        if not self._state_file or not self._state_file.exists():
            return
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
            for payload in raw.get("groups", []):
                group = Group.model_validate(payload)
                for member in group.members:
                    member.online = False  # sockets do not survive a restart
                self._groups[group.id] = group
                self._by_code[group.join_code] = group.id
                if group.slack_thread is not None:
                    self._by_slack[group.slack_thread.key] = group.id
        except Exception:  # a corrupt snapshot must not stop the server
            self._groups.clear()
            self._by_code.clear()
            self._by_slack.clear()

    def _save(self) -> None:
        if not self._state_file:
            return
        payload = {"groups": [g.model_dump(mode="json") for g in self._groups.values()]}
        tmp = self._state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self._state_file)

    # -- groups -----------------------------------------------------------
    async def create_group(
        self,
        name: str,
        city: City,
        interests: list[str],
        transport: Transport,
        slack_thread: SlackThread | None = None,
    ) -> Group:
        async with self._lock:
            code = _join_code()
            while code in self._by_code:
                code = _join_code()
            group = Group(
                id=uuid.uuid4().hex[:12],
                name=name,
                join_code=code,
                city=city,
                created_at=time.time(),
                interests=interests,
                transport=transport,
                slack_thread=slack_thread,
            )
            self._groups[group.id] = group
            self._by_code[code] = group.id
            if slack_thread is not None:
                self._by_slack[slack_thread.key] = group.id
            self._save()
            return group

    def get_by_slack_thread(self, thread: SlackThread) -> Group | None:
        gid = self._by_slack.get(thread.key)
        return self._groups.get(gid) if gid else None

    def get(self, group_id: str) -> Group | None:
        return self._groups.get(group_id)

    def get_by_code(self, join_code: str) -> Group | None:
        gid = self._by_code.get(join_code.strip().upper())
        return self._groups.get(gid) if gid else None

    def list_groups(self) -> list[Group]:
        return list(self._groups.values())

    # -- members ----------------------------------------------------------
    async def add_member(self, group_id: str, display_name: str) -> Member | None:
        async with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                return None
            member = Member(
                id=uuid.uuid4().hex[:12],
                display_name=display_name,
                joined_at=time.time(),
            )
            group.members.append(member)
            self._save()
            return member

    def find_member(self, group_id: str, member_id: str) -> Member | None:
        group = self._groups.get(group_id)
        if group is None:
            return None
        return next((m for m in group.members if m.id == member_id), None)

    async def remove_member(self, group_id: str, member_id: str) -> bool:
        async with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                return False
            before = len(group.members)
            group.members = [m for m in group.members if m.id != member_id]
            changed = len(group.members) != before
            if changed:
                self._save()
            return changed

    async def set_position(
        self, group_id: str, member_id: str, lat: float, lon: float, accuracy_m: float | None
    ) -> Member | None:
        async with self._lock:
            member = self.find_member(group_id, member_id)
            if member is None:
                return None
            member.position = MemberPosition(
                lat=lat, lon=lon, accuracy_m=accuracy_m, updated_at=time.time()
            )
            # Deliberately not persisted. A phone reports its position every few
            # seconds, and _save rewrites every group in the store, so writing
            # here costs O(everything) per tick and scales with the square of
            # how busy the server is. A position is also worthless after a
            # restart: clients re-report within seconds of reconnecting.
            return member

    async def set_online(self, group_id: str, member_id: str, online: bool) -> Member | None:
        member = self.find_member(group_id, member_id)
        if member is None:
            return None
        member.online = online
        return member

    # -- travellers, messages, proposals -----------------------------------
    async def upsert_traveler(
        self,
        group_id: str,
        member_id: str,
        *,
        slack_user_id: str | None = None,
        budget: float | None = None,
        currency: str | None = None,
        preferences: list[str] | None = None,
        constraints: list[str] | None = None,
    ) -> Member | None:
        """Merge, never replace: the agent reports one detail at a time."""
        async with self._lock:
            member = self.find_member(group_id, member_id)
            if member is None:
                return None
            if slack_user_id is not None:
                member.slack_user_id = slack_user_id
            if budget is not None:
                member.budget = budget
            if currency is not None:
                member.currency = currency.upper()
            if preferences is not None:
                member.preferences = _merge(member.preferences, preferences)
            if constraints is not None:
                member.constraints = _merge(member.constraints, constraints)
            self._save()
            return member

    async def append_message(
        self,
        group_id: str,
        source: str,
        text: str,
        source_message_id: str | None,
        author_id: str | None,
        author_name: str | None,
    ) -> tuple[TripMessage | None, bool]:
        """Returns (message, is_new).

        Slack redelivers. A message that carries a source id is stored once;
        the replay gets the original back and writes nothing.
        """
        async with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                return None, False

            if source_message_id is not None:
                existing = next(
                    (
                        m
                        for m in group.messages
                        if m.source == source and m.source_message_id == source_message_id
                    ),
                    None,
                )
                if existing is not None:
                    return existing, False

            message = TripMessage(
                id=uuid.uuid4().hex[:12],
                source=source,  # type: ignore[arg-type]
                source_message_id=source_message_id,
                author_id=author_id,
                author_name=author_name,
                text=text,
                created_at=time.time(),
            )
            group.messages.append(message)
            if len(group.messages) > MAX_MESSAGES_PER_TRIP:
                del group.messages[:-MAX_MESSAGES_PER_TRIP]
            self._save()
            return message, True

    async def add_proposal(
        self, group_id: str, proposal: Proposal, idempotency_key: str | None
    ) -> tuple[Proposal | None, bool]:
        """Returns (proposal, is_new). A repeated idempotency key returns the
        proposal it made the first time, so a redelivered Slack button does not
        stack up identical itineraries."""
        async with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                return None, False

            if idempotency_key is not None:
                existing = next(
                    (p for p in group.proposals if p.id == idempotency_key), None
                )
                if existing is not None:
                    return existing, False
                proposal = proposal.model_copy(update={"id": idempotency_key})

            group.proposals.append(proposal)
            self._save()
            return proposal, True

    def find_proposal(self, group_id: str, proposal_id: str) -> Proposal | None:
        group = self._groups.get(group_id)
        if group is None:
            return None
        return next((p for p in group.proposals if p.id == proposal_id), None)

    async def decide_proposal(
        self, group_id: str, proposal_id: str, status: str, decided_by: str | None
    ) -> tuple[Proposal | None, bool]:
        """Approve or decline. Returns (proposal, changed).

        Deciding twice the same way is not an error and writes nothing: Slack
        can deliver the same button press more than once. Approving promotes
        the proposal's itinerary to the group's plan; declining never writes
        an itinerary anywhere.
        """
        async with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                return None, False
            proposal = next((p for p in group.proposals if p.id == proposal_id), None)
            if proposal is None:
                return None, False
            if proposal.status == status:
                return proposal, False

            proposal.status = status  # type: ignore[assignment]
            proposal.decided_at = time.time()
            proposal.decided_by = decided_by

            if status == "approved":
                group.plan = proposal.plan
                group.meeting_point = proposal.plan.meeting_point
                # One approved itinerary at a time: supersede the others.
                for other in group.proposals:
                    if other.id != proposal.id and other.status == "approved":
                        other.status = "declined"
                        other.decided_at = time.time()

            self._save()
            return proposal, True

    # -- plan -------------------------------------------------------------
    async def set_plan(self, group_id: str, plan: Plan, meeting: Point) -> None:
        async with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                return
            group.plan = plan
            group.meeting_point = meeting
            self._save()

    async def set_preferences(
        self, group_id: str, interests: list[str] | None, transport: Transport | None
    ) -> None:
        async with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                return
            if interests is not None:
                group.interests = interests
            if transport is not None:
                group.transport = transport
            self._save()


store = GroupStore(settings.state_file)
