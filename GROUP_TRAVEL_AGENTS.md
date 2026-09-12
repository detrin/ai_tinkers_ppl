# SomeJoy agents — implementation and handoff

This is the current implementation map, not a promise that every planned agent
is complete. Read the [root README](README.md) for installation and
[the demo script](dev-docs/somejoy-demo.md) for live checks.

## Architecture and ownership

```text
Slack thread -> apps/channel (model + typed tools) -> backend REST API
                                                      |
frontend map/dashboard <------- REST + WebSocket ------+
apps/web itinerary workspace <------ REST -------------+
                                                      |
                                      /ask -> services/agent
apps/web approved follow-up -> server adapter -> Ambiguous AI
```

The shared trip backend owns groups, members, active plans, itinerary proposals,
media metadata, expenses, polls, and memories. Its JSON snapshot is separate
from the advisory agent's in-memory conversation/candidate/proposal store.
Ambiguous stores follow-up tasks, not these trip records.

There is one Slack coordinator with specialist tools and an additional
Pydantic AI advisory agent. Adding a specialist does not require another
process. The map dashboard and Next.js trip workspace are different apps.

## Implemented tools and visible results

| Workflow | Slack tool | Backend/UI result |
| --- | --- | --- |
| Group setup | `create_travel_group`, `lookup_travel_group` | Real group and join code; travellers join separately in the map UI |
| Thread context | `read_thread` | Reads available Slack history; not automatic persistence of messages/preferences |
| Planner | `propose_trip_itinerary` | Shared proposed itinerary; approve/decline in the Next.js workspace |
| Research agent | `ask_travel_agent` | Advisory answer from `/api/groups/{id}/ask`; no active-map publication |
| Search | `search_web` (with Exa key) | Source links in Slack; no saved dashboard search feed |
| Local guide | `prepare_local_guide_search` | Builds a trip-aware query; Exa must then be called for current evidence |
| Media organizer | `organize_travel_media` | Filename/category/note/location/day record, listed under Media |
| Money split | `propose_trip_expense` | Equal-split proposal and Slack receipt; dashboard approval changes balances |
| Consensus | `create_consensus_poll` | Persistent poll; registered members vote in dashboard |
| Packing | `build_packing_list` | Generated personal/shared list; dashboard can generate a separate list |
| Trip memory | `add_trip_memory` | Confirmed text entry with optional known media IDs, listed in dashboard |

The inherited `propose_action` approval card records a decision; it is not a
general executor, a payment tool, or an itinerary-approval endpoint.

### Planning boundaries

- The map's direct Build route operation calls `POST /plan` and updates the
  active plan immediately. It does not wait for itinerary-proposal approval.
- `POST /proposals` creates a proposal. Approving that proposal publishes its
  plan; declining it does not. The Next.js app at port 3100 exposes this UI.
- Stored traveller preferences/constraints can influence ranking and mobility
  limits. Mentioning a preference in Slack does not automatically store it in
  the corresponding backend member record.
- Routes are ordered stops, not a full day-by-day scheduling or booking engine.
  Diet, budget, opening hours, and accessibility still need verification.
- ORS provides the pedestrian path; OSRM's default demo profile is driving.
  Fallback walking estimates are not verified accessible routes.

### Money split boundaries

Payer and participants must be registered group members. Amounts are divided
equally in integer cents; remainder cents go to participants in order.
Only approved expenses affect balances. Approval records an accounting decision,
not a money transfer. Custom weights, debt settlement, refunds, and currency
conversion are not implemented. Keep each demo group in EUR; mixed currencies
are not separated in current totals.

The expense tool posts the real saved proposal as a Slack receipt and avoids an
extra model explanation once that receipt completes. A delivery failure after
saving is still possible. The same prompt resent later can create a duplicate.

### Media, packing, and memory boundaries

Media classification uses explicit category or filename/note keywords. It does
not download Slack attachments, store image bytes, inspect photos, OCR receipts,
or automatically turn receipts into expenses. Packing uses supplied weather
text, not a weather API, and is not persisted. Memories require confirmed events,
not an invented recap.

### Search and advisory agent boundaries

Exa is optional. Without its key, the search tool is not registered. Local-guide
query preparation alone is not a search. Sources returned in Slack are not
automatically saved into dashboard records.

