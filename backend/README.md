# Group City Route — backend

A group picks a city. The server scans it for places worth visiting, Claude
chooses the ones that group will like, the stops get ordered into a walking
route, and everyone's live position stays in sync over a WebSocket.

It runs with **zero API keys**. Places come from OpenStreetMap, geocoding from
Nominatim, distances from a public OSRM server. Add an Anthropic key to turn on
the AI pass; add an OpenRouteService key for real pedestrian routing.

## Run it

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Interactive docs: <http://127.0.0.1:8000/docs>. Provider status: `GET /health`.

```bash
pytest tests -q
```

If `../frontend` has been built with `npm run build`, the same server also hosts
the map UI: <http://127.0.0.1:8000/> redirects to it at `/ui/`. Mounting it
under a prefix keeps it from ever shadowing an API route.

## The flow

```
POST /api/groups                     name + city  ->  group with a 6-char join code
POST /api/groups/{id}/members        display name ->  member id
PUT  /api/groups/{id}/members/{m}/position        ->  broadcast to the group
POST /api/groups/{id}/plan           interests    ->  ordered, measured itinerary
WS   /ws/groups/{id}?member_id={m}                ->  live positions and plan updates
POST /api/groups/{id}/ask            question     ->  Trip Agent's free-text answer
```

Supporting endpoints: `GET /api/cities/resolve?q=Prague` resolves a city name,
and `GET /api/places?city=Prague` returns the raw candidate list for a search
screen, before any group exists.

## `POST /groups/{id}/ask` — the Trip Agent

A separate, additive path alongside `POST /plan`: a free-text question in
("any good rainy-day backup?"), a free-text answer out, with the group's city
and interests riding along as context. It does not touch `Group.plan` -- it's
an advisory sidecar (chat/notes panel), not a second itinerary pipeline, so
it stays independent of the Overpass/Claude/routing flow above.

Backed by [`services/agent`](../services/agent), a separate uv-managed
Pydantic AI project installed here as an editable dependency (see
`requirements.txt`) so the call is in-process, not a network hop to another
service. It reads its own `AGENT_MODEL_PROVIDER`/`AGENT_MODEL`/API key from
the repo-root `.env` (see `services/agent/README.md`) -- nothing to
configure here. Without a configured provider key, `/ask` returns `503`
rather than failing the rest of this backend; every other integration here
degrades the same way (see below).

## What happens inside `POST /plan`

1. **Meeting point.** The geometric median of everyone's last known position,
   not the average, so one member stuck across town does not drag the whole
   route toward them. With no positions reported it falls back to the city
   centre.
2. **Scan.** One Overpass query pulls every named museum, landmark, park,
   gallery, theatre, market and cafe within the radius. Unnamed geometry is
   dropped and places mapped twice are merged. A typical city centre yields
   300 or more candidates.
3. **Prior score.** Each candidate gets a score from its OSM tags. A castle
   outranks a memorial; a Wikidata entry lifts a place above one that is merely
   mapped.
4. **AI pick.** The top 70 candidates go to Claude with the group's interests
   and size. It returns the chosen ids, a fit score, a one-line reason, and how
   long to spend at each. Structured output is schema-constrained, and ids that
   are not in the candidate list are discarded, so the model cannot invent a
   place.
5. **Distances.** One matrix call covers the meeting point and every stop.
6. **Order.** Nearest neighbour, then 2-opt until nothing improves. This is
   exact for the handful of stops a group does in a day; a test checks it
   against brute force.

## Live positions

Each member opens one socket. Sending `{"type":"position","lat":…,"lon":…}`
stores the position and pushes it to everyone in the group, including the
sender, annotated with distance to the meeting point and to the next stop.
Those two distances are straight-line on purpose: they recompute on every
position tick, and routing each one would burn the provider quota for a number
that changes by metres.

Socket events: `snapshot`, `position`, `presence`, `member_joined`,
`member_left`, `plan`, `pong`, `error`.

## Degradation, on purpose

Nothing in the request path is allowed to fail the whole plan.

| Missing | What happens |
|---|---|
| `ANTHROPIC_API_KEY` | Heuristic ranking: tag prior plus interest keyword matching. |
| `ORS_API_KEY` | Public OSRM. Its demo server is car-only, so walking times are re-derived from street distance at 4.8 km/h. |
| Both routing hosts | Straight-line distance with a 1.31 detour factor for dense city centres. |
| Overpass down | Retried three times with backoff, then a 502 with a readable message. |

The response says which path was taken: `routing_provider` and `ranked_by` are
on every plan.

## Cross-surface trip state

The operations `GROUP_TRAVEL_AGENTS.md` names under "Cross-surface
synchronization". Slack (`apps/channel`) and the web app both go through these,
so neither surface holds state the other cannot see.

```
POST   /api/trips/by-slack-thread              find or create a trip for a thread
GET    /api/trips/by-slack-thread              look one up
PATCH  /api/groups/{id}/members/{m}/preferences what the agent heard about a traveller
POST   /api/groups/{id}/messages               record a message against the trip
GET    /api/groups/{id}/messages
POST   /api/groups/{id}/proposals              build an itinerary and put it forward
POST   /api/groups/{id}/proposals/{p}/approve  the approval boundary
POST   /api/groups/{id}/proposals/{p}/decline
GET    /api/groups/{id}/proposals
```

Two rules hold across all of it.

**A proposal is not a plan.** Building an itinerary changes nothing the group is
doing. Approving one is the single place it becomes the group's plan, and
declining writes no itinerary at all. Approving a second one supersedes the
first, so the group always follows exactly one.

**Slack redelivers, so every write is idempotent.** A thread maps to one trip
however many times the mention is delivered. A message carrying a
`source_message_id` is stored once. A proposal created with an
`idempotency_key` returns the original instead of stacking up duplicates. A
repeated approval is not an error and does not re-decide. Replays answer 200
where the first call answered 201, so a caller can tell what happened.

Threads are keyed by workspace, channel and thread id, never by channel name:
names get renamed and would silently remap a trip to the wrong conversation.

Traveller preferences merge rather than replace, because the agent reports one
detail at a time as it hears it. Reporting a new constraint does not erase the
budget it learned earlier.

## Known limits

- **OSRM demo distances are car distances.** In an old town with one-way
  streets they overstate a walk, sometimes badly. An OpenRouteService key fixes
  this properly; it is the single highest-value key to add.
- **State is a JSON file.** Fine for a demo and for one process. Swap
  `app/store.py` for Postgres before running more than one worker, because the
  store and the socket rooms both live in process memory.
- **No authentication.** Anyone holding a group id can read and write it. The
  join code gates joining, nothing else.

## Layout

```
app/
  main.py            app wiring, CORS, /health
  config.py          environment -> Settings
  models.py          the wire schemas
  store.py           groups, members, positions, plans
  hub.py             WebSocket rooms and fan-out
  geo.py             haversine, geometric median, fallback matrix
  services/
    geocode.py       city name -> coordinates (Nominatim)
    places.py        Overpass query, tag scoring, dedupe
    ranking.py       the Claude call, and the heuristic that replaces it
    routing.py       distance matrix providers, 2-opt ordering
    planner.py       ties the above into a Plan
  routers/
    groups.py        REST
    trips.py         Slack mapping, travellers, messages, approvals
    realtime.py      WebSocket
tests/               39 tests, no network
```
