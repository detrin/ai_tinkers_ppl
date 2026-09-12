# Group Travel Agents: Implementation Guide

This document is the handoff specification for building the group-travel project
on another machine. It describes the product, agent responsibilities,
architecture, setup, and recommended implementation order.

Before changing the repository, read:

- `AGENTS.md`
- `hackathon-overview.md`
- `hackathon-rules.md`
- `using-sponsor-tools.md`
- `apps/web/README.md`
- `apps/channel/README.md`
- `.agents/skills/build-channels-agent/SKILL.md` before editing `apps/channel/`

## Product goal

Build a shared group-travel workspace that operates in both Slack and a web
application.

People discuss a trip naturally in Slack. The system extracts preferences,
constraints, decisions, photos, and expenses from the discussion. The same
structured trip state appears in the web application, where the group can
review plans, approve changes, and see the current itinerary and budget.

The surrounding context must matter:

- Slack supplies conversation history, participants, uploaded files, and group
  decisions.
- The web app supplies the selected trip, structured records, approval UI, and
  a persistent overview.
- The agent should not require users to copy the entire Slack discussion into a
  separate chat prompt.

## Initial agent team

Start with three specialist workflows and one coordinator. They may initially
share the same model and process. Do not create separate autonomous services
unless independent execution or state becomes necessary.

### Trip Coordinator

The user-facing entry point in Slack and the web app.

Responsibilities:

- Read the active Slack thread or selected web trip.
- Identify travelers, preferences, constraints, and confirmed decisions.
- Distinguish facts from suggestions and missing information.
- Route itinerary, media, and expense work to the appropriate specialist.
- Present results and request approval for consequential changes.
- Never claim that a booking, payment, or external write happened without a
  verified result.

Example request:

```text
@trip-planner summarize our constraints and tell us what remains undecided.
```

### Itinerary Planner

Responsibilities:

- Produce a day-by-day plan using dates, arrival times, budget, interests,
  accessibility needs, and existing reservations.
- Detect scheduling and budget conflicts.
- Produce at least one alternative when constraints cannot all be satisfied.
- Return a structured proposal with estimated costs and explicit assumptions.
- Save a proposal only after approval.

### Travel Media Organizer

Responsibilities:

- Process photos uploaded through Slack or the web app.
- Classify media as a landmark, food, group photo, ticket, booking confirmation,
  receipt, or other.
- Extract visible text and relevant metadata when possible.
- Associate media with a trip, itinerary day, location, and activity.
- Flag uncertain classifications for human review.
- Never expose private images outside the selected group workspace.

### Budget and Expense Agent

Responsibilities:

- Convert approved receipt extraction into structured expenses.
- Categorize spending and associate it with a trip or itinerary activity.
- Record who paid and which travelers participated.
- Calculate splits and balances deterministically in application code.
- Compare planned and actual costs with individual and group budgets.
- Require review before saving an expense extracted from an image.

## Later agent ideas

Add these only after the initial end-to-end workflow works:

- Consensus Agent: extracts options, creates polls, finds disagreements, and
  records final decisions.
- Destination Research Agent: researches current activities, opening hours,
  transport, weather, and events with inspectable sources.
- Reservation Organizer: extracts confirmation details and detects itinerary
  conflicts without purchasing anything.
- Packing Agent: creates personal and shared packing lists from itinerary and
  weather context.
- Local Guide Agent: provides in-trip alternatives and contextual guidance.
- Trip Memory Agent: builds a post-trip timeline and organized photo story.

## Target architecture

```text
Slack workspace                          Web browser
      |                                       |
      v                                       v
apps/channel                            apps/web
      |                                       |
      +---------- shared trip API ------------+
                          |
                          v
                 persistent data store
                          |
       +------------------+------------------+
       |                  |                  |
     trips             messages           media
     travelers         decisions          expenses
     itinerary         approvals          balances
```

`packages/agent-core` remains the shared model, prompt, schemas, and common
capability layer. Surface-specific tools belong in their respective apps.

