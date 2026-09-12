"""Fan-out of live events to every socket watching a group."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def join(self, group_id: str, socket: WebSocket) -> None:
        async with self._lock:
            self._rooms[group_id].add(socket)

    async def leave(self, group_id: str, socket: WebSocket) -> None:
        async with self._lock:
            self._rooms[group_id].discard(socket)
            if not self._rooms[group_id]:
                self._rooms.pop(group_id, None)

    def connection_count(self, group_id: str) -> int:
        return len(self._rooms.get(group_id, ()))

    async def broadcast(
        self, group_id: str, message: dict[str, Any], skip: WebSocket | None = None
    ) -> None:
        async with self._lock:
            targets = [s for s in self._rooms.get(group_id, set()) if s is not skip]
        dead: list[WebSocket] = []
        for socket in targets:
            try:
                await socket.send_json(message)
            except Exception:
                dead.append(socket)
        if dead:
            async with self._lock:
                for socket in dead:
                    self._rooms.get(group_id, set()).discard(socket)


hub = Hub()
