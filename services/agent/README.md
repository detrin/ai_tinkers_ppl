# Advisory Trip Agent

A Pydantic AI agent for travel research, candidate places, and proposed
itineraries. The normal SomeJoy flow calls it **in-process** from the backend's
`POST /api/groups/{id}/ask` endpoint. No separate server is required.

This is distinct from the CopilotKit Slack coordinator and the backend's
deterministic specialist handlers.

## Tools and state

- `search_web`: optional Exa discovery, enabled with `EXA_API_KEY`.
- `find_places`, `get_place_details`, `route`: optional Google Maps tools,
  enabled with `GOOGLE_MAPS_API_KEY`.
- `save_candidates`, `publish_proposal`: write to the agent's own
  in-memory `TripStore`.

`ask()` keeps per-trip conversation history for follow-up questions.
`plan()` is a separate planning call and does not share that conversation
history. Restarting loses agent history, candidates, and proposals.

Important: `publish_proposal` does **not** publish an active backend map plan,
write a backend itinerary approval record, or post a Slack message. Bridging
that store into the shared dashboard is remaining work. Search evidence and
model instructions do not guarantee verified hours, prices, or accessibility.

## Configuration

The agent loads the repository root `.env`:

| Setting | Purpose |
| --- | --- |
| `AGENT_MODEL_PROVIDER` | Optional override of `MODEL_PROVIDER` |
| `AGENT_MODEL` | Optional override of `MODEL` |
| Selected provider key | Required for a live model run |
| `EXA_API_KEY` | Optional web discovery |
| `GOOGLE_MAPS_API_KEY` | Optional Places/Routes tools |

Configuration maps `openai`, `openrouter`, `anthropic`, and `deepseek`
to their provider keys. Installed provider dependencies and model availability
still need verification for your chosen provider. OpenRouter uses
`OPENROUTER_API_KEY`; it does not require an OpenAI key.
Model choice comes from local configuration, not a fixed model in this README.

## Run independently (optional)

Python 3.12+ and uv, from the repository root:

```bash
cd services/agent
uv sync
uv run agent "Plan Saturday afternoon in Prague, food and museums, under EUR 40"
```

For the standalone AG-UI endpoint, use a different port from the trip backend:

```bash
uv run uvicorn agent.api:app --host 127.0.0.1 --port 8001
```

This exposes the agent's `POST /` protocol endpoint. The main demo does not
point its Slack coordinator at this endpoint; it uses the backend bridge.

## Test

```bash
uv run pytest
```

The agent suite uses mocked external calls/test models. Root `npm run verify`
does not run it. Live credentials and provider behavior need separate checks.

## Layout

- [trip_agent.py](src/agent/trip_agent.py): prompt, tool wiring, ask/plan.
- [storage.py](src/agent/storage.py): in-memory candidates, proposals, history.
- [config.py](src/agent/config.py): provider/environment settings.
- [tools](src/agent/tools): Exa and Google Maps adapters.
- [api.py](src/agent/api.py): optional AG-UI endpoint.
- [backend bridge](../../backend/app/services/agent_bridge.py): normal integration.

Next steps: durable shared storage, publish/read-back integration with backend
proposals, and end-to-end tests proving that advisory results reach the map.
