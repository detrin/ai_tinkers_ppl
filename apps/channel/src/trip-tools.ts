import { defineChannelTool } from "@copilotkit/channels";
import { z } from "zod";
import { logChannel, safeError } from "./diagnostics";
import { expenseReceipt, expenseReceiptSchema } from "./fast-replies";
import { REPLY_FAILED, REPLY_POSTED } from "./completed-reply";

const tripApiUrl = () =>
  (process.env.TRIP_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

type TripApiError = { detail?: unknown };

async function tripRequest(path: string, init?: RequestInit): Promise<unknown> {
  const started = Date.now();
  const operation = { method: init?.method ?? "GET", route: path.split("?")[0] };
  logChannel("backend.start", operation);
  let response: Response;
  try {
    response = await fetch(`${tripApiUrl()}${path}`, init);
  } catch (error) {
    logChannel("backend.failed", { ...operation, elapsedMs: Date.now() - started, error: safeError(error) });
    throw new Error(
      "The trip backend is unavailable. Start backend/app/main.py on port 8000 or set TRIP_API_URL.",
    );
  }

  logChannel("backend.response", { ...operation, elapsedMs: Date.now() - started, status: response.status });

  if (!response.ok) {
    let detail = `Trip backend returned HTTP ${response.status}.`;
    try {
      const body = (await response.json()) as TripApiError;
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Keep the controlled status message; never echo an arbitrary response.
    }
    throw new Error(detail);
  }

  return await response.json();
}

export const createTravelGroup = defineChannelTool({
  name: "create_travel_group",
  description:
    "Create a travel group in the shared Group City Route backend so it immediately becomes joinable from the web UI. Use only when the user explicitly asks to create a group. Return the real six-character join code.",
  parameters: z.object({
    name: z.string().min(1).max(80).describe("The group's display name."),
    city: z.string().min(1).max(120).describe("The destination city."),
    interests: z
      .array(z.string().min(1))
      .default([])
      .describe("Interests stated by the travelers, such as history or food."),
    transport: z
      .enum(["foot", "bike", "car"])
      .default("foot")
      .describe("How the group wants to move around the city."),
  }),
  async handler(args) {
    return await tripRequest("/api/groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(args),
    });
  },
});

export async function lookupTrip(joinCode: string) {
  return await tripRequest(`/api/groups/by-code/${encodeURIComponent(joinCode.trim().toUpperCase())}`);
}

export const lookupTravelGroup = defineChannelTool({
  name: "lookup_travel_group",
  description:
    "Read the shared travel group created in Slack or the web UI using its six-character join code. Use this to prove both surfaces see the same group, members, preferences, and itinerary.",
  parameters: z.object({
    joinCode: z
      .string()
      .min(6)
      .max(6)
      .describe("The six-character group join code shown in the web UI or Slack."),
  }),
  async handler({ joinCode }) {
    return await lookupTrip(joinCode);
  },
});

const groupId = z.string().min(1).describe("The real group id returned by create or lookup; never invent it.");

