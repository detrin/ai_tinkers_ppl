"""Bridge to services/agent's Trip Agent: Exa-grounded advisory Q&A on top
of an existing group.

services/agent is a separate uv-managed project; it's installed here as an
editable local dependency (see requirements.txt) so this runs as one
in-process call with no network hop, rather than a second running service.
Its own config (agent.config.Settings) walks up from its own file location
to the same repo-root .env this backend can also read, so AGENT_MODEL_*,
EXA_API_KEY etc. just work without duplicating them into backend/.env.

Construction is lazy: a missing provider key must not crash this backend on
import (every other integration here degrades the same way, see
app/services/ranking.py), it should only fail the one request that needed it.
"""
from __future__ import annotations

from functools import lru_cache

from agent import TripAgent
from agent.config import Settings as AgentSettings


class AgentNotConfigured(RuntimeError):
    """The Trip Agent's model provider isn't configured."""


@lru_cache(maxsize=1)
def _trip_agent() -> TripAgent:
    try:
        settings = AgentSettings.from_env()
    except RuntimeError as exc:
        raise AgentNotConfigured(str(exc)) from exc
    return TripAgent(settings)


def ask(trip_id: str, question: str) -> str:
    """Blocking -- callers on the event loop should offload this, e.g. with
    starlette.concurrency.run_in_threadpool."""
    return _trip_agent().ask(trip_id, question)
