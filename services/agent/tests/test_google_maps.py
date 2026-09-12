from __future__ import annotations

import httpx
import pytest
from pydantic_ai import ModelRetry

from agent.tools.google_maps import GoogleMapsClient, build_route_tool


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_find_places_appends_location_to_query(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse({"places": [{"id": "place-1"}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    client = GoogleMapsClient(api_key="key")
    places = client.find_places("cozy cafe", location="Prague")

    assert captured["url"] == "https://places.googleapis.com/v1/places:searchText"
    assert captured["json"] == {"textQuery": "cozy cafe near Prague"}
    assert captured["headers"]["X-Goog-Api-Key"] == "key"
    assert places == [{"id": "place-1"}]


def test_get_place_details_uses_place_id_in_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        return _FakeResponse({"id": "place-1", "displayName": {"text": "Cafe Savoy"}})

    monkeypatch.setattr(httpx, "get", fake_get)

    details = GoogleMapsClient(api_key="key").get_place_details("place-1")

    assert captured["url"] == "https://places.googleapis.com/v1/places/place-1"
    assert details["id"] == "place-1"


def test_route_requires_at_least_two_stops() -> None:
    with pytest.raises(ValueError):
        GoogleMapsClient(api_key="key").route(["only-one"])


def test_route_splits_intermediates_from_origin_and_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _FakeResponse({"routes": []})

    monkeypatch.setattr(httpx, "post", fake_post)

    GoogleMapsClient(api_key="key").route(["a", "b", "c"], mode="TRANSIT")

    assert captured["json"]["origin"] == {"placeId": "a"}
    assert captured["json"]["destination"] == {"placeId": "c"}
    assert captured["json"]["intermediates"] == [{"placeId": "b"}]
    assert captured["json"]["travelMode"] == "TRANSIT"


def test_route_tool_wraps_value_error_as_model_retry() -> None:
    route = build_route_tool(GoogleMapsClient(api_key="key"))
    with pytest.raises(ModelRetry):
        route(stops=["only-one"])


def test_route_tool_wraps_http_error_as_model_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)

    route = build_route_tool(GoogleMapsClient(api_key="key"))
    with pytest.raises(ModelRetry):
        route(stops=["a", "b"])
