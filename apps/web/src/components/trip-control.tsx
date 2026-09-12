"use client";

import { useFrontendTool, useAgentContext } from "@copilotkit/react-core/v2";
import { z } from "zod";
import { tripWorkspaceContext, type Trip } from "@/lib/trips";

/**
 * Gives the agent the page it is sitting on, and the two things it may do to it.
 *
 * Opening a trip and proposing an itinerary are safe: neither changes what the
 * group has agreed. Approving is not, so it is deliberately absent here. An
 * approval happens only when a person clicks the button on the page.
 */
export function TripControl({
  trip,
  openTrip,
  proposeItinerary,
}: {
  trip: Trip | null;
  openTrip: (joinCode: string) => Promise<string>;
  proposeItinerary: (maxStops: number) => Promise<string>;
}) {
  useAgentContext({
    description:
      "The trip workspace currently on screen, read live from the shared backend that Slack also writes to. " +
      "CRITICAL: an itinerary is agreed only when a proposal has been approved. " +
      "Never describe a proposed itinerary as settled, and never claim an approval happened. " +
      "Only the user's click on this page approves anything; agreeing in chat approves nothing.",
    value: tripWorkspaceContext(trip),
  });

  useFrontendTool({
    name: "open_trip",
    description:
      "Open a trip in this page by its six-character join code, so the user can see it. Read-only.",
    parameters: z.object({
      joinCode: z.string().min(6).max(6).describe("The trip's join code."),
    }),
    handler: async ({ joinCode }) => {
      try {
        return { status: "ok", message: await openTrip(joinCode) };
      } catch (error) {
        return {
          status: "error",
          message: error instanceof Error ? error.message : "Could not open that trip.",
        };
      }
    },
  });

  useFrontendTool({
    name: "propose_itinerary",
    description:
      "Build a walking itinerary for the open trip and put it forward for the group. " +
      "This is a proposal only: it does not change what the group has agreed, and it " +
      "does not approve anything. A person must click Approve on the page.",
    parameters: z.object({
      maxStops: z.number().int().min(2).max(8).describe("How many places to visit."),
    }),
    handler: async ({ maxStops }) => {
      try {
        return { status: "proposed", message: await proposeItinerary(maxStops) };
      } catch (error) {
        return {
          status: "error",
          message:
            error instanceof Error ? error.message : "Could not build an itinerary.",
        };
      }
    },
  });

  return null;
}
