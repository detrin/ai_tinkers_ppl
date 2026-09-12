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
from .models import City, Group, Member, MemberPosition, Plan, Point, Transport

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike characters


def _join_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


class GroupStore:
    def __init__(self, state_file: Path | None = None) -> None:
        self._groups: dict[str, Group] = {}
        self._by_code: dict[str, str] = {}
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
        except Exception:  # a corrupt snapshot must not stop the server
            self._groups.clear()
            self._by_code.clear()

    def _save(self) -> None:
        if not self._state_file:
            return
        payload = {"groups": [g.model_dump(mode="json") for g in self._groups.values()]}
        tmp = self._state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self._state_file)

    # -- groups -----------------------------------------------------------
    async def create_group(
        self, name: str, city: City, interests: list[str], transport: Transport
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
            )
            self._groups[group.id] = group
            self._by_code[code] = group.id
            self._save()
            return group

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
            self._save()
            return member

    async def set_online(self, group_id: str, member_id: str, online: bool) -> Member | None:
        member = self.find_member(group_id, member_id)
        if member is None:
            return None
        member.online = online
        return member

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