The Slack worker and web server are separate processes:

- `apps/channel` is a long-running Channels runtime. It cannot be hosted as a
  short-lived serverless function.
- `apps/web` is the Next.js application, API, and web/mobile agent runtime.
- Both must use the same persistent trip data rather than separate sample state.

## Core data model

A first implementation should support these records:

```text
Trip
- id
- name
- destination
- startDate
- endDate
- status
- slackWorkspaceId
- slackChannelId
- slackThreadId

Traveler
- id
- tripId
- displayName
- slackUserId (optional)
- budget
- preferences
- constraints

TripMessage
- id
- tripId
- source
- sourceMessageId
- authorId
- text
- createdAt

ItineraryProposal
- id
- tripId
- status: proposed | approved | declined
- days and activities
- estimatedCost
- assumptions

MediaItem
- id
- tripId
- sourceFileId or storage reference
- category
- itineraryDay
- extractedText
- confidence
- reviewStatus

Expense
- id
- tripId
- mediaItemId (optional)
- payerId
- participants
- amount
- currency
- category
- status: proposed | approved | declined
```

Use Slack's workspace, channel, and thread identifiers to map a conversation to
one trip. Do not rely on channel names as stable identifiers.

## Slack behavior

The starter already supports managed Slack delivery through CopilotKit
Channels. Preserve this routing pattern:

1. `onMention` subscribes the thread and runs the agent.
2. `onMessage` runs the agent only for an already subscribed thread.
3. `read_thread` calls `thread.getMessages()` to obtain available conversation
   history.
4. Tools return structured data to the agent and may post native Slack UI.
5. Approval buttons report or execute only the behavior explicitly implemented
   at the write boundary.

Managed Slack supports mentions, messages, reactions, buttons, and selects. It
does not deliver slash commands or modal submissions. Use messages such as:

```text
@trip-planner summarize this trip thread and show the current plan.
```

Do not design the MVP around `/trip-plan` or a Slack modal.

The current Channel code is `trip-planner`. Keep the following aligned:

- `.copilotkit/channels.json`
- root `.env` variable `CHANNEL_CODE`
- the `createChannel({ name })` value loaded by `apps/channel`

Never commit Slack tokens, signing secrets, model keys, or Intelligence keys.

## Web behavior

Replace the sample incident domain with a trip workspace. The page should show:

- Active trip and planning status
- Travelers and their constraints
- Slack discussion summary or recent synchronized messages
- Proposed and approved itinerary
- Media categories
- Budget and balances
- Unresolved decisions

Preserve the useful starter patterns:

- Page context is provided to the agent.
- Frontend tools can select a trip and prepare proposals.
- Generative UI renders structured results.
- Consequential writes occur only behind an explicit approval boundary.
- The UI displays the real saved record ID or verified updated state.

## Cross-surface synchronization

The current starter does not synchronize Slack and web state. Add a shared
storage and API layer.

Recommended production-oriented option: Supabase/Postgres. A local SQLite
implementation is acceptable for an offline prototype, but both running
processes must access the same durable database.

Minimum API operations:

```text
getTrip(tripId)
findTripBySlackThread(workspaceId, channelId, threadId)
createTripFromSlackThread(...)
upsertTravelerPreference(...)
appendSlackMessage(...)
createItineraryProposal(...)
approveItineraryProposal(...)
createMediaClassification(...)
createExpenseProposal(...)
approveExpense(...)
```

Idempotency is required for Slack messages, media, and approvals. Replayed
events must not create duplicate records.

## Suggested MVP demonstration

1. Several travelers discuss a Prague weekend in a Slack thread.
2. Their messages mention different budgets, arrival times, food preferences,
   and activities.
