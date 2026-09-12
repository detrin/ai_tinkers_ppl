"""Group lifecycle, membership, live positions, and the itinerary endpoint."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..hub import hub
from ..models import (
    City,
    CreateGroupRequest,
    Group,
    JoinGroupRequest,
    Member,
    Place,
    Plan,
    PlanRequest,
    PositionRequest,
)
from ..services import geocode, planner
from ..services import places as places_service
from ..store import store

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["groups"])


def _require_group(group_id: str) -> Group:
    group = store.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    return group


def _require_member(group_id: str, member_id: str) -> Member:
    member = store.find_member(group_id, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="member not found in this group")
    return member


# ---------------------------------------------------------------------------
# Cities and places, usable without a group (handy for a search screen)
# ---------------------------------------------------------------------------
@router.get("/cities/resolve", response_model=City)
async def resolve_city(q: str = Query(min_length=1, description="City name")) -> City:
    try:
        return await geocode.resolve_city(q)
    except geocode.GeocodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/places", response_model=list[Place])
async def scan_city(
    city: str = Query(min_length=1),
    radius_m: int | None = Query(default=None, ge=250, le=20_000),
    limit: int = Query(default=60, ge=1, le=300),
) -> list[Place]:
    """What is interesting around a city centre, before any group is involved."""
    try:
        resolved = await geocode.resolve_city(city)
        found = await places_service.discover(resolved.lat, resolved.lon, radius_m)
    except geocode.GeocodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except places_service.PlacesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return sorted(found, key=lambda p: p.base_score, reverse=True)[:limit]


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------
@router.post("/groups", response_model=Group, status_code=201)
async def create_group(request: CreateGroupRequest) -> Group:
    try:
        city = await geocode.resolve_city(request.city)
    except geocode.GeocodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await store.create_group(
        name=request.name,
        city=city,
        interests=request.interests,
        transport=request.transport,
    )


@router.get("/groups/{group_id}", response_model=Group)
async def get_group(group_id: str) -> Group:
    return planner.annotate_members(_require_group(group_id))


@router.get("/groups/by-code/{join_code}", response_model=Group)
async def get_group_by_code(join_code: str) -> Group:
    group = store.get_by_code(join_code)
    if group is None:
        raise HTTPException(status_code=404, detail="no group has that join code")
    return planner.annotate_members(group)


@router.post("/groups/{group_id}/members", response_model=Member, status_code=201)
async def join_group(group_id: str, request: JoinGroupRequest) -> Member:
    group = _require_group(group_id)
    if request.join_code and request.join_code.strip().upper() != group.join_code:
        raise HTTPException(status_code=403, detail="wrong join code")

    member = await store.add_member(group_id, request.display_name)
    if member is None:
        raise HTTPException(status_code=404, detail="group not found")

    await hub.broadcast(
        group_id,
        {"type": "member_joined", "member": member.model_dump(mode="json")},
    )
    return member


@router.delete("/groups/{group_id}/members/{member_id}", status_code=204)
async def leave_group(group_id: str, member_id: str) -> None:
    _require_group(group_id)
    if not await store.remove_member(group_id, member_id):
        raise HTTPException(status_code=404, detail="member not found in this group")
    await hub.broadcast(group_id, {"type": "member_left", "member_id": member_id})


# ---------------------------------------------------------------------------
# Live positions
# ---------------------------------------------------------------------------
@router.put("/groups/{group_id}/members/{member_id}/position", response_model=Group)
async def update_position(
    group_id: str, member_id: str, request: PositionRequest
) -> Group:
    """REST twin of the WebSocket position message, for clients that prefer polling."""
    group = _require_group(group_id)
    _require_member(group_id, member_id)

    member = await store.set_position(
        group_id, member_id, request.lat, request.lon, request.accuracy_m
    )
    if member is None:
        raise HTTPException(status_code=404, detail="member not found in this group")

    annotated = planner.annotate_members(group)
    await hub.broadcast(
        group_id,
        {
            "type": "position",
            "member_id": member_id,
            "position": member.position.model_dump(mode="json") if member.position else None,
            "distance_to_meeting_m": member.distance_to_meeting_m,
            "distance_to_next_stop_m": member.distance_to_next_stop_m,
        },
    )
    return annotated


@router.get("/groups/{group_id}/members", response_model=list[Member])
async def list_members(group_id: str) -> list[Member]:
    """Everyone in the group with their last known position and distances."""
    return planner.annotate_members(_require_group(group_id)).members


# ---------------------------------------------------------------------------
# The itinerary
# ---------------------------------------------------------------------------
@router.post("/groups/{group_id}/plan", response_model=Plan)
async def create_plan(group_id: str, request: PlanRequest) -> Plan:
    group = _require_group(group_id)
    await store.set_preferences(group_id, request.interests, request.transport)

    try:
        plan = await planner.build_plan(group, request)
    except places_service.PlacesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not plan.stops:
        raise HTTPException(
            status_code=404,
            detail="nothing worth visiting was found here; try a larger radius",
        )

    await store.set_plan(group_id, plan, plan.meeting_point)
    await hub.broadcast(
        group_id, {"type": "plan", "plan": plan.model_dump(mode="json")}
    )
    return plan


@router.get("/groups/{group_id}/plan", response_model=Plan)
async def get_plan(group_id: str) -> Plan:
    group = _require_group(group_id)
    if group.plan is None:
        raise HTTPException(status_code=404, detail="this group has no plan yet")
    return group.plan
