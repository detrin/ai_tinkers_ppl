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
from app.services import geocode, planner, ranking, routing  # noqa: E402
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


def test_websocket_rejects_an_unknown_member(client):
    group = client.post("/api/groups", json={"name": "G", "city": "Prague"}).json()
    with pytest.raises(Exception):
        with client.websocket_connect(
            f"/ws/groups/{group['id']}?member_id=nobody"
        ) as socket:
            socket.receive_json()
