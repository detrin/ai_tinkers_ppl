"""Offline tests. Every network call is replaced with a fixture."""
from __future__ import annotations

import asyncio
import itertools
import os

import pytest

os.environ.setdefault("PERSIST_STATE", "0")

from fastapi.testclient import TestClient  # noqa: E402

from app.geo import haversine_m, meeting_point, straight_line_matrix  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Place  # noqa: E402
from app.services import agent_bridge, geocode, planner, ranking, routing  # noqa: E402
from app.services import places as places_service  # noqa: E402
from app.store import store  # noqa: E402

PRAGUE = (50.0875, 14.4213)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def test_haversine_matches_known_distance():
    vienna = (48.2082, 16.3738)
    km = haversine_m(PRAGUE, vienna) / 1000
    assert 250 < km < 256  # Prague to Vienna is about 252 km


def test_meeting_point_is_not_dragged_by_one_outlier():
    cluster = [(50.086, 14.420), (50.087, 14.421), (50.088, 14.422)]
    far_away = (50.140, 14.520)
    median = meeting_point([*cluster, far_away])
    centre_of_cluster = (50.087, 14.421)
    assert haversine_m(median, centre_of_cluster) < 400


def test_straight_line_matrix_is_symmetric_with_a_zero_diagonal():
    points = [(50.08, 14.42), (50.09, 14.43), (50.07, 14.41)]
    dist, dur = straight_line_matrix(points, 4.8)
    for i in range(3):
        assert dist[i][i] == 0
        for j in range(3):
            assert dist[i][j] == pytest.approx(dist[j][i])
            assert dur[i][j] > 0 or i == j


# ---------------------------------------------------------------------------
# Route ordering
# ---------------------------------------------------------------------------
def _cost(points):
    return straight_line_matrix(points, 4.8)[1]


def test_order_stops_matches_brute_force_on_a_small_instance():
    # Five points scattered so that the greedy order is not the best one.
    points = [
        (50.080, 14.400),  # start
        (50.090, 14.430),
        (50.081, 14.404),
        (50.088, 14.428),
        (50.085, 14.415),
    ]
    cost = _cost(points)
    order = routing.order_stops(cost, start=0)

    def path_cost(seq):
        return sum(cost[seq[i]][seq[i + 1]] for i in range(len(seq) - 1))

    best = min(
        ([0, *perm] for perm in itertools.permutations(range(1, len(points)))),
        key=path_cost,
    )
    assert path_cost(order) == pytest.approx(path_cost(best), rel=1e-9)
    assert order[0] == 0
    assert sorted(order) == list(range(len(points)))


def test_car_durations_are_converted_to_walking_time(monkeypatch):
    points = [(50.080, 14.400), (50.090, 14.430)]
    car_distance = [[0.0, 2400.0], [2400.0, 0.0]]
    car_duration = [[0.0, 300.0], [300.0, 0.0]]  # 5 minutes by car

    async def fake_osrm(_points, _transport):
        return car_distance, car_duration, "driving"

    monkeypatch.setattr(routing.settings, "ors_api_key", None)
    monkeypatch.setattr(routing.settings, "osrm_url", "http://osrm.test")
    monkeypatch.setattr(routing, "_osrm_matrix", fake_osrm)

    dist, dur, provider = asyncio.run(routing.distance_matrix(points, "foot"))
    assert provider == "osrm"
    assert dist[0][1] == 2400.0  # street distance is kept
    # 2.4 km on foot is roughly half an hour, not five minutes.
    assert 1500 < dur[0][1] < 2200


def test_order_stops_handles_degenerate_sizes():
    assert routing.order_stops([[0.0]], start=0) == [0]
    assert routing.order_stops([[0.0, 1.0], [1.0, 0.0]], start=0) == [0, 1]


# ---------------------------------------------------------------------------
# Overpass parsing
# ---------------------------------------------------------------------------
OVERPASS_FIXTURE = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": 50.0870,
            "lon": 14.4200,
            "tags": {"name": "Old Town Square", "tourism": "attraction", "wikidata": "Q1"},
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": 50.0900, "lon": 14.4000},
            "tags": {"name": "Prague Castle", "historic": "castle", "wikipedia": "cs:x"},
        },
        {
            "type": "node",
            "id": 3,
            "lat": 50.0880,
            "lon": 14.4210,
            "tags": {"name": "Cafe Slavia", "amenity": "cafe"},
        },
        # Same place, mapped twice a few metres apart: must be deduped.
        {
            "type": "node",
            "id": 4,
            "lat": 50.0871,
            "lon": 14.4201,
            "tags": {"name": "Old Town Square", "tourism": "attraction"},
        },
        # No name: useless to a visitor, must be dropped.
        {"type": "node", "id": 5, "lat": 50.0, "lon": 14.0, "tags": {"amenity": "bar"}},
    ]
}


