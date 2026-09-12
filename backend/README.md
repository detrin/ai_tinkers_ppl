# SomeJoy trip backend

FastAPI owns shared trip records, city/place discovery, routes, specialist
workflows, and live group positions. It serves the built map dashboard at
[/ui/](http://127.0.0.1:8000/ui/) and API docs at
[/docs](http://127.0.0.1:8000/docs).

## Run it

From `backend/`, with Python 3.12+ (macOS/Linux):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Windows use `.venv\Scripts\python.exe` and
`.venv\Scripts\uvicorn.exe` instead. Configure the root `.env` using
[.env.example](../.env.example); preserve any existing file.
Build the map separately with `npm ci --prefix frontend` and
`npm run build --prefix frontend` from the repository root.

Use `--reload` for development only. A normal uvicorn process needs a restart
after backend code changes. A frontend build needs rebuilding after frontend
changes. Do not start a duplicate process when port 8000 is occupied.

## Configuration and health

`GET /health` reports configured ranking/routing status, not a successful live
call to every upstream provider.

| Setting | Behavior |
| --- | --- |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Optional AI ranking; without a key, heuristic ranking |
| `ORS_API_KEY` | Pedestrian routing; otherwise OSRM, then distance estimates on routing failure |
| `NOMINATIM_USER_AGENT` | Set a meaningful application/contact identifier for public geocoding |
| `PERSIST_STATE` | Defaults to true; false disables the group JSON snapshot |
| `STATE_FILE` | Defaults to `state.json`, relative to process working directory |
| `CORS_ORIGINS` | Defaults to `*`; CORS is not authentication |
| `HTTP_TIMEOUT_S` | Upstream HTTP timeout; defaults to 45 seconds |

Core route planning needs no model key but still depends on external city and
place data. Overpass failures can return 502 after retries. Fallbacks are not a
guarantee that a plan will succeed.

## API map

All group-scoped endpoints below begin with `/api/groups/{id}`.
Use the interactive docs for exact request schemas.

| Operation | Endpoint |
| --- | --- |
| Create group / add traveller | `POST /api/groups` / `POST /members` |
| Share position | `PUT /members/{member_id}/position` |
| Publish a route directly | `POST /plan` |
| Propose itinerary | `POST /proposals` |
| Review itinerary | `POST /proposals/{proposal_id}/approve` or `/decline` |
| Advisory question | `POST /ask` |
| Media metadata | `POST /media` |
| Propose expense | `POST /expenses` |
| Review expense | `POST /expenses/{expense_id}/approve` or `/decline` |
| Approved ledger | `GET /balances` |
| Create / vote / close poll | `POST /polls`, `/polls/{poll_id}/vote`, `/polls/{poll_id}/close` |
| Generate packing list | `POST /packing` |
| Prepare search query | `GET /local-guide` |
| Save confirmed memory | `POST /memories` |

WebSocket: `/ws/groups/{id}?member_id={member_id}` supports snapshots, live
position/presence and route updates. The dashboard's **Agent workspace →
Refresh** retrieves current specialist records.

## Route pipeline and approval

The planner uses a geometric median of supplied member positions (city centre
when absent), discovers candidate places with Overpass, ranks them heuristically
or with optional Anthropic, and orders stops with nearest-neighbour/2-opt routing.
Model-selected place IDs must match candidates. This is a routing heuristic,
not a general optimal multi-day scheduling guarantee.

Stored member preferences and constraints feed the planner. Mobility handling
can restrict candidate/leg distances and report `constraints_applied`.
Without ORS, mobility checks may use straight-line walking estimates because
the public OSRM profile is driving. Review distances, accessibility, opening
hours, and budget manually.

There are two distinct write paths:

- `POST /plan`, used by the map's Build route, publishes immediately.
- `POST /proposals` stores a proposed route. Its approval endpoint publishes;
  decline does not. The Next.js app at port 3100 has the proposal approval UI.

## Slack synchronization APIs

The backend also implements:

- `GET/POST /api/trips/by-slack-thread`.
- `PATCH /api/groups/{id}/members/{member_id}/preferences`.
- `GET/POST /api/groups/{id}/messages`.
- Itinerary proposal deduplication with a caller-supplied idempotency key.

These are integration building blocks. The current Slack handlers do **not**
automatically call the mapping/message/preference endpoints. Reading a Slack
thread therefore does not guarantee that its constraints are saved on members.

Deduplication applies to specific thread/message/proposal operations with
their required identifiers, not every endpoint. Resending an expense, poll,
media entry, or memory can create another record.

## Advisory agent

`POST /api/groups/{id}/ask` invokes
[services/agent](../services/agent/README.md) in-process via
[agent_bridge.py](app/services/agent_bridge.py). The requirements install that
package as an editable dependency. A separate agent server is unnecessary.

It uses `AGENT_MODEL_PROVIDER`/`AGENT_MODEL`, falling back to shared model
settings. Missing dependency/provider configuration can return 503 without
taking down the basic trip API. Exa and Google Maps tools are optional.

Conversation history, candidates, and advisory proposals live in the agent's
separate in-memory store and disappear on restart. They are not included in the
backend JSON snapshot or automatically copied into `Group.plan`.

## Specialist limits

Expenses split equally among registered members and affect balances only when
approved. No payment is made. Use one currency per group; mixed-currency totals
are not supported. Media saves metadata, not image files or OCR. Packing is
generated, not persisted. Local-guide preparation is not itself a web search.
Poll results do not execute bookings or publish plans.
See [the complete implementation guide](../GROUP_TRAVEL_AGENTS.md).

## Tests

```bash
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

Tests use local/mocked data. Verify live provider calls separately.

## Storage and security

One worker only: group state and WebSocket rooms are process-local, with an
optional JSON snapshot for groups. Keep a consistent working directory or an
absolute `STATE_FILE` to preserve the expected dataset. Never commit private
state snapshots.

The trip API has no production authentication or per-trip authorization.
Anyone with access and a group ID can issue operations. Join codes and
`decided_by` strings are not identity verification. Add authentication,
authorization, database persistence, and retention controls before exposing
sensitive data or using multiple workers.

Source: [models](app/models.py), [store](app/store.py),
[trip integration routes](app/routers/trips.py),
[specialists](app/routers/specialists.py), [planner](app/services/planner.py).
