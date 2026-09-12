"""Google Maps adapter: the Trip Agent's factual validator.

Web search can suggest a place; only this adapter confirms it actually
exists, where it is, whether it's open, and how long it takes to get there.
Uses the Places API (New) and Routes API directly over HTTP.
"""

from __future__ import annotations

from typing import Callable

import httpx
from pydantic_ai import ModelRetry

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

_SEARCH_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.rating,places.priceLevel"
)
_DETAILS_FIELD_MASK = (
    "id,displayName,formattedAddress,rating,priceLevel,"
    "regularOpeningHours,location"
)
_ROUTES_FIELD_MASK = "routes.duration,routes.distanceMeters,routes.legs"


class GoogleMapsClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def find_places(self, query: str, location: str | None = None) -> list[dict]:
        text_query = f"{query} near {location}" if location else query
        response = httpx.post(
            PLACES_SEARCH_URL,
            headers=self._headers(_SEARCH_FIELD_MASK),
            json={"textQuery": text_query},
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json().get("places", [])

    def get_place_details(self, place_id: str) -> dict:
        response = httpx.get(
            PLACES_DETAILS_URL.format(place_id=place_id),
            headers=self._headers(_DETAILS_FIELD_MASK),
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()

    def route(self, stops: list[str], mode: str = "WALK") -> dict:
        if len(stops) < 2:
            raise ValueError("route requires at least an origin and a destination")
        response = httpx.post(
            ROUTES_URL,
            headers=self._headers(_ROUTES_FIELD_MASK),
            json={
                "origin": {"placeId": stops[0]},
                "destination": {"placeId": stops[-1]},
                "intermediates": [{"placeId": stop} for stop in stops[1:-1]],
                "travelMode": mode,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        return response.json()

    def _headers(self, field_mask: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
        }


def build_find_places_tool(client: GoogleMapsClient) -> Callable[..., list[dict]]:
    def find_places(query: str, location: str | None = None) -> list[dict]:
        """Find candidate places by text query, optionally near a location.

        Use this to confirm a place from search_web actually exists, or to
        discover options directly.

        Args:
            query: What to search for, e.g. 'cozy cafe' or 'board game bar'.
            location: City, neighborhood, or 'lat,lng' to search near.
        """
        try:
            return client.find_places(query, location)
        except httpx.HTTPError as exc:
            raise ModelRetry(f"find_places failed: {exc}") from exc

    return find_places


def build_get_place_details_tool(client: GoogleMapsClient) -> Callable[[str], dict]:
    def get_place_details(place_id: str) -> dict:
        """Get authoritative details for a place: address, rating, price
        level, and opening hours. Use before including a place in a final
        itinerary.

        Args:
            place_id: The place's Google Places ID.
        """
        try:
            return client.get_place_details(place_id)
        except httpx.HTTPError as exc:
            raise ModelRetry(f"get_place_details failed: {exc}") from exc

    return get_place_details


def build_route_tool(client: GoogleMapsClient) -> Callable[..., dict]:
    def route(stops: list[str], mode: str = "WALK") -> dict:
        """Compute a route across an ordered list of place IDs (origin
        first, destination last). Returns duration and distance so you can
        confirm the plan fits the time window.

        Args:
            stops: Ordered place IDs, origin first and destination last.
            mode: One of WALK, TRANSIT, DRIVE, BICYCLE.
        """
        try:
            return client.route(stops, mode)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ModelRetry(f"route failed: {exc}") from exc

    return route
