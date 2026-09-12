"""Scan a city for places worth visiting, using Overpass (OpenStreetMap).

Keyless and unmetered. The output is a candidate list; the AI pass in
`ranking.py` decides which of these the group actually wants.
"""
from __future__ import annotations

import asyncio
from typing import Any

from ..config import settings
from ..geo import haversine_m
from ..models import Place
from . import http

# (OSM key, OSM value) -> (category, prior). The prior is how interesting the
# place type is before anything is known about this group. Keep the spread wide:
# if everything scores 0.8 the heuristic fallback has nothing to sort on.
_TAG_WEIGHTS: dict[tuple[str, str], tuple[str, float]] = {
    ("tourism", "museum"): ("sight", 0.82),
    ("tourism", "attraction"): ("sight", 0.78),
    ("tourism", "gallery"): ("sight", 0.70),
    ("tourism", "viewpoint"): ("sight", 0.68),
    ("tourism", "zoo"): ("sight", 0.72),
    ("tourism", "aquarium"): ("sight", 0.70),
    ("tourism", "theme_park"): ("sight", 0.66),
    ("tourism", "artwork"): ("sight", 0.52),
    ("tourism", "picnic_site"): ("outdoors", 0.40),
    ("historic", "castle"): ("history", 0.84),
    ("historic", "archaeological_site"): ("history", 0.72),
    ("historic", "fort"): ("history", 0.72),
    ("historic", "monument"): ("history", 0.68),
    ("historic", "city_gate"): ("history", 0.66),
    ("historic", "manor"): ("history", 0.66),
    ("historic", "ruins"): ("history", 0.64),
    ("historic", "tower"): ("history", 0.62),
    ("historic", "church"): ("history", 0.60),
    ("historic", "memorial"): ("history", 0.50),
    ("leisure", "nature_reserve"): ("outdoors", 0.64),
    ("leisure", "garden"): ("outdoors", 0.58),
    ("leisure", "park"): ("outdoors", 0.56),
    ("leisure", "water_park"): ("outdoors", 0.52),
    ("amenity", "planetarium"): ("culture", 0.68),
    ("amenity", "arts_centre"): ("culture", 0.62),
    ("amenity", "theatre"): ("culture", 0.60),
    ("amenity", "marketplace"): ("culture", 0.58),
    ("amenity", "public_bath"): ("culture", 0.54),
    ("amenity", "cinema"): ("culture", 0.46),
    ("amenity", "biergarten"): ("food", 0.50),
    ("amenity", "cafe"): ("food", 0.44),
    ("amenity", "restaurant"): ("food", 0.44),
    ("amenity", "ice_cream"): ("food", 0.40),
    ("amenity", "bar"): ("food", 0.38),
    ("amenity", "pub"): ("food", 0.38),
    ("amenity", "food_court"): ("food", 0.34),
    ("shop", "art"): ("shopping", 0.44),
    ("shop", "antiques"): ("shopping", 0.42),
    ("shop", "books"): ("shopping", 0.40),
    ("shop", "chocolate"): ("shopping", 0.38),
    ("shop", "bakery"): ("shopping", 0.34),
}

# Same table, grouped by key, for building the Overpass query.
_SELECTORS: dict[str, list[str]] = {}
for _key, _value in _TAG_WEIGHTS:
    _SELECTORS.setdefault(_key, []).append(_value)


class PlacesError(RuntimeError):
    pass


def _build_query(lat: float, lon: float, radius_m: int, limit: int) -> str:
    clauses = "\n".join(
        f'  nwr["{key}"~"^({"|".join(values)})$"](around:{radius_m},{lat:.6f},{lon:.6f});'
        for key, values in _SELECTORS.items()
    )
    return f"[out:json][timeout:60];\n(\n{clauses}\n);\nout center {limit};"


def _classify(tags: dict[str, str]) -> tuple[str, float]:
    """Best matching tag wins, so a castle that is also a museum scores as a castle."""
    best: tuple[str, float] = ("other", 0.3)
    for key, value in tags.items():
        match = _TAG_WEIGHTS.get((key, value))
        if match and match[1] > best[1]:
            best = match
    return best


def _score(tags: dict[str, str], base: float) -> float:
    score = base
    # A Wikipedia or Wikidata entry is the strongest cheap signal that a place
    # is known rather than merely mapped.
    if tags.get("wikidata") or tags.get("wikipedia"):
        score += 0.10
    if tags.get("heritage") or tags.get("heritage:operator"):
        score += 0.03
    if tags.get("website") or tags.get("contact:website"):
        score += 0.02
    if tags.get("image") or tags.get("wikimedia_commons"):
        score += 0.02
    if tags.get("opening_hours"):
        score += 0.01
    return round(min(0.99, score), 3)


def _address(tags: dict[str, str]) -> str | None:
    street = tags.get("addr:street")
    number = tags.get("addr:housenumber")
    city = tags.get("addr:city")
    parts = [" ".join(p for p in (street, number) if p), city]
    joined = ", ".join(p for p in parts if p)
    return joined or None


def _element_to_place(element: dict[str, Any]) -> Place | None:
    tags = element.get("tags") or {}
    name = tags.get("name")
    if not name:
        return None  # unnamed geometry is useless to a visitor

    if element.get("type") == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    if lat is None or lon is None:
        return None

    category, base = _classify(tags)
    return Place(
        id=f"{element.get('type', 'node')}/{element.get('id')}",
        name=name,
        lat=float(lat),
        lon=float(lon),
        category=category,
        tags=[f"{k}={v}" for k, v in tags.items() if k in {"tourism", "historic", "leisure", "amenity", "shop", "cuisine"}],
        base_score=_score(tags, base),
        address=_address(tags),
        website=tags.get("website") or tags.get("contact:website"),
        wikidata=tags.get("wikidata"),
        opening_hours=tags.get("opening_hours"),
    )


def _dedupe(places: list[Place], radius_m: float = 120.0) -> list[Place]:
    """Drop repeats of the same name mapped a few metres apart."""
    kept: list[Place] = []
    by_name: dict[str, list[Place]] = {}
    for place in sorted(places, key=lambda p: p.base_score, reverse=True):
        twin = next(
            (
                other
                for other in by_name.get(place.name.lower(), [])
                if haversine_m((place.lat, place.lon), (other.lat, other.lon)) < radius_m
            ),
            None,
        )
        if twin is not None:
            continue
        by_name.setdefault(place.name.lower(), []).append(place)
        kept.append(place)
    return kept


async def discover(
    lat: float, lon: float, radius_m: int | None = None, limit: int | None = None
) -> list[Place]:
    radius_m = radius_m or settings.search_radius_m
    limit = limit or settings.max_candidates
    query = _build_query(lat, lon, radius_m, limit)

    last_error: Exception | None = None
    for attempt in range(3):  # Overpass returns 429/504 under load; back off
        try:
            response = await http.client().post(
                settings.overpass_url, data={"data": query}
            )
            if response.status_code in (429, 502, 503, 504):
                raise PlacesError(f"overpass busy ({response.status_code})")
            response.raise_for_status()
            elements = response.json().get("elements", [])
            break
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                raise PlacesError(f"place lookup failed: {exc}") from exc
            await asyncio.sleep(1.5 * (attempt + 1))
    else:  # pragma: no cover - loop always breaks or raises
        raise PlacesError(str(last_error))

    places = [p for p in (_element_to_place(e) for e in elements) if p is not None]
    return _dedupe(places)
