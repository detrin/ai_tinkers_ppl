import { defineChannelTool } from "@copilotkit/channels";
import { z } from "zod";

const tripApiUrl = () =>
  (process.env.TRIP_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

type TripApiError = { detail?: unknown };

async function tripRequest(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${tripApiUrl()}${path}`, init);
  } catch {
    throw new Error(
      "The trip backend is unavailable. Start backend/app/main.py on port 8000 or set TRIP_API_URL.",
    );
  }

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
    return await tripRequest(
      `/api/groups/by-code/${encodeURIComponent(joinCode.trim().toUpperCase())}`,
    );
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

