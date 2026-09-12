# SomeJoy — Slack-to-UI demo

Pitch: “Plan in the conversation you already have. SomeJoy turns group requests
into shared trip records that everyone can review on a map dashboard.”

## Before recording

Follow the [quickstart](../README.md#get-started). Run the backend on port 8000
and exactly one stable Slack listener with `npm run start --workspace channel`.
Open [the dashboard](http://127.0.0.1:8000/ui/). Use a disposable demo group.

Send one prompt at a time and wait for its result. Replace `CODE` below with
the actual six-character join code; it is a placeholder, not a working code.
Use Slack's autocomplete to select the bot mention.

## 1. Create the shared group

In a new Slack channel, invite the installed bot:

```text
/invite @trip-planner
```

Then:

```text
@trip-planner Create a travel group called Prague Weekend in Prague.
We like history, museums, local food, and architecture. We prefer walking.
Return the real join code from the backend.
```

Expected: a real group/code. Join that code in the dashboard as **Alice**.
Use a separate browser profile/private session to join as **Bob**. Slack group
creation alone does not create registered travellers. For the exact split
below, use a fresh group with only Alice and Bob and no prior expenses.

```text
@trip-planner Look up group CODE.
```

Expected: a backend-backed group card. This short lookup is the best first
connection check; it can use the deterministic fast path without a model run.

## 2. Show a real money split

```text
@trip-planner For group CODE, propose a EUR 12 expense called Demo coffee,
paid by Alice and split equally between Alice and Bob. Look up their real
registered member IDs. Leave it proposed, not approved.
```

Expected in Slack: saved expense proposal/receipt, EUR 6 per person.
In **Agent workspace → Refresh → Expenses & splits**, show **proposed**.
Balances should not change yet. Click **Approve**: Alice should be +EUR 6
and Bob -EUR 6 in this fresh group. This is accounting, not a payment.

If the bot reports failure after saving, refresh before repeating. Resending
the prompt can create a second expense. Do not infer failure from an empty
Slack reply alone.

## 3. Turn a discussion into a vote

```text
@trip-planner For group CODE, create a poll: What should we do tomorrow?
Options: National Museum, Prague Castle, River walk.
```

Expected: a saved poll. Refresh the dashboard, expand **Group decisions**, and
vote as Alice and Bob. Counts should reflect those votes. A winning option
does not book anything or automatically replace the route.

These first three steps form the core short demo. Rehearse the live timing
before recording; model and provider delays vary.

## Additional small tests

### Search with evidence (Exa key required)

```text
@trip-planner Use search_web to find two vegetarian restaurants near Old Town
Square in Prague. Include source links and say which details need checking.
Do not create a booking or change our trip.
```

Expected: actual source links in Slack. Open one. Search results do not
automatically appear in the dashboard, and a search snippet is not proof of
current opening hours.

### Context-aware local guide

```text
@trip-planner For group CODE, prepare a local-guide search for indoor museums,
then run search_web with the prepared query. Give two options with sources.
```

Expected: query preparation followed by real search. Preparing a query alone
does not prove Exa ran. Only stored member constraints reach that query;
automatic extraction of every Slack preference is not implemented.

### Packing

```text
@trip-planner For group CODE, generate a packing list for three days with rainy
weather. Separate personal and shared items. Treat rain as my assumption,
not a weather forecast.
```

Expected: personal/shared items including rain gear. The dashboard's **Packing
assistant → Generate list** makes a separate default request; it is not a
read-back of this Slack list.

### Media metadata

Share a demo file named `museum-ticket.pdf`, then ask:

```text
@trip-planner For group CODE, register the file museum-ticket.pdf as a ticket.
Note: National Museum visit, day 1. Save metadata only; do not claim that you
read the file or extracted its price.
```

Expected: a Media record with that filename/category after Refresh. No PDF/image
bytes, preview, OCR, or automatic expense extraction are stored by this tool.

### Confirmed memory

For this disposable demo, explicitly supply the test event:

```text
@trip-planner For group CODE, save this confirmed demo memory:
Title: First coffee together. Description: Alice and Bob met for coffee in
Prague. Do not add details or attach media that I did not provide.
```

Expected: that entry under **Trip memories** after Refresh. Repeating creates
another entry; use only events the group confirms for a real trip.

### Itinerary proposal (longer optional flow)

```text
@trip-planner For group CODE, propose a museum-focused itinerary with three
stops. Leave it awaiting approval and return the real proposal ID.
```

Expected: a backend proposal. Start `npm run dev:web` and open the same code at
[port 3100](http://127.0.0.1:3100) to review/approve it, then check the active
route in the map dashboard. Do not confuse this with the map's direct Build
route, which publishes immediately. The planner produces ordered stops, not a
guaranteed multi-day schedule or verified accessible route.

## If a step stalls

```bash
curl --max-time 5 http://127.0.0.1:8000/health
npm run channel:status
```

Check the Slack listener's diagnostic stage/timing. Backend health and Channel
online status do not prove the selected model or Exa is responding. Check for
saved records before retrying writes. See [troubleshooting](troubleshooting.md).