def _fixture_places() -> list[Place]:
    parsed = [
        p
        for p in (places_service._element_to_place(e) for e in OVERPASS_FIXTURE["elements"])
        if p is not None
    ]
    return places_service._dedupe(parsed)


def test_overpass_parsing_drops_unnamed_and_deduplicates():
    places = _fixture_places()
    names = sorted(p.name for p in places)
    assert names == ["Cafe Slavia", "Old Town Square", "Prague Castle"]


def test_wikidata_lifts_the_base_score_above_a_plain_cafe():
    by_name = {p.name: p for p in _fixture_places()}
    assert by_name["Old Town Square"].base_score > by_name["Cafe Slavia"].base_score
    assert by_name["Prague Castle"].category == "history"


def test_way_geometry_uses_its_centre():
    castle = next(p for p in _fixture_places() if p.name == "Prague Castle")
    assert castle.lat == pytest.approx(50.0900)
    assert castle.id.startswith("way/")


# ---------------------------------------------------------------------------
# Ranking without an API key
# ---------------------------------------------------------------------------
def test_heuristic_ranking_respects_interests_and_the_stop_limit():
    places = _fixture_places()
    picked, summary = ranking.heuristic_rank(places, ["cafe"], max_stops=2)
    assert len(picked) == 2
    assert summary
    assert all(p.ranked_by == "heuristic" for p in picked)


def test_rank_places_falls_back_to_the_heuristic_without_a_key(monkeypatch):
    monkeypatch.setattr(ranking.settings, "anthropic_api_key", None)
    picked, _summary, source = asyncio.run(
        ranking.rank_places(_fixture_places(), [], 3, "Prague", 3)
    )
    assert source == "heuristic"
    assert len(picked) == 3


def test_rank_places_ignores_places_the_model_invents(monkeypatch):
    monkeypatch.setattr(ranking.settings, "anthropic_api_key", "test-key")

    async def fake_call(_prompt):
        return {
            "summary": "A short history walk.",
            "picks": [
                {"id": "node/1", "score": 0.9, "reason": "Heart of the city", "suggested_minutes": 30},
                {"id": "node/999", "score": 0.9, "reason": "Not real", "suggested_minutes": 30},
            ],
        }

    monkeypatch.setattr(ranking, "_call_claude", fake_call)
    picked, summary, source = asyncio.run(
        ranking.rank_places(_fixture_places(), [], 3, "Prague", 3)
    )
    assert source == "ai"
    assert [p.id for p in picked] == ["node/1"]
    assert summary == "A short history walk."


class _FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    stop_reason = "end_turn"

    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


def _install_fake_sdk(monkeypatch, *, beta_works: bool, calls: list):
    """Stand in for anthropic.AsyncAnthropic without touching the network."""
    import anthropic

    payload = (
        '{"summary": "Old town on foot.", "picks": ['
        '{"id": "way/2", "score": 0.95, "reason": "The castle is the view",'
        ' "suggested_minutes": 60}]}'
    )

    class FakeMessages:
        async def create(self, **kwargs):
            calls.append(("plain", kwargs))
            return _FakeResponse(payload)

    class FakeBetaMessages:
        async def create(self, **kwargs):
            calls.append(("beta", kwargs))
            if not beta_works:
                raise RuntimeError("beta not enabled for this key")
            return _FakeResponse(payload)

    class FakeBeta:
        messages = FakeBetaMessages()

    class FakeClient:
        def __init__(self, **_kwargs):
            self.messages = FakeMessages()
            self.beta = FakeBeta()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)


def test_claude_request_carries_the_schema_and_the_model(monkeypatch):
    monkeypatch.setattr(ranking.settings, "anthropic_api_key", "test-key")
    calls: list = []
    _install_fake_sdk(monkeypatch, beta_works=True, calls=calls)

    picked, summary, source = asyncio.run(
        ranking.rank_places(_fixture_places(), ["history"], 2, "Prague", 1)
    )

    assert source == "ai"
    assert [p.name for p in picked] == ["Prague Castle"]
    assert picked[0].suggested_minutes == 60
    assert summary == "Old town on foot."

    kind, kwargs = calls[0]
    assert kind == "beta"
    assert kwargs["model"] == ranking.settings.anthropic_model
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert kwargs["output_config"]["format"]["schema"]["required"] == ["summary", "picks"]
    assert "history" in kwargs["messages"][0]["content"]


def test_claude_call_retries_on_the_plain_endpoint_when_the_beta_is_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(ranking.settings, "anthropic_api_key", "test-key")
    calls: list = []
    _install_fake_sdk(monkeypatch, beta_works=False, calls=calls)

    _picked, _summary, source = asyncio.run(
        ranking.rank_places(_fixture_places(), [], 2, "Prague", 1)
    )

    assert source == "ai"
    assert [kind for kind, _ in calls] == ["beta", "plain"]


