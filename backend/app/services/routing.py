"""Real-world distances between points, and the order to walk them in.

Provider order: OpenRouteService (needs a free key) -> OSRM (keyless public
demo) -> straight-line estimate. The estimate always works, so the endpoint
never fails just because a routing host is down.
"""
from __future__ import annotations

import logging
from typing import Sequence

from ..config import settings
from ..geo import Coord, straight_line_matrix
from . import http

log = logging.getLogger(__name__)

Matrix = list[list[float]]

_ORS_PROFILE = {
    "foot": "foot-walking",
    "bike": "cycling-regular",
    "car": "driving-car",
}
_OSRM_PROFILE = {"foot": "foot", "bike": "bike", "car": "driving"}


async def _ors_matrix(points: Sequence[Coord], transport: str) -> tuple[Matrix, Matrix]:
    profile = _ORS_PROFILE.get(transport, "foot-walking")
    response = await http.client().post(
        f"{settings.ors_url}/v2/matrix/{profile}",
        headers={
            "Authorization": settings.ors_api_key or "",
            "Content-Type": "application/json",
        },
        json={
            "locations": [[lon, lat] for lat, lon in points],
            "metrics": ["distance", "duration"],
            "units": "m",
        },
    )
    response.raise_for_status()
    body = response.json()
    return body["distances"], body["durations"]


async def _osrm_matrix(
    points: Sequence[Coord], transport: str
) -> tuple[Matrix, Matrix, str]:
    # The public demo server only carries the car profile; a self-hosted OSRM
    # can serve foot, in which case set OSRM_PROFILE=foot.
    profile = settings.osrm_profile or _OSRM_PROFILE.get(transport, "driving")
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    response = await http.client().get(
        f"{settings.osrm_url}/table/v1/{profile}/{coords}",
        params={"annotations": "distance,duration"},
    )
    response.raise_for_status()
    body = response.json()
    if body.get("code") != "Ok":
        raise RuntimeError(f"osrm said {body.get('code')}")
    return body["distances"], body["durations"], profile


def _retime_for_walking(distances: Matrix) -> Matrix:
    """Car durations are useless to someone on foot; re-derive them from distance."""
    speed = settings.walking_speed_kmh * 1000 / 3600
    return [[(0.0 if d is None else float(d)) / speed for d in row] for row in distances]


def _clean(matrix: Matrix, fallback: Matrix) -> Matrix:
    """Providers return null for unreachable pairs; patch those from the estimate."""
    return [
        [
            fallback[i][j] if value is None else float(value)
            for j, value in enumerate(row)
        ]
        for i, row in enumerate(matrix)
    ]


async def distance_matrix(
    points: Sequence[Coord], transport: str = "foot"
) -> tuple[Matrix, Matrix, str]:
    """Returns (distances in metres, durations in seconds, provider name)."""
    estimate_d, estimate_t = straight_line_matrix(points, settings.walking_speed_kmh)
    if len(points) < 2:
        return estimate_d, estimate_t, "straight-line"

    if settings.ors_api_key:
        try:
            dist, dur = await _ors_matrix(points, transport)
            return _clean(dist, estimate_d), _clean(dur, estimate_t), "openrouteservice"
        except Exception as exc:
            log.warning("OpenRouteService matrix failed: %s", exc)

    if settings.osrm_url:
        try:
            dist, dur, profile = await _osrm_matrix(points, transport)
            distances = _clean(dist, estimate_d)
            if transport == "foot" and profile not in {"foot", "walking"}:
                durations = _retime_for_walking(distances)
            else:
                durations = _clean(dur, estimate_t)
            return distances, durations, "osrm"
        except Exception as exc:
            log.warning("OSRM matrix failed: %s", exc)

    return estimate_d, estimate_t, "straight-line"


# ---------------------------------------------------------------------------
# Ordering the stops
# ---------------------------------------------------------------------------
def _path_cost(order: Sequence[int], cost: Matrix) -> float:
    return sum(cost[order[i]][order[i + 1]] for i in range(len(order) - 1))


def order_stops(cost: Matrix, start: int = 0) -> list[int]:
    """Open-path travelling-salesman: start fixed, no return leg.

    Nearest neighbour for a first guess, then 2-opt until nothing improves.
    Exact for the handful of stops a group can do in a day.
    """
    n = len(cost)
    if n <= 2:
        return list(range(n))

    unvisited = set(range(n)) - {start}
    order = [start]
    while unvisited:
        last = order[-1]
        nxt = min(unvisited, key=lambda j: cost[last][j])
        order.append(nxt)
        unvisited.remove(nxt)

    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                candidate = order[:i] + order[i : j + 1][::-1] + order[j + 1 :]
                if _path_cost(candidate, cost) + 1e-9 < _path_cost(order, cost):
                    order = candidate
                    improved = True
    return order
