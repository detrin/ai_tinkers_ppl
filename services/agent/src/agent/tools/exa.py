"""Exa adapter: qualitative web discovery for the Trip Agent.

Mirrors the shape of `packages/agent-core/src/capabilities/search.ts` so the
two surfaces stay conceptually aligned, but talks to Exa's REST API directly
to avoid a second SDK dependency.
"""

from __future__ import annotations

from typing import Callable

import httpx
from pydantic_ai import ModelRetry

SEARCH_URL = "https://api.exa.ai/search"


class ExaClient:
    def __init__(self, api_key: str, search_type: str = "fast") -> None:
        self._api_key = api_key
        self._search_type = search_type

    def search(self, query: str, num_results: int = 5) -> list[dict[str, str]]:
        response = httpx.post(
            SEARCH_URL,
            headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
            json={
                "query": query,
                "type": self._search_type,
                "numResults": num_results,
                "contents": {"highlights": True},
            },
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        return [
            {
                "title": item.get("title") or item.get("url", ""),
                "url": item.get("url", ""),
                "highlight": " ".join(item.get("highlights", [])),
            }
            for item in data.get("results", [])
        ]


def build_search_web_tool(client: ExaClient) -> Callable[[str], list[dict[str, str]]]:
    def search_web(query: str) -> list[dict[str, str]]:
        """Search the web for qualitative context: rainy-day activity ideas,
        local guide recommendations, current event pages.

        Treat results as inspiration, not fact -- validate any place,
        address, hours, or price with find_places / get_place_details
        before including it in a plan.

        Args:
            query: Search query.
        """
        try:
            return client.search(query)
        except httpx.HTTPError as exc:
            raise ModelRetry(f"search_web failed: {exc}") from exc

    return search_web