The advisory agent can research and save candidates/proposals in its own
`TripStore`. That store is in-memory and is not the backend Group store.
Its `publish_proposal` name does not mean a map itinerary or Slack message was
published. Google Maps tools are optional and require separate credentials.
Model output is not proof a venue is open or a booking exists.

### Ambiguous boundary

The Next.js app has an approved follow-up task create/read-back workflow.
Raw Ambiguous MCP tools are disabled for the current Slack agent; configuring
its key does not turn Slack into an unrestricted workplace agent. Keep this
integration separate from itinerary and expense approval.

## Source map

| Area | Start here |
| --- | --- |
| Slack lifecycle and fast lookup | [channel.tsx](apps/channel/src/channel.tsx) |
| Slack trip/specialist tools | [trip-tools.ts](apps/channel/src/trip-tools.ts) |
| Slack run lifecycle | [agent.ts](apps/channel/src/agent.ts) |
| Shared model factory and prompt | [agent-core](packages/agent-core/src/agent.ts), [prompt](packages/agent-core/src/prompt.ts) |
| Backend group schemas and state | [models.py](backend/app/models.py), [store.py](backend/app/store.py) |
| Specialist REST handlers | [specialists.py](backend/app/routers/specialists.py) |
| Thread mapping/preferences/proposals API | [trips.py](backend/app/routers/trips.py) |
| Route planning | [planner.py](backend/app/services/planner.py) |
| Advisory agent bridge | [agent_bridge.py](backend/app/services/agent_bridge.py) |
| Advisory agent | [services/agent](services/agent/README.md) |
| Expense/poll/media/packing/memory UI | [SpecialistsPanel.tsx](frontend/src/components/SpecialistsPanel.tsx) |
| Next.js trip controls | [trip-control.tsx](apps/web/src/components/trip-control.tsx) |
| Ambiguous write boundary | [followups.ts](apps/web/src/lib/server/followups.ts) |

## Cross-surface synchronization

These backend endpoints exist but still need automatic Slack wiring:

- Thread-to-trip mapping keyed by workspace, channel, thread ID.
- A message log with caller-supplied source-message deduplication.
- Member preference/constraint updates.

Current Slack tools explicitly create/look up groups by ID/code and call shared
specialist endpoints. They do not automatically identify every Slack speaker as
a registered traveller, archive the whole thread, or apply every stated constraint.

Use the same backend URL on both surfaces. On another machine,
`127.0.0.1` means that machine, not the original laptop. Share a deployed
backend URL securely, or run your own backend with your own trip data.
Do not copy the team's live secrets or private state into Git.

## Remaining work, in practical order

1. **Reliable identity/context sync:** map Slack thread and user IDs to trips
   and members, archive source messages, extract preferences with provenance and
   explicit correction/confirmation.
2. **Write safety:** request-level idempotency across specialist writes,
   actionable user-facing errors, retry/read-back recovery, and delivery tracing.
3. **Persistent shared agent state:** database-backed groups and conversations;
   connect advisory candidates/proposals to the same approval and map pipeline.
4. **Planning completeness:** multi-day timing, verified hours/costs, explicit
   accessibility/diet constraints and conflict resolution.
5. **Real media pipeline:** permission-scoped attachment downloads, object storage,
   vision/OCR with uncertainty, receipt review before proposing expenses.
6. **Expense completeness:** currency-aware ledgers, non-equal splits, settlement
   suggestions, and edit/audit flows (no payment execution without authorization).
7. **Production readiness:** authentication, per-trip authorization, privacy and
   retention controls, multi-worker persistence, deployment and observability.
8. **UX polish:** itinerary approval in the map dashboard, saved search candidates,
   shared packing checklist, poll closing, and cross-surface status feedback.

## Working on another machine

Follow the root quickstart; request secrets privately or use your own accounts.
Use an independent managed Channel/project while developing if another teammate
is already serving the team's Channel. Two listeners can compete for deliveries.

Do not overwrite `.env`, commit state snapshots, or replace pinned SDK versions
casually. Read AGENTS.md and the Channels skill before Slack changes.
Run root verification, frontend build, backend tests, and the advisory-agent
suite for changes affecting those components. Finish with a real Slack mention
and verify the actual saved record in the UI/API; offline tests are not enough.
