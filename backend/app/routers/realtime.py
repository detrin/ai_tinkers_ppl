"""WebSocket channel: one socket per member, one room per group.

Client sends:
  {"type": "position", "lat": 50.08, "lon": 14.42, "accuracy_m": 12}
  {"type": "ping"}
Server sends:
  {"type": "snapshot", "group": {...}}      on connect, and after a plan change
  {"type": "position", "member_id": ..., "position": {...}, "distance_...": ...}
  {"type": "member_joined" | "member_left" | "plan" | "pong" | "error"}
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..hub import hub
from ..services import planner
from ..store import store

log = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])


@router.websocket("/ws/groups/{group_id}")
async def group_socket(websocket: WebSocket, group_id: str, member_id: str) -> None:
    group = store.get(group_id)
    member = store.find_member(group_id, member_id) if group else None
    if group is None or member is None:
        # 1008 = policy violation; the client should re-join over REST first.
        await websocket.close(code=1008, reason="unknown group or member")
        return

    await websocket.accept()
    await hub.join(group_id, websocket)
    await store.set_online(group_id, member_id, True)

    try:
        await websocket.send_json(
            {
                "type": "snapshot",
                "group": planner.annotate_members(group).model_dump(mode="json"),
            }
        )
        await hub.broadcast(
            group_id,
            {"type": "presence", "member_id": member_id, "online": True},
            skip=websocket,
        )

        while True:
            message = await websocket.receive_json()
            kind = message.get("type")

            if kind == "position":
                try:
                    lat = float(message["lat"])
                    lon = float(message["lon"])
                except (KeyError, TypeError, ValueError):
                    await websocket.send_json(
                        {"type": "error", "detail": "position needs numeric lat and lon"}
                    )
                    continue
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    await websocket.send_json(
                        {"type": "error", "detail": "position out of range"}
                    )
                    continue

                updated = await store.set_position(
                    group_id, member_id, lat, lon, message.get("accuracy_m")
                )
                if updated is None:
                    continue
                planner.annotate_members(group)
                await hub.broadcast(
                    group_id,
                    {
                        "type": "position",
                        "member_id": member_id,
                        "position": updated.position.model_dump(mode="json")
                        if updated.position
                        else None,
                        "distance_to_meeting_m": updated.distance_to_meeting_m,
                        "distance_to_next_stop_m": updated.distance_to_next_stop_m,
                    },
                )

            elif kind == "snapshot":
                await websocket.send_json(
                    {
                        "type": "snapshot",
                        "group": planner.annotate_members(group).model_dump(mode="json"),
                    }
                )

            elif kind == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json(
                    {"type": "error", "detail": f"unknown message type {kind!r}"}
                )

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # a bad frame must not take the room down
        log.warning("socket error in group %s: %s", group_id, exc)
    finally:
        await hub.leave(group_id, websocket)
        await store.set_online(group_id, member_id, False)
        await hub.broadcast(
            group_id, {"type": "presence", "member_id": member_id, "online": False}
        )