def test_a_refusal_falls_back_to_the_heuristic(monkeypatch):
    import anthropic

    monkeypatch.setattr(ranking.settings, "anthropic_api_key", "test-key")

    class Refused:
        stop_reason = "refusal"
        content: list = []

    class FakeMessages:
        async def create(self, **_kwargs):
            return Refused()

    class FakeClient:
        def __init__(self, **_kwargs):
            self.messages = FakeMessages()
            self.beta = type("B", (), {"messages": FakeMessages()})()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)

    picked, _summary, source = asyncio.run(
        ranking.rank_places(_fixture_places(), [], 2, "Prague", 2)
    )
    assert source == "heuristic"
    assert len(picked) == 2


# ---------------------------------------------------------------------------
# End to end over HTTP
# ---------------------------------------------------------------------------
@pytest.fixture()
def client(monkeypatch):
    async def fake_resolve(query: str):
        from app.models import City

        return City(
            name="Prague",
            display_name="Prague, Czechia",
            lat=PRAGUE[0],
            lon=PRAGUE[1],
            country="Czechia",
        )

    async def fake_discover(lat, lon, radius_m=None, limit=None):
        return _fixture_places()

    monkeypatch.setattr(geocode, "resolve_city", fake_resolve)
    monkeypatch.setattr(places_service, "discover", fake_discover)
    monkeypatch.setattr(planner.places_service, "discover", fake_discover)
    monkeypatch.setattr(ranking.settings, "anthropic_api_key", None)
    # No routing provider: the straight-line estimate must carry the request.
    monkeypatch.setattr(routing.settings, "ors_api_key", None)
    monkeypatch.setattr(routing.settings, "osrm_url", None)

    store._groups.clear()
    store._by_code.clear()
    with TestClient(app) as test_client:
        yield test_client