3. Someone mentions `@trip-planner` and asks for a plan.
4. The Coordinator reads the thread and extracts structured constraints.
5. The Planner creates an itinerary proposal and renders a native Slack card.
6. The same trip and proposal appear in the web dashboard.
7. A traveler uploads a receipt photo.
8. The Media Organizer classifies it and extracts a proposed expense.
9. A human approves the expense.
10. The Budget Agent updates the group balance in Slack and the web dashboard.

If time is limited, stop after step 6. That is already a complete cross-surface
agent workflow.

## Implementation order

### Milestone 1: preserve and verify the starter

- Configure OpenRouter and the managed Slack Channel.
- Run the existing Slack agent.
- Verify a real mention receives a response.
- Verify an unmentioned follow-up in the subscribed thread receives a response.
- Verify an unrelated unmentioned conversation remains silent.
- Run `npm run typecheck` and `npm run verify`.

### Milestone 2: establish shared trip state

- Add the database schema and server-side data access layer.
- Replace incident sample records with trips and travelers.
- Add a Slack thread-to-trip mapping.
- Expose recent Slack messages and structured constraints in the web app.

### Milestone 3: Coordinator and Planner

- Replace incident prompts and schemas with travel equivalents.
- Add tools for reading and updating trip state.
- Add a native Slack trip/itinerary component.
- Add a web itinerary component.
- Add proposal, approval, decline, and idempotency tests.

### Milestone 4: photos and expenses

- Accept Slack or web image metadata through a controlled server path.
- Classify images and store only authorized references.
- Extract receipt fields into a proposal, not a final expense.
- Approve or decline the expense through native UI.
- Calculate splits in deterministic code and display the updated balances.

### Milestone 5: deployment and demo hardening

- Deploy the Next.js app and shared database.
- Deploy `apps/channel` to a persistent Node.js host.
- Store all secrets in the host's secret manager.
- Test failures, cancellation, duplicated Slack delivery, and model errors.
- Document inherited starter code separately from hackathon-created work.
- Prepare the two-minute demo using one complete, repeatable scenario.

## Environment configuration

Use a root `.env` locally. Never commit it.

```dotenv
MODEL_PROVIDER=openrouter
OPENROUTER_API_KEY=replace-locally
MODEL=deepseek/deepseek-v4-flash-0731

CHANNEL_CODE=trip-planner
INTELLIGENCE_API_KEY=replace-locally
LOG_LEVEL=debug
```

The selected OpenRouter model must support tool calling. Model availability and
pricing can change, so verify the current catalog before relying on a slug.

Slack setup credentials are temporary. After the CLI reports the adapter as
attached and says they are removable, delete the bot-token and signing-secret
variables from local `.env`.

## Local run commands

Install and verify:

```bash
npm ci
npm run check-env
npm run typecheck
npm run verify
```

Run the web app:

```bash
npm run dev:web
```

Run the Slack worker in another terminal:

```bash
npm run dev:slack
```

Check the managed Channel:

```bash
npx --yes copilotkit@4.9.60 channels status --json
```

Use the repository's selected CLI version when it changes rather than assuming
`4.9.60` remains current forever.

## Completion criteria

The MVP is complete only when all of these are demonstrated:

- A real Slack mention gets a model-backed response.
- Earlier Slack messages materially change that response.
- A native Slack travel component renders.
- An unmentioned follow-up works only in a subscribed conversation.
- A trip created or updated through Slack appears in the web app.
- A web approval changes the same shared trip state Slack reads.
- A declined action makes no write.
- A replayed event does not create duplicates.
- The repository type-checks and relevant tests pass.
- The demo distinguishes sample data, proposed actions, and actual persisted
  results.

## Safety and privacy

- Obtain consent before ingesting a private group conversation or its files.
- Store the minimum Slack message and image data necessary for the trip.
- Keep workspace and trip data isolated from other groups.
- Never expose provider credentials to the browser or model prompt.
- Require approval before bookings, payments, messages to third parties, or
  persistent expense writes.
- Treat OCR and image classifications as uncertain until reviewed.
- Provide a way to delete synchronized messages, images, and trip records.

