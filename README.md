# SomeJoy — group trips from Slack to a shared map

Plan together in Slack, then review the result in a shared web dashboard.
SomeJoy connects a Slack travel assistant to a FastAPI trip backend, a live
map, expense approvals, group polls, and trip records.

Built from the Agents, Everywhere hackathon starter kit. See
[SUBMISSION.md](SUBMISSION.md) for inherited infrastructure and event work.

## Overview

The main demo uses **two processes**: the Python backend (which serves the
built map UI) and the Slack listener. The Next.js app is an additional,
separate surface—not the map dashboard.

| Surface | Local address | Purpose |
| --- | --- | --- |
| Map dashboard (`frontend/`) | [127.0.0.1:8000/ui/](http://127.0.0.1:8000/ui/) | Join groups, share positions, build routes, approve expenses, vote, view media and memories |
| Backend | [127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | Shared REST API, WebSocket updates, API explorer |
| Slack (`apps/channel/`) | In your Slack workspace; listener uses port 3000 | Read threads, call trip tools, research, post results |
| Optional Next.js workspace (`apps/web/`) | [127.0.0.1:3100](http://127.0.0.1:3100) | Trip chat, itinerary-proposal approval, Ambiguous follow-ups |
| Optional Vite development server | [127.0.0.1:5173](http://127.0.0.1:5173) | Hot-reloading version of the map dashboard |

### Implemented capabilities

| Capability | What works now | Boundary |
| --- | --- | --- |
| Groups | Create a trip, return its real join code, join from the map UI | Slack creation does not register travellers automatically |
| Planning | Discover real city places, rank stops, calculate meeting point and route | Direct map route building publishes immediately; itinerary proposals have a separate approval flow |
| Live map | Member positions, presence, route updates | Location sharing requires user action; no background phone tracking |
| Expenses | Equal splits, proposed/approved/declined expenses, approved balances | Accounting only: no payments, settlement transfer, or safe mixed-currency totals |
| Consensus | Create polls in Slack, vote in the dashboard | No automatic booking or plan approval from a winning vote |
| Media organizer | Save filename, category, note, location, and day | Metadata/keyword classification, not photo upload, vision, or receipt OCR |
| Packing | Generate personal/shared lists from trip length and supplied weather | Generated on demand; not a shared persisted checklist or live weather feed |
| Memories | Save confirmed moments and references to known media records | No automatic photo montage or inferred events |
| Search/local guide | Exa search with source links; trip-aware query preparation | Requires Exa configuration; search results are not automatically saved to the map |
| Advisory research agent | Multi-turn research through backend `/ask`, optional Maps tools | Separate in-memory conversation/candidate store; does not publish the active map plan |
| Ambiguous AI | Optional approved follow-up task creation/read-back in the Next.js app | Not the trip database; raw MCP tools are disabled in the current Slack agent |

These are specialist **tools/workflows**, coordinated by the Slack agent, plus
an advisory Pydantic AI agent. They are not separate autonomous servers.
See [the implementation and handoff guide](GROUP_TRAVEL_AGENTS.md) for source
files, state ownership, and remaining work.

## Get started

Use Node.js 22+ and Python 3.12+. Check `node --version` in each terminal:
a directory-specific version manager may select a different Node version.

### 1. Install a fresh checkout

```bash
git clone https://github.com/detrin/ai_tinkers_ppl.git
cd ai_tinkers_ppl
npm ci
cp .env.example .env
npm ci --prefix frontend
npm run build --prefix frontend
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Run the copy step **only for a fresh checkout without an existing .env**.
If you already pulled this repository, keep your current folder and secrets.
The frontend is not a root npm workspace and needs its own install.
The Python requirements install `services/agent` as an editable dependency;
no separate agent server is needed for the demo.

### 2. Configure only the integrations you use

Edit the root `.env` locally. Never commit it or paste credentials into chat.

| Setting | Needed for |
| --- | --- |
| `MODEL_PROVIDER`, `MODEL`, selected provider API key | Slack/Next.js chat; OpenRouter uses `OPENROUTER_API_KEY` and a tool-capable model slug |
| `INTELLIGENCE_API_KEY`, `CHANNEL_CODE` | Managed Slack connection; follow onboarding below |
| `TRIP_API_URL=http://127.0.0.1:8000` | Slack reaching the local trip backend |
| `EXA_API_KEY` | Live web research; absent means no Exa search tool |
| `ANTHROPIC_API_KEY`, optional `ANTHROPIC_MODEL` | Optional backend AI place ranking; otherwise heuristic ranking |
| `ORS_API_KEY` | Optional pedestrian routing; otherwise OSRM/estimated fallback |
| `NOMINATIM_USER_AGENT` | An identifying application/contact string for public geocoding |
| `AMBIGUOUS_API_KEY` | Optional Next.js follow-up task workflow |
| `AGENT_MODEL_PROVIDER`, `AGENT_MODEL` | Optional independent advisory-agent model; otherwise uses shared configuration |
| `GOOGLE_MAPS_API_KEY` | Optional advisory-agent Places/Routes tools |

The basic backend works without model keys, but still uses external geocoding
and place services. Missing keys are not a guarantee that every operation has a
fallback: Slack chat needs its selected model, and `/ask` needs a configured
advisory provider. See [.env.example](.env.example) and
[the sponsor guide](using-sponsor-tools.md).

### 3. Start the demo

Terminal 1, from the repository root:

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, from the repository root after Slack onboarding:

```bash
npm run start --workspace channel
```

Open [the map dashboard](http://127.0.0.1:8000/ui/).
For frontend development, run `npm run dev --prefix frontend` in another
terminal. For the optional Next.js workspace, run `npm run dev:web`.

Use the stable Slack start command for a demo. `npm run dev:slack` enables
watch mode; edits can interrupt a turn. Keep only one listener per managed
Channel. An `EADDRINUSE` error means a port is occupied, not that the existing
process is healthy. See [troubleshooting](dev-docs/troubleshooting.md).

### CopilotKit onboarding

For a new Slack connection, run from the repository root:

```bash
npm run channel:setup -- --no-clipboard
```

Give the emitted prompt to your coding agent and specify **Slack using the
existing apps/channel app**. It installs the current `channels-setup` skill;
the command alone does not provision or connect a Channel. Follow its current
instructions through project selection, Slack installation, credentials, and a
real reply. Preserve existing code and environment values. The listener reads
`INTELLIGENCE_API_KEY` and `CHANNEL_CODE`; map CLI-provisioned credentials to
the variable this runtime actually reads.

Web/mobile can use the configured model provider without Intelligence.
Managed conversation persistence is an additional integration, separate from
trip-state persistence. If you choose it, use this handoff:

```text
Read AGENTS.md and the selected app README. Connect that app to CopilotKit
Intelligence using the current official onboarding workflow. Preserve the
existing app, model provider, tools, and approval behavior. For apps/mobile,
keep Expo and its separate install; its runtime is served by apps/web.
Generate a fresh 12-character hexadecimal run ID and substitute it for RUN_ID:
npx --yes copilotkit@latest onboard start --run RUN_ID
Follow the returned instructions using the same run ID. Show the integration
plan before editing, and verify the selected app before and after connecting.
```

## Demo and verification

Start with [the Slack-to-UI demo script](dev-docs/somejoy-demo.md). It includes
prompts, expected UI changes, and checks that distinguish saved records from
assistant prose.

```bash
npm run verify
npm run build --prefix frontend
cd backend
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

`npm run verify` runs root workspace typechecks/tests (agent-core, channel,
web). It does not include frontend builds, Python tests, or mobile checks.
For the advisory agent's own suite, see [services/agent](services/agent/README.md).
Offline tests do not establish that live Slack, model, Exa, or Ambiguous
credentials work; rehearse the live flow separately.

## State and limitations

- Shared trip records live in backend memory with a JSON snapshot by default.
  Run one worker. Preserve the same `STATE_FILE` across restarts; the default
  `state.json` is relative to the backend working directory.
- Slack thread reading is implemented. Automatic thread-to-trip mapping,
  message archiving, and per-traveller preference extraction are **not wired
  into the Slack handlers**, even though supporting backend APIs exist.
- Use one currency per group. The balance code does not separate currencies.
- Not all writes are idempotent. Check the dashboard before retrying a timed-out
  expense, poll, media entry, or memory to avoid duplicates.
- There is no production authentication/authorization on the trip API. A join
  code is not an access-control system. Do not expose private trip data publicly.
- Without pedestrian routing, walking distances and mobility checks are
  estimates. Generated stops are not a guaranteed multi-day schedule, accessible
  route, current opening-hours check, or enforceable budget.

## Templates

The retained starter surfaces are [Slack](apps/channel/README.md),
[Next.js web](apps/web/README.md), and [React Native](apps/mobile/README.md).
The mobile app remains a separate finance example, not a SomeJoy mobile app.
Inherited demos in `assets/demos/` illustrate starter infrastructure rather
than the current trip workflow.

## Coding agent

Read [AGENTS.md](AGENTS.md), [the hackathon overview](hackathon-overview.md),
[the rules](hackathon-rules.md), and [the sponsor guide](using-sponsor-tools.md).
Use [GROUP_TRAVEL_AGENTS.md](GROUP_TRAVEL_AGENTS.md) as the current handoff.
Read the [Channels skill](.agents/skills/build-channels-agent/SKILL.md) before
changing `apps/channel/`. Preserve pinned dependency pairs and existing work.

## Resources

- [Backend setup and API](backend/README.md)
- [Map dashboard](frontend/README.md)
- [Slack setup and tools](apps/channel/README.md)
- [Developer documentation](dev-docs/README.md)
- [Submission checklist](SUBMISSION.md)
