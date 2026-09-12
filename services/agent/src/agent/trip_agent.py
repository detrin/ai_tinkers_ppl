"""The Trip Agent: research, validate, and propose group trip itineraries.

Built on Pydantic AI's `Agent`, which owns the tool-calling loop, JSON
schema generation (from type hints + docstrings), and model provider
selection. This module only supplies the domain layer: the system prompt
and the fixed tool set (search_web, find_places, get_place_details, route,
save_candidates, publish_proposal). Optional tools (Exa, Google Maps) are
only registered when their API key is configured, mirroring the pattern
already used by `packages/agent-core/src/capabilities/search.ts`.
"""

from __future__ import annotations

import logging
from typing import Callable

from pydantic_ai import Agent

from .config import Settings
from .storage import InMemoryTripStore, TripStore
from .tools.exa import ExaClient, build_search_web_tool
from .tools.google_maps import (
    GoogleMapsClient,
    build_find_places_tool,
    build_get_place_details_tool,
    build_route_tool,
)

logger = logging.getLogger(__name__)

INSTRUCTIONS = """You are the Trip Agent for a group trip-planning tool.

Given a trip_id and constraints (city, date/time window, group size,
interests, budget), produce two or three concrete itinerary options for the
requested window.

Use search_web for qualitative discovery: rainy-day ideas, local guide
posts, current event pages. Never trust it for exact facts. Use
find_places and get_place_details to confirm every place you propose
actually exists, is open during the requested window, and fits the budget.
Use route to confirm travel between consecutive stops is feasible in the
time available.

Call save_candidates once you've validated the places you're considering,
passing the same trip_id you were given. When you've settled on final
itineraries, call publish_proposal with the finished options and the same
trip_id, then stop.
"""


def build_save_candidates_tool(store: TripStore) -> Callable[[str, list[dict]], dict]:
    def save_candidates(trip_id: str, candidates: list[dict]) -> dict:
        """Persist validated candidate places for a trip so they can be
        reused across itinerary options.

        Args:
            trip_id: The trip these candidates belong to.
            candidates: Validated place candidates to store.
        """
        total = store.save_candidates(trip_id, candidates)
        return {"saved": len(candidates), "total_candidates": total}

    return save_candidates


def build_publish_proposal_tool(store: TripStore) -> Callable[[str, list[dict]], dict]:
    def publish_proposal(trip_id: str, itineraries: list[dict]) -> dict:
        """Publish the finished itinerary options for a trip. Call this
        once, with the final 2-3 options, to complete planning.

        Args:
            trip_id: The trip these itineraries belong to.
            itineraries: The finished itinerary options.
        """
        store.save_itineraries(trip_id, itineraries)
        return {
            "published": True,
            "trip_id": trip_id,
            "option_count": len(itineraries),
        }

    return publish_proposal


class TripAgent:
    def __init__(self, settings: Settings, store: TripStore | None = None) -> None:
        self.store = store or InMemoryTripStore()
        self.tools = self._build_tools(settings)
        self.agent: Agent = Agent(
            settings.model_id,
            instructions=INSTRUCTIONS,
            tools=self.tools,
        )

    def _build_tools(self, settings: Settings) -> list[Callable]:
        tools: list[Callable] = []

        if settings.exa_api_key:
            exa = ExaClient(settings.exa_api_key, settings.exa_search_type)
            tools.append(build_search_web_tool(exa))
        else:
            logger.warning("EXA_API_KEY not set; search_web tool disabled")

        if settings.google_maps_api_key:
            maps = GoogleMapsClient(settings.google_maps_api_key)
            tools.append(build_find_places_tool(maps))
            tools.append(build_get_place_details_tool(maps))
            tools.append(build_route_tool(maps))
        else:
            logger.warning(
                "GOOGLE_MAPS_API_KEY not set; find_places/get_place_details/"
                "route tools disabled"
            )

        tools.append(build_save_candidates_tool(self.store))
        tools.append(build_publish_proposal_tool(self.store))
        return tools

    def plan(self, trip_id: str, constraints: str) -> str:
        user_message = f"trip_id: {trip_id}\nConstraints: {constraints}"
        result = self.agent.run_sync(user_message)
        return result.output

    def ask(self, trip_id: str, question: str) -> str:
        """Answer a single question about a trip -- e.g. a rainy-day backup
        idea -- without producing a full itinerary. Reuses the same tools
        and instructions as `plan`, just redirected via the user message.

        Follow-up questions for the same trip_id see prior Q&A: history is
        kept in `self.store`, keyed by trip_id, so this is a running
        conversation per trip rather than an isolated call each time.
        """
        history = self.store.get_messages(trip_id)
        if history:
            prompt = question
        else:
            prompt = (
                f"trip_id: {trip_id}\n"
                "A group member has a quick question about their trip. "
                "Answer it directly and concisely, using search_web if it "
                "needs current information. Do not produce a full "
                "itinerary or call save_candidates/publish_proposal unless "
                "the question actually asks for one.\n"
                f"Question: {question}"
            )

        result = self.agent.run_sync(prompt, message_history=history)
        self.store.save_messages(trip_id, result.all_messages())
        return result.output
