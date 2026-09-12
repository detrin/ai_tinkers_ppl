# services/agent — Trip Agent

The Trip Agent researches, validates, and proposes group trip itineraries.
It's built on [Pydantic AI](https://ai.pydantic.dev/), not a hand-rolled
loop — Pydantic AI owns the tool-calling loop, JSON schema generation (from
type hints + docstrings), and model provider selection. This service only
supplies the domain layer.

Pydantic AI was chosen over the OpenAI Agents SDK / LangGraph / CrewAI
because it has first-party [AG-UI](https://docs.ag-ui.com/) support — the
same protocol `packages/agent-core/src/agent.ts` already documents as the
intended way to swap a non-CopilotKit agent into `apps/channel`/`apps/web`
(`HttpAgent` from `@ag-ui/client`). LangGraph/CrewAI/Google ADK also have
AG-UI adapters but are heavier multi-agent orchestration frameworks than a
single tool-calling loop needs; the OpenAI Agents SDK has no AG-UI support
(open, unresolved requests on both repos as of writing).

## Layout

```
src/agent/
  trip_agent.py       System prompt + tool wiring + plan()/ask(). The domain layer.
  storage.py          TripStore protocol + InMemoryTripStore -- candidates,
                       itineraries, and per-trip_id conversation history for
                       ask(). Swap for a real DB once services/api owns the
                       trips schema.
  config.py           Settings, loaded from the repo-root .env.
  cli.py              `uv run agent "<constraints>"` for local runs.
  api.py              AG-UI endpoint (Starlette) -- `uv run uvicorn agent.api:app`.
  tools/
    exa.py            search_web — qualitative web discovery.
    google_maps.py    find_places / get_place_details / route — the
                       factual validator (Places API (New) + Routes API).
tests/                One test module per source module; tools are tested
                       against a mocked httpx, the full loop against
                       Pydantic AI's built-in `test` model — no network
                       calls or API keys needed anywhere.
```

The tool layer is the crucial boundary: `search_web` is for discovery and
qualitative context, `find_places` / `get_place_details` / `route` are for
facts (existence, hours, price, travel time). The instructions in
`trip_agent.py` tell the model to validate anything search_web surfaces
before including it in a plan, so it can't invent logistics from a blog
post. Tool failures raise `pydantic_ai.ModelRetry` instead of crashing the
run, so the model sees the failure and can adapt.

`search_web` and the Maps tools are only registered when their API key is
set (`EXA_API_KEY`, `GOOGLE_MAPS_API_KEY` in the repo-root `.env`) — same
pattern as `packages/agent-core`'s search capability. `save_candidates` and
`publish_proposal` are always registered; they write into the in-memory
`TripStore` for now.

Model provider comes from the repo-root `.env`'s `AGENT_MODEL_PROVIDER`/
`AGENT_MODEL` (falling back to the shared `MODEL_PROVIDER`/`MODEL` that
`apps/channel`/`apps/web` use if unset), mapped in `config.py` to a Pydantic
AI `"provider:model"` string. Currently `openrouter` /
`thinkingmachines/inkling-small`. `openai`, `anthropic`, and `deepseek` are
also wired up — extend `_PROVIDER_ENV_VARS` there before using another one.

`plan()` produces a full itinerary in one shot. `ask()` is a running
conversation per `trip_id` -- each call's messages are appended to
`TripStore`, so a follow-up ("how much does that cost?") sees the prior
answer instead of starting fresh. `plan()` does not share that history.

## Run it

```bash
cd services/agent
uv sync
uv run agent "Plan Saturday afternoon for six of us in Prague, food + activity, under EUR 40"
```

Requires `OPENAI_API_KEY` in the repo-root `.env`. `EXA_API_KEY` and
`GOOGLE_MAPS_API_KEY` are optional — without them the agent runs with a
smaller tool set and a warning in the logs.

### As an AG-UI service

```bash
uv run uvicorn agent.api:app --reload
```

Exposes `POST /` speaking the AG-UI protocol, so an `HttpAgent` from
`@ag-ui/client` (JS) can point at it directly — see the swap-out comment in
`packages/agent-core/src/agent.ts`.

## Test

```bash
uv run pytest
```

No API keys required; every external call is mocked, and the end-to-end
loop test uses Pydantic AI's built-in `test` model (`Agent('test')`).

## Used by backend/

`backend/` (a separate FastAPI project) installs this as an editable
dependency (`-e ../services/agent` in `backend/requirements.txt`) and calls
`TripAgent.ask()` in-process from `POST /api/groups/{id}/ask` — see
`backend/app/services/agent_bridge.py` and `backend/README.md`. `group_id`
is passed straight through as `trip_id`, so the group *is* the session; no
separate agent-side session concept exists.

## Not built yet

- `services/api` — the HTTP layer (`POST /trips/:id/plan`, auth, webhook
  endpoints) that would front this agent for Slack and web, if the AG-UI
  path above and the backend/ bridge above don't end up covering that need.
- A real `TripStore` backed by the `trips` / `candidate_places` /
  `itinerary_options` tables from the architecture doc (currently in-memory
  only -- conversation history and candidates are gone on restart).
- `publish_proposal` pushing to Slack/web instead of just persisting.
