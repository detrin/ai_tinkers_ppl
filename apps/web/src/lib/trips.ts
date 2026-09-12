/**
 * Real trips, read from the shared backend.
 *
 * This replaces the sample incident data the starter shipped with. Nothing here
 * is fictional: every record comes from the same Python service that Slack
 * (`apps/channel`) writes to, so the two surfaces cannot drift apart.
 */

export const TRIP_API_URL = (
  process.env.NEXT_PUBLIC_TRIP_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

/** Where the live map lives. Same service, so the same origin. */
export const MAP_UI_URL = `${TRIP_API_URL}/ui/`;

export interface City {
  name: string;
  display_name: string;
  lat: number;
  lon: number;
  country: string | null;
}

export interface Traveler {
  id: string;
  display_name: string;
  online: boolean;
  slack_user_id: string | null;
  budget: number | null;
  currency: string;
  preferences: string[];
  constraints: string[];
  distance_to_meeting_m: number | null;
}

export interface Stop {
  order: number;
  place: { id: string; name: string; category: string; reason: string; suggested_minutes: number };
  distance_from_previous_m: number;
  travel_seconds_from_previous: number;
}

export interface Plan {
  stops: Stop[];
  total_distance_m: number;
  total_travel_seconds: number;
  total_visit_seconds: number;
  routing_provider: string;
  ranked_by: string;
  summary: string;
}

export interface Proposal {
  id: string;
  status: "proposed" | "approved" | "declined";
  created_at: number;
  created_by: string | null;
  decided_by: string | null;
  plan: Plan;
  estimated_cost: number | null;
  currency: string;
  assumptions: string[];
  note: string;
}

export interface TripMessage {
  id: string;
  source: "slack" | "web";
  author_name: string | null;
  text: string;
  created_at: number;
}

export interface Trip {
  id: string;
  name: string;
  join_code: string;
  city: City;
  interests: string[];
  members: Traveler[];
  plan: Plan | null;
  messages: TripMessage[];
  proposals: Proposal[];
}

export class TripApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${TRIP_API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new TripApiError(
      "The trip backend is not reachable. Start it with `uvicorn app.main:app` in backend/.",
    );
  }

  if (!response.ok) {
    let detail = `The trip backend returned HTTP ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Keep the controlled message rather than echoing an arbitrary body.
    }
    throw new TripApiError(detail);
  }

  return (await response.json()) as T;
}

export const tripApi = {
  byCode: (joinCode: string) =>
    request<Trip>(`/api/groups/by-code/${encodeURIComponent(joinCode.toUpperCase())}`),

  byId: (tripId: string) => request<Trip>(`/api/groups/${tripId}`),

  proposals: (tripId: string) => request<Proposal[]>(`/api/groups/${tripId}/proposals`),

  propose: (tripId: string, maxStops: number) =>
    request<Proposal>(`/api/groups/${tripId}/proposals`, {
      method: "POST",
      body: JSON.stringify({ max_stops: maxStops }),
    }),

  approve: (tripId: string, proposalId: string, decidedBy: string) =>
    request<Proposal>(`/api/groups/${tripId}/proposals/${proposalId}/approve`, {
      method: "POST",
      body: JSON.stringify({ decided_by: decidedBy }),
    }),

  decline: (tripId: string, proposalId: string, decidedBy: string) =>
    request<Proposal>(`/api/groups/${tripId}/proposals/${proposalId}/decline`, {
      method: "POST",
      body: JSON.stringify({ decided_by: decidedBy }),
    }),
};

export function metres(value: number | null | undefined): string {
  if (value == null) return "—";
  return value < 950 ? `${Math.round(value)} m` : `${(value / 1000).toFixed(1)} km`;
}

export function minutes(seconds: number): string {
  const total = Math.round(seconds / 60);
  if (total < 60) return `${total} min`;
  return `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, "0")}`;
}

/**
 * What the agent is told about the page. Says plainly which parts are decided
 * and which are only proposed, so the model does not report a proposal as if
 * the group had agreed to it.
 */
export function tripWorkspaceContext(trip: Trip | null) {
  if (!trip) {
    return {
      dataSource:
        "No trip is open. The user opens one with its six-character join code. Trips are created in Slack or in the map UI.",
      trip: null,
    };
  }

  const open = trip.proposals.filter((p) => p.status === "proposed");
  return {
    dataSource:
      "Live records from the shared trip backend, the same ones Slack reads and writes. An itinerary counts as agreed only when a proposal is approved; a proposed one is still just a suggestion.",
    trip: {
      id: trip.id,
      name: trip.name,
      joinCode: trip.join_code,
      city: trip.city.display_name,
      interests: trip.interests,
      travelers: trip.members.map((m) => ({
        name: m.display_name,
        budget: m.budget,
        currency: m.currency,
        preferences: m.preferences,
        constraints: m.constraints,
        sharingLocation: m.distance_to_meeting_m != null,
      })),
      agreedItinerary: trip.plan
        ? {
            stops: trip.plan.stops.map((s) => s.place.name),
            walking: metres(trip.plan.total_distance_m),
            summary: trip.plan.summary,
          }
        : null,
      openProposals: open.map((p) => ({
        id: p.id,
        stops: p.plan.stops.map((s) => s.place.name),
        assumptions: p.assumptions,
        estimatedCost: p.estimated_cost,
      })),
      recentMessages: trip.messages.slice(-15).map((m) => ({
        from: m.author_name ?? "someone",
        via: m.source,
        text: m.text,
      })),
    },
  };
}
