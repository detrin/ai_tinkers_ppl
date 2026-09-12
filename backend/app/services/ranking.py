"""Choose which of the candidate places this particular group should see.

Claude does the choosing and writes the one-line reason shown in the UI. If no
API key is configured, or the call fails, a deterministic heuristic takes over
so the endpoint always returns an itinerary.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from ..config import settings
from ..models import Member, Place, RankedPlace

log = logging.getLogger(__name__)

MAX_CANDIDATES_TO_MODEL = 70

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One sentence describing the day this route gives the group.",
        },
        "picks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "id copied from the candidate list"},
                    "score": {"type": "number", "description": "0 to 1, how well it fits the group"},
                    "reason": {"type": "string", "description": "at most 15 words, why this group"},
                    "suggested_minutes": {"type": "integer", "description": "time to spend there"},
                },
                "required": ["id", "score", "reason", "suggested_minutes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "picks"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You plan half-day walking routes for groups of friends visiting a city.\n"
    "You are given real places taken from OpenStreetMap, with coordinates.\n"
    "Pick the ones this specific group would enjoy and say why in a few words.\n"
    "Rules:\n"
    "- Only ever return ids that appear in the candidate list. Never invent a place.\n"
    "- Prefer a varied route: do not return five cafes or five churches.\n"
    "- Respect the stated interests. With no interests given, favour landmarks "
    "a first-time visitor would regret missing.\n"
    "- Keep the picks geographically sensible; a group walks between them.\n"
    "- The travellers matter individually. What each one wants and cannot do "
    "comes from their own words in the group's conversation.\n"
    "- A constraint beats a preference. If one person cannot walk far, keep the "
    "whole route tight, even if that costs somebody else their first choice.\n"
    "- Try to give every traveller at least one place they asked for, and say "
    "whose it is in the reason.\n"
    "- Watch the money. Where a budget is tight, favour places that are free or "
    "cheap to enter.\n"
    "- suggested_minutes is time spent at the place, typically 20 to 90."
)


def _traveler_payload(travelers: Sequence[Member]) -> list[dict[str, Any]]:
    """What the group said about each person, as the agent recorded it."""
    return [
        {
            "name": t.display_name,
            "wants": t.preferences,
            "constraints": t.constraints,
            "budget": None if t.budget is None else f"{t.budget:g} {t.currency}",
        }
        for t in travelers
    ]


def _candidate_payload(places: Sequence[Place]) -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "tags": p.tags,
            "lat": round(p.lat, 5),
            "lon": round(p.lon, 5),
            "notable": bool(p.wikidata),
        }
        for p in places
    ]


def heuristic_rank(
    places: Sequence[Place], interests: Sequence[str], max_stops: int
) -> tuple[list[RankedPlace], str]:
    """Scoring without the model: base prior, nudged by interest keywords."""
    wanted = {i.strip().lower() for i in interests if i.strip()}
    ranked: list[RankedPlace] = []
    for place in places:
        score = place.base_score
        haystack = " ".join([place.category, place.name, *place.tags]).lower()
        if wanted and any(w in haystack for w in wanted):
            score = min(1.0, score + 0.25)
        ranked.append(
            RankedPlace(
                **place.model_dump(),
                score=round(score, 3),
                reason=f"Well-known {place.category} spot nearby.",
                suggested_minutes=40 if place.category in {"sight", "history"} else 30,
                ranked_by="heuristic",
            )
        )

    ranked.sort(key=lambda p: p.score, reverse=True)
    # Spread the categories so the day is not five of the same thing.
    picked: list[RankedPlace] = []
    seen: dict[str, int] = {}
    cap = max(1, max_stops // 3)
    for place in ranked:
        if len(picked) >= max_stops:
            break
        if seen.get(place.category, 0) >= cap:
            continue
        seen[place.category] = seen.get(place.category, 0) + 1
        picked.append(place)
    for place in ranked:  # top up if the category caps were too strict
        if len(picked) >= max_stops:
            break
        if all(p.id != place.id for p in picked):
            picked.append(place)

    return picked, "Route built from the highest-rated places near the group."


async def _call_claude(prompt: str) -> dict[str, Any] | None:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    request: dict[str, Any] = {
        "model": settings.anthropic_model,
        "max_tokens": 8000,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {
            # Ranking a short list is not a hard reasoning problem; medium effort
            # keeps the endpoint responsive.
            "effort": "medium",
            "format": {"type": "json_schema", "schema": _SCHEMA},
        },
    }

    try:
        # Server-side fallback re-routes the request if a safety classifier
        # declines it, so a single odd place name cannot fail the whole plan.
        response = await client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **request,
        )
    except Exception as exc:  # older SDK, or the beta is not enabled on this key
        log.info("using the plain messages endpoint: %s", exc)
        response = await client.messages.create(**request)

    if getattr(response, "stop_reason", None) == "refusal":
        log.warning("the model declined the ranking request")
        return None

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return None
    return json.loads(text)


async def rank_places(
    places: Sequence[Place],
    interests: Sequence[str],
    group_size: int,
    city_name: str,
    max_stops: int,
    travelers: Sequence[Member] = (),
) -> tuple[list[RankedPlace], str, str]:
    """Returns (picked places, summary, "ai" or "heuristic")."""
    if not places:
        return [], "No places were found in this area.", "heuristic"

    shortlist = sorted(places, key=lambda p: p.base_score, reverse=True)[
        :MAX_CANDIDATES_TO_MODEL
    ]

    # Everything anyone asked for, whoever asked for it. Without the model, a
    # preference one person voiced in the thread still steers the scoring.
    wanted = list(interests) + [w for t in travelers for w in t.preferences]

    if not settings.ai_enabled:
        picked, summary = heuristic_rank(places, wanted, max_stops)
        return picked, summary, "heuristic"

    interest_text = ", ".join(interests) if interests else "not stated"
    traveler_text = (
        json.dumps(_traveler_payload(travelers), ensure_ascii=False)
        if travelers
        else "not stated"
    )
    prompt = (
        f"City: {city_name}\n"
        f"Group size: {group_size}\n"
        f"Interests the group picked: {interest_text}\n"
        f"Travellers, in their own words:\n{traveler_text}\n\n"
        f"Pick exactly {min(max_stops, len(shortlist))} places.\n\n"
        f"Candidates:\n{json.dumps(_candidate_payload(shortlist), ensure_ascii=False)}"
    )

    try:
        data = await _call_claude(prompt)
    except Exception as exc:
        log.warning("AI ranking failed, using the heuristic: %s", exc)
        data = None

    if not data or not data.get("picks"):
        picked, summary = heuristic_rank(places, wanted, max_stops)
        return picked, summary, "heuristic"

    by_id = {p.id: p for p in places}
    picked = []
    for pick in data["picks"]:
        place = by_id.get(pick.get("id", ""))
        if place is None:  # the model named something outside the candidate list
            continue
        if any(existing.id == place.id for existing in picked):
            continue
        picked.append(
            RankedPlace(
                **place.model_dump(),
                score=round(float(pick.get("score", place.base_score)), 3),
                reason=str(pick.get("reason", ""))[:160],
                suggested_minutes=max(10, min(180, int(pick.get("suggested_minutes", 45)))),
                ranked_by="ai",
            )
        )
        if len(picked) >= max_stops:
            break

    if not picked:
        picked, summary = heuristic_rank(places, wanted, max_stops)
        return picked, summary, "heuristic"

    return picked, str(data.get("summary", ""))[:400], "ai"
