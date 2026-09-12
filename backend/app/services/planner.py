"""Turn a group plus a city into an ordered, measured itinerary."""
from __future__ import annotations

import time

from ..config import settings
from ..geo import Coord, haversine_m, meeting_point, straight_line_matrix
from ..models import Group, Leg, Plan, PlanRequest, Point, Stop
from . import accessibility
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

    # Find the limit before choosing places, not after. Ranking the whole city
    # and then removing what is too far strands the group with one distant stop;
    # the model has to be choosing from reachable places in the first place.
    limit, constraint_notes = accessibility.walking_limit(group.members)

    candidates = await places_service.discover(
        start.lat, start.lon, radius_m=request.radius_m
    )

    if limit is not None:
        near = [
            place
            for place in candidates
            if haversine_m((start.lat, start.lon), (place.lat, place.lon)) <= limit
        ]
        if near:
            candidates = near
    picked, summary, ranked_by = await ranking.rank_places(
        candidates,
        interests=interests,
        group_size=max(1, len(group.members)),
        city_name=group.city.name,
        max_stops=request.max_stops,
        travelers=group.members,
    )

    # Index 0 is the meeting point; the stops follow it.
    points: list[Coord] = [(start.lat, start.lon)] + [(p.lat, p.lon) for p in picked]
    distances, durations, provider = await routing.distance_matrix(points, transport)
    order = routing.order_stops(durations, start=0)

    # Asking the model to keep it tight is not enough: the route is rebuilt so
    # the limit holds by construction rather than being trimmed and hoped over.
    if limit is not None:
        # Judge the limit on walking distance. Only OpenRouteService gives a real
        # pedestrian profile here; the public OSRM server answers for cars, and a
        # 300 m stroll across a pedestrianised old town comes back as 1.7 km of
        # one-way streets. Holding someone's knee to that number is nonsense, so
        # fall back to the straight-line walking estimate when that is all we have.
        walkable = (
            distances
            if provider in {"openrouteservice", "straight-line"}
            else straight_line_matrix(points, settings.walking_speed_kmh)[0]
        )

        order = _route_within_limit(walkable, limit)
        if len(order) == 1:
            # Nothing at all is close enough. Give the single nearest stop and
            # say plainly that it is further than asked, rather than pretending.
            nearest = min(range(1, len(walkable)), key=lambda j: walkable[0][j])
            order = [0, nearest]
            constraint_notes.append(
                f"nothing lies within {limit} m of the meeting point; the nearest "
                f"stop is about {round(walkable[0][nearest])} m away"
            )
        else:
            constraint_notes.append(f"every leg kept under {limit} m on foot")

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
    dropped = len(picked) - len(stops)
    if limit is not None and dropped > 0:
        constraint_notes.append(
            f"{dropped} stop{'s' if dropped > 1 else ''} left out to stay within it"
        )

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
        constraints_applied=constraint_notes,
    )


def _route_within_limit(
    distances: list[list[float]], limit: int
) -> list[int]:
    """Build a route where every leg is within the limit, by construction.

    Nearest reachable neighbour from the meeting point outward, taking only
    stops within the limit of wherever the group already is. Trimming an
    existing route cannot do this: removing a stop can join two others into a
    leg longer than either, which is how a "shortened" route ends up worse.

    No 2-opt pass afterwards. Reordering could re-introduce a leg over the
    limit, and a slightly longer route everyone can walk beats a shorter one
    somebody cannot.
    """
    unvisited = set(range(1, len(distances)))
    order = [0]

    while unvisited:
        current = order[-1]
        reachable = [j for j in unvisited if distances[current][j] <= limit]
        if not reachable:
            break
        nearest = min(reachable, key=lambda j: distances[current][j])
        order.append(nearest)
        unvisited.discard(nearest)

    return order


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
