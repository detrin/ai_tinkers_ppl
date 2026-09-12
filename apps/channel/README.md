# SomeJoy Slack trip assistant

The managed CopilotKit Channel connects Slack conversations to the shared trip
backend. It reads thread context, calls typed travel tools, and posts native
cards, search sources, and expense receipts.

## Get started

Follow the [root quickstart](../../README.md#get-started), start the backend,
and configure the root `.env` with:

- `MODEL_PROVIDER`, `MODEL`, and the selected provider key.
- `INTELLIGENCE_API_KEY` and matching `CHANNEL_CODE`.
- `TRIP_API_URL` (defaults to the local backend at port 8000).
- Optional `EXA_API_KEY` for live search.

For a new Slack connection, run:

```bash
npm run channel:setup -- --no-clipboard
```

Give the emitted prompt to your coding agent; choose Slack and preserve this
app. Follow the installed `channels-setup` skill through provisioning and a
real reply. Installing the skill alone does not connect Slack.
See [CopilotKit onboarding](../../README.md#copilotkit-onboarding).

Start a stable listener from the repository root:

```bash
npm run start --workspace channel
```

Use `npm run dev:slack` only when you want file watching. Do not run both.
Keep one listener per managed Channel, including other teammates' machines.
The managed path needs a long-running process but no public tunnel to this
listener; Intelligence owns Slack ingress and platform credentials.

## Try the flow

In the target Slack channel:

```text
/invite @trip-planner
```

Use your actual bot name if different. Then mention it:

```text
@trip-planner Create a travel group called Prague Weekend in Prague.
We like history, museums, local food, and architecture. We prefer walking.
Return the real join code.
```

Join that code in the map dashboard and register travellers before testing
expenses. Use [the complete demo script](../../dev-docs/somejoy-demo.md) for
lookup, search, split, polls, and expected UI results. There is no custom
`/trip` command in this app; `/invite` is Slack's own command.

## Tools and behavior

See [the capability matrix](../../GROUP_TRAVEL_AGENTS.md#implemented-tools-and-visible-results)
for all registered trip tools and their limitations.

- Mentions subscribe the thread; subsequent subscribed-thread messages can
  trigger the agent without another mention.
- Simple read-only join-code lookups have a deterministic fast path that posts
  real backend data without running a model. Multi-part requests use the agent.
- Expense proposals save shared data and post a deterministic receipt. Completed
  receipt-only continuations skip an unnecessary model response.
- `ChannelRunAgent` preserves the outer transcript/state and creates a fresh
  inner agent per low-level run to avoid same-tick lifecycle conflicts.
- Tool status is enabled. Diagnostic logs capture timing/stage/tool names and
  redacted errors, rather than prompt text or tool arguments.
- Exa tools are registered only with a key. Raw Ambiguous MCP tools are disabled
  in the current Slack factory; the approved task flow lives in `apps/web`.

Reading a thread is not the same as persisting each traveller's preferences.
The current handlers do not automatically archive Slack messages, map every
speaker to a member, or call the backend preference APIs.

## Source files

| Piece | File |
| --- | --- |
| Lifecycle and fast lookup | [src/channel.tsx](src/channel.tsx) |
| Trip/specialist tools | [src/trip-tools.ts](src/trip-tools.ts) |
| Run adapter | [src/agent.ts](src/agent.ts) |
| Thread tools and search | [src/tools.tsx](src/tools.tsx), [src/search.tsx](src/search.tsx) |
| Native cards | [src/components.tsx](src/components.tsx) |
| Model factory | [shared agent](../../packages/agent-core/src/agent.ts) |
| Domain prompt | [shared prompt](../../packages/agent-core/src/prompt.ts) |

Some inherited incident components and generic approval tools remain as
infrastructure references. Their approval cards do not execute trip writes.

## Verify and troubleshoot

```bash
npm run verify
npm run channel:status
curl --max-time 5 http://127.0.0.1:8000/health
```

Offline tests do not prove live provider delivery. An online listener does not
prove the backend, selected model, or search provider is responding. Send one
small lookup, inspect diagnostics, and verify the real group/card.

For a timeout after a write, refresh the dashboard before resending; the write
may have succeeded even if Slack failed to deliver its receipt. Specialist
writes are not globally deduplicated. See [troubleshooting](../../dev-docs/troubleshooting.md).

Before changing this app, read the
[Channels skill](../../.agents/skills/build-channels-agent/SKILL.md).
Keep the pinned Channels/runtime pair and deduped `@ag-ui/client`.
