"""City name -> coordinates, via Nominatim (OpenStreetMap). No key required."""
from __future__ import annotations

from ..config import settings
from ..models import City
from . import http

_cache: dict[str, City] = {}


class GeocodeError(RuntimeError):
    pass


async def resolve_city(query: str) -> City:
    key = query.strip().lower()
    if key in _cache:
        return _cache[key]

    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
        # Keep the answer to things a group can actually walk around in.
        "featuretype": "settlement",
    }
    try:
        response = await http.client().get(
            f"{settings.nominatim_url}/search", params=params
        )
        response.raise_for_status()
        results = response.json()
    except Exception as exc:  # network, DNS, rate limit, malformed JSON
        raise GeocodeError(f"could not reach the geocoder: {exc}") from exc

    if not results:
        raise GeocodeError(f"no place called {query!r} was found")

    hit = results[0]
    city = City(
        name=(hit.get("name") or query).strip(),
        display_name=hit.get("display_name", query),
        lat=float(hit["lat"]),
        lon=float(hit["lon"]),
        country=(hit.get("address") or {}).get("country"),
    )
    _cache[key] = city
    return city
