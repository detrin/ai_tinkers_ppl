"""Opt-in live check against the real Exa API.

Everything else in this suite mocks httpx and needs no network or API key.
This one test is the exception: it only runs when a real EXA_API_KEY is
configured (via the repo-root .env), so it's skipped by default in CI and
for anyone who hasn't set one up, but still gives a fast, real signal that
search_web actually works end to end.
"""

from __future__ import annotations

import pytest

from agent.config import Settings
from agent.tools.exa import ExaClient

_settings = Settings.from_env()


@pytest.mark.skipif(not _settings.exa_api_key, reason="EXA_API_KEY not configured")
def test_search_returns_real_results() -> None:
    client = ExaClient(_settings.exa_api_key, _settings.exa_search_type)

    results = client.search("good rainy-day activities in Prague")

    assert results, "expected at least one real Exa result"
    for result in results:
        assert result["title"]
        assert result["url"].startswith("http")