export const proposeItinerary = defineChannelTool({
  name: "propose_trip_itinerary",
  description:
    "Generate and persist a proposed itinerary for a real travel group. This never approves the itinerary; approval or rejection happens in the web dashboard.",
  parameters: z.object({
    groupId,
    interests: z.array(z.string().min(1)).optional(),
    maxStops: z.number().int().min(1).max(12).default(5),
    transport: z.enum(["foot", "bike", "car"]).optional(),
    radiusM: z.number().int().min(250).max(20_000).optional(),
    estimatedCost: z.number().nonnegative().optional(),
    currency: z.string().length(3).default("EUR"),
    assumptions: z.array(z.string().min(1)).default([]),
    note: z.string().max(500).default(""),
  }),
  async handler({
    groupId,
    maxStops,
    radiusM,
    estimatedCost,
    ...rest
  }) {
    return await tripRequest(`/api/groups/${encodeURIComponent(groupId)}/proposals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...rest,
        max_stops: maxStops,
        radius_m: radiusM,
        estimated_cost: estimatedCost,
      }),
    });
  },
});

export const askTravelAgent = defineChannelTool({
  name: "ask_travel_agent",
  description:
    "Ask the Trip Agent a free-text question about an existing travel group: research a place, get a rainy-day backup, or add a place as a candidate ('add the National Gallery as a candidate'). Requires the group's id, not its join code -- get it from create_travel_group or lookup_travel_group first. Remembers earlier questions asked for the same group, so this can be a running conversation.",
  parameters: z.object({
    groupId: z
      .string()
      .min(1)
      .describe("The group's id field (not the six-character join code)."),
    question: z
      .string()
      .min(1)
      .max(500)
      .describe("The question or request, in plain language."),
  }),
  async handler({ groupId, question }) {
    return await tripRequest(`/api/groups/${encodeURIComponent(groupId)}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  },
});

export const organizeTravelMedia = defineChannelTool({
  name: "organize_travel_media",
  description: "Classify a photo or file already shared by the user and attach its metadata to a trip. Do not claim image contents you cannot see.",
  parameters: z.object({
    groupId,
    filename: z.string().min(1).max(240),
    category: z.enum(["landmark", "food", "group_photo", "ticket", "booking", "receipt", "other"]).optional(),
    note: z.string().max(1000).default(""),
    location: z.string().max(160).optional(),
    day: z.number().int().min(1).max(60).optional(),
  }),
  async handler({ groupId, ...body }) {
    return await tripRequest(`/api/groups/${encodeURIComponent(groupId)}/media`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  },
});

export const proposeExpense = defineChannelTool({
  name: "propose_trip_expense",
  description: "Propose an expense and calculate an exact equal split. This does not approve the expense; tell the user to approve it in the web dashboard.",
  parameters: z.object({
    groupId, title: z.string().min(1).max(120), amount: z.number().positive(),
    currency: z.string().length(3).default("EUR"), paidBy: z.string().min(1),
    participantIds: z.array(z.string().min(1)).min(1), mediaId: z.string().optional(),
  }),
  async handler({ groupId, paidBy, participantIds, mediaId, ...rest }, { thread }) {
    // Resolve display names with a bounded read; the backend still validates
    // payer/participant membership at the write boundary.
    let names: Record<string, string> = {};
    try {
      const group = z.object({ members: z.array(z.object({ id: z.string(), display_name: z.string() })) }).parse(
        await tripRequest(`/api/groups/${encodeURIComponent(groupId)}`, { signal: AbortSignal.timeout(3000) }),
      );
      names = Object.fromEntries(group.members.map(m => [m.id, m.display_name]));
    } catch { /* A name lookup must never cause a successful write to be retried. */ }
    const result = await tripRequest(`/api/groups/${encodeURIComponent(groupId)}/expenses`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...rest, paid_by: paidBy, participant_ids: participantIds, media_id: mediaId }),
    });
    const parsed = expenseReceiptSchema.safeParse(result);
    if (!parsed.success) {
      // A POST may have succeeded. Never invite an automatic retry of the write.
      return { [REPLY_FAILED]: true, error: "The expense endpoint returned an unexpected result. Check Expenses & splits before retrying; the expense may already be saved." };
    }
    try {
      await thread.post(expenseReceipt(parsed.data, names));
    } catch (error) {
      logChannel("expense.receipt_failed", { expenseId: parsed.data.id, error: safeError(error) });
      return { id: parsed.data.id, [REPLY_FAILED]: true, error: "The expense was saved, but its Slack receipt failed. Do not create it again." };
    }
    return { ...parsed.data, [REPLY_POSTED]: true };
  },
});

export const createConsensusPoll = defineChannelTool({
  name: "create_consensus_poll",
  description: "Create a persistent group poll when travelers have multiple options. Voting happens in the web dashboard.",
  parameters: z.object({ groupId, question: z.string().min(1).max(300), options: z.array(z.string().min(1)).min(2).max(10) }),
  async handler({ groupId, ...body }) {
    return await tripRequest(`/api/groups/${encodeURIComponent(groupId)}/polls`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  },
});

export const buildPackingList = defineChannelTool({
  name: "build_packing_list",
  description: "Generate a deterministic personal and shared packing list from trip length, destination, interests, and stated weather.",
  parameters: z.object({ groupId, days: z.number().int().min(1).max(60).default(2), weather: z.string().max(120).default("unknown") }),
  async handler({ groupId, ...body }) {
    return await tripRequest(`/api/groups/${encodeURIComponent(groupId)}/packing`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  },
});

export const prepareLocalGuideSearch = defineChannelTool({
  name: "prepare_local_guide_search",
  description: "Build a location-aware web search prompt using the trip and traveler constraints. After calling this, call search_web with search_prompt for current sources.",
  parameters: z.object({ groupId, need: z.string().min(1).max(200) }),
  async handler({ groupId, need }) {
    return await tripRequest(`/api/groups/${encodeURIComponent(groupId)}/local-guide?need=${encodeURIComponent(need)}`);
  },
});

export const addTripMemory = defineChannelTool({
  name: "add_trip_memory",
  description: "Add a confirmed moment to the persistent trip timeline. Use only for something the group explicitly says happened; never invent memories.",
  parameters: z.object({ groupId, title: z.string().min(1).max(120), description: z.string().max(1000).default(""), mediaIds: z.array(z.string()).default([]) }),
  async handler({ groupId, mediaIds, ...body }) {
    return await tripRequest(`/api/groups/${encodeURIComponent(groupId)}/memories`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, media_ids: mediaIds }),
    });
  },
});
