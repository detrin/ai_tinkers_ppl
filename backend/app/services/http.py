"""One shared async HTTP client so connections are pooled across requests."""
from __future__ import annotations

import httpx

from ..config import settings

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=settings.http_timeout_s,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
