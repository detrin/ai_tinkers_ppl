"""Turn a group plus a city into an ordered, measured itinerary."""
from __future__ import annotations

import time

from ..geo import Coord, haversine_m, meeting_point
from ..models import Group, Leg, Plan, PlanRequest, Point, Stop
from . import places as places_service
from . import ranking, routing


def group_positions(group: Group) -> list[Coord]:
    return [
        (m.position.lat, m.position.lon) for m in group.members if m.position is not None
    ]


def resolve_start(group: Group, override: Point | None) -> Point:
    """Where the walk begins: an explicit choice, the group's centre, or the city."""
    if override is not None:
        return override
    positions = group_positions(group)
    if positions:
        lat, lon = meeting_point(positions)
        return Point(lat=lat, lon=lon)
    return Point(lat=group.city.lat, lon=group.city.lon)


async def build_plan(group: Group, request: PlanRequest) -> Plan:
    interests = request.interests if request.interests is not None else group.interests
    transport = request.transport or group.transport
    start = resolve_start(group, request.start_from)

    candidates = await places_service.discover(
        start.lat, start.lon, radius_m=request.radius_m
    )
    picked, summary, ranked_by = await ranking.rank_places(
        candidates,
        interests=interests,
        group_size=max(1, len(group.members)),
        city_name=group.city.name,
        max_stops=request.max_stops,
    )

    # Index 0 is the meeting point; the stops follow it.
    points: list[Coord] = [(start.lat, start.lon)] + [(p.lat, p.lon) for p in picked]
    distances, durations, provider = await routing.distance_matrix(points, transport)
    order = routing.order_stops(durations, start=0)

    stops: list[Stop] = []
    legs: list[Leg] = []
    total_distance = total_travel = 0.0

    for position, index in enumerate(order[1:]):
        previous = order[position]  # order[position] is the stop before this one
        leg_distance = float(distances[previous][index])
        leg_duration = float(durations[previous][index])
        total_distance += leg_distance
        total_travel += leg_duration

        legs.append(
            Leg(
                # Indices address the stop list, so a client can draw the line
                # without knowing anything about the ranking order.
                from_index=position - 1,  # -1 here means the meeting point
                to_index=position,
                distance_m=round(leg_distance, 1),
                duration_s=round(leg_duration, 1),
            )
        )
        stops.append(
            Stop(
                order=position,
                place=picked[index - 1],
                distance_from_previous_m=round(leg_distance, 1),
                travel_seconds_from_previous=round(leg_duration, 1),
                distance_from_meeting_m=round(float(distances[0][index]), 1),
            )
        )

    visit_seconds = sum(s.place.suggested_minutes * 60 for s in stops)

    return Plan(
        generated_at=time.time(),
        transport=transport,
        meeting_point=start,
        stops=stops,
        legs=legs,
        total_distance_m=round(total_distance, 1),
        total_travel_seconds=round(total_travel, 1),
        total_visit_seconds=float(visit_seconds),
        routing_provider=provider,
        ranked_by=ranked_by,
        summary=summary,
    )


def annotate_members(group: Group) -> Group:
    """Fill in how far each member is from the meeting point and the next stop.

    Straight-line on purpose: this runs on every position update, and a routed
    distance per member per tick would burn the provider quota for no real gain.
    """
    meeting = group.meeting_point
    next_stop = group.plan.stops[0].place if group.plan and group.plan.stops else None

    for member in group.members:
        if member.position is None:
            member.distance_to_meeting_m = None
            member.distance_to_next_stop_m = None
            continue
        here = (member.position.lat, member.position.lon)
        member.distance_to_meeting_m = (
            round(haversine_m(here, (meeting.lat, meeting.lon)), 1) if meeting else None
        )
        member.distance_to_next_stop_m = (
            round(haversine_m(here, (next_stop.lat, next_stop.lon)), 1)
            if next_stop
            else None
        )
    return group