def test_health_reports_which_providers_are_live(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["places"] == "overpass"


def test_full_group_flow(client):
    created = client.post(
        "/api/groups",
        json={"name": "Weekend crew", "city": "Prague", "interests": ["history"]},
    )
    assert created.status_code == 201
    group = created.json()
    group_id = group["id"]
    assert len(group["join_code"]) == 6

    # Two people join, one of them with the join code.
    ana = client.post(
        f"/api/groups/{group_id}/members", json={"display_name": "Ana"}
    ).json()
    bo = client.post(
        f"/api/groups/{group_id}/members",
        json={"display_name": "Bo", "join_code": group["join_code"]},
    ).json()

    wrong_code = client.post(
        f"/api/groups/{group_id}/members",
        json={"display_name": "Cy", "join_code": "ZZZZZZ"},
    )
    assert wrong_code.status_code == 403

    # They report where they are, a few hundred metres apart.
    client.put(
        f"/api/groups/{group_id}/members/{ana['id']}/position",
        json={"lat": 50.0860, "lon": 14.4190},
    )
    positioned = client.put(
        f"/api/groups/{group_id}/members/{bo['id']}/position",
        json={"lat": 50.0890, "lon": 14.4230},
    )
    assert positioned.status_code == 200

    plan = client.post(f"/api/groups/{group_id}/plan", json={"max_stops": 3}).json()
    assert plan["routing_provider"] == "straight-line"
    assert plan["ranked_by"] == "heuristic"
    assert 1 <= len(plan["stops"]) <= 3
    assert len(plan["legs"]) == len(plan["stops"])
    assert plan["legs"][0]["from_index"] == -1  # the walk starts at the meeting point
    assert plan["total_distance_m"] > 0
    assert plan["total_visit_seconds"] > 0

    # The stops come back already in walking order.
    assert [s["order"] for s in plan["stops"]] == list(range(len(plan["stops"])))

    # Members are annotated with how far they are from the group.
    members = client.get(f"/api/groups/{group_id}/members").json()
    assert all(m["distance_to_meeting_m"] is not None for m in members)
    assert all(m["distance_to_next_stop_m"] is not None for m in members)

    by_code = client.get(f"/api/groups/by-code/{group['join_code']}").json()
    assert by_code["id"] == group_id


def test_plan_is_readable_after_it_is_generated(client):
    group = client.post("/api/groups", json={"name": "G", "city": "Prague"}).json()
    assert client.get(f"/api/groups/{group['id']}/plan").status_code == 404
    client.post(f"/api/groups/{group['id']}/plan", json={"max_stops": 2})
    assert client.get(f"/api/groups/{group['id']}/plan").status_code == 200


# ---------------------------------------------------------------------------
# Trip Agent advisory Q&A (services/agent, bridged in app/services/agent_bridge.py)
# ---------------------------------------------------------------------------
def test_ask_returns_the_agent_answer(client, monkeypatch):
    calls = {}

    def fake_ask(trip_id: str, question: str) -> str:
        calls["trip_id"] = trip_id
        calls["question"] = question
        return "Try the National Technical Museum if it rains."

    monkeypatch.setattr(agent_bridge, "ask", fake_ask)

    group = client.post(
        "/api/groups", json={"name": "G", "city": "Prague", "interests": ["history"]}
    ).json()
    response = client.post(
        f"/api/groups/{group['id']}/ask", json={"question": "Rainy day backup?"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "Rainy day backup?"
    assert body["answer"] == "Try the National Technical Museum if it rains."
    # The group's city and interests ride along as context, not just the raw question.
    assert calls["trip_id"] == group["id"]
    assert "Prague" in calls["question"]
    assert "history" in calls["question"]


def test_a_missing_agent_package_does_not_take_the_backend_down(monkeypatch):
    """services/agent is optional. Importing it eagerly would mean every
    endpoint in this backend dies when it is not installed, so the bridge
    imports lazily and reports the same 503 a missing key does."""
    import sys

    monkeypatch.setitem(sys.modules, "agent", None)  # makes `import agent` fail
    agent_bridge._trip_agent.cache_clear()

    with pytest.raises(agent_bridge.AgentNotConfigured):
        agent_bridge.ask("trip", "anything")

    agent_bridge._trip_agent.cache_clear()


def test_ask_is_503_when_the_agent_has_no_provider_key(client, monkeypatch):
    def fake_ask(trip_id: str, question: str) -> str:
        raise agent_bridge.AgentNotConfigured("OPENROUTER_API_KEY is not set")

    monkeypatch.setattr(agent_bridge, "ask", fake_ask)

    group = client.post("/api/groups", json={"name": "G", "city": "Prague"}).json()
    response = client.post(f"/api/groups/{group['id']}/ask", json={"question": "?"})

    assert response.status_code == 503


def test_ask_404s_for_an_unknown_group(client):
    response = client.post("/api/groups/does-not-exist/ask", json={"question": "?"})
    assert response.status_code == 404


def test_unknown_group_is_a_404(client):
    assert client.get("/api/groups/does-not-exist").status_code == 404
    assert (
        client.post("/api/groups/does-not-exist/plan", json={}).status_code == 404
    )


def test_websocket_broadcasts_positions_between_members(client):
    group = client.post("/api/groups", json={"name": "G", "city": "Prague"}).json()
    gid = group["id"]
    ana = client.post(f"/api/groups/{gid}/members", json={"display_name": "Ana"}).json()
    bo = client.post(f"/api/groups/{gid}/members", json={"display_name": "Bo"}).json()

    with client.websocket_connect(f"/ws/groups/{gid}?member_id={ana['id']}") as ana_ws:
        assert ana_ws.receive_json()["type"] == "snapshot"

        with client.websocket_connect(f"/ws/groups/{gid}?member_id={bo['id']}") as bo_ws:
            assert bo_ws.receive_json()["type"] == "snapshot"
            # Ana is told Bo came online.
            assert ana_ws.receive_json() == {
                "type": "presence",
                "member_id": bo["id"],
                "online": True,
            }

            bo_ws.send_json({"type": "position", "lat": 50.088, "lon": 14.422})
            event = ana_ws.receive_json()
            assert event["type"] == "position"
            assert event["member_id"] == bo["id"]
            assert event["position"]["lat"] == pytest.approx(50.088)

            # The sender gets the same event back, carrying the server's
            # distance calculation, so it can render without a second request.
            echo = bo_ws.receive_json()
            assert echo["type"] == "position"
            assert echo["distance_to_meeting_m"] is None  # no plan yet

            bo_ws.send_json({"type": "position", "lat": 999, "lon": 0})
            assert bo_ws.receive_json()["type"] == "error"

            bo_ws.send_json({"type": "ping"})
            assert bo_ws.receive_json()["type"] == "pong"


def test_plan_broadcast_carries_refreshed_member_distances(client):
    group = client.post("/api/groups", json={"name": "G", "city": "Prague"}).json()
    gid = group["id"]
    ana = client.post(f"/api/groups/{gid}/members", json={"display_name": "Ana"}).json()

    with client.websocket_connect(f"/ws/groups/{gid}?member_id={ana['id']}") as socket:
        assert socket.receive_json()["type"] == "snapshot"

        socket.send_json({"type": "position", "lat": 50.0865, "lon": 14.4180})
        first = socket.receive_json()
        assert first["type"] == "position"
        # No plan yet, so there is no meeting point to measure against.
        assert first["distance_to_meeting_m"] is None

        client.post(f"/api/groups/{gid}/plan", json={"max_stops": 2})
        event = socket.receive_json()
        assert event["type"] == "plan"
        # The same event refreshes the distances the member list renders.
        assert event["members"][0]["distance_to_meeting_m"] is not None
        assert event["members"][0]["distance_to_next_stop_m"] is not None


def test_leaving_tells_the_rest_of_the_group(client):
    group = client.post("/api/groups", json={"name": "G", "city": "Prague"}).json()
    gid = group["id"]
    ana = client.post(f"/api/groups/{gid}/members", json={"display_name": "Ana"}).json()
    bo = client.post(f"/api/groups/{gid}/members", json={"display_name": "Bo"}).json()

    with client.websocket_connect(f"/ws/groups/{gid}?member_id={bo['id']}") as bo_ws:
        assert bo_ws.receive_json()["type"] == "snapshot"

        gone = client.delete(f"/api/groups/{gid}/members/{ana['id']}")
        assert gone.status_code == 204

        event = bo_ws.receive_json()
        assert event == {"type": "member_left", "member_id": ana["id"]}

    remaining = client.get(f"/api/groups/{gid}/members").json()
    assert [m["display_name"] for m in remaining] == ["Bo"]

    # Leaving twice is not an error the caller has to guard against; it is a 404.
    assert client.delete(f"/api/groups/{gid}/members/{ana['id']}").status_code == 404


def test_a_member_who_left_cannot_reopen_the_socket(client):
    group = client.post("/api/groups", json={"name": "G", "city": "Prague"}).json()
    gid = group["id"]
    ana = client.post(f"/api/groups/{gid}/members", json={"display_name": "Ana"}).json()
    client.delete(f"/api/groups/{gid}/members/{ana['id']}")

    with pytest.raises(Exception):
        with client.websocket_connect(
            f"/ws/groups/{gid}?member_id={ana['id']}"
        ) as socket:
            socket.receive_json()


def test_websocket_rejects_an_unknown_member(client):
    group = client.post("/api/groups", json={"name": "G", "city": "Prague"}).json()
    with pytest.raises(Exception):
        with client.websocket_connect(
            f"/ws/groups/{group['id']}?member_id=nobody"
        ) as socket:
            socket.receive_json()


# ---------------------------------------------------------------------------
# Cross-surface trip state (GROUP_TRAVEL_AGENTS.md)
# ---------------------------------------------------------------------------
SLACK_THREAD = {
    "workspace_id": "T123",
    "channel_id": "C456",
    "thread_id": "1726000000.0001",
}


def _slack_trip(client, **overrides):
    body = {**SLACK_THREAD, "name": "Prague weekend", "city": "Prague", **overrides}
    return client.post("/api/trips/by-slack-thread", json=body)


def test_a_slack_thread_maps_to_one_trip_however_often_it_is_delivered(client):
    first = _slack_trip(client)
    assert first.status_code == 201

    # Slack redelivers, and every mention calls this. It must not fan out into
    # a new trip each time.
    second = _slack_trip(client)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

    found = client.get("/api/trips/by-slack-thread", params=SLACK_THREAD)
    assert found.status_code == 200
    assert found.json()["id"] == first.json()["id"]


def test_a_different_thread_in_the_same_channel_is_a_different_trip(client):
    first = _slack_trip(client).json()
    other = _slack_trip(client, thread_id="1726000000.9999").json()
    assert other["id"] != first["id"]


def test_an_unmapped_thread_is_a_404(client):
    missing = client.get(
        "/api/trips/by-slack-thread",
        params={"workspace_id": "T1", "channel_id": "C1", "thread_id": "nope"},
    )
    assert missing.status_code == 404


def test_traveler_preferences_merge_instead_of_overwriting(client):
    group = _slack_trip(client).json()
    ana = client.post(
        f"/api/groups/{group['id']}/members", json={"display_name": "Ana"}
    ).json()

    client.patch(
        f"/api/groups/{group['id']}/members/{ana['id']}/preferences",
        json={"preferences": ["museums"], "budget": 120, "slack_user_id": "U1"},
    )
    # A later message mentions one constraint. The budget heard earlier must
    # survive it.
    updated = client.patch(
        f"/api/groups/{group['id']}/members/{ana['id']}/preferences",
        json={"preferences": ["food"], "constraints": ["arrives late Friday"]},
    ).json()

    assert updated["preferences"] == ["museums", "food"]
    assert updated["constraints"] == ["arrives late Friday"]
    assert updated["budget"] == 120
    assert updated["slack_user_id"] == "U1"


def test_a_replayed_slack_message_is_stored_once(client):
    group = _slack_trip(client).json()
    body = {
        "source": "slack",
        "source_message_id": "1726000001.0002",
        "author_name": "Bo",
        "text": "I land at 9pm on Friday",
    }

    first = client.post(f"/api/groups/{group['id']}/messages", json=body)
    replay = client.post(f"/api/groups/{group['id']}/messages", json=body)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]

    stored = client.get(f"/api/groups/{group['id']}/messages").json()
    assert len(stored) == 1


def test_a_proposal_is_not_the_plan_until_it_is_approved(client):
    group = _slack_trip(client).json()
    gid = group["id"]

    proposal = client.post(
        f"/api/groups/{gid}/proposals",
        json={"max_stops": 2, "assumptions": ["everyone walks"]},
    )
    assert proposal.status_code == 201
    assert proposal.json()["status"] == "proposed"
    assert proposal.json()["plan"]["stops"]

    # Proposing built an itinerary but changed nothing the group is doing.
    assert client.get(f"/api/groups/{gid}/plan").status_code == 404

    approved = client.post(
        f"/api/groups/{gid}/proposals/{proposal.json()['id']}/approve",
        json={"decided_by": "Ana"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_by"] == "Ana"

    # And now the same shared state both surfaces read has the itinerary.
    plan = client.get(f"/api/groups/{gid}/plan")
    assert plan.status_code == 200
    assert plan.json()["stops"] == proposal.json()["plan"]["stops"]


def test_declining_writes_no_itinerary(client):
    group = _slack_trip(client).json()
    gid = group["id"]
    proposal = client.post(f"/api/groups/{gid}/proposals", json={"max_stops": 2}).json()

    declined = client.post(
        f"/api/groups/{gid}/proposals/{proposal['id']}/decline", json={}
    )
    assert declined.status_code == 200
    assert declined.json()["status"] == "declined"
    assert client.get(f"/api/groups/{gid}/plan").status_code == 404


def test_approving_the_same_proposal_twice_changes_nothing_further(client):
    group = _slack_trip(client).json()
    gid = group["id"]
    proposal = client.post(f"/api/groups/{gid}/proposals", json={"max_stops": 2}).json()

    first = client.post(f"/api/groups/{gid}/proposals/{proposal['id']}/approve", json={})
    decided_at = first.json()["decided_at"]

    # A redelivered button press is not an error and does not re-decide.
    again = client.post(f"/api/groups/{gid}/proposals/{proposal['id']}/approve", json={})
    assert again.status_code == 200
    assert again.json()["decided_at"] == decided_at


def test_an_idempotency_key_does_not_stack_up_proposals(client):
    group = _slack_trip(client).json()
    gid = group["id"]
    body = {"max_stops": 2, "idempotency_key": "slack-button-1"}

    first = client.post(f"/api/groups/{gid}/proposals", json=body)
    replay = client.post(f"/api/groups/{gid}/proposals", json=body)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"] == "slack-button-1"
    assert len(client.get(f"/api/groups/{gid}/proposals").json()) == 1


def test_approving_a_second_itinerary_supersedes_the_first(client):
    group = _slack_trip(client).json()
    gid = group["id"]
    one = client.post(f"/api/groups/{gid}/proposals", json={"max_stops": 2}).json()
    two = client.post(f"/api/groups/{gid}/proposals", json={"max_stops": 3}).json()

    client.post(f"/api/groups/{gid}/proposals/{one['id']}/approve", json={})
    client.post(f"/api/groups/{gid}/proposals/{two['id']}/approve", json={})

    by_id = {p["id"]: p for p in client.get(f"/api/groups/{gid}/proposals").json()}
    assert by_id[one["id"]]["status"] == "declined"
    assert by_id[two["id"]]["status"] == "approved"
    # The group follows exactly one itinerary.
    assert len(client.get(f"/api/groups/{gid}/plan").json()["stops"]) == len(
        two["plan"]["stops"]
    )


def test_an_approval_reaches_the_other_surface_over_the_socket(client):
    group = _slack_trip(client).json()
    gid = group["id"]
    ana = client.post(
        f"/api/groups/{gid}/members", json={"display_name": "Ana"}
    ).json()
    proposal = client.post(f"/api/groups/{gid}/proposals", json={"max_stops": 2}).json()

    with client.websocket_connect(f"/ws/groups/{gid}?member_id={ana['id']}") as socket:
        assert socket.receive_json()["type"] == "snapshot"
        client.post(f"/api/groups/{gid}/proposals/{proposal['id']}/approve", json={})

        event = socket.receive_json()
        assert event["type"] == "proposal_decision"
        assert event["proposal"]["status"] == "approved"
        assert event["plan"]["stops"]


# ---------------------------------------------------------------------------
# Specialist travel workflows
# ---------------------------------------------------------------------------
def _specialist_group(client):
    group = client.post("/api/groups", json={"name": "Specialists", "city": "Prague", "interests": ["food", "walking"]}).json()
    ana = client.post(f"/api/groups/{group['id']}/members", json={"display_name": "Ana"}).json()
    bo = client.post(f"/api/groups/{group['id']}/members", json={"display_name": "Bo"}).json()
    return group, ana, bo


def test_media_organizer_classifies_receipts_and_persists_metadata(client):
    group, _ana, _bo = _specialist_group(client)
    item = client.post(f"/api/groups/{group['id']}/media", json={"filename": "dinner-receipt.jpg", "location": "Old Town", "day": 1}).json()
    assert item["category"] == "receipt"
    saved = client.get(f"/api/groups/{group['id']}").json()
    assert saved["media"][0]["location"] == "Old Town"


def test_expense_is_only_counted_after_approval_and_splits_exactly(client):
    group, ana, bo = _specialist_group(client)
    expense = client.post(f"/api/groups/{group['id']}/expenses", json={
        "title": "Dinner", "amount": 10.01, "paid_by": ana["id"],
        "participant_ids": [ana["id"], bo["id"]],
    }).json()
    assert expense["status"] == "proposed"
    assert sum(expense["shares"].values()) == 10.01
    assert client.get(f"/api/groups/{group['id']}/balances").json()["balances"] == {}
    client.post(f"/api/groups/{group['id']}/expenses/{expense['id']}/approve", json={"decided_by": "Ana"})
    balances = client.get(f"/api/groups/{group['id']}/balances").json()["balances"]
    assert round(sum(balances.values()), 2) == 0


def test_consensus_vote_moves_between_options_and_close_records_winner(client):
    group, ana, _bo = _specialist_group(client)
    poll = client.post(f"/api/groups/{group['id']}/polls", json={"question": "Dinner?", "options": ["Pizza", "Curry"]}).json()
    first, second = poll["options"]
    client.post(f"/api/groups/{group['id']}/polls/{poll['id']}/vote", json={"option_id": first["id"], "voter_id": ana["id"]})
    moved = client.post(f"/api/groups/{group['id']}/polls/{poll['id']}/vote", json={"option_id": second["id"], "voter_id": ana["id"]}).json()
    assert moved["options"][0]["voter_ids"] == []
    closed = client.post(f"/api/groups/{group['id']}/polls/{poll['id']}/close").json()
    assert closed["winner_option_id"] == second["id"]


def test_packing_list_uses_weather_and_trip_interests(client):
    group, _ana, _bo = _specialist_group(client)
    result = client.post(f"/api/groups/{group['id']}/packing", json={"days": 3, "weather": "rain"}).json()
    assert "waterproof jacket" in result["personal"]
    assert "refillable water bottle" in result["personal"]


def test_local_guide_returns_an_exa_ready_prompt_with_constraints(client):
    group, ana, _bo = _specialist_group(client)
    client.patch(f"/api/groups/{group['id']}/members/{ana['id']}/preferences", json={"constraints": ["limited walking"]})
    result = client.get(f"/api/groups/{group['id']}/local-guide", params={"need": "rainy-day lunch"}).json()
    assert "Prague" in result["search_prompt"]
    assert "limited walking" in result["search_prompt"]


def test_trip_memory_accepts_only_known_media(client):
    group, _ana, _bo = _specialist_group(client)
    bad = client.post(f"/api/groups/{group['id']}/memories", json={"title": "Dinner", "media_ids": ["missing"]})
    assert bad.status_code == 422
    media = client.post(f"/api/groups/{group['id']}/media", json={"filename": "group-selfie.jpg"}).json()
    memory = client.post(f"/api/groups/{group['id']}/memories", json={"title": "First dinner", "description": "We all met.", "media_ids": [media["id"]]}).json()
    assert memory["media_ids"] == [media["id"]]


# ---------------------------------------------------------------------------
# Planning around what each traveller said
# ---------------------------------------------------------------------------
def _member(name, **kwargs):
    from app.models import Member

    return Member(id=name.lower(), display_name=name, joined_at=0.0, **kwargs)


def test_the_walking_limit_comes_from_the_least_mobile_person():
    from app.services import accessibility

    limit, notes = accessibility.walking_limit(
        [
            _member("Ana", constraints=["no long walks please"]),
            _member("Bo", constraints=["uses a wheelchair"]),
            _member("Cy", constraints=["happy with anything"]),
        ]
    )
    # A group walks together, so the tightest limit wins.
    assert limit == 400
    assert any("Ana" in n for n in notes) and any("Bo" in n for n in notes)


def test_an_unconstrained_group_has_no_walking_limit():
    from app.services import accessibility

    limit, notes = accessibility.walking_limit(
        [_member("Ana", preferences=["long walks", "hiking"])]
    )
    assert limit is None
    assert notes == []


def test_every_leg_of_a_limited_route_is_within_the_limit():
    """The limit is satisfied by construction, not by trimming and hoping.

    Trimming is what fails: drop the middle stop of A-B-C and the new A-C leg
    can be longer than either of the two it replaced.
    """
    from app.services import planner

    distances = [
        #        meet   near  near2   far
        [0, 300, 400, 5000],
        [300, 0, 200, 4800],
        [400, 200, 0, 4700],
        [5000, 4800, 4700, 0],
    ]
    order = planner._route_within_limit(distances, limit=900)

    assert order[0] == 0
    assert 3 not in order  # the far stop is unreachable within the limit
    for i in range(1, len(order)):
        assert distances[order[i - 1]][order[i]] <= 900


def test_a_trimmed_route_would_have_broken_the_limit():
    """Guards the bug this replaced: the old trim left a 3 km leg behind."""
    from app.services import planner

    # Dropping the middle stop joins 0 and 2 into a leg longer than the limit.
    distances = [
        [0, 500, 2400],
        [500, 0, 500],
        [2400, 500, 0],
    ]
    order = planner._route_within_limit(distances, limit=900)
    for i in range(1, len(order)):
        assert distances[order[i - 1]][order[i]] <= 900
    # It keeps both stops by going through the middle one, rather than dropping it.
    assert order == [0, 1, 2]


def test_an_unreachable_route_says_so_instead_of_pretending(client):
    group = client.post("/api/groups", json={"name": "G", "city": "Prague"}).json()
    gid = group["id"]
    ana = client.post(
        f"/api/groups/{gid}/members", json={"display_name": "Ana"}
    ).json()
    client.patch(
        f"/api/groups/{gid}/members/{ana['id']}/preferences",
        json={"constraints": ["uses a wheelchair"]},
    )

    plan = client.post(f"/api/groups/{gid}/plan", json={"max_stops": 4}).json()
    notes = " ".join(plan["constraints_applied"])

    if plan["stops"]:
        longest = max(s["distance_from_previous_m"] for s in plan["stops"])
        # Either every leg fits, or the plan admits that it does not.
        assert longest <= 400 or "nothing lies within" in notes
    assert "Ana" in notes


def test_the_plan_reports_which_constraint_changed_it(client):
    group = client.post(
        "/api/groups", json={"name": "G", "city": "Prague"}
    ).json()
    gid = group["id"]
    ana = client.post(
        f"/api/groups/{gid}/members", json={"display_name": "Ana"}
    ).json()
    client.patch(
        f"/api/groups/{gid}/members/{ana['id']}/preferences",
        json={"constraints": ["bad knee today"]},
    )

    plan = client.post(f"/api/groups/{gid}/plan", json={"max_stops": 4}).json()
    # The group is told what was applied, rather than it happening silently.
    assert any("Ana" in note for note in plan["constraints_applied"])
    assert any("bad knee" in note for note in plan["constraints_applied"])


def test_a_preference_only_one_person_voiced_still_steers_the_heuristic(monkeypatch):
    """Without a model, one person's stated want still moves the scoring.

    It lifts a place rather than trumping everything: a cafe somebody asked for
    should not outrank Prague Castle, and it does not.
    """
    monkeypatch.setattr(ranking.settings, "anthropic_api_key", None)
    places = _fixture_places()

    def score_of(name, travelers):
        picked, _summary, _source = asyncio.run(
            ranking.rank_places(places, [], 1, "Prague", 5, travelers=travelers)
        )
        return next(p.score for p in picked if p.name == name)

    plain = score_of("Cafe Slavia", [])
    wanted = score_of("Cafe Slavia", [_member("Ana", preferences=["cafe"])])

    assert wanted > plain
    # And the landmark still leads the route.
    picked, _s, _b = asyncio.run(
        ranking.rank_places(
            places, [], 1, "Prague", 5, travelers=[_member("Ana", preferences=["cafe"])]
        )
    )
    assert picked[0].name == "Prague Castle"


def test_travellers_reach_the_model_in_their_own_words(monkeypatch):
    monkeypatch.setattr(ranking.settings, "anthropic_api_key", "test-key")
    captured = {}

    async def fake_call(prompt):
        captured["prompt"] = prompt
        return {"summary": "ok", "picks": [
            {"id": "node/1", "score": 0.9, "reason": "Ana asked for it", "suggested_minutes": 30}
        ]}

    monkeypatch.setattr(ranking, "_call_claude", fake_call)
    asyncio.run(
        ranking.rank_places(
            _fixture_places(), ["history"], 2, "Prague", 1,
            travelers=[
                _member("Ana", preferences=["museums"], constraints=["bad knee"], budget=120.0),
                _member("Bo", preferences=["beer"]),
            ],
        )
    )

    prompt = captured["prompt"]
    for expected in ["Ana", "museums", "bad knee", "120 EUR", "Bo", "beer"]:
        assert expected in prompt, f"{expected!r} never reached the model"
