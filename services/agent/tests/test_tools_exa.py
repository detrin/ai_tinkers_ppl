from __future__ import annotations

import httpx
import pytest
from pydantic_ai import ModelRetry

from agent.tools.exa import ExaClient, build_search_web_tool


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_search_maps_results_to_flat_dicts(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse(
            {
                "results": [
                    {
                        "title": "Cafe Savoy",
                        "url": "https://example.com/cafe-savoy",
                        "highlights": ["great coffee", "cozy interior"],
                    }
                ]
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = ExaClient(api_key="key", search_type="fast")
    results = client.search("best cafes in prague")

    assert captured["url"] == "https://api.exa.ai/search"
    assert captured["json"]["query"] == "best cafes in prague"
    assert captured["json"]["type"] == "fast"
    assert captured["json"]["contents"] == {"highlights": True}
    assert results == [
        {
            "title": "Cafe Savoy",
            "url": "https://example.com/cafe-savoy",
            "highlight": "great coffee cozy interior",
        }
    ]


def test_search_falls_back_to_url_when_title_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResponse({"results": [{"url": "https://example.com", "highlights": []}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    results = ExaClient(api_key="key").search("q")
    assert results == [{"title": "https://example.com", "url": "https://example.com", "highlight": ""}]


def test_search_web_tool_raises_model_retry_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)

    search_web = build_search_web_tool(ExaClient(api_key="key"))
    with pytest.raises(ModelRetry):
        search_web(query="best cafes in prague")
