import { createChannel } from "@copilotkit/channels";
import { isSearchConfigured } from "agent-core";
import { makeChannelAgent } from "./agent";
import { required } from "./env";
import { IncidentCard, Timeline, TripCard, welcomeMessage } from "./components";
import { proposeAction, readThread, searchTheWeb } from "./tools";
import { addTripMemory, askTravelAgent, buildPackingList, createConsensusPoll, createTravelGroup, lookupTravelGroup, organizeTravelMedia, prepareLocalGuideSearch, proposeExpense, proposeItinerary } from "./trip-tools";

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
  askTravelAgent,
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
        "You coordinate specialist travel workflows. Only create a group after an explicit user request; for each such request, call create_travel_group even if an earlier attempt failed. Use lookup_travel_group for a real six-character code and use the returned group id in subsequent tools. For trip research, rainy-day alternatives, or adding a place as a candidate, use ask_travel_agent; it remembers earlier questions for the same group. For structured actions, use the dedicated tools: propose_trip_itinerary for an itinerary proposal, propose_trip_expense for expense splits, create_consensus_poll for disagreements, build_packing_list for preparation, organize_travel_media for supplied media, and add_trip_memory for confirmed events. Do not also send the same structured action to ask_travel_agent. Itineraries and expenses remain proposals until human approval in the web dashboard. For an explicit live web search use search_web; prepare_local_guide_search can supply a location-aware search prompt. Media classification must reflect only visible or user-stated facts. Always return real backend ids and never invent a booking, payment, photo detail, vote, or memory.",
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
