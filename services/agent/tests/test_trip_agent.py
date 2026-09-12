from __future__ import annotations

from agent.config import Settings
from agent.storage import InMemoryTripStore
from agent.trip_agent import TripAgent, build_publish_proposal_tool, build_save_candidates_tool


def _settings(**overrides) -> Settings:
    # 'test' is Pydantic AI's built-in reserved model id: no provider, no
    # API key, no network -- it calls every registered tool once with
    # generated arguments and returns a deterministic summary.
    base = dict(
        model_id="test",
        exa_api_key=None,
        exa_search_type="fast",
        google_maps_api_key=None,
    )
    base.update(overrides)
    return Settings(**base)


def test_optional_tools_disabled_without_api_keys() -> None:
    agent = TripAgent(_settings())
    assert {tool.__name__ for tool in agent.tools} == {"save_candidates", "publish_proposal"}


def test_optional_tools_enabled_with_api_keys() -> None:
    agent = TripAgent(_settings(exa_api_key="exa-key", google_maps_api_key="maps-key"))
    assert {tool.__name__ for tool in agent.tools} == {
        "search_web",
        "find_places",
        "get_place_details",
        "route",
        "save_candidates",
        "publish_proposal",
    }


def test_save_candidates_persists_to_store() -> None:
    store = InMemoryTripStore()
    tool = build_save_candidates_tool(store)

    result = tool(trip_id="trip-1", candidates=[{"name": "Cafe Savoy"}])

    assert result == {"saved": 1, "total_candidates": 1}
    assert store.get("trip-1").candidates == [{"name": "Cafe Savoy"}]


def test_publish_proposal_stores_itineraries() -> None:
    store = InMemoryTripStore()
    tool = build_publish_proposal_tool(store)

    result = tool(trip_id="trip-1", itineraries=[{"title": "Option A"}])

    assert result == {"published": True, "trip_id": "trip-1", "option_count": 1}
    assert store.get("trip-1").itineraries == [{"title": "Option A"}]


def test_plan_runs_the_full_loop_against_the_builtin_test_model() -> None:
    """End-to-end through Pydantic AI's real Agent.run_sync -- no network,
    no API key needed. The 'test' model calls every registered tool once
    with schema-conforming placeholder arguments (not the real trip_id),
    so this only proves the loop and tool wiring work end to end."""
    agent = TripAgent(_settings())

    output = agent.plan("trip-1", "Saturday afternoon in Prague for six, under EUR 40")

    assert isinstance(output, str) and output
    # save_candidates ran (against whatever placeholder trip_id TestModel generated).
    assert len(agent.store) > 0


def test_ask_runs_against_the_builtin_test_model() -> None:
    agent = TripAgent(_settings())

    output = agent.ask("trip-1", "Any rainy-day backup if it storms Saturday?")

    assert isinstance(output, str) and output


def test_ask_keeps_conversation_history_per_trip_id() -> None:
    agent = TripAgent(_settings())

    agent.ask("trip-1", "Any rainy-day backup if it storms Saturday?")
    first_len = len(agent.store.get_messages("trip-1"))
    assert first_len > 0

    # A follow-up on the same trip_id extends the same conversation.
    agent.ask("trip-1", "What about something cheaper?")
    second_len = len(agent.store.get_messages("trip-1"))
    assert second_len > first_len

    # A different trip_id gets its own, independent conversation.
    agent.ask("trip-2", "Any tips for Vienna instead?")
    assert len(agent.store.get_messages("trip-2")) < second_len
