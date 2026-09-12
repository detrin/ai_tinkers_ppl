# Submission checklist

Choose your city on the [global event page](https://aitinkerers.org/hackathons/global/agents-everywhere). Use that city's participant portal for the submission deadline and published judging criteria, and its handbook for eligibility and required deliverables. See [hackathon-rules.md](hackathon-rules.md) for the agent-readable summary.

## Build eligibility

- [x] Our submitted project is a net-new build created during the official hackathon period
- [x] Its core functionality was built during the event; we are not resubmitting or extending a pre-existing project and entering it as new
- [x] We identify inherited templates, libraries, prompts, components, and starter code separately from our event work

**What we inherited**

The CopilotKit *Agents, Everywhere* starter kit, at commit `86f547d`. Everything before that commit is theirs, not ours. Specifically:

- `apps/channel` — the Channels runtime, Slack delivery, `onMention` / `onMessage` subscription, and the `read_thread` and `propose_action` tools.
- `apps/web` — the Next.js app, CopilotKit runtime routes, generative-UI plumbing, and the Ambiguous follow-up integration under `src/lib/server/`.
- `packages/agent-core` — the agent factory, model resolution, and the domain-free half of the system prompt (`SURFACE_RULES`).
- The shipped incident-response demo, which we removed.

Third-party libraries: FastAPI, Pydantic, Pydantic AI, React, Vite, Leaflet, Next.js, the Anthropic SDK.

Data and services we did not build: OpenStreetMap via Overpass, Nominatim, OSRM, OpenRouteService.

**What we built during the hackathon**

A shared trip backend and two surfaces on top of it. Every commit from `2093be5` onward.

- `backend/` — the whole service. Place discovery from OpenStreetMap, AI ranking, walking-route construction, live group positions over WebSocket, the trip data model, and the itinerary approval boundary. 47 tests.
- `frontend/` — the React map UI. Groups, join codes, live member positions, the drawn route.
- `services/agent/` — a Pydantic AI Trip Agent that researches with Exa and validates with Google Maps, reachable from the backend at `/api/groups/{id}/ask`.
- `apps/channel/src/trip-tools.ts` — the Slack tools that create and look up a trip against the shared backend.
- `apps/web` — we deleted the incident sample (`src/lib/incidents.ts`, `app-control.tsx`) and replaced the page with the trip workspace (`src/lib/trips.ts`, `src/components/trip-control.tsx`, `src/app/page.tsx`).
- `packages/agent-core/src/prompt.ts` — we replaced `ONCALL_ROLE` with `TRAVEL_ROLE`. The starter's own comment calls that half the disposable demo domain; we kept `SURFACE_RULES` untouched.

## Title and description

**What you built**

A group trip planner that lives in the Slack thread where the trip is already being discussed, and on a live map the group can open on their phones.

People talk about the trip in Slack. The agent reads the thread and records what each traveller actually said: what they want to see, what they cannot do, what they can spend. When someone asks for a plan, the backend scans the real city from OpenStreetMap, Claude picks the places that suit those particular people, and the stops are ordered into a walking route. The itinerary comes back as a proposal. It becomes the group's plan only when a person approves it, in Slack or on the web.

The map shows where everyone currently is, the meeting point computed from their actual positions, and how far each person is from it.

**Who it is for**

Four friends with one weekend in Prague, organising it in a Slack thread. One lands at 9pm on Friday. One has a bad knee. One is on a tight budget. Today that group ends up with a Google Doc nobody updates and an argument about where to meet.

**Why the context matters**

The agent knows things nobody typed into a form.

- **It heard the constraints.** Ana writing "my knee is bad today" in the thread is recorded against her and changes the route: the planner drops stops beyond her reach and rebuilds so no leg exceeds her limit. In our Prague run the route went from five stops with a 1011 m leg to four with nothing over 778 m, and the plan says why. A chatbox would need her to fill in a mobility field she would never fill in.
- **It knows where people are.** The meeting point is the geometric median of the group's live positions, not the city centre, so one person stuck across town does not drag everyone else. That cannot exist in a chat window with no map and no location.
- **The thread is the record.** Slack redelivers events, so every write is idempotent: one mention maps to one trip however many times it arrives, a message is stored once, and a repeated approval does not re-decide.

**Sponsor technologies used**

- **CopilotKit Channels** — puts the agent in Slack: thread subscription, mentions, and the tools that reach the shared backend.
- **Anthropic Claude** — picks which of several hundred real candidate places suit this group, and writes the one-line reason shown against each stop. Schema-constrained, and any place id it returns that was not in the candidate list is discarded, so it cannot invent a landmark.
- **Exa** — qualitative discovery in the Trip Agent (`services/agent/src/agent/tools/exa.py`).
- **Google Maps Places and Routes** — the factual validator in the Trip Agent, registered only when `GOOGLE_MAPS_API_KEY` is set.
- **OpenRouter** — model provider for the Trip Agent, configurable independently of the shared model.
- **Ambiguous** — the follow-up write path inherited from the starter, now keyed by trip rather than by the sample incident.

## Evidence for the judging criteria

Judges score each of the four official criteria from 1–5. This checklist helps you gather evidence; it does not guarantee a score. A working starter is a foundation for your own project.

| Official criterion | Show in your project and demo |
|---|---|
| Core Requirements & Functionality | Run one complete workflow in the intended environment, from user request through tools to a verified result. Repeat it with live integrations; offline tests alone do not prove the deployed flow. |
| Innovation & Theme Alignment | Show the surrounding context before the prompt and explain the original interaction it enables. Compare with the context removed: what value would a standalone chatbox lose? |
| Technical Execution & Integration | Show how tools, data, and the environment connect. Demonstrate a relevant failure or cancellation path and explain recovery, state persistence, and integration limits. |
| Usefulness & Agentic Experience | Identify the user and problem, show a meaningful action in the surface, and demonstrate clear feedback and appropriate user control. Explain what work the agent saves. |

**Our evidence**

- *Core.* One trip travels the whole path: created from a Slack thread, travellers recorded, itinerary proposed, approved on the web, drawn on the map. **Still outstanding: a live Slack mention against a real workspace.** Until that is recorded, this criterion rests on the backend flow alone.
- *Innovation.* Show the thread first, then the route. Say "my knee is bad today" in Slack and rebuild: fewer stops, shorter legs, and the plan names Ana and quotes her.
- *Technical.* Every provider degrades to a working fallback, and the response says which path it took through `routing_provider` and `ranked_by`. Declining a proposal writes no itinerary. A replayed Slack event creates no duplicate. 47 backend tests plus 94 JavaScript tests, none of which touch the network.
- *Usefulness.* The approval boundary is the user control: proposing changes nothing, and only a person's click makes an itinerary the group's plan.

- [ ] We can point to visible evidence for every criterion
- [x] We distinguish live services, sample data, session-only state, and standalone recipes
- [x] Sponsor technologies contribute to the workflow; their count is not a judging criterion

## Public repository

- [x] A new participant can run the quickstart from a clean clone
- [x] The README lists the credentials and separate processes required
- [x] `npm run verify` passes; optional recipe checks pass if used
- [x] `.env`, tokens, generated traces with sensitive data, and account secrets are excluded
- [x] Sample data, session-only state, and unimplemented integrations are clearly labeled

Known limits, stated rather than hidden:

- Trip state lives in one process with a JSON snapshot. Fine for the demo, not for two workers. `backend/app/store.py` is the single place to swap for Postgres.
- There is no authentication. Anyone with a group id can read and write it; the join code only gates joining.
- Without an `ORS_API_KEY` the public OSRM server answers for cars, so street distances in a pedestrianised old town are overstated. Walking times are re-derived, and mobility limits are judged on a walking estimate rather than the car figure.
- Photos and expenses from `GROUP_TRAVEL_AGENTS.md` are not built.

## Two-minute demo video

- [ ] Show the surface and existing context before the prompt
- [ ] Demonstrate one complete interaction
- [ ] Show a visible result: an actual record, local state change, or research source links
- [ ] If showing an approval, distinguish the decision from execution and demonstrate the resulting behavior
- [ ] State which sponsor technologies made the interaction possible
- [ ] Keep the video within the event's limit and check audio

Suggested run of show, in order: the Slack thread with the constraints already in it; the mention; the proposal arriving; the web workspace showing it as waiting rather than agreed; the approval click; the map redrawing with everyone's live position; then "my knee is bad today" and a rebuild that visibly shortens the walk.

## Social post and final submission

- [ ] Follow the organizer's posting and sponsor-tagging instructions
- [ ] Link the public repository and video
- [ ] Credit the sponsors you used and applicable local partners
- [ ] Check the live integration once more before recording or submitting
- [ ] Inspect the repository, video and screenshots for secrets

Prepare the post and submission for a human to publish; running the starter kit
does not publish either automatically.
