import type { Group, Member, Plan } from "./types";

/** Same-origin by default: Vite proxies to the backend in dev, and the backend
 *  serves the built files in production. Override with VITE_API_URL if you host
 *  the two apart. */
const BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("Cannot reach the server. Is the backend running?");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* error body was not JSON */
    }
    throw new ApiError(detail);
  }

  return response.status === 204 ? (null as T) : ((await response.json()) as T);
}

export interface CreateGroupInput {
  name: string;
  city: string;
  interests: string[];
}

export interface PlanInput {
  interests: string[];
  max_stops: number;
}

export const api = {
  createGroup: (input: CreateGroupInput) =>
    request<Group>("/api/groups", { method: "POST", body: JSON.stringify(input) }),

  getGroup: (groupId: string) => request<Group>(`/api/groups/${groupId}`),

  getGroupByCode: (joinCode: string) =>
    request<Group>(`/api/groups/by-code/${encodeURIComponent(joinCode)}`),

  joinGroup: (groupId: string, displayName: string, joinCode?: string) =>
    request<Member>(`/api/groups/${groupId}/members`, {
      method: "POST",
      body: JSON.stringify({ display_name: displayName, join_code: joinCode ?? null }),
    }),

  buildPlan: (groupId: string, input: PlanInput) =>
    request<Plan>(`/api/groups/${groupId}/plan`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
};

/** Socket URL for a group. Relative to the page so the Vite proxy and the
 *  backend's own static hosting both work without configuration. */
export function socketUrl(groupId: string, memberId: string): string {
  if (BASE) {
    const base = new URL(BASE);
    base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
    return `${base.origin}/ws/groups/${groupId}?member_id=${memberId}`;
  }
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}/ws/groups/${groupId}?member_id=${memberId}`;
}
