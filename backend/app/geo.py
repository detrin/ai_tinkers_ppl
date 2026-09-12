"""Pure-geometry helpers. No network, no state."""
from __future__ import annotations

import math
from typing import Iterable, Sequence

EARTH_RADIUS_M = 6_371_008.8
Coord = tuple[float, float]  # (lat, lon)


def haversine_m(a: Coord, b: Coord) -> float:
    """Great-circle distance in metres between two (lat, lon) points."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def centroid(points: Sequence[Coord]) -> Coord:
    """Average position, computed on the unit sphere so it survives the date line."""
    if not points:
        raise ValueError("centroid of an empty set")
    x = y = z = 0.0
    for lat, lon in points:
        rlat, rlon = math.radians(lat), math.radians(lon)
        x += math.cos(rlat) * math.cos(rlon)
        y += math.cos(rlat) * math.sin(rlon)
        z += math.sin(rlat)
    n = len(points)
    x, y, z = x / n, y / n, z / n
    lon = math.atan2(y, x)
    lat = math.atan2(z, math.hypot(x, y))
    return (math.degrees(lat), math.degrees(lon))


def meeting_point(points: Sequence[Coord], iterations: int = 64) -> Coord:
    """Geometric median: the spot that minimises total walking for the group.

    Weiszfeld's algorithm. Unlike the centroid this is not dragged around by one
    member who is far away, which is what you want when picking where to meet.
    """
    if not points:
        raise ValueError("meeting point of an empty set")
    if len(points) <= 2:
        return centroid(points)

    current = centroid(points)
    for _ in range(iterations):
        num_lat = num_lon = denom = 0.0
        for p in points:
            d = haversine_m(current, p)
            if d < 1.0:  # standing on a member: that point is already optimal
                return p
            w = 1.0 / d
            num_lat += p[0] * w
            num_lon += p[1] * w
            denom += w
        nxt = (num_lat / denom, num_lon / denom)
        if haversine_m(nxt, current) < 0.5:
            return nxt
        current = nxt
    return current


def bounding_box(points: Iterable[Coord]) -> tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon)."""
    lats, lons = zip(*points)
    return (min(lats), min(lons), max(lats), max(lons))


def walking_seconds(distance_m: float, speed_kmh: float) -> float:
    return distance_m / (speed_kmh * 1000 / 3600)


def straight_line_matrix(
    points: Sequence[Coord], speed_kmh: float, detour_factor: float = 1.31
) -> tuple[list[list[float]], list[list[float]]]:
    """Fallback distance/duration matrices when no routing provider answers.

    Street networks are longer than a straight line; the detour factor is the
    usual correction for dense European city centres.
    """
    n = len(points)
    dist = [[0.0] * n for _ in range(n)]
    dur = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_m(points[i], points[j]) * detour_factor
            t = walking_seconds(d, speed_kmh)
            dist[i][j] = dist[j][i] = d
            dur[i][j] = dur[j][i] = t
    return dist, dur
