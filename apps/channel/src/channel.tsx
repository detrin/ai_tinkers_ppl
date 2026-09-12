import { createChannel } from "@copilotkit/channels";
import { isSearchConfigured } from "agent-core";
import { makeChannelAgent } from "./agent";
import { required } from "./env";
import { IncidentCard, Timeline, TripCard, welcomeMessage } from "./components";
import { proposeAction, readThread, searchTheWeb } from "./tools";
import { addTripMemory, buildPackingList, createConsensusPoll, createTravelGroup, lookupTravelGroup, organizeTravelMedia, prepareLocalGuideSearch, proposeExpense, proposeItinerary } from "./trip-tools";

// Tools are registered only when their credential is present, so the agent is
// never handed a tool that will fail when it calls it.
const tools = [
  readThread,
  createTravelGroup,
  lookupTravelGroup,
  proposeItinerary,
  organizeTravelMedia,
  proposeExpense,
  createConsensusPoll,
  buildPackingList,
  prepareLocalGuideSearch,
  addTripMemory,
  proposeAction,
  ...(isSearchConfigured() ? [searchTheWeb] : []),
];

export const channel = createChannel({
  // Must equal the Channel Code in Intelligence, character for character. A
  // mismatch leaves the Channel at "Waiting for runtime" and is validated at
  // startup, not here.
  name: required("CHANNEL_CODE"),

  // Required. "platform" derives the canonical user from provider + workspace +
  // platform user id. Do NOT move this onto CopilotRuntime — that one is for
  // web requests and must be absent on a Channels-only runtime.
  identifyUser: "platform",

  agent: makeChannelAgent,
  tools,
  components: [TripCard, IncidentCard, Timeline],

  // Injected into the agent's prompt on every run.
  context: [
    
    {
      description: "Rendering",
      value:
        "Draw trip summaries with trip_card and chronological trip memories with timeline. Prefer native cards over long prose.",
    },
    {
      description: "Surface",
      value:
        "This is a chat thread in a channel people are actively working in. Assume others are reading and that some joined late.",
    },
    {
      description: "Group travel",
      value:
        "You coordinate specialist travel workflows. For every explicit request to create a group, you MUST call create_travel_group during that turn—even if an earlier attempt failed; never repeat a cached failure without retrying the tool. Use lookup_travel_group for a real six-character code. For an itinerary request, look up the group and call propose_trip_itinerary; state clearly that it still needs human approval in the web dashboard. Media classification must reflect only visible/user-stated facts. Expenses are proposals until a person approves them in the web dashboard. Use polls for disagreements, packing lists for preparation, prepare_local_guide_search plus search_web for current nearby help, and add_trip_memory only for confirmed events. Always use real backend ids and never invent a booking, payment, photo detail, vote, or memory.",
    },
  ],

});

// A mention subscribes the conversation, so the agent then follows along instead
// of needing to be @-mentioned every single turn.
channel.onMention(async ({ thread }) => {
  await thread.subscribe();
  await thread.runAgent();
});

// Non-mentioned turns only ever reach onMessage — gate them on the flag or the
// agent will answer every message in every channel it has been invited to.
channel.onMessage(async ({ thread }) => {
  if (await thread.isSubscribed()) {
    await thread.runAgent();
  }
});

channel.onWelcome(async ({ thread, platform }) => {
  await thread.post(welcomeMessage(platform));
});
